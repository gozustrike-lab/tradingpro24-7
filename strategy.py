# ═══════════════════════════════════════════════════════════════
#  TRADING BOT HIBRIDO — STRATEGY ENGINE v8.1 MOMENTUM ICT
#  ═══ Estrategia unificada: Seguir momentum del mercado ═══
#  ═══ R:R 1:1 dinamico (SL = TP via ATR) ═══
#  ═══ NUEVO: XAUUSD en M1 con params especificos ═══
#  ═══ Objetivo: 10-20+ senales diarias, 70-80% win rate ═══
# ═══════════════════════════════════════════════════════════════

import pandas as pd
import numpy as np
import logging
from datetime import datetime

from config import STRATEGY, PAIR_SESSIONS, SESSIONS
from data_feed import DataFeed

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
#  CONFIGURACION POR PAR — XAUUSD usa M1, el resto M15
# ═══════════════════════════════════════════════════════════════

PAIR_CONFIG = {
    "XAUUSD": {
        "timeframe": "M1",
        "ema_fast": 10,           # EMA rapida para M1
        "ema_slow": 25,           # EMA lenta para M1
        "atr_period": 10,         # ATR rapido para M1
        "atr_multiplier": 1.8,    # Mas room para volatilidad del oro
        "sl_min": 20.0,           # SL minimo 20 pips
        "sl_max": 35.0,           # SL maximo 35 pips
        "spread_limit": 5.0,      # Spread maximo 5 pips (oro es mas ancho)
        "cooldown": 60,           # 1 minuto entre señales (M1)
        "score_min": 2,           # 2 de 4 para entrar
        "momentum_threshold": 3,  # 3 de 4 indicadores alineados
        "min_price_change": 5.0,  # 5 pips de cambio minimo (oro se mueve rapido)
        "min_slope": 2.0,         # Pendiente EMA minima en pips
    },
    # DEFAULT para Forex majors (EURUSD, GBPUSD, etc.)
    "_DEFAULT": {
        "timeframe": "M15",
        "ema_fast": 20,
        "ema_slow": 50,
        "atr_period": 14,
        "atr_multiplier": 1.2,
        "sl_min": 12.0,
        "sl_max": 22.0,
        "spread_limit": 3.0,
        "cooldown": 120,          # 2 minutos
        "score_min": 2,
        "momentum_threshold": 3,
        "min_price_change": 3.0,
        "min_slope": 1.0,
    },
}


def get_pair_config(symbol: str) -> dict:
    """Retorna config especifica del par o default."""
    return PAIR_CONFIG.get(symbol, PAIR_CONFIG["_DEFAULT"])


