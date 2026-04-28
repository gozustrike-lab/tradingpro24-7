# ═══════════════════════════════════════════════════════════════
#  TRADING BOT HIBRIDO — STRATEGY ENGINE v8.0 MOMENTUM ICT
#  ═══ Estrategia unificada: Seguir momentum del mercado ═══
#  ═══ R:R 1:1 dinamico (SL = TP = 12-22 pips via ATR) ═══
#  ═══ Killzones ampliadas (13h cobertura) ═══
#  ═══ Objetivo: 8-15 senales diarias, 70-80% win rate ═══
# ═══════════════════════════════════════════════════════════════

import pandas as pd
import numpy as np
import logging
from datetime import datetime

from config import STRATEGY, PAIR_SESSIONS, SESSIONS
from data_feed import DataFeed

logger = logging.getLogger(__name__)


class StrategyEngine:
    """Motor de estrategia Momentum ICT v8.0 — Seguir direccion, 1:1 R:R."""

    def __init__(self, data_feed: DataFeed):
        self.data_feed = data_feed
        self.params = STRATEGY
        self.last_signal_time = {}
        self.last_sweep_time = {}

    # ═══════════════════════════════════════════════════════════
    #  ANALISIS PRINCIPAL
    # ═══════════════════════════════════════════════════════════

    def analyze(self, symbol: str):
        """Analiza un par con estrategia Momentum ICT."""
        # Filtro 1: Sesion activa
        if not self._is_session_active(symbol):
            return None

        # Filtro 2: Killzone ICT (ampliada para mas señales)
        if not self._is_killzone_active(symbol):
            return None

        # Obtener datos
        df = self.data_feed.get_ohlc(symbol, num_candles=100)
        if df is None or len(df) < 50:
            return None

        # Filtro 3: Spread bajo
        spread = self.data_feed.get_current_spread(symbol) if hasattr(self.data_feed, 'get_current_spread') else None
        if spread is not None and spread > 3.0:
            return None

        # Filtro 4: Cooldown entre señales (2 min)
        if not self._check_signal_cooldown(symbol):
            return None

        # Detectar direccion del momentum
        direction = self._detect_momentum(symbol, df)
        if direction is None:
            return None

        # Evaluar condiciones de entrada
        result = self._evaluate_entry(symbol, df, direction)
        if result is None or not result.get("passed"):
            return None

        # FVG Detection (bonus score)
        fvg = self._detect_fvg(symbol, df, direction)
        if fvg:
            result["fvg"] = fvg
            result["conditions"]["fvg"] = {
                "passed": True,
                "detail": f"FVG detectado: {fvg['type']} ({fvg['size_pips']:.1f} pips)"
            }
            result["score"] = result.get("score", 0) + 1
            result["max_score"] = result.get("max_score", 4) + 1

        # Order Block Detection (bonus)
        ob = self._detect_order_block(symbol, df, direction)
        if ob:
            result["order_block"] = ob
            result["conditions"]["order_block"] = {
                "passed": True,
                "detail": f"Order Block: {ob['type']} @ {ob['level']:.5f}"
            }
            result["score"] = result.get("score", 0) + 1
            result["max_score"] = result.get("max_score", 4) + 1

        # Completar resultado
        result["symbol"] = symbol
        result["timestamp"] = datetime.now().isoformat()
        result["current_price"] = df.iloc[-1]['close']
        result["market_mode"] = "MOMENTUM"
        self.last_signal_time[symbol] = datetime.now()

        logger.debug(f"[{symbol}] Momentum {direction} detectado — Score: {result['score']}/{result['max_score']}")
        return result

    # ═══════════════════════════════════════════════════════════
    #  DETECCION DE MOMENTUM (direccion del mercado)
    # ═══════════════════════════════════════════════════════════

    def _detect_momentum(self, symbol: str, df: pd.DataFrame) -> str:
        """
        Detecta la direccion del momentum actual usando multiples indicadores.
        Requiere al menos 3 de 4 indicadores alineados.
        """
        pip_value = self.params.get("pip_values", {}).get(symbol, 0.0001)

        # Indicador 1: Cruce EMA (20 y 50)
        ema_fast = df['close'].ewm(span=20, adjust=False).mean()
        ema_slow = df['close'].ewm(span=50, adjust=False).mean()
        ema_bullish = ema_fast.iloc[-1] > ema_slow.iloc[-1]
        ema_bearish = ema_fast.iloc[-1] < ema_slow.iloc[-1]

        # Indicador 2: Pendiente EMA (ultimas 5 velas)
        ema_slope = (ema_fast.iloc[-1] - ema_fast.iloc[-5]) / pip_value
        slope_up = ema_slope > 1.0
        slope_down = ema_slope < -1.0

        # Indicador 3: Cambio de precio (5 velas)
        price_change = (df.iloc[-1]['close'] - df.iloc[-6]['close']) / pip_value
        price_up = price_change > 3.0
        price_down = price_change < -3.0

        # Indicador 4: Estructura de precio (HH/HL o LH/LL)
        recent = df.iloc[-5:]
        hh_hl = recent['high'].iloc[-1] > recent['high'].iloc[-3] and recent['low'].iloc[-1] > recent['low'].iloc[-3]
        lh_ll = recent['high'].iloc[-1] < recent['high'].iloc[-3] and recent['low'].iloc[-1] < recent['low'].iloc[-3]

        # Puntuacion alcista vs bajista
        up_score = (1 if ema_bullish else 0) + (1 if slope_up else 0) + (1 if price_up else 0) + (1 if hh_hl else 0)
        down_score = (1 if ema_bearish else 0) + (1 if slope_down else 0) + (1 if price_down else 0) + (1 if lh_ll else 0)

        # Requiere al menos 3 de 4 indicadores alineados
        if up_score >= 3 and up_score > down_score:
            return "LONG"
        elif down_score >= 3 and down_score > up_score:
            return "SHORT"

        return None  # Sin momentum claro

    # ═══════════════════════════════════════════════════════════
    #  EVALUACION DE ENTRADA (4 condiciones ICT)
    # ═══════════════════════════════════════════════════════════

    def _evaluate_entry(self, symbol: str, df: pd.DataFrame, direction: str):
        """Evalua 4 condiciones para entrada: pullback, sweep, wick, close."""
        pip_value = self.params.get("pip_values", {}).get(symbol, 0.0001)
        digits = self.params.get("digits", {}).get(symbol, 5)
        current = df.iloc[-1]

        score = 0
        conditions = {}

        # ── C1: Pullback en direccion del momentum ──
        pb_candles = 5
        change = df.iloc[-2]['close'] - df.iloc[-(pb_candles + 1)]['close']
        change_pips = abs(change / pip_value)

        if direction == "LONG":
            is_pullback = change < 0 and change_pips >= 2
        else:
            is_pullback = change > 0 and change_pips >= 2

        conditions["pullback"] = {
            "passed": is_pullback,
            "pullback_pips": round(change_pips, 1),
            "detail": f"Pullback {change_pips:.1f} pips vs {direction}"
        }
        if is_pullback:
            score += 1

        # ── C2: Sweep de liquidez (BONUS — no obligatorio) ──
        lb = self.params.get("lookback_candles", 15)
        if direction == "LONG":
            prev_low = df['low'].iloc[-lb:-3].min()
            sweep = (prev_low - current['low']) / pip_value
            rejection = current['close'] > prev_low
        elif direction == "SHORT":
            prev_high = df['high'].iloc[-lb:-3].max()
            sweep = (current['high'] - prev_high) / pip_value
            rejection = current['close'] < prev_high
        else:
            sweep = 0
            rejection = False

        conditions["sweep"] = {
            "passed": sweep > 0,
            "sweep_pips": round(max(sweep, 0), 1),
            "rejection": rejection,
            "detail": f"Sweep {max(sweep,0):.1f} pips" + (" +RECHAZO" if rejection and sweep > 0 else "")
        }
        if sweep > 0:
            score += 1

        # ── C3: Mecha de rechazo ──
        cr = current['high'] - current['low']
        uw = current['high'] - max(current['open'], current['close'])
        lw = min(current['open'], current['close']) - current['low']
        wick_min_pips = self.params.get("wick_min_pips", 3)
        wick_ratio_min = self.params.get("wick_ratio_min", 1.2)

        if direction == "LONG" and cr > 0:
            wick_ratio = lw / uw if uw > 0 else 10.0
            wick_pips = lw / pip_value
            has_wick = wick_ratio >= wick_ratio_min and wick_pips >= wick_min_pips
        elif direction == "SHORT" and cr > 0:
            wick_ratio = uw / lw if lw > 0 else 10.0
            wick_pips = uw / pip_value
            has_wick = wick_ratio >= wick_ratio_min and wick_pips >= wick_min_pips
        else:
            wick_ratio = 0
            wick_pips = 0
            has_wick = False

        conditions["rejection_wick"] = {
            "passed": has_wick,
            "detail": f"Mecha {'inf' if direction == 'LONG' else 'sup'} {wick_ratio:.1f}x ({wick_pips:.1f} pips)"
        }
        if has_wick:
            score += 1

        # ── C4: Cierre fuerte en direccion del momentum ──
        if cr > 0:
            if direction == "LONG":
                close_pct = (current['close'] - current['low']) / cr * 100
            else:
                close_pct = (current['high'] - current['close']) / cr * 100
            strong_close = close_pct >= 55
        else:
            close_pct = 50
            strong_close = False

        conditions["close_position"] = {
            "passed": strong_close,
            "close_position": round(close_pct, 1),
            "detail": f"Cierre en {close_pct:.1f}% del rango"
        }
        if strong_close:
            score += 1

        # ── SL/TP dinamico basado en ATR (1:1 R:R) ──
        atr = self._calculate_atr(df, 14)
        atr_pips = atr / pip_value

        # SL = TP = 1.2x ATR, clamped a 12-22 pips
        sl_pips = max(12.0, min(22.0, round(atr_pips * 1.2, 1)))
        tp_pips = sl_pips  # 1:1 exacto

        # Score minimo: 2 de 4 (pullback + wick, o pullback + sweep, etc.)
        min_score = self.params.get("min_score", 2)

        return {
            "signal": "BUY" if direction == "LONG" else "SELL",
            "score": score,
            "max_score": 4,
            "passed": score >= min_score,
            "conditions": conditions,
            "direction": direction,
            "sl_pips": sl_pips,
            "tp_pips": tp_pips,
            "needs_ai_confirmation": True,
            # Keys compatibles con main.py para Telegram:
            "ema_trend": "bullish" if direction == "LONG" else "bearish",
            "sweep_passed": sweep > 0,
            "sweep_pips": round(max(sweep, 0), 1),
            "wick_passed": has_wick,
            "wick_ratio": round(wick_ratio, 2),
            "close_passed": strong_close,
            "close_range_pct": round(close_pct, 1),
            "pullback_passed": is_pullback,
            "pullback_pips": round(change_pips, 1),
        }

    # ═══════════════════════════════════════════════════════════
    #  ATR (Average True Range) para SL/TP dinamico
    # ═══════════════════════════════════════════════════════════

    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        """Calcula ATR para SL/TP dinamico adaptado a volatilidad."""
        recent = df.iloc[-period:]
        if len(recent) < 2:
            return 0.001  # Default seguro

        trs = []
        for i in range(1, len(recent)):
            h = recent['high'].iloc[i]
            l = recent['low'].iloc[i]
            pc = recent['close'].iloc[i - 1]
            tr = max(h - l, abs(h - pc), abs(l - pc))
            trs.append(tr)

        return np.mean(trs)

    # ═══════════════════════════════════════════════════════════
    #  KILLZONES ICT — AMPLIADAS (13 horas cobertura)
    # ═══════════════════════════════════════════════════════════

    def _is_killzone_active(self, symbol: str) -> bool:
        """Killzones ampliadas para maximizar oportunidades de señal."""
        from datetime import datetime as dt
        import pytz

        now_utc = dt.now(pytz.utc)
        current_hour = now_utc.hour
        day = now_utc.weekday()

        # No operar domingos ni sabados
        if day >= 5:
            return False

        # Killzones v8.0 — AMPLIADAS para mas señales
        # Zona 1: London Open + transicion (6-12 UTC = 1AM-7AM Peru)
        # Zona 2: NY Open + overlap (12-17 UTC = 7AM-12PM Peru)
        # Zona 3: London Close extendida (15-19 UTC = 10AM-2PM Peru)
        zones = [
            ("London+NY Bridge", 6, 12),
            ("NY Open Premium", 12, 17),
            ("London Close+", 15, 19),
        ]

        for zone_name, start, end in zones:
            if start <= current_hour < end:
                logger.debug(f"Killzone activa: {zone_name} ({start}:00-{end}:00 UTC)")
                return True

        return False

    # ═══════════════════════════════════════════════════════════
    #  FVG (FAIR VALUE GAP) DETECTION — Bonus
    # ═══════════════════════════════════════════════════════════

    def _detect_fvg(self, symbol: str, df: pd.DataFrame, direction: str) -> dict:
        """Detecta Fair Value Gaps — bonus de score."""
        if direction is None or len(df) < 5:
            return None

        pip_value = self.params.get("pip_values", {}).get(symbol, 0.0001)
        digits = self.params.get("digits", {}).get(symbol, 5)
        fvg_min_pips = self.params.get("fvg_min_pips", 3)

        for i in range(-10, -2):
            c1 = df.iloc[i]
            c2 = df.iloc[i + 1]
            c3 = df.iloc[i + 2]

            if direction == "LONG":
                gap_top = c3['low']
                gap_bottom = c1['high']
                gap_size = gap_top - gap_bottom
                if gap_size > 0:
                    gap_pips = gap_size / pip_value
                    if gap_pips >= fvg_min_pips:
                        current_price = df.iloc[-1]['close']
                        if gap_bottom <= current_price <= gap_top:
                            return {
                                "type": "BULLISH",
                                "top": round(gap_top, digits),
                                "bottom": round(gap_bottom, digits),
                                "size_pips": round(gap_pips, 1),
                                "candle_index": i,
                            }
            elif direction == "SHORT":
                gap_top = c1['low']
                gap_bottom = c3['high']
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
                            }
        return None

    # ═══════════════════════════════════════════════════════════
    #  ORDER BLOCK DETECTION — Bonus
    # ═══════════════════════════════════════════════════════════

    def _detect_order_block(self, symbol: str, df: pd.DataFrame, direction: str) -> dict:
        """Detecta Order Blocks ICT — bonus de score."""
        if direction is None or len(df) < 10:
            return None

        pip_value = self.params.get("pip_values", {}).get(symbol, 0.0001)
        digits = self.params.get("digits", {}).get(symbol, 5)
        ob_lookback = self.params.get("ob_lookback", 15)
        ob_min_body = self.params.get("ob_min_body_pips", 5)

        recent = df.iloc[-ob_lookback:]
        current_price = df.iloc[-1]['close']

        if direction == "LONG":
            for i in range(len(recent) - 2, 1, -1):
                c = recent.iloc[i]
                body_top = max(c['open'], c['close'])
                body_bottom = min(c['open'], c['close'])
                body_size = body_top - body_bottom
                if c['close'] < c['open'] and body_size / pip_value >= ob_min_body:
                    next_c = recent.iloc[i + 1]
                    if next_c['close'] > c['high']:
                        ob_level = body_bottom
                        dist = abs(current_price - ob_level) / pip_value
                        if dist <= 10:
                            return {
                                "type": "BULLISH_OB",
                                "level": round(ob_level, digits),
                                "top": round(body_top, digits),
                                "body_pips": round(body_size / pip_value, 1),
                                "dist_to_price": round(dist, 1),
                            }
                    break

        elif direction == "SHORT":
            for i in range(len(recent) - 2, 1, -1):
                c = recent.iloc[i]
                body_top = max(c['open'], c['close'])
                body_bottom = min(c['open'], c['close'])
                body_size = body_top - body_bottom
                if c['close'] > c['open'] and body_size / pip_value >= ob_min_body:
                    next_c = recent.iloc[i + 1]
                    if next_c['close'] < c['low']:
                        ob_level = body_top
                        dist = abs(current_price - ob_level) / pip_value
                        if dist <= 10:
                            return {
                                "type": "BEARISH_OB",
                                "level": round(ob_level, digits),
                                "bottom": round(body_bottom, digits),
                                "body_pips": round(body_size / pip_value, 1),
                                "dist_to_price": round(dist, 1),
                            }
                    break

        return None

    # ═══════════════════════════════════════════════════════════
    #  SWEEP DETECTION (alertas tempranas)
    # ═══════════════════════════════════════════════════════════

    def detect_sweep(self, symbol: str):
        """Detecta sweep para alertas tempranas."""
        if not self._is_session_active(symbol) or not self._is_killzone_active(symbol):
            return None
        if not self._check_sweep_cooldown(symbol):
            return None

        df = self.data_feed.get_ohlc(symbol, num_candles=100)
        if df is None or len(df) < 50:
            return None

        direction = self._detect_momentum(symbol, df)
        if direction is None:
            return None

        pip_value = self.params.get("pip_values", {}).get(symbol, 0.0001)
        digits = self.params.get("digits", {}).get(symbol, 5)
        c = df.iloc[-1]
        lb = self.params.get("lookback_candles", 15)

        if direction == "LONG":
            pl = df['low'].iloc[-lb:-3].min()
            sp = (pl - c['low']) / pip_value
            if sp > 0 and c['close'] > pl:
                self.last_sweep_time[symbol] = datetime.now()
                return {"symbol": symbol, "direction": direction, "sweep_level": round(pl, digits), "current_price": round(c['close'], digits), "sweep_pips": round(sp, 1), "score": 3, "rejection": True, "timestamp": datetime.now().isoformat()}
        else:
            ph = df['high'].iloc[-lb:-3].max()
            sp = (c['high'] - ph) / pip_value
            if sp > 0 and c['close'] < ph:
                self.last_sweep_time[symbol] = datetime.now()
                return {"symbol": symbol, "direction": direction, "sweep_level": round(ph, digits), "current_price": round(c['close'], digits), "sweep_pips": round(sp, 1), "score": 3, "rejection": True, "timestamp": datetime.now().isoformat()}
        return None

    # ═══════════════════════════════════════════════════════════
    #  UTILIDADES
    # ═══════════════════════════════════════════════════════════

    def _is_session_active(self, symbol: str) -> bool:
        """Verifica si la sesion esta activa para el par."""
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
        """Cooldown de 2 minutos entre señales del mismo par."""
        cooldown = 120  # v8.0: 2 minutos (era 300 = 5 min)
        try:
            from config import BOT
            cooldown = BOT.get("min_timeframe_between_signals", 120)
        except Exception:
            pass

        if symbol in self.last_signal_time:
            return (datetime.now() - self.last_signal_time[symbol]).total_seconds() >= cooldown
        return True

    def _check_sweep_cooldown(self, symbol: str) -> bool:
        """Cooldown de 5 minutos entre alerts de sweep."""
        if symbol in self.last_sweep_time:
            return (datetime.now() - self.last_sweep_time[symbol]).total_seconds() >= 300
        return True
