# ═══════════════════════════════════════════════════════════════
#  TRADING BOT HÍBRIDO — STRATEGY ENGINE v5.0
#  MODO 1: ICT Sweep (tendencia) — TP grande, 5 condiciones
#  MODO 2: Rango/Lateral — TP corto 10-30 pips, soporte/resistencia
# ═══════════════════════════════════════════════════════════════

import pandas as pd
import numpy as np
import logging
from datetime import datetime

from config import STRATEGY, PAIR_SESSIONS, SESSIONS
from data_feed import DataFeed

logger = logging.getLogger(__name__)


class StrategyEngine:
    """Motor de estrategia con 2 modos: Tendencia (ICT) y Rango (S/R)."""

    def __init__(self, data_feed: DataFeed):
        self.data_feed = data_feed
        self.params = STRATEGY
        self.last_signal_time = {}
        self.last_sweep_time = {}

    # ═══════════════════════════════════════════════════════════
    #  ANALISIS PRINCIPAL — Intenta Tendencia primero, luego Rango
    # ═══════════════════════════════════════════════════════════

    def analyze(self, symbol: str):
        """Analiza un par: primero busca tendencia, luego rango."""
        if not self._is_session_active(symbol):
            return None

        df = self.data_feed.get_ohlc(symbol, num_candles=100)
        if df is None or len(df) < 50:
            return None

        spread = self.data_feed.get_current_spread(symbol) if hasattr(self.data_feed, 'get_current_spread') else None
        if spread is not None and spread > 3.0:
            return None

        if not self._check_signal_cooldown(symbol):
            return None

        # Determinar el modo del mercado
        market_mode = self._detect_market_mode(symbol, df)

        if market_mode == "TENDENCIA":
            result = self._evaluate_trend(symbol, df)
        elif market_mode == "RANGO":
            result = self._evaluate_range(symbol, df)
        else:
            return None

        if result:
            result["symbol"] = symbol
            result["timestamp"] = datetime.now().isoformat()
            result["current_price"] = df.iloc[-1]['close']
            result["market_mode"] = market_mode
            self.last_signal_time[symbol] = datetime.now()

        return result

    # ═══════════════════════════════════════════════════════════
    #  DETECTOR DE MERCADO — Tendencia vs Rango vs Caótico
    # ═══════════════════════════════════════════════════════════

    def _detect_market_mode(self, symbol: str, df: pd.DataFrame) -> str:
        """Detecta si el mercado está en tendencia, rango o caótico."""
        pip_value = self.params["pip_values"].get(symbol, 0.0001)
        digits = self.params["digits"].get(symbol, 5)

        ema_fast = df['close'].ewm(span=self.params["ema_fast"], adjust=False).mean()
        ema_slow = df['close'].ewm(span=self.params["ema_slow"], adjust=False).mean()

        ema_f_slope = ema_fast.iloc[-1] - ema_fast.iloc[-5]
        ema_s_slope = ema_slow.iloc[-1] - ema_slow.iloc[-5]
        ema_distance = abs(ema_fast.iloc[-1] - ema_slow.iloc[-1]) / pip_value

        # Estructura de mercado
        recent_highs = df['high'].iloc[-10:]
        recent_lows = df['low'].iloc[-10:]
        hh_hl = (recent_highs.iloc[-1] > recent_highs.iloc[-3] and
                 recent_lows.iloc[-1] > recent_lows.iloc[-3])
        lh_ll = (recent_highs.iloc[-1] < recent_highs.iloc[-3] and
                 recent_lows.iloc[-1] < recent_lows.iloc[-3])

        # Verificar ADX (volatilidad direccional)
        high = df['high'].iloc[-14:]
        low = df['low'].iloc[-14:]
        close = df['close'].iloc[-14:]
        tr_sum = 0
        plus_dm_sum = 0
        minus_dm_sum = 0
        for i in range(1, len(high)):
            tr = max(high.iloc[i] - low.iloc[i],
                     abs(high.iloc[i] - close.iloc[i-1]),
                     abs(low.iloc[i] - close.iloc[i-1]))
            tr_sum += tr

            up_move = high.iloc[i] - high.iloc[i-1]
            down_move = low.iloc[i-1] - low.iloc[i]

            plus_dm = up_move if (up_move > down_move and up_move > 0) else 0
            minus_dm = down_move if (down_move > up_move and down_move > 0) else 0

            plus_dm_sum += plus_dm
            minus_dm_sum += minus_dm

        if tr_sum > 0:
            plus_di = 100 * plus_dm_sum / tr_sum
            minus_di = 100 * minus_dm_sum / tr_sum
            di_diff = abs(plus_di - minus_di)
            di_sum = plus_di + minus_di
            adx = 100 * di_diff / di_sum if di_sum > 0 else 0
        else:
            adx = 0

        # CRITERIOS DE TENDENCIA
        uptrend = (ema_fast.iloc[-1] > ema_slow.iloc[-1]
                   and ema_f_slope > 0 and hh_hl)
        downtrend = (ema_fast.iloc[-1] < ema_slow.iloc[-1]
                     and ema_f_slope < 0 and lh_ll)

        if (uptrend or downtrend) and adx > 20 and ema_distance > 5:
            return "TENDENCIA"

        # CRITERIOS DE RANGO
        # EMAs planas (sin pendiente clara) Y adx bajo Y estructura sin HH/HL ni LH/LL
        slope_flat = abs(ema_f_slope) / pip_value < 3
        structure_flat = not hh_hl and not lh_ll

        if slope_flat and structure_flat and adx < 25:
            return "RANGO"

        # Caótico o en transición — no operar
        return "CAOTICO"

    # ═══════════════════════════════════════════════════════════
    #  MODO 1: ICT SWEEP (Tendencia) — 5 condiciones
    # ═══════════════════════════════════════════════════════════

    def _evaluate_trend(self, symbol: str, df: pd.DataFrame):
        """Evalúa las 5 condiciones ICT para mercado en tendencia."""
        pip_value = self.params["pip_values"].get(symbol, 0.0001)
        digits = self.params["digits"].get(symbol, 5)
        current = df.iloc[-1]

        score = 0
        conditions = {}

        # CONDICIÓN 1: Tendencia
        ema_fast = df['close'].ewm(span=self.params["ema_fast"], adjust=False).mean()
        ema_slow = df['close'].ewm(span=self.params["ema_slow"], adjust=False).mean()
        uptrend = ema_fast.iloc[-1] > ema_slow.iloc[-1]
        downtrend = ema_fast.iloc[-1] < ema_slow.iloc[-1]
        ema_f_slope = ema_fast.iloc[-1] - ema_fast.iloc[-5]

        recent_highs = df['high'].iloc[-10:]
        recent_lows = df['low'].iloc[-10:]
        hh_hl = (recent_highs.iloc[-1] > recent_highs.iloc[-3] and
                 recent_lows.iloc[-1] > recent_lows.iloc[-3])
        lh_ll = (recent_highs.iloc[-1] < recent_highs.iloc[-3] and
                 recent_lows.iloc[-1] < recent_lows.iloc[-3])

        trend_strong = False
        if uptrend and ema_f_slope > 0 and hh_hl:
            trend_strong = True
        elif downtrend and ema_f_slope < 0 and lh_ll:
            trend_strong = True

        conditions["trend"] = {
            "passed": (uptrend or downtrend),
            "strong": trend_strong,
            "detail": f"EMA{self.params['ema_fast']}{'>' if uptrend else '<'}EMA{self.params['ema_slow']}"
                      + (" FUERTE" if trend_strong else "")
        }

        if uptrend or downtrend:
            score += 1
            direction = "LONG" if uptrend else "SHORT"
        else:
            direction = None

        # CONDICIÓN 2: Pullback direccional
        if direction is not None and len(df) > self.params["pullback_candles"] + 1:
            pb_candles = self.params["pullback_candles"]
            pb_start = df.iloc[-(pb_candles + 1)]['close']
            pb_end = df.iloc[-2]['close']
            price_change = pb_end - pb_start
            change_pips = abs(price_change / pip_value)

            if direction == "LONG":
                is_pullback = price_change < 0 and change_pips >= self.params["pullback_min_pips"]
            else:
                is_pullback = price_change > 0 and change_pips >= self.params["pullback_min_pips"]

            conditions["pullback"] = {
                "passed": is_pullback,
                "pullback_pips": round(change_pips, 1),
                "detail": f"Pullback {change_pips:.1f} pips vs {direction}"
            }
            if is_pullback:
                score += 1
        else:
            conditions["pullback"] = {"passed": False, "detail": "Sin datos"}

        # CONDICIÓN 3: Sweep real con rechazo
        lookback = self.params["lookback_candles"]
        if direction == "LONG":
            prev_low = df['low'].iloc[-lookback:-3].min()
            sweep_pips = (prev_low - current['low']) / pip_value
            rejection = current['close'] > prev_low
            conditions["sweep"] = {
                "passed": sweep_pips > 0,
                "sweep_pips": round(sweep_pips, 1),
                "rejection": rejection,
                "detail": f"Sweep {sweep_pips:.1f} pips" + (" +RECHAZO" if rejection else "")
            }
            if sweep_pips > 0:
                score += 1
        elif direction == "SHORT":
            prev_high = df['high'].iloc[-lookback:-3].max()
            sweep_pips = (current['high'] - prev_high) / pip_value
            rejection = current['close'] < prev_high
            conditions["sweep"] = {
                "passed": sweep_pips > 0,
                "sweep_pips": round(sweep_pips, 1),
                "rejection": rejection,
                "detail": f"Sweep {sweep_pips:.1f} pips" + (" +RECHAZO" if rejection else "")
            }
            if sweep_pips > 0:
                score += 1
        else:
            conditions["sweep"] = {"passed": False, "detail": "Sin dirección"}

        # CONDICIÓN 4: Mecha de rechazo con mínimo en pips
        candle_range = current['high'] - current['low']
        upper_wick = current['high'] - max(current['open'], current['close'])
        lower_wick = min(current['open'], current['close']) - current['low']
        lower_wick_pips = lower_wick / pip_value
        upper_wick_pips = upper_wick / pip_value
        wick_min = self.params.get("wick_min_pips", 5)

        if direction == "LONG" and candle_range > 0:
            wick_ratio = lower_wick / upper_wick if upper_wick > 0 else 10.0
            wick_ok = wick_ratio >= self.params["wick_ratio_min"] and lower_wick_pips >= wick_min
            conditions["rejection_wick"] = {
                "passed": wick_ok,
                "detail": f"Mecha inf {wick_ratio:.2f}x, {lower_wick_pips:.1f} pips"
            }
            if wick_ok:
                score += 1
        elif direction == "SHORT" and candle_range > 0:
            wick_ratio = upper_wick / lower_wick if lower_wick > 0 else 10.0
            wick_ok = wick_ratio >= self.params["wick_ratio_min"] and upper_wick_pips >= wick_min
            conditions["rejection_wick"] = {
                "passed": wick_ok,
                "detail": f"Mecha sup {wick_ratio:.2f}x, {upper_wick_pips:.1f} pips"
            }
            if wick_ok:
                score += 1
        else:
            conditions["rejection_wick"] = {"passed": False}

        # CONDICIÓN 5: Cierre fuerte
        if candle_range > 0:
            if direction == "LONG":
                close_pos = (current['close'] - current['low']) / candle_range * 100
            else:
                close_pos = (current['high'] - current['close']) / candle_range * 100

            conditions["close_position"] = {
                "passed": close_pos >= self.params["close_percentile"],
                "close_position": round(close_pos, 1),
                "detail": f"Cierre en {close_pos:.1f}% (min: {self.params['close_percentile']}%)"
            }
            if close_pos >= self.params["close_percentile"]:
                score += 1
        else:
            conditions["close_position"] = {"passed": False}

        passed = score >= self.params["min_score"]

        return {
            "signal": "BUY" if direction == "LONG" else ("SELL" if direction == "SHORT" else None),
            "score": score,
            "max_score": 5,
            "passed": passed,
            "conditions": conditions,
            "direction": direction,
            "sl_pips": self.params.get("trend_sl_pips", 18),
            "tp_pips": self.params.get("trend_tp_pips", 45),
            "needs_ai_confirmation": passed,
        }

    # ═══════════════════════════════════════════════════════════
    #  MODO 2: RANGO/LATERAL — Soporte/Resistencia
    # ═══════════════════════════════════════════════════════════

    def _evaluate_range(self, symbol: str, df: pd.DataFrame):
        """Evalúa señales de trading en rango — compra en soporte, venta en resistencia."""
        pip_value = self.params["pip_values"].get(symbol, 0.0001)
        digits = self.params["digits"].get(symbol, 5)
        current = df.iloc[-1]
        range_params = self.params.get("range_mode", {})

        lookback = range_params.get("sr_lookback", 30)
        zone_pips = range_params.get("zone_pips", 5)
        min_range_pips = range_params.get("min_range_pips", 20)
        wick_min_range = range_params.get("wick_min_pips", 3)
        close_pct_range = range_params.get("close_percentile", 70)

        score = 0
        conditions = {}

        # PASO 1: Encontrar soporte y resistencia del rango
        sr_df = df.iloc[-lookback:]
        support = sr_df['low'].min()
        resistance = sr_df['high'].max()
        range_pips = (resistance - support) / pip_value

        conditions["range"] = {
            "passed": range_pips >= min_range_pips,
            "support": round(support, digits),
            "resistance": round(resistance, digits),
            "range_pips": round(range_pips, 1),
            "min_required": min_range_pips,
            "detail": f"Rango: {range_pips:.1f} pips (S: {support:.5f} | R: {resistance:.5f})"
        }

        if range_pips < min_range_pips:
            return None
        score += 1

        # PASO 2: ¿El precio está cerca de soporte o resistencia?
        dist_to_support_pips = (current['low'] - support) / pip_value
        dist_to_resistance_pips = (resistance - current['high']) / pip_value

        # Determinar zona: precio toca o penetra S/R
        near_support = dist_to_support_pips <= zone_pips
        near_resistance = dist_to_resistance_pips <= zone_pips

        conditions["zone"] = {
            "passed": near_support or near_resistance,
            "near_support": near_support,
            "near_resistance": near_resistance,
            "dist_support": round(dist_to_support_pips, 1),
            "dist_resistance": round(dist_to_resistance_pips, 1),
            "detail": (f"En zona de SOPORTE ({dist_to_support_pips:.1f} pips)"
                      if near_support else
                      f"En zona de RESISTENCIA ({dist_to_resistance_pips:.1f} pips)")
                     if (near_support or near_resistance) else
                     f"En medio del rango (S: {dist_to_support_pips:.1f} | R: {dist_to_resistance_pips:.1f})"
        }

        if not near_support and not near_resistance:
            return None
        score += 1

        # PASO 3: Mecha de rechazo (BÁRBULA de rechazo en S/R)
        candle_range = current['high'] - current['low']
        upper_wick = current['high'] - max(current['open'], current['close'])
        lower_wick = min(current['open'], current['close']) - current['low']
        lower_wick_pips = lower_wick / pip_value
        upper_wick_pips = upper_wick / pip_value

        wick_ok = False
        if near_support:
            # Cerca de soporte: busco mecha INFERIOR grande (rechazo del soporte)
            wick_ok = lower_wick_pips >= wick_min_range
            direction = "LONG"
            conditions["wick"] = {
                "passed": wick_ok,
                "lower_wick": round(lower_wick_pips, 1),
                "detail": f"Mecha inf {lower_wick_pips:.1f} pips (min: {wick_min_range})"
            }
        elif near_resistance:
            # Cerca de resistencia: busco mecha SUPERIOR grande (rechazo de la resistencia)
            wick_ok = upper_wick_pips >= wick_min_range
            direction = "SHORT"
            conditions["wick"] = {
                "passed": wick_ok,
                "upper_wick": round(upper_wick_pips, 1),
                "detail": f"Mecha sup {upper_wick_pips:.1f} pips (min: {wick_min_range})"
            }

        if not wick_ok:
            return None
        score += 1

        # PASO 4: Verificar que el precio RECHAZÓ (no rompió el nivel)
        if near_support:
            # Para BUY: el close debe estar POR ENCIMA del soporte
            rejection_ok = current['close'] > support
            conditions["rejection"] = {
                "passed": rejection_ok,
                "detail": f"Close {current['close']:.5f} > Soporte {support:.5f}" if rejection_ok
                          else f"Close POR DEBAJO del soporte — rotura"
            }
        else:
            # Para SELL: el close debe estar POR DEBAJO de la resistencia
            rejection_ok = current['close'] < resistance
            conditions["rejection"] = {
                "passed": rejection_ok,
                "detail": f"Close {current['close']:.5f} < Resistencia {resistance:.5f}" if rejection_ok
                          else f"Close POR ENCIMA de la resistencia — rotura"
            }

        if not rejection_ok:
            return None
        score += 1

        # PASO 5: Cierre en porcentaje favorable
        if candle_range > 0:
            if direction == "LONG":
                close_pos = (current['close'] - current['low']) / candle_range * 100
            else:
                close_pos = (current['high'] - current['close']) / candle_range * 100

            close_ok = close_pos >= close_pct_range
            conditions["close"] = {
                "passed": close_ok,
                "close_position": round(close_pos, 1),
                "detail": f"Cierre en {close_pos:.1f}% (min: {close_pct_range}%)"
            }
            if close_ok:
                score += 1
        else:
            conditions["close"] = {"passed": False, "detail": "Vela sin rango"}

        # PASO 6: Calcular SL y TP proporcionales al rango
        # TP = mitad del rango o máximo configurado
        range_sl = range_params.get("sl_pips", 15)
        range_tp = range_params.get("tp_pips", 20)

        # TP no puede ser más grande que el 60% del rango (para que no choque con S/R opuesto)
        max_tp = range_pips * 0.6
        final_tp = min(range_tp, max_tp)
        final_tp = max(final_tp, 8)  # Mínimo 8 pips de TP

        # SL = igual al TP (1:1) o un poco menos
        final_sl = final_tp * 1.0

        # Verificar que hay espacio suficiente para el TP
        if direction == "LONG":
            space_to_tp = (resistance - current['close']) / pip_value
            if space_to_tp < final_tp * 0.8:
                conditions["space"] = {"passed": False, "detail": f"Espacio a R: {space_to_tp:.1f} pips < TP: {final_tp:.0f}"}
                return None
        else:
            space_to_tp = (current['close'] - support) / pip_value
            if space_to_tp < final_tp * 0.8:
                conditions["space"] = {"passed": False, "detail": f"Espacio a S: {space_to_tp:.1f} pips < TP: {final_tp:.0f}"}
                return None

        min_score_range = range_params.get("min_score", 4)
        passed = score >= min_score_range

        return {
            "signal": "BUY" if direction == "LONG" else "SELL",
            "score": score,
            "max_score": 5,
            "passed": passed,
            "conditions": conditions,
            "direction": direction,
            "sl_pips": round(final_sl, 1),
            "tp_pips": round(final_tp, 1),
            "support": round(support, digits),
            "resistance": round(resistance, digits),
            "range_pips": round(range_pips, 1),
            "needs_ai_confirmation": passed,
        }

    # ═══════════════════════════════════════════════════════════
    #  SWEEP DETECTION (alertas tempranas — solo modo tendencia)
    # ═══════════════════════════════════════════════════════════

    def detect_sweep(self, symbol: str):
        """Detecta sweep en tendencia para alertas tempranas."""
        if not self._is_session_active(symbol):
            return None
        if not self._check_sweep_cooldown(symbol):
            return None

        df = self.data_feed.get_ohlc(symbol, num_candles=100)
        if df is None or len(df) < 50:
            return None

        market_mode = self._detect_market_mode(symbol, df)
        if market_mode != "TENDENCIA":
            return None

        pip_value = self.params["pip_values"].get(symbol, 0.0001)
        digits = self.params["digits"].get(symbol, 5)

        ema_fast = df['close'].ewm(span=self.params["ema_fast"], adjust=False).mean()
        ema_slow = df['close'].ewm(span=self.params["ema_slow"], adjust=False).mean()

        uptrend = ema_fast.iloc[-1] > ema_slow.iloc[-1]
        downtrend = ema_fast.iloc[-1] < ema_slow.iloc[-1]

        if uptrend:
            if ema_fast.iloc[-1] - ema_fast.iloc[-5] <= 0:
                uptrend = False
        if downtrend:
            if ema_fast.iloc[-1] - ema_fast.iloc[-5] >= 0:
                downtrend = False

        if not uptrend and not downtrend:
            return None

        direction = "LONG" if uptrend else "SHORT"
        current = df.iloc[-1]
        lookback = self.params["lookback_candles"]

        if direction == "LONG":
            prev_low = df['low'].iloc[-lookback:-3].min()
            sweep_pips = (prev_low - current['low']) / pip_value
            rejection = current['close'] > prev_low
            if sweep_pips > 0 and rejection:
                self.last_sweep_time[symbol] = datetime.now()
                return {
                    "symbol": symbol, "direction": direction,
                    "sweep_level": round(prev_low, digits),
                    "current_price": round(current['close'], digits),
                    "sweep_pips": round(sweep_pips, 1), "score": 3,
                    "rejection": True,
                    "timestamp": datetime.now().isoformat(),
                }
        else:
            prev_high = df['high'].iloc[-lookback:-3].max()
            sweep_pips = (current['high'] - prev_high) / pip_value
            rejection = current['close'] < prev_high
            if sweep_pips > 0 and rejection:
                self.last_sweep_time[symbol] = datetime.now()
                return {
                    "symbol": symbol, "direction": direction,
                    "sweep_level": round(prev_high, digits),
                    "current_price": round(current['close'], digits),
                    "sweep_pips": round(sweep_pips, 1), "score": 3,
                    "rejection": True,
                    "timestamp": datetime.now().isoformat(),
                }

        return None

    # ═══════════════════════════════════════════════════════════
    #  UTILIDADES
    # ═══════════════════════════════════════════════════════════

    def _is_session_active(self, symbol: str) -> bool:
        from datetime import datetime as dt
        import pytz
        now_utc = dt.now(pytz.utc)
        current_hour = now_utc.hour
        active_sessions = PAIR_SESSIONS.get(symbol, ["london", "new_york"])
        for session_name in active_sessions:
            session = SESSIONS.get(session_name)
            if session:
                if session["start"] <= current_hour < session["end"]:
                    return True
        return False

    def _check_signal_cooldown(self, symbol: str) -> bool:
        from config import BOT
        min_interval = BOT["min_timeframe_between_signals"]
        if symbol in self.last_signal_time:
            elapsed = (datetime.now() - self.last_signal_time[symbol]).total_seconds()
            return elapsed >= min_interval
        return True

    def _check_sweep_cooldown(self, symbol: str) -> bool:
        if symbol in self.last_sweep_time:
            elapsed = (datetime.now() - self.last_sweep_time[symbol]).total_seconds()
            return elapsed >= 600
        return True