class StrategyEngine:
    """Motor de estrategia Momentum ICT v8.1 — Seguir direccion, 1:1 R:R, XAUUSD M1."""

    def __init__(self, data_feed: DataFeed):
        self.data_feed = data_feed
        self.params = STRATEGY
        self.last_signal_time = {}
        self.last_sweep_time = {}

    # ═══════════════════════════════════════════════════════════
    #  ANALISIS PRINCIPAL
    # ═══════════════════════════════════════════════════════════

    def analyze(self, symbol: str):
        """Analiza un par con estrategia Momentum ICT (soporta M1 y M15)."""
        pc = get_pair_config(symbol)

        # Filtro 1: Sesion activa
        if not self._is_session_active(symbol):
            return None

        # Filtro 2: Killzone ICT
        if not self._is_killzone_active(symbol):
            return None

        # Obtener datos con timeframe del par
        timeframe = pc["timeframe"]
        num_candles = 200 if timeframe == "M1" else 100  # Mas velas para M1

        df = self.data_feed.get_ohlc(symbol, num_candles=num_candles, timeframe=timeframe)
        if df is None or len(df) < 50:
            return None

        # Filtro 3: Spread bajo (limite por par)
        spread = self.data_feed.get_current_spread(symbol) if hasattr(self.data_feed, 'get_current_spread') else None
        if spread is not None and spread > pc["spread_limit"]:
            return None

        # Filtro 4: Cooldown entre señales
        if not self._check_signal_cooldown(symbol, pc["cooldown"]):
            return None

        # Detectar direccion del momentum (con params del par)
        direction = self._detect_momentum(symbol, df, pc)
        if direction is None:
            return None

        # Evaluar condiciones de entrada
        result = self._evaluate_entry(symbol, df, direction, pc)
        if result is None or not result.get("passed"):
            return None

        # FVG Detection (bonus)
        fvg = self._detect_fvg(symbol, df, direction)
        if fvg:
            result["fvg"] = fvg
            result["conditions"]["fvg"] = {
                "passed": True,
                "detail": f"FVG: {fvg['type']} ({fvg['size_pips']:.1f} pips)"
            }
            result["score"] = result.get("score", 0) + 1
            result["max_score"] = result.get("max_score", 4) + 1

        # Order Block Detection (bonus)
        ob = self._detect_order_block(symbol, df, direction)
        if ob:
            result["order_block"] = ob
            result["conditions"]["order_block"] = {
                "passed": True,
                "detail": f"OB: {ob['type']} @ {ob['level']:.5f}"
            }
            result["score"] = result.get("score", 0) + 1
            result["max_score"] = result.get("max_score", 4) + 1

        # Completar resultado
        result["symbol"] = symbol
        result["timestamp"] = datetime.now().isoformat()
        result["current_price"] = df.iloc[-1]['close']
        result["market_mode"] = "MOMENTUM"
        result["timeframe"] = timeframe
        self.last_signal_time[symbol] = datetime.now()

        logger.debug(f"[{symbol}] Momentum {direction} ({timeframe}) — Score: {result['score']}/{result['max_score']}")
        return result

    # ═══════════════════════════════════════════════════════════
    #  DETECCION DE MOMENTUM (4 indicadores)
    # ═══════════════════════════════════════════════════════════

    def _detect_momentum(self, symbol: str, df: pd.DataFrame, pc: dict) -> str:
        """Detecta direccion del momentum con params adaptados al par/timeframe."""
        pip_value = self.params.get("pip_values", {}).get(symbol, 0.0001)

        # Usar EMA del par (XAUUSD=10/25, Forex=20/50)
        ema_fast = df['close'].ewm(span=pc["ema_fast"], adjust=False).mean()
        ema_slow = df['close'].ewm(span=pc["ema_slow"], adjust=False).mean()
        ema_bullish = ema_fast.iloc[-1] > ema_slow.iloc[-1]
        ema_bearish = ema_fast.iloc[-1] < ema_slow.iloc[-1]

        # Pendiente EMA (5 velas)
        ema_slope = (ema_fast.iloc[-1] - ema_fast.iloc[-5]) / pip_value
        slope_up = ema_slope > pc["min_slope"]
        slope_down = ema_slope < -pc["min_slope"]

        # Cambio de precio (5 velas)
        lookback = min(6, len(df) - 1)
        price_change = (df.iloc[-1]['close'] - df.iloc[-lookback]['close']) / pip_value
        price_up = price_change > pc["min_price_change"]
        price_down = price_change < -pc["min_price_change"]

        # Estructura de precio (HH/HL o LH/LL)
        recent = df.iloc[-5:]
        hh_hl = recent['high'].iloc[-1] > recent['high'].iloc[-3] and recent['low'].iloc[-1] > recent['low'].iloc[-3]
        lh_ll = recent['high'].iloc[-1] < recent['high'].iloc[-3] and recent['low'].iloc[-1] < recent['low'].iloc[-3]

        # Puntuacion
        threshold = pc["momentum_threshold"]
        up_score = (1 if ema_bullish else 0) + (1 if slope_up else 0) + (1 if price_up else 0) + (1 if hh_hl else 0)
        down_score = (1 if ema_bearish else 0) + (1 if slope_down else 0) + (1 if price_down else 0) + (1 if lh_ll else 0)

        if up_score >= threshold and up_score > down_score:
            return "LONG"
        elif down_score >= threshold and down_score > up_score:
            return "SHORT"

        return None

    # ═══════════════════════════════════════════════════════════
    #  EVALUACION DE ENTRADA (4 condiciones ICT)
    # ═══════════════════════════════════════════════════════════

    def _evaluate_entry(self, symbol: str, df: pd.DataFrame, direction: str, pc: dict):
        """Evalua 4 condiciones con params adaptados al par."""
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

        # ── C2: Sweep de liquidez (BONUS) ──
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

        # ── C4: Cierre fuerte ──
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

        # ── SL/TP dinamico via ATR (1:1 R:R) adaptado al par ──
        atr = self._calculate_atr(df, pc["atr_period"])
        atr_pips = atr / pip_value
        sl_pips = max(pc["sl_min"], min(pc["sl_max"], round(atr_pips * pc["atr_multiplier"], 1)))
        tp_pips = sl_pips  # 1:1 exacto

        min_score = pc["score_min"]

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
    #  ATR para SL/TP dinamico
    # ═══════════════════════════════════════════════════════════

    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        """Calcula ATR para SL/TP adaptado a volatilidad."""
        recent = df.iloc[-period:]
        if len(recent) < 2:
            return 0.001
        trs = []
        for i in range(1, len(recent)):
            h = recent['high'].iloc[i]
            l = recent['low'].iloc[i]
            pc = recent['close'].iloc[i - 1]
            tr = max(h - l, abs(h - pc), abs(l - pc))
            trs.append(tr)
        return np.mean(trs)

    # ═══════════════════════════════════════════════════════════
    #  KILLZONES ICT (13 horas cobertura)
    # ═══════════════════════════════════════════════════════════

    def _is_killzone_active(self, symbol: str) -> bool:
        """Killzones ampliadas — XAUUSD opera en killzone extendida."""
        from datetime import datetime as dt
        import pytz

        now_utc = dt.now(pytz.utc)
        current_hour = now_utc.hour
        day = now_utc.weekday()

        if day >= 5:
            return False

        if symbol == "XAUUSD":
            # XAUUSD: killzone extendida 5-20 UTC (15 horas)
            # Oro se mueve bien en sesion asiatica tambien
            zones = [
                ("Asian+London", 5, 10),
                ("London Open", 7, 12),
                ("NY Open Premium", 12, 17),
                ("London Close+", 15, 20),
            ]
        else:
            # Forex majors: killzones normales
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
    #  FVG DETECTION (Bonus)
    # ═══════════════════════════════════════════════════════════

    def _detect_fvg(self, symbol: str, df: pd.DataFrame, direction: str) -> dict:
        """Detecta Fair Value Gaps."""
        if direction is None or len(df) < 5:
            return None
        pip_value = self.params.get("pip_values", {}).get(symbol, 0.0001)
        digits = self.params.get("digits", {}).get(symbol, 5)
        fvg_min_pips = self.params.get("fvg_min_pips", 3)

        for i in range(-10, -2):
            c1 = df.iloc[i]
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
                            return {"type": "BULLISH", "top": round(gap_top, digits), "bottom": round(gap_bottom, digits), "size_pips": round(gap_pips, 1), "candle_index": i}
            elif direction == "SHORT":
                gap_top = c1['low']
                gap_bottom = c3['high']
                gap_size = gap_top - gap_bottom
                if gap_size > 0:
                    gap_pips = gap_size / pip_value
                    if gap_pips >= fvg_min_pips:
                        current_price = df.iloc[-1]['close']
                        if gap_bottom <= current_price <= gap_top:
                            return {"type": "BEARISH", "top": round(gap_top, digits), "bottom": round(gap_bottom, digits), "size_pips": round(gap_pips, 1), "candle_index": i}
        return None

    # ═══════════════════════════════════════════════════════════
    #  ORDER BLOCK DETECTION (Bonus)
    # ═══════════════════════════════════════════════════════════

    def _detect_order_block(self, symbol: str, df: pd.DataFrame, direction: str) -> dict:
        """Detecta Order Blocks ICT."""
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
                        if dist <= 15:
                            return {"type": "BULLISH_OB", "level": round(ob_level, digits), "top": round(body_top, digits), "body_pips": round(body_size / pip_value, 1), "dist_to_price": round(dist, 1)}
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
                        if dist <= 15:
                            return {"type": "BEARISH_OB", "level": round(ob_level, digits), "bottom": round(body_bottom, digits), "body_pips": round(body_size / pip_value, 1), "dist_to_price": round(dist, 1)}
                    break
        return None

    # ═══════════════════════════════════════════════════════════
    #  SWEEP DETECTION (alertas)
    # ═══════════════════════════════════════════════════════════

    def detect_sweep(self, symbol: str):
        """Detecta sweep para alertas tempranas."""
        if not self._is_session_active(symbol) or not self._is_killzone_active(symbol):
            return None
        if not self._check_sweep_cooldown(symbol):
            return None

        pc = get_pair_config(symbol)
        timeframe = pc["timeframe"]
        df = self.data_feed.get_ohlc(symbol, num_candles=100, timeframe=timeframe)
        if df is None or len(df) < 50:
            return None

        direction = self._detect_momentum(symbol, df, pc)
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
        """XAUUSD siempre activo en sesion (24h market)."""
        if symbol == "XAUUSD":
            from datetime import datetime as dt
            import pytz
            now_utc = dt.now(pytz.utc)
            # Solo descansar sabado completo
            if now_utc.weekday() == 5 and now_utc.hour >= 21:
                return False
            if now_utc.weekday() == 6 and now_utc.hour < 21:
                return False
            return True
        from datetime import datetime as dt
        import pytz
        now_utc = dt.now(pytz.utc)
        h = now_utc.hour
        for sn in PAIR_SESSIONS.get(symbol, ["london", "new_york"]):
            s = SESSIONS.get(sn)
            if s and s["start"] <= h < s["end"]:
                return True
        return False

    def _check_signal_cooldown(self, symbol: str, cooldown: int = 120) -> bool:
        """Cooldown entre señales."""
        if symbol in self.last_signal_time:
            return (datetime.now() - self.last_signal_time[symbol]).total_seconds() >= cooldown
        return True

    def _check_sweep_cooldown(self, symbol: str) -> bool:
        """Cooldown de 5 minutos entre alerts de sweep."""
        if symbol in self.last_sweep_time:
            return (datetime.now() - self.last_sweep_time[symbol]).total_seconds() >= 300
        return True
