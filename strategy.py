# ═══════════════════════════════════════════════════════════════
#  TRADINGPRO24-7 — STRATEGY ENGINE v8.4 ICT PRO
#  ═══ S/R AUTOMATICO + S/R FLIP + PULLBACK ENTRY ═══
#  ═══ Deteccion de mercado: ALCISTA / BAJISTA / LATERAL ═══
#  ═══ PATTERN RECOGNITION: Ondas/Montañitas ═══
#  ═══ Repeticiones de patron + Agotamiento + Impulsivo ═══
#  ═══ MTF: M5 direccion + M1 entrada ═══
#  ═══════════════════════════════════════════════════════════════
#
#  CONCEPTO CLAVE v8.4:
#  1. El mercado repite 2-4 veces el mismo patron de ondas
#  2. Bot detecta cuantas "montañitas" se han formado
#  3. Si un patron se repite 2-3 veces → es probable que continue
#  4. Si la 4ta onda FALLA (no supera la anterior) → AGOTAMIENTO
#  5. Movimientos impulsivos (caida/subida rapida) = fuerte tendencia
#  6. Movimientos correctivos (rebote pequeño) = contrarios a tendencia
#  7. Combina ondas + S/R + Flip para entradas de alta precision
#
#  PATRONES DETECTADOS:
#  - REPETICION: mismo patron 2-4 veces → entradas a favor
#  - AGOTAMIENTO: 4ta onda no supera la anterior → inversion
#  - IMPULSIVO: movimiento fuerte + correccion debil → continuar
#  - CORRECTIVO: movimiento debil + correccion fuerte → rango
#
# ═══════════════════════════════════════════════════════════════

import pandas as pd
import numpy as np
import logging
from datetime import datetime
import pytz

from config import STRATEGY, PAIR_SESSIONS, SESSIONS
from data_feed import DataFeed

logger = logging.getLogger(__name__)

# ─── Config por par ──────────────────────────────────────────
PAIR_CONFIG = {
    "XAUUSD": {
        "timeframe": "M1",
        "mtf_timeframe": "M5",
        "ema_fast": 10, "ema_slow": 25,
        "mtf_ema_fast": 10, "mtf_ema_slow": 25,
        "atr_period": 10, "atr_multiplier": 1.8,
        "sl_min": 20.0, "sl_max": 35.0,
        "spread_limit": 5.0,
        "cooldown": 45,
        "sr_lookback": 50,
        "sr_touches": 2,
        "sr_zone_pips": 3.0,
        "pullback_zone_pips": 5,
        # v8.4: Pattern Recognition config
        "wave_lookback": 80,        # Velas para analizar ondas
        "wave_swing_min": 3,        # Minimo pips para considerar un swing
        "exhaustion_wave": 4,       # Onda de agotamiento (4ta)
        "impulse_ratio": 2.0,       # Impulso debe ser 2x mas grande que correccion
    },
    "_DEFAULT": {
        "timeframe": "M15",
        "mtf_timeframe": None,
        "ema_fast": 20, "ema_slow": 50,
        "mtf_ema_fast": 20, "mtf_ema_slow": 50,
        "atr_period": 14, "atr_multiplier": 1.2,
        "sl_min": 12.0, "sl_max": 22.0,
        "spread_limit": 3.0,
        "cooldown": 90,
        "sr_lookback": 50,
        "sr_touches": 2,
        "sr_zone_pips": 2.0,
        "pullback_zone_pips": 3,
        "wave_lookback": 60,
        "wave_swing_min": 2,
        "exhaustion_wave": 4,
        "impulse_ratio": 2.0,
    },
}


def get_pair_config(symbol: str) -> dict:
    return PAIR_CONFIG.get(symbol, PAIR_CONFIG["_DEFAULT"])


