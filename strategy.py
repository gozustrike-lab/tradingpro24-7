# ═══════════════════════════════════════════════════════════════
#  TRADING BOT HÍBRIDO — STRATEGY ENGINE
#  5 condiciones matemáticas OHLC + Scoring
# ═══════════════════════════════════════════════════════════════

import pandas as pd
import numpy as np
import logging
from datetime import datetime

from config import STRATEGY, PAIR_SESSIONS, SESSIONS
from data_feed import DataFeed

logger = logging.getLogger(__name__)


class StrategyEngine:
    """Motor de estrategia ICT Liquidity Sweep con filtros OHLC."""

    def __init__(self, data_feed: DataFeed):
        self.data_feed = data_feed
        self.params = STRATEGY
        self.last_signal_time = {}  # Evitar señales duplicadas

    def analyze(self, symbol: str):
        """
        Analiza un par buscando señales de Liquidity Sweep.

        Returns:
            dict con señal o None si no hay oportunidad
        """
        # 1. Verificar sesión activa
        if not self._is_session_active(symbol):
            return None

        # 2. Obtener datos OHLC
        df = self.data_feed.get_ohlc(symbol, num_candles=100)
        if df is None or len(df) < 50:
            return None

        # 3. Verificar tiempo mínimo entre señales
        if not self._check_signal_cooldown(symbol):
            return None

        # 4. Ejecutar las 5 condiciones
        result = self._evaluate_conditions(symbol, df)

        if result:
            result["symbol"] = symbol
            result["timestamp"] = datetime.now().isoformat()
            result["current_price"] = df.iloc[-1]['close']
            self.last_signal_time[symbol] = datetime.now()

        return result

    def _evaluate_conditions(self, symbol: str, df: pd.DataFrame):
        """
        Evalúa las 5 condiciones matemáticas.

        Returns:
            dict con score, condiciones individuales, dirección
        """
        pip_value = self.params["pip_values"].get(symbol, 0.0001)
        digits = self.params["digits"].get(symbol, 5)

        # Datos actuales y anteriores
        current = df.iloc[-1]
        prev_1 = df.iloc[-2] if len(df) > 1 else None
        lookback = max(2, len(df) - self.params["lookback_candles"])
        prev_n = df.iloc[lookback] if len(df) > self.params["lookback_candles"] else df.iloc[2]

        score = 0
        conditions = {}

        # ─── CONDICIÓN 1: Tendencia (EMA 20 > EMA 50) ───
        ema_fast = df['close'].ewm(span=self.params["ema_fast"], adjust=False).mean()
        ema_slow = df['close'].ewm(span=self.params["ema_slow"], adjust=False).mean()

        uptrend = ema_fast.iloc[-1] > ema_slow.iloc[-1]
        downtrend = ema_fast.iloc[-1] < ema_slow.iloc[-1]

        conditions["trend"] = {
            "passed": uptrend or downtrend,
            "direction": "LONG" if uptrend else "SHORT",
            "ema_fast": round(ema_fast.iloc[-1], digits),
            "ema_slow": round(ema_slow.iloc[-1], digits),
            "detail": f"EMA{self.params['ema_fast']}>{self.params['ema_slow']}" if uptrend
                      else f"EMA{self.params['ema_fast']}<{self.params['ema_slow']}"
        }

        if uptrend or downtrend:
            score += 1
            direction = "LONG" if uptrend else "SHORT"
        else:
            direction = None

        # ─── CONDICIÓN 2: Pullback mínimo ───
        if prev_1 is not None:
            recent_highs = df['high'].iloc[-self.params["pullback_candles"]:]
            recent_lows = df['low'].iloc[-self.params["pullback_candles"]:]
            pullback = max(recent_highs) - min(recent_lows)
            pullback_pips = pullback / pip_value

            conditions["pullback"] = {
                "passed": pullback_pips >= self.params["pullback_min_pips"],
                "pullback_pips": round(pullback_pips, 1),
                "min_required": self.params["pullback_min_pips"],
                "detail": f"Pullback {pullback_pips:.1f} pips (min: {self.params['pullback_min_pips']})"
            }

            if pullback_pips >= self.params["pullback_min_pips"]:
                score += 1

        # ─── CONDICIÓN 3: Sweep de low/high previo ───
        tolerance_pips = self.params["sweep_pip_tolerance"]

        if direction == "LONG":
            # Buscar low previo que fue barrido
            prev_low = df['low'].iloc[-self.params["lookback_candles"]:-3].min()
            current_low = current['low']
            sweep_pips = (prev_low - current_low) / pip_value

            conditions["sweep"] = {
                "passed": sweep_pips >= -tolerance_pips,
                "sweep_pips": round(sweep_pips, 1),
                "prev_level": round(prev_low, digits),
                "current_level": round(current_low, digits),
                "detail": f"Sweep {sweep_pips:.1f} pips bajo low previo ({round(prev_low, digits)})"
            }
            if sweep_pips >= -tolerance_pips:
                score += 1

        elif direction == "SHORT":
            # Buscar high previo que fue barrido
            prev_high = df['high'].iloc[-self.params["lookback_candles"]:-3].max()
            current_high = current['high']
            sweep_pips = (current_high - prev_high) / pip_value

            conditions["sweep"] = {
                "passed": sweep_pips >= -tolerance_pips,
                "sweep_pips": round(sweep_pips, 1),
                "prev_level": round(prev_high, digits),
                "current_level": round(current_high, digits),
                "detail": f"Sweep {sweep_pips:.1f} pips sobre high previo ({round(prev_high, digits)})"
            }
            if sweep_pips >= -tolerance_pips:
                score += 1

        else:
            conditions["sweep"] = {"passed": False, "detail": "Sin tendencia definida"}

        # ─── CONDICIÓN 4: Mechá de rechazo ───
        candle_range = current['high'] - current['low']
        upper_wick = current['high'] - max(current['open'], current['close'])
        lower_wick = min(current['open'], current['close']) - current['low']

        if direction == "LONG" and candle_range > 0:
            wick_ratio = lower_wick / upper_wick if upper_wick > 0 else 10.0
            conditions["rejection_wick"] = {
                "passed": wick_ratio >= self.params["wick_ratio_min"],
                "wick_ratio": round(wick_ratio, 2),
                "lower_wick_pips": round(lower_wick / pip_value, 1),
                "upper_wick_pips": round(upper_wick / pip_value, 1),
                "detail": f"Mecha inf {wick_ratio:.2f}x sup (min: {self.params['wick_ratio_min']}x)"
            }
            if wick_ratio >= self.params["wick_ratio_min"]:
                score += 1

        elif direction == "SHORT" and candle_range > 0:
            wick_ratio = upper_wick / lower_wick if lower_wick > 0 else 10.0
            conditions["rejection_wick"] = {
                "passed": wick_ratio >= self.params["wick_ratio_min"],
                "wick_ratio": round(wick_ratio, 2),
                "lower_wick_pips": round(lower_wick / pip_value, 1),
                "upper_wick_pips": round(upper_wick / pip_value, 1),
                "detail": f"Mecha sup {wick_ratio:.2f}x inf (min: {self.params['wick_ratio_min']}x)"
            }
            if wick_ratio >= self.params["wick_ratio_min"]:
                score += 1

        else:
            conditions["rejection_wick"] = {"passed": False, "detail": "Sin dirección"}

        # ─── CONDICIÓN 5: Cierre en porcentaje favorable ───
        if candle_range > 0:
            if direction == "LONG":
                close_position = (current['close'] - current['low']) / candle_range * 100
                conditions["close_position"] = {
                    "passed": close_position >= self.params["close_percentile"],
                    "close_position": round(close_position, 1),
                    "required": self.params["close_percentile"],
                    "detail": f"Cierre en {close_position:.1f}% del rango (min: {self.params['close_percentile']}%)"
                }
                if close_position >= self.params["close_percentile"]:
                    score += 1

            elif direction == "SHORT":
                close_position = (current['high'] - current['close']) / candle_range * 100
                conditions["close_position"] = {
                    "passed": close_position >= self.params["close_percentile"],
                    "close_position": round(close_position, 1),
                    "required": self.params["close_percentile"],
                    "detail": f"Cierre en {close_position:.1f}% del rango (min: {self.params['close_percentile']}%)"
                }
                if close_position >= self.params["close_percentile"]:
                    score += 1
        else:
            conditions["close_position"] = {"passed": False, "detail": "Vela sin rango"}

        # ─── RESULTADO FINAL ───
        passed = score >= self.params["min_score"]

        return {
            "signal": "BUY" if direction == "LONG" else ("SELL" if direction == "SHORT" else None),
            "score": score,
            "max_score": 5,
            "passed": passed,
            "conditions": conditions,
            "direction": direction,
            "needs_ai_confirmation": passed,
        }

    def _is_session_active(self, symbol: str) -> bool:
        """Verifica si el par está en su sesión de trading activa."""
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
        """Verifica que no se envíe otra señal muy pronto para el mismo par."""
        from config import BOT
        min_interval = BOT["min_timeframe_between_signals"]

        if symbol in self.last_signal_time:
            elapsed = (datetime.now() - self.last_signal_time[symbol]).total_seconds()
            return elapsed >= min_interval

        return True
