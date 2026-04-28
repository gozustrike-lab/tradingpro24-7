# ═══════════════════════════════════════════════════════════════
#  TRADINGPRO24-7 — STRATEGY ENGINE v8.2 MOMENTUM ICT + MTF
#  ═══ MULTI-TIMEFRAME para XAUUSD ═══
#  ═══ M5 confirma direccion → M1 busca entrada ═══
#  ═══ Forex: M15 directo (no necesita MTF) ═══
#  ═══ Precision maxima: cero senales falsas ═══
# ═══════════════════════════════════════════════════════════════

import pandas as pd
import numpy as np
import logging
from datetime import datetime
import pytz

from config import STRATEGY, PAIR_SESSIONS, SESSIONS
from data_feed import DataFeed

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
#  CONFIGURACION POR PAR
# ═══════════════════════════════════════════════════════════════

PAIR_CONFIG = {
    "XAUUSD": {
        "timeframe": "M1",          # Entrada en M1
        "mtf_timeframe": "M5",      # Direccion en M5
        "ema_fast": 10,
        "ema_slow": 25,
        "mtf_ema_fast": 10,
        "mtf_ema_slow": 25,
        "atr_period": 10,
        "atr_multiplier": 1.8,
        "sl_min": 20.0,
        "sl_max": 35.0,
        "spread_limit": 5.0,
        "cooldown": 60,
        "score_min": 2,
        "momentum_threshold": 2,    # 2/4 para M1 (mas senales)
        "mtf_threshold": 2,         # 2/4 para confirmar M5
    },
    "_DEFAULT": {
        "timeframe": "M15",
        "mtf_timeframe": None,       # Forex no usa MTF
        "ema_fast": 20,
        "ema_slow": 50,
        "mtf_ema_fast": 20,
        "mtf_ema_slow": 50,
        "atr_period": 14,
        "atr_multiplier": 1.2,
        "sl_min": 12.0,
        "sl_max": 22.0,
        "spread_limit": 3.0,
        "cooldown": 120,
        "score_min": 2,
        "momentum_threshold": 2,
        "mtf_threshold": 2,
    },
}


def get_pair_config(symbol: str) -> dict:
    return PAIR_CONFIG.get(symbol, PAIR_CONFIG["_DEFAULT"])