class StrategyEngine:
    """Motor v8.4 — S/R + Flip + Ondas + Mercado Adaptativo + Pattern Repetition."""

    def __init__(self, data_feed: DataFeed):
        self.data_feed = data_feed
        self.params = STRATEGY
        self.last_signal_time = {}

    # ═══════════════════════════════════════════════════════════
    #  ANALISIS PRINCIPAL — 7 PASOS
    # ═══════════════════════════════════════════════════════════

    def analyze(self, symbol: str):
        pc = get_pair_config(symbol)

        # PASO 0: Sesion y killzone activos
        if not self._is_session_active(symbol):
            return None
        if not self._is_killzone_active(symbol):
            return None

        # PASO 1: Detectar condicion del mercado
        market_condition = "NORMAL"
        mtf_direction = None
        mtf_score = 0
        mtf_timeframe = pc.get("mtf_timeframe")

        if mtf_timeframe:
            mtf_direction, mtf_score, market_condition = self._check_mtf_condition(symbol, pc)
            logger.info("[{}] MTF: {} | Mercado: {} | Score: {}".format(
                symbol, mtf_direction or "NEUTRO", market_condition, mtf_score))

        # PASO 2: Obtener datos OHLC
        timeframe = pc["timeframe"]
        num_candles = 200 if timeframe == "M1" else 100

        df = self.data_feed.get_ohlc(symbol, num_candles=num_candles, timeframe=timeframe)
        if df is None or len(df) < 50:
            return None

        # Verificar spread
        spread = self.data_feed.get_current_spread(symbol) if hasattr(self.data_feed, 'get_current_spread') else None
        if spread is not None and spread > pc["spread_limit"]:
            return None

        # Cooldown
        if not self._check_signal_cooldown(symbol, pc["cooldown"]):
            return None

        pip_value = self.params.get("pip_values", {}).get(symbol, 0.0001)
        digits = self.params.get("digits", {}).get(symbol, 5)
        current = df.iloc[-1]
        current_price = current['close']

        # PASO 3: Detectar niveles S/R
        supports, resistances = self._detect_sr_levels(df, pip_value, pc)

        # PASO 4: Detectar S/R flips
        sr_flips = self._detect_sr_flips(df, supports, resistances, pip_value, pc)

        # PASO 5: PATTERN RECOGNITION — Analizar ondas/montañitas
        wave_pattern = self._analyze_wave_pattern(df, pip_value, pc)
        logger.info("[{}] Ondas: {} | Rep: {} | Tipo: {}".format(
            symbol,
            wave_pattern.get("wave_count", 0),
            wave_pattern.get("repetitions", 0),
            wave_pattern.get("pattern_type", "N/A")
        ))

        # PASO 6: Buscar entrada combinando ondas + S/R + mercado
        result = self._find_entry(symbol, df, current, market_condition,
                                   mtf_direction, supports, resistances, sr_flips,
                                   wave_pattern, pip_value, digits, pc)

        if result is None:
            return None

        # PASO 7: En tendencia, verificar direccion
        direction = result["direction"]
        if market_condition == "ALCISTA" and direction != "LONG":
            logger.info("[{}] Bloqueada: {} en mercado alcista".format(symbol, direction))
            return None
        if market_condition == "BAJISTA" and direction != "SHORT":
            logger.info("[{}] Bloqueada: {} en mercado bajista".format(symbol, direction))
            return None

        # Completar resultado
        result["symbol"] = symbol
        result["timestamp"] = datetime.now().isoformat()
        result["current_price"] = current_price
        result["timeframe"] = timeframe
        result["market_condition"] = market_condition

        # S/R levels para el grafico
        result["chart_levels"] = {
            "supports": [s["price"] for s in supports[:3]],
            "resistances": [r["price"] for r in resistances[:3]],
            "flips": [f["price"] for f in sr_flips[:2]],
        }

        # Wave pattern info
        result["wave_pattern"] = wave_pattern

        self.last_signal_time[symbol] = datetime.now()

        # Info MTF
        if mtf_direction:
            result["mtf_direction"] = mtf_direction
            result["mtf_timeframe"] = mtf_timeframe
            result["mtf_score"] = mtf_score

        logger.info("[{}] {} {} | Mercado:{} | Patron:{} | S/R:{:.2f} | Flip:{}".format(
            symbol, direction, result.get("sr_reason", ""),
            market_condition, wave_pattern.get("pattern_type", ""),
            result.get("sr_level", 0), result.get("sr_is_flip", False)))
        return result

    # ═══════════════════════════════════════════════════════════
    #  PATTERN RECOGNITION — ANALISIS DE ONDAS
    # ═══════════════════════════════════════════════════════════

    def _analyze_wave_pattern(self, df: pd.DataFrame, pip_value: float, pc: dict):
        """
        Analiza las ondas/montañitas del precio y detecta:
        - Cuantas ondas se han formado
        - Cuantas veces se repite el patron (2, 3, 4+)
        - Si la ultima onda muestra AGOTAMIENTO (4ta mas baja)
        - Si el movimiento es IMPULSIVO o CORRECTIVO
        - La estructura HH/HL o LH/LL

        Esto es lo que el usuario llamo "montañitas":
        - Cada "montaña" = un pico (swing high) + un valle (swing low)
        - Repeticion = cuantas montañas similares seguidas
        - Agotamiento = la 4ta montaña no supera la 3ra
        """
        lookback = pc.get("wave_lookback", 80)
        swing_min = pc.get("wave_swing_min", 3)
        exhaustion_num = pc.get("exhaustion_wave", 4)

        recent = df.iloc[-lookback:].copy()
        current_price = recent.iloc[-1]['close']

        # ── PASO 1: Extraer swings (picos y valles) ──
        swings = self._extract_swings(recent, pip_value, swing_min)

        if len(swings) < 4:
            return self._empty_wave_pattern()

        # ── PASO 2: Medir cada "montaña" (onda completa) ──
        # Una montaña = pico → valle (onda bajista) o valle → pico (onda alcista)
        waves_up = []    # Ondas alcistas (valle → pico)
        waves_down = []  # Ondas bajistas (pico → valle)

        for i in range(1, len(swings)):
            prev = swings[i - 1]
            curr = swings[i]
            height_pips = abs(curr["price"] - prev["price"]) / pip_value

            if curr["type"] == "HIGH":
                # Onda alcista: del valle anterior al pico actual
                waves_up.append({
                    "start_price": prev["price"],
                    "end_price": curr["price"],
                    "height_pips": height_pips,
                    "index": i,
                })
            else:
                # Onda bajista: del pico anterior al valle actual
                waves_down.append({
                    "start_price": prev["price"],
                    "end_price": curr["price"],
                    "height_pips": height_pips,
                    "index": i,
                })

        # ── PASO 3: Contar repeticiones del patron ──
        # El mercado repite 2-4 veces el mismo patron
        # Comparamos la altura de ondas consecutivas del mismo tipo
        pattern_type = "N/A"
        repetitions = 0
        exhaustion = False
        exhaustion_signal = None

        # Analizar ondas alcistas para detectar patron
        if len(waves_up) >= 3:
            # Comparar ultimas 3-4 ondas alcistas
            recent_up = waves_up[-4:] if len(waves_up) >= 4 else waves_up
            reps = self._count_similar_waves(recent_up)

            # Detectar patron alcista (montañitas hacia arriba = HH+HL)
            hh_count = 0  # Higher highs
            for i in range(1, len(recent_up)):
                if recent_up[i]["end_price"] > recent_up[i-1]["end_price"]:
                    hh_count += 1

            # Detectar AGOTAMIENTO: la 4ta onda no supera la 3ra
            if len(recent_up) >= 4:
                last = recent_up[-1]
                prev = recent_up[-2]
                prev2 = recent_up[-3]
                # La 4ta montaña es mas baja que la 3ra
                if last["end_price"] < prev["end_price"] and prev["end_price"] > prev2["end_price"]:
                    exhaustion = True
                    exhaustion_signal = "SHORT"  # Agotamiento alcista → buscar venta

            # Detectar patron bajista (montañitas hacia abajo = LH+LL)
            lh_count = 0  # Lower highs
            for i in range(1, len(recent_up)):
                if recent_up[i]["end_price"] < recent_up[i-1]["end_price"]:
                    lh_count += 1

            # Determinar patron dominante
            if hh_count >= 2 and not exhaustion:
                pattern_type = "REPETICION_ALCISTA"
                repetitions = hh_count + 1
            elif lh_count >= 2:
                pattern_type = "REPETICION_BAJISTA"
                repetitions = lh_count + 1
            elif reps >= 2:
                pattern_type = "REPETICION_RANGO"
                repetitions = reps

        # Analizar ondas bajistas para completar la imagen
        if len(waves_down) >= 3:
            recent_down = waves_down[-4:] if len(waves_down) >= 4 else waves_down
            reps_down = self._count_similar_waves(recent_down)

            # LL (Lower lows) en ondas bajistas
            ll_count = 0
            for i in range(1, len(recent_down)):
                if recent_down[i]["end_price"] < recent_down[i-1]["end_price"]:
                    ll_count += 1

            # Agotamiento bajista: 4ta caida no supera la 3ra
            if len(recent_down) >= 4:
                last_d = recent_down[-1]
                prev_d = recent_down[-2]
                prev2_d = recent_down[-3]
                if last_d["end_price"] > prev_d["end_price"] and prev_d["end_price"] < prev2_d["end_price"]:
                    exhaustion = True
                    exhaustion_signal = "LONG"  # Agotamiento bajista → buscar compra

            # Refinar patron
            if ll_count >= 2 and pattern_type == "N/A":
                pattern_type = "REPETICION_BAJISTA"
                repetitions = max(repetitions, ll_count + 1)

        # ── PASO 4: Detectar si es IMPULSIVO o CORRECTIVO ──
        move_type = "NEUTRAL"
        if len(waves_up) >= 2 and len(waves_down) >= 2:
            last_up = waves_up[-1]["height_pips"]
            last_down = waves_down[-1]["height_pips"]
            impulse_ratio = pc.get("impulse_ratio", 2.0)

            if last_up > 0 and last_down > 0:
                if last_up / last_down >= impulse_ratio:
                    move_type = "IMPULSIVO_ALCISTA"  # Subida fuerte, correccion debil
                elif last_down / last_up >= impulse_ratio:
                    move_type = "IMPULSIVO_BAJISTA"  # Caida fuerte, rebote debil
                else:
                    move_type = "RANGO"  # Subidas y bajadas similares

        # ── PASO 5: Predecir proximo movimiento ──
        prediction = None
        prediction_confidence = 0

        if exhaustion:
            # AGOTAMIENTO: el patron se rompe → operar en contra
            prediction = exhaustion_signal
            prediction_confidence = 75  # Alta confianza en agotamiento
            pattern_type = "AGOTAMIENTO_{}".format(exhaustion_signal)
        elif repetitions >= 3 and pattern_type != "N/A":
            # REPETICION 3+: el patron se repite → operar a favor
            if "ALCISTA" in pattern_type:
                prediction = "LONG"
                prediction_confidence = 70
            elif "BAJISTA" in pattern_type:
                prediction = "SHORT"
                prediction_confidence = 70
            elif "RANGO" in pattern_type:
                prediction = None  # En rango no predecimos direccion
                prediction_confidence = 40
        elif repetitions >= 2 and pattern_type != "N/A":
            # REPETICION 2: probable continuacion
            if "ALCISTA" in pattern_type:
                prediction = "LONG"
                prediction_confidence = 55
            elif "BAJISTA" in pattern_type:
                prediction = "SHORT"
                prediction_confidence = 55

        # ── PASO 6: Generar resumen para el grafico ──
        wave_summary = []
        for w in waves_up[-4:]:
            wave_summary.append({"type": "UP", "pips": round(w["height_pips"], 1)})
        for w in waves_down[-4:]:
            wave_summary.append({"type": "DOWN", "pips": round(w["height_pips"], 1)})
        wave_summary.sort(key=lambda x: 0, reverse=False)

        return {
            "wave_count": len(swings),
            "waves_up": len(waves_up),
            "waves_down": len(waves_down),
            "repetitions": min(repetitions, 5),
            "pattern_type": pattern_type,
            "exhaustion": exhaustion,
            "exhaustion_signal": exhaustion_signal,
            "move_type": move_type,
            "prediction": prediction,
            "prediction_confidence": prediction_confidence,
            "last_up_pips": waves_up[-1]["height_pips"] if waves_up else 0,
            "last_down_pips": waves_down[-1]["height_pips"] if waves_down else 0,
            "wave_summary": wave_summary[-8:],
            "swing_points": [(s["type"], s["price"]) for s in swings[-10:]],
        }

    def _extract_swings(self, df: pd.DataFrame, pip_value: float, swing_min_pips: float):
        """
        Extrae puntos de swing (picos y valles) del dataframe.
        Un swing se confirma cuando el precio cambia de direccion
        al menos swing_min_pips pips.
        """
        swings = []
        min_distance = swing_min_pips * pip_value

        # Buscar swing highs y swing lows
        lookback = len(df)
        for i in range(2, lookback - 2):
            candle = df.iloc[i]
            prev1 = df.iloc[i - 1]
            prev2 = df.iloc[i - 2]
            next1 = df.iloc[i + 1]
            next2 = df.iloc[i + 2]

            # Swing High
            if (candle['high'] >= prev1['high'] and candle['high'] >= prev2['high'] and
                candle['high'] >= next1['high'] and candle['high'] >= next2['high']):
                # Verificar que es significativo (no ruido)
                if swings:
                    last = swings[-1]
                    dist = abs(candle['high'] - last["price"]) / pip_value
                    if dist >= swing_min_pips or last["type"] != "HIGH":
                        swings.append({"type": "HIGH", "price": candle['high'], "index": i})
                else:
                    swings.append({"type": "HIGH", "price": candle['high'], "index": i})

            # Swing Low
            if (candle['low'] <= prev1['low'] and candle['low'] <= prev2['low'] and
                candle['low'] <= next1['low'] and candle['low'] <= next2['low']):
                if swings:
                    last = swings[-1]
                    dist = abs(candle['low'] - last["price"]) / pip_value
                    if dist >= swing_min_pips or last["type"] != "LOW":
                        swings.append({"type": "LOW", "price": candle['low'], "index": i})
                else:
                    swings.append({"type": "LOW", "price": candle['low'], "index": i})

        return swings

    def _count_similar_waves(self, waves: list) -> int:
        """
        Cuenta cuantas ondas consecutivas tienen altura similar.
        "Similar" = dentro del 50% de la altura promedio.
        """
        if len(waves) < 2:
            return 0

        heights = [w["height_pips"] for w in waves]
        avg_height = np.mean(heights)
        if avg_height == 0:
            return 0

        # Contar cuantas ondas son similares (dentro del 50% del promedio)
        tolerance = 0.5
        similar = 0
        for h in heights:
            if abs(h - avg_height) / avg_height <= tolerance:
                similar += 1

        return similar

    def _empty_wave_pattern(self):
        return {
            "wave_count": 0, "waves_up": 0, "waves_down": 0,
            "repetitions": 0, "pattern_type": "INSUFICIENTE",
            "exhaustion": False, "exhaustion_signal": None,
            "move_type": "NEUTRAL", "prediction": None,
            "prediction_confidence": 0, "last_up_pips": 0,
            "last_down_pips": 0, "wave_summary": [],
            "swing_points": [],
        }

    # ═══════════════════════════════════════════════════════════
    #  DETECCION DE CONDICION DE MERCADO
    # ═══════════════════════════════════════════════════════════

    def _check_mtf_condition(self, symbol: str, pc: dict):
        mtf_tf = pc["mtf_timeframe"]
        if not mtf_tf:
            return None, 0, "NORMAL"

        try:
            df_mtf = self.data_feed.get_ohlc(symbol, num_candles=100, timeframe=mtf_tf)
            if df_mtf is None or len(df_mtf) < 50:
                return None, 0, "NORMAL"

            pip_value = self.params.get("pip_values", {}).get(symbol, 0.0001)

            ema_fast = df_mtf['close'].ewm(span=pc["mtf_ema_fast"], adjust=False).mean()
            ema_slow = df_mtf['close'].ewm(span=pc["mtf_ema_slow"], adjust=False).mean()

            bullish_ema = ema_fast.iloc[-1] > ema_slow.iloc[-1]
            bearish_ema = ema_fast.iloc[-1] < ema_slow.iloc[-1]

            slope_fast = (ema_fast.iloc[-1] - ema_fast.iloc[-5]) / pip_value
            slope_up = slope_fast > 1.0
            slope_down = slope_fast < -1.0

            price_change = (df_mtf.iloc[-1]['close'] - df_mtf.iloc[-6]['close']) / pip_value
            price_up = price_change > 3.0
            price_down = price_change < -3.0

            recent_highs = df_mtf['high'].iloc[-15:]
            recent_lows = df_mtf['low'].iloc[-15:]
            hh_hl = (recent_highs.iloc[-1] > recent_highs.iloc[-5] and
                     recent_lows.iloc[-1] > recent_lows.iloc[-5])
            lh_ll = (recent_highs.iloc[-1] < recent_highs.iloc[-5] and
                     recent_lows.iloc[-1] < recent_lows.iloc[-5])

            up_score = (1 if bullish_ema else 0) + (1 if slope_up else 0) + \
                       (1 if price_up else 0) + (1 if hh_hl else 0)
            down_score = (1 if bearish_ema else 0) + (1 if slope_down else 0) + \
                         (1 if price_down else 0) + (1 if lh_ll else 0)

            range_20 = (df_mtf['high'].iloc[-20:].max() - df_mtf['low'].iloc[-20:].min()) / pip_value
            ema_distance = abs(ema_fast.iloc[-1] - ema_slow.iloc[-1]) / pip_value

            is_consolidating = (
                (up_score < 3 and down_score < 3) or
                abs(up_score - down_score) <= 1
            )
            is_flat_emas = ema_distance < 3.0
            is_low_volatility = range_20 < 25

            if is_consolidating and (is_flat_emas or is_low_volatility):
                return None, max(up_score, down_score), "LATERAL"
            if up_score >= 2 and up_score > down_score:
                return "LONG", up_score, "ALCISTA"
            if down_score >= 2 and down_score > up_score:
                return "SHORT", down_score, "BAJISTA"

            return None, max(up_score, down_score), "LATERAL"

        except Exception as e:
            logger.error("Error MTF {}: {}".format(symbol, e))
            return None, 0, "NORMAL"

    # ═══════════════════════════════════════════════════════════
    #  BUSCAR ENTRADA — CON ONDAS + S/R + MERCADO
    # ═══════════════════════════════════════════════════════════

    def _find_entry(self, symbol, df, current, market_condition,
                     mtf_direction, supports, resistances, sr_flips,
                     wave_pattern, pip_value, digits, pc):
        """
        Busca entrada combinando:
        1. Patron de ondas (repeticion/agotamiento/impulsivo)
        2. S/R levels y flips
        3. Condicion de mercado (alcista/bajista/lateral)
        """
        current_price = current['close']
        pullback_zone = pc.get("pullback_zone_pips", 5)
        wave_pred = wave_pattern.get("prediction")
        wave_conf = wave_pattern.get("prediction_confidence", 0)
        wave_type = wave_pattern.get("pattern_type", "")
        is_exhaustion = wave_pattern.get("exhaustion", False)
        exhaustion_signal = wave_pattern.get("exhaustion_signal")
        move_type = wave_pattern.get("move_type", "")

        # ═══ PRIORIDAD 0: AGOTAMIENTO (mejor oportunidad) ═══
        # Cuando el patron se repite 3+ veces y la 4ta FALLA = reversión
        if is_exhaustion and exhaustion_signal:
            if exhaustion_signal == "SHORT" and market_condition in ("ALCISTA", "LATERAL"):
                # Agotamiento alcista → VENTA (la 4ta montaña no supera la 3ra)
                if self._has_bearish_momentum(df, pc) or wave_conf >= 70:
                    return self._build_signal(
                        symbol, df, "SELL", "SHORT",
                        current_price,
                        "Agotamiento (4ta onda falla)",
                        pip_value, digits, pc,
                        {"sr_flip": False, "sr_type": "exhaustion",
                         "wave_pattern": wave_type,
                         "wave_confidence": wave_conf}
                    )
            elif exhaustion_signal == "LONG" and market_condition in ("BAJISTA", "LATERAL"):
                # Agotamiento bajista → COMPRA (la 4ta caida no supera la 3ra)
                if self._has_bullish_momentum(df, pc) or wave_conf >= 70:
                    return self._build_signal(
                        symbol, df, "BUY", "LONG",
                        current_price,
                        "Agotamiento (4ta onda falla)",
                        pip_value, digits, pc,
                        {"sr_flip": False, "sr_type": "exhaustion",
                         "wave_pattern": wave_type,
                         "wave_confidence": wave_conf}
                    )

        # ═══ PRIORIDAD 1: S/R Flip (resistencia→soporte o viceversa) ═══
        # Potenciado por patron de ondas
        for flip in sr_flips:
            flip_price = flip["price"]
            flip_direction = flip["direction"]

            # En tendencia, solo flip a favor
            if market_condition == "ALCISTA" and flip_direction != "LONG":
                continue
            if market_condition == "BAJISTA" and flip_direction != "SHORT":
                continue

            # Potenciar con patron de ondas
            if wave_pred and wave_pred != flip_direction and wave_conf >= 60:
                continue  # El patron de ondas dice otra cosa

            dist = abs(current_price - flip_price) / pip_value

            if flip_direction == "LONG":
                if dist <= pullback_zone and current_price >= flip_price:
                    if self._has_bullish_momentum(df, pc):
                        reason = "S/R Flip (R>S)"
                        if wave_type and "ALCISTA" in wave_type:
                            reason += " + Ondas alcistas x{}".format(wave_pattern.get("repetitions", 0))
                        return self._build_signal(
                            symbol, df, "BUY", "LONG",
                            flip_price, reason, pip_value, digits, pc,
                            {"sr_flip": True, "sr_type": "RESISTANCE_TO_SUPPORT",
                             "wave_pattern": wave_type, "wave_confidence": wave_conf}
                        )
            elif flip_direction == "SHORT":
                if dist <= pullback_zone and current_price <= flip_price:
                    if self._has_bearish_momentum(df, pc):
                        reason = "S/R Flip (S>R)"
                        if wave_type and "BAJISTA" in wave_type:
                            reason += " + Ondas bajistas x{}".format(wave_pattern.get("repetitions", 0))
                        return self._build_signal(
                            symbol, df, "SELL", "SHORT",
                            flip_price, reason, pip_value, digits, pc,
                            {"sr_flip": True, "sr_type": "SUPPORT_TO_RESISTANCE",
                             "wave_pattern": wave_type, "wave_confidence": wave_conf}
                        )

        # ═══ PRIORIDAD 2: Pullback a soporte (compras) ═══
        if market_condition in ("ALCISTA", "LATERAL"):
            for s in supports:
                s_price = s["price"]
                dist = abs(current_price - s_price) / pip_value
                if dist <= pullback_zone and current_price >= s_price * 0.998:
                    if self._has_bullish_momentum(df, pc):
                        reason = "Soporte ({} toques)".format(s["touches"])
                        if wave_pattern.get("repetitions", 0) >= 2:
                            reason += " + Patron repite {}x".format(wave_pattern["repetitions"])
                        return self._build_signal(
                            symbol, df, "BUY", "LONG",
                            s_price, reason, pip_value, digits, pc,
                            {"sr_flip": False, "sr_type": "support",
                             "touches": s["touches"],
                             "wave_pattern": wave_type, "wave_confidence": wave_conf}
                        )

        # ═══ PRIORIDAD 3: Pullback a resistencia (ventas) ═══
        if market_condition in ("BAJISTA", "LATERAL"):
            for r in resistances:
                r_price = r["price"]
                dist = abs(current_price - r_price) / pip_value
                if dist <= pullback_zone and current_price <= r_price * 1.002:
                    if self._has_bearish_momentum(df, pc):
                        reason = "Resistencia ({} toques)".format(r["touches"])
                        if wave_pattern.get("repetitions", 0) >= 2:
                            reason += " + Patron repite {}x".format(wave_pattern["repetitions"])
                        return self._build_signal(
                            symbol, df, "SELL", "SHORT",
                            r_price, reason, pip_value, digits, pc,
                            {"sr_flip": False, "sr_type": "resistance",
                             "touches": r["touches"],
                             "wave_pattern": wave_type, "wave_confidence": wave_conf}
                        )

        # ═══ PRIORIDAD 4: Movimiento IMPULSIVO (continuar a favor) ═══
        # Si el movimiento es impulsivo (fuerte) → seguir la direccion
        if move_type == "IMPULSIVO_ALCISTA" and market_condition != "BAJISTA":
            if self._has_bullish_momentum(df, pc):
                reason = "Impulso alcista ({} pips)".format(round(wave_pattern.get("last_up_pips", 0), 1))
                return self._build_signal(
                    symbol, df, "BUY", "LONG",
                    current_price, reason, pip_value, digits, pc,
                    {"sr_flip": False, "sr_type": "impulsive",
                     "wave_pattern": move_type, "wave_confidence": 65}
                )

        if move_type == "IMPULSIVO_BAJISTA" and market_condition != "ALCISTA":
            if self._has_bearish_momentum(df, pc):
                reason = "Impulso bajista ({} pips)".format(round(wave_pattern.get("last_down_pips", 0), 1))
                return self._build_signal(
                    symbol, df, "SELL", "SHORT",
                    current_price, reason, pip_value, digits, pc,
                    {"sr_flip": False, "sr_type": "impulsive",
                     "wave_pattern": move_type, "wave_confidence": 65}
                )

        # ═══ PRIORIDAD 5: Patron repetitivo sin S/R (momentum) ═══
        if wave_pred and wave_conf >= 55:
            if wave_pred == "LONG" and market_condition != "BAJISTA":
                if self._has_bullish_momentum(df, pc):
                    return self._build_signal(
                        symbol, df, "BUY", "LONG",
                        current_price, "Patron repite {}x".format(wave_pattern["repetitions"]),
                        pip_value, digits, pc,
                        {"sr_flip": False, "sr_type": "pattern_repeat",
                         "wave_pattern": wave_type, "wave_confidence": wave_conf}
                    )
            elif wave_pred == "SHORT" and market_condition != "ALCISTA":
                if self._has_bearish_momentum(df, pc):
                    return self._build_signal(
                        symbol, df, "SELL", "SHORT",
                        current_price, "Patron repite {}x".format(wave_pattern["repetitions"]),
                        pip_value, digits, pc,
                        {"sr_flip": False, "sr_type": "pattern_repeat",
                         "wave_pattern": wave_type, "wave_confidence": wave_conf}
                    )

        # ═══ PRIORIDAD 6: Momentum puro a favor de tendencia ═══
        if market_condition == "ALCISTA" and mtf_direction == "LONG":
            if self._has_bullish_momentum(df, pc) and self._strong_momentum(df, pc):
                return self._build_signal(
                    symbol, df, "BUY", "LONG",
                    current_price, "Momentum alcista", pip_value, digits, pc,
                    {"sr_flip": False, "sr_type": "momentum",
                     "wave_pattern": wave_type}
                )

        if market_condition == "BAJISTA" and mtf_direction == "SHORT":
            if self._has_bearish_momentum(df, pc) and self._strong_momentum(df, pc):
                return self._build_signal(
                    symbol, df, "SELL", "SHORT",
                    current_price, "Momentum bajista", pip_value, digits, pc,
                    {"sr_flip": False, "sr_type": "momentum",
                     "wave_pattern": wave_type}
                )

        return None

    # ═══════════════════════════════════════════════════════════
    #  DETECCION DE SOPORTES Y RESISTENCIAS
    # ═══════════════════════════════════════════════════════════

    def _detect_sr_levels(self, df: pd.DataFrame, pip_value: float, pc: dict):
        lookback = pc.get("sr_lookback", 50)
        min_touches = pc.get("sr_touches", 2)

        recent = df.iloc[-lookback:]
        supports = []
        resistances = []

        for i in range(2, len(recent) - 2):
            candle = recent.iloc[i]
            prev1 = recent.iloc[i - 1]
            prev2 = recent.iloc[i - 2]
            next1 = recent.iloc[i + 1]
            next2 = recent.iloc[i + 2]

            if (candle['low'] <= prev1['low'] and candle['low'] <= prev2['low'] and
                candle['low'] <= next1['low'] and candle['low'] <= next2['low']):
                supports.append({
                    "price": candle['low'], "index": i,
                    "type": "SWING_LOW", "strength": 1
                })

            if (candle['high'] >= prev1['high'] and candle['high'] >= prev2['high'] and
                candle['high'] >= next1['high'] and candle['high'] >= next2['high']):
                resistances.append({
                    "price": candle['high'], "index": i,
                    "type": "SWING_HIGH", "strength": 1
                })

        zone_pips = pc.get("sr_zone_pips", 3.0)
        for level in supports + resistances:
            level_price = level["price"]
            touches = 0
            for _, row in recent.iterrows():
                dist = abs(row['low'] - level_price) / pip_value
                dist_h = abs(row['high'] - level_price) / pip_value
                if dist <= zone_pips or dist_h <= zone_pips:
                    touches += 1
            level["touches"] = touches
            level["validated"] = touches >= min_touches

        valid_supports = [s for s in supports if s["validated"]]
        valid_resistances = [r for r in resistances if r["validated"]]

        current_price = df.iloc[-1]['close']
        valid_supports.sort(key=lambda x: abs(x["price"] - current_price))
        valid_resistances.sort(key=lambda x: abs(x["price"] - current_price))

        return valid_supports[:5], valid_resistances[:5]

    # ═══════════════════════════════════════════════════════════
    #  DETECCION DE S/R FLIP
    # ═══════════════════════════════════════════════════════════

    def _detect_sr_flips(self, df: pd.DataFrame, supports, resistances,
                         pip_value: float, pc: dict):
        flips = []
        current_price = df.iloc[-1]['close']

        for r in resistances:
            r_price = r["price"]
            if current_price > r_price:
                recent = df.iloc[-20:]
                was_below = any(row['close'] < r_price for _, row in recent.iterrows())
                if was_below:
                    flips.append({
                        "price": r_price,
                        "type": "RESISTANCE_TO_SUPPORT",
                        "direction": "LONG",
                        "original_type": "resistance",
                        "new_type": "support",
                    })

        for s in supports:
            s_price = s["price"]
            if current_price < s_price:
                recent = df.iloc[-20:]
                was_above = any(row['close'] > s_price for _, row in recent.iterrows())
                if was_above:
                    flips.append({
                        "price": s_price,
                        "type": "SUPPORT_TO_RESISTANCE",
                        "direction": "SHORT",
                        "original_type": "support",
                        "new_type": "resistance",
                    })

        return flips

    # ═══════════════════════════════════════════════════════════
    #  MOMENTUM CHECK
    # ═══════════════════════════════════════════════════════════

    def _has_bullish_momentum(self, df: pd.DataFrame, pc: dict) -> bool:
        ema_f = df['close'].ewm(span=pc["ema_fast"], adjust=False).mean()
        ema_s = df['close'].ewm(span=pc["ema_slow"], adjust=False).mean()
        return ema_f.iloc[-1] > ema_s.iloc[-1]

    def _has_bearish_momentum(self, df: pd.DataFrame, pc: dict) -> bool:
        ema_f = df['close'].ewm(span=pc["ema_fast"], adjust=False).mean()
        ema_s = df['close'].ewm(span=pc["ema_slow"], adjust=False).mean()
        return ema_f.iloc[-1] < ema_s.iloc[-1]

    def _strong_momentum(self, df: pd.DataFrame, pc: dict) -> bool:
        ema_f = df['close'].ewm(span=pc["ema_fast"], adjust=False).mean()
        ema_s = df['close'].ewm(span=pc["ema_slow"], adjust=False).mean()
        pip_value = self.params.get("pip_values", {}).get("XAUUSD", 0.0001)
        gap = abs(ema_f.iloc[-1] - ema_s.iloc[-1]) / pip_value
        return gap > 0.5

    # ═══════════════════════════════════════════════════════════
    #  CONSTRUIR SENAL
    # ═══════════════════════════════════════════════════════════

    def _build_signal(self, symbol, df, signal, direction,
                      sr_level, sr_reason, pip_value, digits, pc, extra):
        current = df.iloc[-1]
        current_price = current['close']

        atr = self._calculate_atr(df, pc["atr_period"])
        atr_pips = atr / pip_value
        sl_pips = max(pc["sl_min"], min(pc["sl_max"], round(atr_pips * pc["atr_multiplier"], 1)))
        tp_pips = sl_pips  # 1:1

        if direction == "LONG":
            sl_price = round(current_price - sl_pips * pip_value, digits)
            tp_price = round(current_price + tp_pips * pip_value, digits)
        else:
            sl_price = round(current_price + sl_pips * pip_value, digits)
            tp_price = round(current_price - tp_pips * pip_value, digits)

        cr = current['high'] - current['low']
        if cr > 0 and direction == "LONG":
            lw = min(current['open'], current['close']) - current['low']
            uw = current['high'] - max(current['open'], current['close'])
            wick_ratio = lw / uw if uw > 0 else 10.0
            wick_pips = lw / pip_value
        elif cr > 0 and direction == "SHORT":
            uw = current['high'] - max(current['open'], current['close'])
            lw = min(current['open'], current['close']) - current['low']
            wick_ratio = uw / lw if lw > 0 else 10.0
            wick_pips = uw / pip_value
        else:
            wick_ratio = 0
            wick_pips = 0

        is_flip = extra.get("sr_flip", False)
        is_exhaustion = extra.get("sr_type") == "exhaustion"
        is_impulsive = extra.get("sr_type") == "impulsive"
        wave_conf = extra.get("wave_confidence", 0)

        # Scoring v8.4:
        # Agotamiento = 3.5, Flip = 3, Impulsivo = 2.5, S/R = 2, Patron = 2, Momentum = 1.5
        if is_exhaustion:
            score = 3.5
        elif is_flip:
            score = 3.0
        elif is_impulsive:
            score = 2.5
        elif extra.get("sr_type") in ("support", "resistance") and extra.get("touches", 0) >= 3:
            score = 2.5
        elif extra.get("sr_type") in ("support", "resistance"):
            score = 2.0
        elif extra.get("sr_type") == "pattern_repeat":
            score = 2.0
        else:
            score = 1.5

        # Boost por patron de ondas
        if wave_conf >= 70:
            score = min(4.0, score + 0.5)
        elif wave_conf >= 55:
            score = min(4.0, score + 0.3)

        conditions = {
            "sr_level": {
                "passed": True,
                "detail": "{} @ {:.2f}".format(sr_reason, sr_level)
            },
            "sr_flip": {
                "passed": is_flip,
                "detail": "S/R FLIP confirmado" if is_flip else "S/R sin flip"
            },
            "ema_trend": {
                "passed": True,
                "detail": "EMA{} > EMA{}".format(pc["ema_fast"], pc["ema_slow"]) if direction == "LONG"
                else "EMA{} < EMA{}".format(pc["ema_fast"], pc["ema_slow"])
            },
            "wick": {
                "passed": wick_ratio >= 1.0,
                "detail": "Mecha {:.1f}x ({:.1f} pips)".format(wick_ratio, wick_pips)
            },
            "wave_pattern": {
                "passed": wave_conf >= 55,
                "detail": "{} ({}%)".format(
                    extra.get("wave_pattern", "N/A"), wave_conf)
            },
        }

        return {
            "signal": signal,
            "direction": direction,
            "score": round(score, 1),
            "max_score": 4,
            "passed": True,
            "conditions": conditions,
            "sl_pips": sl_pips,
            "tp_pips": tp_pips,
            "sl_price": sl_price,
            "tp_price": tp_price,
            "needs_ai_confirmation": True,
            "sr_level": sr_level,
            "sr_reason": sr_reason,
            "sr_is_flip": is_flip,
            "wick_ratio": round(wick_ratio, 2),
            "wave_pattern": extra.get("wave_pattern", ""),
            "wave_confidence": wave_conf,
        }

    # ═══════════════════════════════════════════════════════════
    #  ATR
    # ═══════════════════════════════════════════════════════════

    def _calculate_atr(self, df, period=14):
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
    #  KILLZONES
    # ═══════════════════════════════════════════════════════════

    def _is_killzone_active(self, symbol: str) -> bool:
        now_utc = datetime.now(pytz.utc)
        h = now_utc.hour
        if now_utc.weekday() >= 5:
            return False

        if symbol == "XAUUSD":
            zones = [(5, 10), (7, 12), (12, 17), (15, 20)]
        else:
            zones = [(6, 12), (12, 17), (15, 19)]

        for start, end in zones:
            if start <= h < end:
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
