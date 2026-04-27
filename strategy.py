# ═══════════════════════════════════════════════════════════════
#  TRADING BOT HÍBRIDO — STRATEGY ENGINE v6.0 PROFESSIONAL
#  ═══ MODO 1: ICT Sweep (tendencia) — TP grande ═══
#  ═══ MODO 2: Rango/Lateral — TP corto S/R ═══
#  ═══ NUEVO: Killzones ICT, FVG, Order Blocks, Multi-TF ═══
# ═══════════════════════════════════════════════════════════════

import pandas as pd
import numpy as np
import logging
from datetime import datetime

from config import STRATEGY, PAIR_SESSIONS, SESSIONS
from data_feed import DataFeed

logger = logging.getLogger(__name__)


class StrategyEngine:
    """Motor de estrategia profesional ICT con 2 modos + FVG + OB + Killzones."""

    def __init__(self, data_feed: DataFeed):
        self.data_feed = data_feed
        self.params = STRATEGY
        self.last_signal_time = {}
        self.last_sweep_time = {}

    # ═══════════════════════════════════════════════════════════
    #  ANALISIS PRINCIPAL
    # ═══════════════════════════════════════════════════════════

    def analyze(self, symbol: str):
        """Analiza un par con todos los filtros ICT profesionales."""
        if not self._is_session_active(symbol):
            return None
        if not self._is_killzone_active(symbol):
            return None

        df = self.data_feed.get_ohlc(symbol, num_candles=100)
        if df is None or len(df) < 50:
            return None

        spread = self.data_feed.get_current_spread(symbol) if hasattr(self.data_feed, 'get_current_spread') else None
        if spread is not None and spread > 3.0:
            return None
        if not self._check_signal_cooldown(symbol):
            return None

        market_mode = self._detect_market_mode(symbol, df)

        if market_mode == "TENDENCIA":
            result = self._evaluate_trend(symbol, df)
        elif market_mode == "RANGO":
            result = self._evaluate_range(symbol, df)
        else:
            return None

        if result:
            # FVG Detection (bonus score)
            fvg = self._detect_fvg(symbol, df, result.get("direction"))
            if fvg:
                result["fvg"] = fvg
                result["conditions"]["fvg"] = {
                    "passed": True,
                    "detail": f"FVG detectado: {fvg['type']} ({fvg['size_pips']:.1f} pips)"
                }

            # Order Block Detection (bonus)
            ob = self._detect_order_block(symbol, df, result.get("direction"))
            if ob:
                result["order_block"] = ob
                result["conditions"]["order_block"] = {
                    "passed": True,
                    "detail": f"Order Block: {ob['type']} @ {ob['level']:.5f}"
                }

            # Multi-timeframe confirmation
            mtf = self._multi_tf_confirm(symbol, result.get("direction"))
            result["mtf_confirmed"] = mtf
            result["conditions"]["multi_tf"] = {
                "passed": mtf,
                "detail": "H1 confirma dirección" if mtf else "H1 no confirma"
            }

            result["symbol"] = symbol
            result["timestamp"] = datetime.now().isoformat()
            result["current_price"] = df.iloc[-1]['close']
            result["market_mode"] = market_mode
            self.last_signal_time[symbol] = datetime.now()

        return result

    # ═══════════════════════════════════════════════════════════
    #  KILLZONES ICT — Solo operar en horas de alta probabilidad
    # ═══════════════════════════════════════════════════════════

    def _is_killzone_active(self, symbol: str) -> bool:
        """Verifica si estamos en una killzone ICT de alta probabilidad."""
        from datetime import datetime as dt
        import pytz

        killzones = self.params.get("killzones", {
            "enabled": True,
            "zones": {
                "london_open": {"start": 7, "end": 10},    # 7-10 UTC = 2-5AM EST
                "ny_open": {"start": 12, "end": 15},       # 12-15 UTC = 7-10AM EST
                "london_close": {"start": 15, "end": 17},   # 15-17 UTC = 10AM-12PM EST
            }
        })

        if not killzones.get("enabled", True):
            return True  # Si killzones desactivado, siempre operativo

        now_utc = dt.now(pytz.utc)
        current_hour = now_utc.hour
        day = now_utc.weekday()  # 0= lunes, 6= domingo

        # No operar domingos ni sábados
        if day >= 5:
            return False

        for zone_name, zone in killzones.get("zones", {}).items():
            if zone["start"] <= current_hour < zone["end"]:
                logger.debug(f"Killzone activa: {zone_name} ({zone['start']}:00-{zone['end']}:00 UTC)")
                return True

        return False

    # ═══════════════════════════════════════════════════════════
    #  FVG (FAIR VALUE GAP) DETECTION
    # ═══════════════════════════════════════════════════════════

    def _detect_fvg(self, symbol: str, df: pd.DataFrame, direction: str) -> dict:
        """
        Detecta Fair Value Gaps (FVG) — huecos de valor justo ICT.
        Un FVG ocurre cuando el cuerpo de la vela 1 no se superpone
        con el cuerpo de la vela 3 (impulso fuerte).
        """
        if direction is None or len(df) < 5:
            return None

        pip_value = self.params["pip_values"].get(symbol, 0.0001)
        digits = self.params["digits"].get(symbol, 5)
        fvg_min_pips = self.params.get("fvg_min_pips", 3)

        # Buscar en las últimas 10 velas
        for i in range(-10, -2):
            c1 = df.iloc[i]      # Vela 1
            c2 = df.iloc[i + 1]  # Vela 2 (gap)
            c3 = df.iloc[i + 2]  # Vela 3

            if direction == "LONG":
                # FVG alcista: high de vela 1 < low de vela 3 (hueco alcista)
                gap_top = c3['low']    # Borde inferior del hueco
                gap_bottom = c1['high']  # Borde superior del hueco
                gap_size = gap_top - gap_bottom

                if gap_size > 0:
                    gap_pips = gap_size / pip_value
                    if gap_pips >= fvg_min_pips:
                        # Verificar que el precio actual está cerca del FVG (zona de entrada)
                        current_price = df.iloc[-1]['close']
                        if gap_bottom <= current_price <= gap_top:
                            return {
                                "type": "BULLISH",
                                "top": round(gap_top, digits),
                                "bottom": round(gap_bottom, digits),
                                "size_pips": round(gap_pips, 1),
                                "candle_index": i,
                                "detail": f"FVG Alcista: {gap_bottom:.5f} - {gap_top:.5f} ({gap_pips:.1f} pips)"
                            }

            elif direction == "SHORT":
                # FVG bajista: low de vela 1 > high de vela 3 (hueco bajista)
                gap_top = c1['low']     # Borde superior del hueco
                gap_bottom = c3['high']  # Borde inferior del hueco
                gap_size = gap_top - gap_bottom

                if gap_size > 0:
                    gap_pips = gap_size / pip_value
                    if gap_pips >= fvg_min_pips:
                        current_price = df.iloc[-1]['close']
                        if gap_bottom <= current_price <= gap_top:
                            return {
                                "type": "BEARISH",
                                "top": round(gap_top, digits),
                                "bottom": round(gap_bottom, digits),
                                "size_pips": round(gap_pips, 1),
                                "candle_index": i,
                                "detail": f"FVG Bajista: {gap_bottom:.5f} - {gap_top:.5f} ({gap_pips:.1f} pips)"
                            }

        return None

    # ═══════════════════════════════════════════════════════════
    #  ORDER BLOCK DETECTION
    # ═══════════════════════════════════════════════════════════

    def _detect_order_block(self, symbol: str, df: pd.DataFrame, direction: str) -> dict:
        """
        Detecta Order Blocks ICT — última vela bajista antes de impulso alcista
        (o última vela alcista antes de impulso bajista).
        """
        if direction is None or len(df) < 10:
            return None

        pip_value = self.params["pip_values"].get(symbol, 0.0001)
        digits = self.params["digits"].get(symbol, 5)

        ob_lookback = self.params.get("ob_lookback", 15)
        ob_min_body = self.params.get("ob_min_body_pips", 5)

        recent = df.iloc[-ob_lookback:]
        current_price = df.iloc[-1]['close']

        if direction == "LONG":
            # Buscar última vela bajista (roja) antes de un impulso alcista
            for i in range(len(recent) - 2, 1, -1):
                c = recent.iloc[i]
                body_top = max(c['open'], c['close'])
                body_bottom = min(c['open'], c['close'])
                body_size = body_top - body_bottom

                # Vela bajista con cuerpo suficiente
                if c['close'] < c['open'] and body_size / pip_value >= ob_min_body_pips:
                    # Verificar que después hubo impulso alcista
                    next_c = recent.iloc[i + 1]
                    if next_c['close'] > c['high']:  # Impulso rompió el máximo
                        ob_level = body_bottom
                        # Verificar que el precio está cerca del OB
                        dist = abs(current_price - ob_level) / pip_value
                        if dist <= 10:  # Dentro de 10 pips del OB
                            return {
                                "type": "BULLISH_OB",
                                "level": round(ob_level, digits),
                                "top": round(body_top, digits),
                                "body_pips": round(body_size / pip_value, 1),
                                "dist_to_price": round(dist, 1),
                                "detail": f"OB Alcista @ {ob_level:.5f} (cuerpo {body_size/pip_value:.1f} pips)"
                            }
                    break  # Solo buscar el primero

        elif direction == "SHORT":
            # Buscar última vela alcista (verde) antes de un impulso bajista
            for i in range(len(recent) - 2, 1, -1):
                c = recent.iloc[i]
                body_top = max(c['open'], c['close'])
                body_bottom = min(c['open'], c['close'])
                body_size = body_top - body_bottom

                # Vela alcista con cuerpo suficiente
                if c['close'] > c['open'] and body_size / pip_value >= ob_min_body_pips:
                    next_c = recent.iloc[i + 1]
                    if next_c['close'] < c['low']:  # Impulso rompió el mínimo
                        ob_level = body_top
                        dist = abs(current_price - ob_level) / pip_value
                        if dist <= 10:
                            return {
                                "type": "BEARISH_OB",
                                "level": round(ob_level, digits),
                                "bottom": round(body_bottom, digits),
                                "body_pips": round(body_size / pip_value, 1),
                                "dist_to_price": round(dist, 1),
                                "detail": f"OB Bajista @ {ob_level:.5f} (cuerpo {body_size/pip_value:.1f} pips)"
                            }
                    break

        return None

    # ═══════════════════════════════════════════════════════════
    #  MULTI-TIMEFRAME CONFIRMATION (M15 + H1)
    # ═══════════════════════════════════════════════════════════

    def _multi_tf_confirm(self, symbol: str, direction: str) -> bool:
        """Confirma la dirección en H1 para mayor confiabilidad."""
        mtf_enabled = self.params.get("multi_tf_enabled", True)
        if not mtf_enabled or direction is None:
            return True  # Si desactivado, siempre confirma

        try:
            # Intentar obtener datos H1
            df_h1 = self.data_feed.get_ohlc(symbol, num_candles=50, timeframe="H1")
            if df_h1 is None or len(df_h1) < 30:
                return True  # No hay datos H1, no bloquear

            ema_fast = df_h1['close'].ewm(span=20, adjust=False).mean()
            ema_slow = df_h1['close'].ewm(span=50, adjust=False).mean()

            if direction == "LONG":
                return ema_fast.iloc[-1] > ema_slow.iloc[-1]
            else:
                return ema_fast.iloc[-1] < ema_slow.iloc[-1]

        except Exception:
            return True  # Si falla, no bloquear la señal

    # ═══════════════════════════════════════════════════════════
    #  DETECTOR DE MERCADO — Tendencia vs Rango vs Caótico
    # ═══════════════════════════════════════════════════════════

    def _detect_market_mode(self, symbol: str, df: pd.DataFrame) -> str:
        """Detecta si el mercado está en tendencia, rango o caótico."""
        pip_value = self.params["pip_values"].get(symbol, 0.0001)

        ema_fast = df['close'].ewm(span=self.params["ema_fast"], adjust=False).mean()
        ema_slow = df['close'].ewm(span=self.params["ema_slow"], adjust=False).mean()

        ema_f_slope = ema_fast.iloc[-1] - ema_fast.iloc[-5]
        ema_distance = abs(ema_fast.iloc[-1] - ema_slow.iloc[-1]) / pip_value

        recent_highs = df['high'].iloc[-10:]
        recent_lows = df['low'].iloc[-10:]
        hh_hl = (recent_highs.iloc[-1] > recent_highs.iloc[-3] and
                 recent_lows.iloc[-1] > recent_lows.iloc[-3])
        lh_ll = (recent_highs.iloc[-1] < recent_highs.iloc[-3] and
                 recent_lows.iloc[-1] < recent_lows.iloc[-3])

        # ADX
        adx = self._calculate_adx(df)

        uptrend = ema_fast.iloc[-1] > ema_slow.iloc[-1] and ema_f_slope > 0 and hh_hl
        downtrend = ema_fast.iloc[-1] < ema_slow.iloc[-1] and ema_f_slope < 0 and lh_ll

        if (uptrend or downtrend) and adx > 20 and ema_distance > 5:
            return "TENDENCIA"

        slope_flat = abs(ema_f_slope) / pip_value < 3
        structure_flat = not hh_hl and not lh_ll

        if slope_flat and structure_flat and adx < 25:
            return "RANGO"

        return "CAOTICO"

    def _calculate_adx(self, df: pd.DataFrame, period: int = 14) -> float:
        """Calcula ADX (Average Directional Index)."""
        high = df['high'].iloc[-period:]
        low = df['low'].iloc[-period:]
        close = df['close'].iloc[-period:]
        if len(high) < 2:
            return 0

        tr_sum = plus_dm_sum = minus_dm_sum = 0
        for i in range(1, len(high)):
            tr = max(high.iloc[i] - low.iloc[i],
                     abs(high.iloc[i] - close.iloc[i-1]),
                     abs(low.iloc[i] - close.iloc[i-1]))
            tr_sum += tr
            up = high.iloc[i] - high.iloc[i-1]
            down = low.iloc[i-1] - low.iloc[i]
            plus_dm_sum += up if (up > down and up > 0) else 0
            minus_dm_sum += down if (down > up and down > 0) else 0

        if tr_sum == 0:
            return 0
        plus_di = 100 * plus_dm_sum / tr_sum
        minus_di = 100 * minus_dm_sum / tr_sum
        di_sum = plus_di + minus_di
        return 100 * abs(plus_di - minus_di) / di_sum if di_sum > 0 else 0

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

        # C1: Tendencia
        ema_fast = df['close'].ewm(span=self.params["ema_fast"], adjust=False).mean()
        ema_slow = df['close'].ewm(span=self.params["ema_slow"], adjust=False).mean()
        uptrend = ema_fast.iloc[-1] > ema_slow.iloc[-1]
        downtrend = ema_fast.iloc[-1] < ema_slow.iloc[-1]
        ema_f_slope = ema_fast.iloc[-1] - ema_fast.iloc[-5]

        recent_highs = df['high'].iloc[-10:]
        recent_lows = df['low'].iloc[-10:]
        hh_hl = (recent_highs.iloc[-1] > recent_highs.iloc[-3] and recent_lows.iloc[-1] > recent_lows.iloc[-3])
        lh_ll = (recent_highs.iloc[-1] < recent_highs.iloc[-3] and recent_lows.iloc[-1] < recent_lows.iloc[-3])

        trend_strong = (uptrend and ema_f_slope > 0 and hh_hl) or (downtrend and ema_f_slope < 0 and lh_ll)
        conditions["trend"] = {
            "passed": uptrend or downtrend,
            "strong": trend_strong,
            "detail": f"EMA{self.params['ema_fast']}{'>' if uptrend else '<'}EMA{self.params['ema_slow']}" + (" FUERTE" if trend_strong else "")
        }
        if uptrend or downtrend:
            score += 1
            direction = "LONG" if uptrend else "SHORT"
        else:
            direction = None

        # C2: Pullback direccional
        if direction and len(df) > self.params["pullback_candles"] + 1:
            pb = self.params["pullback_candles"]
            change = df.iloc[-2]['close'] - df.iloc[-(pb + 1)]['close']
            change_pips = abs(change / pip_value)
            is_pb = (change < 0 and change_pips >= self.params["pullback_min_pips"]) if direction == "LONG" else (change > 0 and change_pips >= self.params["pullback_min_pips"])
            conditions["pullback"] = {"passed": is_pb, "pullback_pips": round(change_pips, 1), "detail": f"Pullback {change_pips:.1f} pips vs {direction}"}
            if is_pb:
                score += 1
        else:
            conditions["pullback"] = {"passed": False, "detail": "Sin datos"}

        # C3: Sweep real
        lb = self.params["lookback_candles"]
        if direction == "LONG":
            prev_low = df['low'].iloc[-lb:-3].min()
            sp = (prev_low - current['low']) / pip_value
            rej = current['close'] > prev_low
            conditions["sweep"] = {"passed": sp > 0, "sweep_pips": round(sp, 1), "rejection": rej, "detail": f"Sweep {sp:.1f} pips" + (" +RECHAZO" if rej else "")}
            if sp > 0: score += 1
        elif direction == "SHORT":
            prev_high = df['high'].iloc[-lb:-3].max()
            sp = (current['high'] - prev_high) / pip_value
            rej = current['close'] < prev_high
            conditions["sweep"] = {"passed": sp > 0, "sweep_pips": round(sp, 1), "rejection": rej, "detail": f"Sweep {sp:.1f} pips" + (" +RECHAZO" if rej else "")}
            if sp > 0: score += 1
        else:
            conditions["sweep"] = {"passed": False}

        # C4: Mecha con mínimo
        cr = current['high'] - current['low']
        uw = current['high'] - max(current['open'], current['close'])
        lw = min(current['open'], current['close']) - current['low']
        lw_p = lw / pip_value
        uw_p = uw / pip_value
        wm = self.params.get("wick_min_pips", 5)

        if direction == "LONG" and cr > 0:
            wr = lw / uw if uw > 0 else 10.0
            wk = wr >= self.params["wick_ratio_min"] and lw_p >= wm
            conditions["rejection_wick"] = {"passed": wk, "detail": f"Mecha inf {wr:.2f}x, {lw_p:.1f} pips"}
            if wk: score += 1
        elif direction == "SHORT" and cr > 0:
            wr = uw / lw if lw > 0 else 10.0
            wk = wr >= self.params["wick_ratio_min"] and uw_p >= wm
            conditions["rejection_wick"] = {"passed": wk, "detail": f"Mecha sup {wr:.2f}x, {uw_p:.1f} pips"}
            if wk: score += 1
        else:
            conditions["rejection_wick"] = {"passed": False}

        # C5: Cierre fuerte
        if cr > 0:
            cp = ((current['close'] - current['low']) / cr * 100) if direction == "LONG" else ((current['high'] - current['close']) / cr * 100)
            conditions["close_position"] = {"passed": cp >= self.params["close_percentile"], "close_position": round(cp, 1), "detail": f"Cierre en {cp:.1f}%"}
            if cp >= self.params["close_percentile"]: score += 1
        else:
            conditions["close_position"] = {"passed": False}

        return {
            "signal": "BUY" if direction == "LONG" else ("SELL" if direction == "SHORT" else None),
            "score": score, "max_score": 5, "passed": score >= self.params["min_score"],
            "conditions": conditions, "direction": direction,
            "sl_pips": self.params.get("trend_sl_pips", 18),
            "tp_pips": self.params.get("trend_tp_pips", 45),
            "needs_ai_confirmation": score >= self.params["min_score"],
        }

    # ═══════════════════════════════════════════════════════════
    #  MODO 2: RANGO/LATERAL — Soporte/Resistencia
    # ═══════════════════════════════════════════════════════════

    def _evaluate_range(self, symbol: str, df: pd.DataFrame):
        """Evalúa señales en rango — compra en soporte, venta en resistencia."""
        pip_value = self.params["pip_values"].get(symbol, 0.0001)
        digits = self.params["digits"].get(symbol, 5)
        current = df.iloc[-1]
        rp = self.params.get("range_mode", {})

        lookback = rp.get("sr_lookback", 30)
        zone_pips = rp.get("zone_pips", 5)
        min_range = rp.get("min_range_pips", 20)
        wick_min = rp.get("wick_min_pips", 3)
        close_pct = rp.get("close_percentile", 70)

        score = 0
        conditions = {}

        # S/R
        sr_df = df.iloc[-lookback:]
        support = sr_df['low'].min()
        resistance = sr_df['high'].max()
        range_pips = (resistance - support) / pip_value

        conditions["range"] = {"passed": range_pips >= min_range, "support": round(support, digits), "resistance": round(resistance, digits), "range_pips": round(range_pips, 1), "detail": f"Rango: {range_pips:.1f} pips"}
        if range_pips < min_range:
            return None
        score += 1

        # Zona
        d_s = (current['low'] - support) / pip_value
        d_r = (resistance - current['high']) / pip_value
        ns = d_s <= zone_pips
        nr = d_r <= zone_pips

        conditions["zone"] = {"passed": ns or nr, "detail": f"Zona {'SOPORTE' if ns else 'RESISTENCIA'} ({min(d_s, d_r):.1f} pips)" if (ns or nr) else "En medio del rango"}
        if not ns and not nr:
            return None
        score += 1

        # Mecha
        cr = current['high'] - current['low']
        uw = current['high'] - max(current['open'], current['close'])
        lw = min(current['open'], current['close']) - current['low']

        if ns:
            wk = (lw / pip_value) >= wick_min
            direction = "LONG"
            conditions["wick"] = {"passed": wk, "detail": f"Mecha inf {lw/pip_value:.1f} pips"}
        else:
            wk = (uw / pip_value) >= wick_min
            direction = "SHORT"
            conditions["wick"] = {"passed": wk, "detail": f"Mecha sup {uw/pip_value:.1f} pips"}
        if not wk:
            return None
        score += 1

        # Rechazo
        if ns:
            ro = current['close'] > support
            conditions["rejection"] = {"passed": ro, "detail": f"Close > Soporte" if ro else "Rotura de soporte"}
        else:
            ro = current['close'] < resistance
            conditions["rejection"] = {"passed": ro, "detail": f"Close < Resistencia" if ro else "Rotura de resistencia"}
        if not ro:
            return None
        score += 1

        # Cierre
        if cr > 0:
            cp = ((current['close'] - current['low']) / cr * 100) if direction == "LONG" else ((current['high'] - current['close']) / cr * 100)
            co = cp >= close_pct
            conditions["close"] = {"passed": co, "detail": f"Cierre {cp:.1f}%"}
            if co: score += 1
        else:
            conditions["close"] = {"passed": False}

        # SL/TP proporcional
        r_sl = rp.get("sl_pips", 15)
        r_tp = rp.get("tp_pips", 20)
        max_tp = range_pips * 0.6
        ftp = max(min(r_tp, max_tp), 8)
        fsl = ftp * 1.0

        # Espacio
        if direction == "LONG" and (resistance - current['close']) / pip_value < ftp * 0.8:
            return None
        if direction == "SHORT" and (current['close'] - support) / pip_value < ftp * 0.8:
            return None

        return {
            "signal": "BUY" if direction == "LONG" else "SELL",
            "score": score, "max_score": 5, "passed": score >= rp.get("min_score", 4),
            "conditions": conditions, "direction": direction,
            "sl_pips": round(fsl, 1), "tp_pips": round(ftp, 1),
            "support": round(support, digits), "resistance": round(resistance, digits),
            "range_pips": round(range_pips, 1), "needs_ai_confirmation": True,
        }

    # ═══════════════════════════════════════════════════════════
    #  SWEEP DETECTION (alertas tempranas)
    # ═══════════════════════════════════════════════════════════

    def detect_sweep(self, symbol: str):
        """Detecta sweep en tendencia para alertas tempranas."""
        if not self._is_session_active(symbol) or not self._is_killzone_active(symbol):
            return None
        if not self._check_sweep_cooldown(symbol):
            return None

        df = self.data_feed.get_ohlc(symbol, num_candles=100)
        if df is None or len(df) < 50:
            return None
        if self._detect_market_mode(symbol, df) != "TENDENCIA":
            return None

        pip_value = self.params["pip_values"].get(symbol, 0.0001)
        digits = self.params["digits"].get(symbol, 5)
        ema_f = df['close'].ewm(span=self.params["ema_fast"], adjust=False).mean()
        ema_s = df['close'].ewm(span=self.params["ema_slow"], adjust=False).mean()

        up = ema_f.iloc[-1] > ema_s.iloc[-1] and (ema_f.iloc[-1] - ema_f.iloc[-5]) > 0
        dn = ema_f.iloc[-1] < ema_s.iloc[-1] and (ema_f.iloc[-1] - ema_f.iloc[-5]) < 0
        if not up and not dn:
            return None

        d = "LONG" if up else "SHORT"
        c = df.iloc[-1]
        lb = self.params["lookback_candles"]

        if d == "LONG":
            pl = df['low'].iloc[-lb:-3].min()
            sp = (pl - c['low']) / pip_value
            if sp > 0 and c['close'] > pl:
                self.last_sweep_time[symbol] = datetime.now()
                return {"symbol": symbol, "direction": d, "sweep_level": round(pl, digits), "current_price": round(c['close'], digits), "sweep_pips": round(sp, 1), "score": 3, "rejection": True, "timestamp": datetime.now().isoformat()}
        else:
            ph = df['high'].iloc[-lb:-3].max()
            sp = (c['high'] - ph) / pip_value
            if sp > 0 and c['close'] < ph:
                self.last_sweep_time[symbol] = datetime.now()
                return {"symbol": symbol, "direction": d, "sweep_level": round(ph, digits), "current_price": round(c['close'], digits), "sweep_pips": round(sp, 1), "score": 3, "rejection": True, "timestamp": datetime.now().isoformat()}
        return None

    # ═══════════════════════════════════════════════════════════
    #  UTILIDADES
    # ═══════════════════════════════════════════════════════════

    def _is_session_active(self, symbol: str) -> bool:
        from datetime import datetime as dt
        import pytz
        now_utc = dt.now(pytz.utc)
        h = now_utc.hour
        for sn in PAIR_SESSIONS.get(symbol, ["london", "new_york"]):
            s = SESSIONS.get(sn)
            if s and s["start"] <= h < s["end"]:
                return True
        return False

    def _check_signal_cooldown(self, symbol: str) -> bool:
        from config import BOT
        if symbol in self.last_signal_time:
            return (datetime.now() - self.last_signal_time[symbol]).total_seconds() >= BOT["min_timeframe_between_signals"]
        return True

    def _check_sweep_cooldown(self, symbol: str) -> bool:
        if symbol in self.last_sweep_time:
            return (datetime.now() - self.last_sweep_time[symbol]).total_seconds() >= 600
        return True