class StrategyEngine:
    """Motor de estrategia v8.2 — Momentum ICT + Multi-Timeframe."""

    def __init__(self, data_feed: DataFeed):
        self.data_feed = data_feed
        self.params = STRATEGY
        self.last_signal_time = {}
        self.last_sweep_time = {}

    # ═══════════════════════════════════════════════════════════
    #  ANALISIS PRINCIPAL
    # ═══════════════════════════════════════════════════════════

    def analyze(self, symbol: str):
        """Analiza un par — XAUUSD usa MTF (M5+M1), Forex usa M15."""
        pc = get_pair_config(symbol)

        if not self._is_session_active(symbol):
            return None
        if not self._is_killzone_active(symbol):
            return None

        # ── PASO 1: Confirmar direccion en timeframe superior (MTF) ──
        mtf_direction = None
        mtf_score = 0
        mtf_timeframe = pc.get("mtf_timeframe")

        if mtf_timeframe:
            mtf_direction, mtf_score = self._check_mtf_direction(symbol, pc)
            if mtf_direction is None:
                logger.debug("[{}] MTF ({}) sin direccion clara — sin senal".format(symbol, mtf_timeframe))
                return None
            logger.debug("[{}] MTF ({}) confirma: {} ({}/4)".format(symbol, mtf_timeframe, mtf_direction, mtf_score))

        # ── PASO 2: Obtener datos del timeframe de entrada ──
        timeframe = pc["timeframe"]
        num_candles = 200 if timeframe == "M1" else 100

        df = self.data_feed.get_ohlc(symbol, num_candles=num_candles, timeframe=timeframe)
        if df is None or len(df) < 50:
            return None

        spread = self.data_feed.get_current_spread(symbol) if hasattr(self.data_feed, 'get_current_spread') else None
        if spread is not None and spread > pc["spread_limit"]:
            return None

        if not self._check_signal_cooldown(symbol, pc["cooldown"]):
            return None

        # ── PASO 3: Detectar momentum en timeframe de entrada ──
        entry_direction = self._detect_momentum(symbol, df, pc)

        # ── PASO 4: CRITICO — La entrada debe coincidir con MTF ──
        if mtf_direction and entry_direction:
            if mtf_direction != entry_direction:
                logger.debug("[{}] MTF={} pero M1={} — CONFLICTO, ignorar".format(
                    symbol, mtf_direction, entry_direction))
                return None
            # Coinciden! Usar la direccion MTF (mas fuerte)
            direction = mtf_direction
        elif mtf_direction:
            # MTF confirma pero M1 no tiene momentum claro aun
            direction = None
        else:
            # Forex sin MTF — usar momentum directo
            direction = entry_direction

        if direction is None:
            return None

        # ── PASO 5: Evaluar condiciones de entrada ──
        result = self._evaluate_entry(symbol, df, direction, pc)
        if result is None or not result.get("passed"):
            return None

        # Agregar info MTF al resultado
        if mtf_direction:
            result["mtf_direction"] = mtf_direction
            result["mtf_score"] = mtf_score
            result["mtf_timeframe"] = mtf_timeframe
            result["conditions"]["mtf_confirm"] = {
                "passed": True,
                "detail": "M5 confirma {} ({}/4)".format(mtf_direction, mtf_score)
            }

        # Completar resultado
        result["symbol"] = symbol
        result["timestamp"] = datetime.now().isoformat()
        result["current_price"] = df.iloc[-1]['close']
        result["market_mode"] = "MOMENTUM"
        result["timeframe"] = timeframe
        self.last_signal_time[symbol] = datetime.now()

        logger.info("[{}] SENAL {} (M1 entrada, M5 direccion) — Score: {}/{}".format(
            symbol, direction, result["score"], result["max_score"]))
        return result

    # ═══════════════════════════════════════════════════════════
    #  MULTI-TIMEFRAME — M5 confirma direccion para XAUUSD
    # ═══════════════════════════════════════════════════════════

    def _check_mtf_direction(self, symbol: str, pc: dict):
        """
        Verifica la direccion en el timeframe superior (M5 para XAUUSD).
        Retorna (direction, score) o (None, 0) si no hay direccion clara.
        """
        mtf_tf = pc["mtf_timeframe"]
        if not mtf_tf:
            return None, 0

        try:
            df_mtf = self.data_feed.get_ohlc(symbol, num_candles=100, timeframe=mtf_tf)
            if df_mtf is None or len(df_mtf) < 50:
                return None, 0

            pip_value = self.params.get("pip_values", {}).get(symbol, 0.0001)

            # EMAs en M5
            ema_fast = df_mtf['close'].ewm(span=pc["mtf_ema_fast"], adjust=False).mean()
            ema_slow = df_mtf['close'].ewm(span=pc["mtf_ema_slow"], adjust=False).mean()
            ema_bullish = ema_fast.iloc[-1] > ema_slow.iloc[-1]
            ema_bearish = ema_fast.iloc[-1] < ema_slow.iloc[-1]

            # Pendiente EMA M5
            mtf_slope = (ema_fast.iloc[-1] - ema_fast.iloc[-5]) / pip_value
            slope_up = mtf_slope > 2.0
            slope_down = mtf_slope < -2.0

            # Precio M5
            mtf_price_change = (df_mtf.iloc[-1]['close'] - df_mtf.iloc[-6]['close']) / pip_value
            price_up = mtf_price_change > 5.0
            price_down = mtf_price_change < -5.0

            # Estructura HH/HL M5
            rh = df_mtf['high'].iloc[-10:]
            rl = df_mtf['low'].iloc[-10:]
            hh_hl = rh.iloc[-1] > rh.iloc[-3] and rl.iloc[-1] > rl.iloc[-3]
            lh_ll = rh.iloc[-1] < rh.iloc[-3] and rl.iloc[-1] < rl.iloc[-3]

            # Score MTF
            up_score = (1 if ema_bullish else 0) + (1 if slope_up else 0) + (1 if price_up else 0) + (1 if hh_hl else 0)
            down_score = (1 if ema_bearish else 0) + (1 if slope_down else 0) + (1 if price_down else 0) + (1 if lh_ll else 0)

            threshold = pc.get("mtf_threshold", 2)

            if up_score >= threshold and up_score > down_score:
                return "LONG", up_score
            elif down_score >= threshold and down_score > up_score:
                return "SHORT", down_score

            return None, 0

        except Exception as e:
            logger.error("Error MTF {}: {}".format(symbol, e))
            return None, 0

    # ═══════════════════════════════════════════════════════════
    #  DETECCION DE MOMENTUM (4 indicadores en TF de entrada)
    # ═══════════════════════════════════════════════════════════

    def _detect_momentum(self, symbol: str, df: pd.DataFrame, pc: dict) -> str:
        pip_value = self.params.get("pip_values", {}).get(symbol, 0.0001)

        ema_fast = df['close'].ewm(span=pc["ema_fast"], adjust=False).mean()
        ema_slow = df['close'].ewm(span=pc["ema_slow"], adjust=False).mean()
        ema_bullish = ema_fast.iloc[-1] > ema_slow.iloc[-1]
        ema_bearish = ema_fast.iloc[-1] < ema_slow.iloc[-1]

        ema_slope = (ema_fast.iloc[-1] - ema_fast.iloc[-5]) / pip_value
        slope_up = ema_slope > 1.0
        slope_down = ema_slope < -1.0

        lookback = min(6, len(df) - 1)
        price_change = (df.iloc[-1]['close'] - df.iloc[-lookback]['close']) / pip_value
        price_up = price_change > 3.0
        price_down = price_change < -3.0

        recent = df.iloc[-5:]
        hh_hl = recent['high'].iloc[-1] > recent['high'].iloc[-3] and recent['low'].iloc[-1] > recent['low'].iloc[-3]
        lh_ll = recent['high'].iloc[-1] < recent['high'].iloc[-3] and recent['low'].iloc[-1] < recent['low'].iloc[-3]

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
        pip_value = self.params.get("pip_values", {}).get(symbol, 0.0001)
        digits = self.params.get("digits", {}).get(symbol, 5)
        current = df.iloc[-1]

        score = 0
        conditions = {}

        # C1: Pullback en direccion del momentum
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
            "detail": "Pullback {:.1f} pips vs {}".format(change_pips, direction)
        }
        if is_pullback:
            score += 1

        # C2: Sweep de liquidez
        lb = 15
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
            "detail": "Sweep {:.1f} pips".format(max(sweep, 0)) + (" +RECHAZO" if rejection and sweep > 0 else "")
        }
        if sweep > 0:
            score += 1

        # C3: Mecha de rechazo
        cr = current['high'] - current['low']
        uw = current['high'] - max(current['open'], current['close'])
        lw = min(current['open'], current['close']) - current['low']
        wick_min_pips = 2.0
        wick_ratio_min = 1.0

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
            "detail": "Mecha {} {:.1f}x ({:.1f} pips)".format("inf" if direction == "LONG" else "sup", wick_ratio, wick_pips)
        }
        if has_wick:
            score += 1

        # C4: Cierre fuerte
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
            "detail": "Cierre en {:.1f}% del rango".format(close_pct)
        }
        if strong_close:
            score += 1

        # SL/TP via ATR (1:1 R:R)
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
    #  KILLZONES ICT
    # ═══════════════════════════════════════════════════════════

    def _is_killzone_active(self, symbol: str) -> bool:
        now_utc = datetime.now(pytz.utc)
        current_hour = now_utc.hour
        day = now_utc.weekday()

        if day >= 5:
            return False

        if symbol == "XAUUSD":
            zones = [
                ("Asian+London", 5, 10),
                ("London Open", 7, 12),
                ("NY Open", 12, 17),
                ("London Close", 15, 20),
            ]
        else:
            zones = [
                ("London+NY", 6, 12),
                ("NY Open", 12, 17),
                ("London Close", 15, 19),
            ]

        for zone_name, start, end in zones:
            if start <= current_hour < end:
                return True
        return False

    # ═══════════════════════════════════════════════════════════
    #  UTILIDADES
    # ═══════════════════════════════════════════════════════════

    def _is_session_active(self, symbol: str) -> bool:
        if symbol == "XAUUSD":
            now_utc = datetime.now(pytz.utc)
            if now_utc.weekday() == 5 and now_utc.hour >= 21:
                return False
            if now_utc.weekday() == 6 and now_utc.hour < 21:
                return False
            return True
        now_utc = datetime.now(pytz.utc)
        h = now_utc.hour
        for sn in PAIR_SESSIONS.get(symbol, ["london", "new_york"]):
            s = SESSIONS.get(sn)
            if s and s["start"] <= h < s["end"]:
                return True
        return False

    def _check_signal_cooldown(self, symbol: str, cooldown: int = 120) -> bool:
        if symbol in self.last_signal_time:
            return (datetime.now() - self.last_signal_time[symbol]).total_seconds() >= cooldown
        return True

    def _check_sweep_cooldown(self, symbol: str) -> bool:
        if symbol in self.last_sweep_time:
            return (datetime.now() - self.last_sweep_time[symbol]).total_seconds() >= 300
        return True

    def detect_sweep(self, symbol: str):
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
        lb = 15

        if direction == "LONG":
            pl = df['low'].iloc[-lb:-3].min()
            sp = (pl - c['low']) / pip_value
            if sp > 0 and c['close'] > pl:
                self.last_sweep_time[symbol] = datetime.now()
                return {"symbol": symbol, "direction": direction, "sweep_level": round(pl, digits), "current_price": round(c['close'], digits), "sweep_pips": round(sp, 1)}
        else:
            ph = df['high'].iloc[-lb:-3].max()
            sp = (c['high'] - ph) / pip_value
            if sp > 0 and c['close'] < ph:
                self.last_sweep_time[symbol] = datetime.now()
                return {"symbol": symbol, "direction": direction, "sweep_level": round(ph, digits), "current_price": round(c['close'], digits), "sweep_pips": round(sp, 1)}
        return None
