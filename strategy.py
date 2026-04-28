# ═══════════════════════════════════════════════════════════════
#  TRADINGPRO24-7 — STRATEGY ENGINE v8.3 ICT PRO
#  ═══ S/R AUTOMATICO + S/R FLIP + PULLBACK ENTRY ═══
#  ═══ MTF: M5 direccion + M1 entrada ═══
#  ═══ Auto-ejecucion en MT5 ═══
#  ═══════════════════════════════════════════════════════════════
#
#  CONCEPTO CLAVE (lo que el usuario dibujo con lineas rojas):
#  1. Bot detecta resistencias/soportes clave automaticamente
#  2. Cuando precio rompe resistencia → esa zona se convierte en SOPORTE
#  3. Cuando precio hace pullback a esa zona → SENAL DE COMPRA
#  4. Viceversa para ventas
#  5. M5 confirma direccion, M1 busca entrada en S/R flip
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
        "sr_lookback": 50,       # Velas para buscar S/R
        "sr_touches": 2,         # Minimo toques para validar S/R
        "sr_zone_pips": 3.0,     # Zona de tolerancia en pips
        "pullback_zone_pips": 5, # Zona de pullback valida
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
    },
}


def get_pair_config(symbol: str) -> dict:
    return PAIR_CONFIG.get(symbol, PAIR_CONFIG["_DEFAULT"])


class StrategyEngine:
    """Motor v8.3 — S/R Automatico + Flip + Pullback + MTF."""

    def __init__(self, data_feed: DataFeed):
        self.data_feed = data_feed
        self.params = STRATEGY
        self.last_signal_time = {}

    # ═══════════════════════════════════════════════════════════
    #  ANALISIS PRINCIPAL
    # ═══════════════════════════════════════════════════════════

    def analyze(self, symbol: str):
        pc = get_pair_config(symbol)

        if not self._is_session_active(symbol):
            return None
        if not self._is_killzone_active(symbol):
            return None

        # PASO 1: MTF confirma direccion
        mtf_direction = None
        mtf_timeframe = pc.get("mtf_timeframe")
        if mtf_timeframe:
            mtf_direction, mtf_score = self._check_mtf_direction(symbol, pc)
            if mtf_direction is None:
                return None

        # PASO 2: Obtener datos
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

        pip_value = self.params.get("pip_values", {}).get(symbol, 0.0001)
        digits = self.params.get("digits", {}).get(symbol, 5)
        current = df.iloc[-1]
        current_price = current['close']

        # PASO 3: Detectar niveles S/R
        supports, resistances = self._detect_sr_levels(df, pip_value, pc)

        # PASO 4: Detectar S/R flips (resistencia→soporte, soporte→resistencia)
        sr_flips = self._detect_sr_flips(df, supports, resistances, pip_value, pc)

        # PASO 5: Buscar pullback a S/R flip (la entrada perfecta)
        result = self._find_pullback_to_sr(symbol, df, current, mtf_direction,
                                           supports, resistances, sr_flips,
                                           pip_value, digits, pc)

        if result is None:
            return None

        # PASO 6: Verificar que la direccion coincide con MTF
        direction = result["direction"]
        if mtf_direction and direction != mtf_direction:
            return None

        # Completar resultado
        result["symbol"] = symbol
        result["timestamp"] = datetime.now().isoformat()
        result["current_price"] = current_price
        result["timeframe"] = timeframe
        result["market_mode"] = "SR_FLIP"
        self.last_signal_time[symbol] = datetime.now()

        # Info MTF
        if mtf_direction:
            result["mtf_direction"] = mtf_direction
            result["mtf_timeframe"] = mtf_timeframe

        logger.info("[{}] SR_FLIP {} — Entrada en S/R ({:.2f})".format(
            symbol, direction, result.get("sr_level", 0)))
        return result

    # ═══════════════════════════════════════════════════════════
    #  DETECCION DE SOPORTES Y RESISTENCIAS
    # ═══════════════════════════════════════════════════════════

    def _detect_sr_levels(self, df: pd.DataFrame, pip_value: float, pc: dict):
        """
        Detecta niveles de soporte y resistencia buscando:
        - Swing highs (resistencia): velas con highs mayores que vecinos
        - Swing lows (soporte): velas con lows menores que vecinos
        """
        lookback = pc.get("sr_lookback", 50)
        min_touches = pc.get("sr_touches", 2)

        recent = df.iloc[-lookback:]
        supports = []
        resistances = []

        # Buscar swing lows (soportes) y swing highs (resistencias)
        for i in range(2, len(recent) - 2):
            candle = recent.iloc[i]
            prev1 = recent.iloc[i - 1]
            prev2 = recent.iloc[i - 2]
            next1 = recent.iloc[i + 1]
            next2 = recent.iloc[i + 2]

            # Swing low = soporte
            if (candle['low'] <= prev1['low'] and candle['low'] <= prev2['low'] and
                candle['low'] <= next1['low'] and candle['low'] <= next2['low']):
                supports.append({
                    "price": candle['low'],
                    "index": i,
                    "type": "SWING_LOW",
                    "strength": 1
                })

            # Swing high = resistencia
            if (candle['high'] >= prev1['high'] and candle['high'] >= prev2['high'] and
                candle['high'] >= next1['high'] and candle['high'] >= next2['high']):
                resistances.append({
                    "price": candle['high'],
                    "index": i,
                    "type": "SWING_HIGH",
                    "strength": 1
                })

        # Validar niveles: buscar cuantas veces el precio toco el nivel
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

        # Solo retornar niveles validados
        valid_supports = [s for s in supports if s["validated"]]
        valid_resistances = [r for r in resistances if r["validated"]]

        # Ordenar por precio
        valid_supports.sort(key=lambda x: x["price"], reverse=True)  # Mas cercano primero
        valid_resistances.sort(key=lambda x: x["price"])  # Mas cercano primero

        return valid_supports[:3], valid_resistances[:3]

    # ═══════════════════════════════════════════════════════════
    #  DETECCION DE S/R FLIP
    # ═══════════════════════════════════════════════════════════

    def _detect_sr_flips(self, df: pd.DataFrame, supports, resistances,
                         pip_value: float, pc: dict):
        """
        Detecta cuando una resistencia se convierte en soporte o viceversa.
        Esto es la clave: precio rompe un nivel y luego lo respeta al otro lado.
        """
        flips = []
        current_price = df.iloc[-1]['close']
        zone_pips = pc.get("sr_zone_pips", 3.0)

        # Resistencia que el precio rompio hacia arriba = ahora es SOPORTE
        for r in resistances:
            r_price = r["price"]
            # El precio cerro arriba de la resistencia (la rompio)
            if current_price > r_price:
                # Verificar que paso por debajo antes (confirma que fue resistencia)
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

        # Soporte que el precio rompio hacia abajo = ahora es RESISTENCIA
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
    #  PULLBACK A S/R — LA ENTRADA PERFECTA
    # ═══════════════════════════════════════════════════════════

    def _find_pullback_to_sr(self, symbol, df, current, mtf_direction,
                              supports, resistances, sr_flips,
                              pip_value, digits, pc):
        """
        Busca la entrada perfecta: pullback a un nivel S/R o S/R flip.
        Esta es la estrategia que el usuario dibujo con lineas rojas.
        """
        current_price = current['close']
        pullback_zone = pc.get("pullback_zone_pips", 5)

        # ── ESCENARIO 1: Pullback a S/R flip (mejor senal) ──
        for flip in sr_flips:
            flip_price = flip["price"]
            direction = flip["direction"]

            # Verificar que MTF coincide
            if mtf_direction and direction != mtf_direction:
                continue

            dist = abs(current_price - flip_price) / pip_value

            if direction == "LONG":
                # Precio esta cerca o arriba del flip (pullback alcista)
                if dist <= pullback_zone and current_price >= flip_price:
                    # Verificar que hay momento alcista
                    if self._has_bullish_momentum(df, pc):
                        return self._build_signal(
                            symbol, df, "BUY", "LONG", direction,
                            flip_price, "S/R Flip (R→S)", pip_value, digits, pc,
                            {"sr_flip": True, "sr_type": flip["type"]}
                        )
            elif direction == "SHORT":
                if dist <= pullback_zone and current_price <= flip_price:
                    if self._has_bearish_momentum(df, pc):
                        return self._build_signal(
                            symbol, df, "SELL", "SHORT", direction,
                            flip_price, "S/R Flip (S→R)", pip_value, digits, pc,
                            {"sr_flip": True, "sr_type": flip["type"]}
                        )

        # ── ESCENARIO 2: Pullback a soporte valido ──
        for s in supports:
            s_price = s["price"]
            if mtf_direction and mtf_direction != "LONG":
                continue

            dist = abs(current_price - s_price) / pip_value
            if dist <= pullback_zone and current_price >= s_price * 0.998:
                if self._has_bullish_momentum(df, pc):
                    return self._build_signal(
                        symbol, df, "BUY", "LONG", "LONG",
                        s_price, "Soporte ({})".format(s["touches"]) + " toques",
                        pip_value, digits, pc,
                        {"sr_flip": False, "sr_type": "support", "touches": s["touches"]}
                    )

        # ── ESCENARIO 3: Pullback a resistencia valida ──
        for r in resistances:
            r_price = r["price"]
            if mtf_direction and mtf_direction != "SHORT":
                continue

            dist = abs(current_price - r_price) / pip_value
            if dist <= pullback_zone and current_price <= r_price * 1.002:
                if self._has_bearish_momentum(df, pc):
                    return self._build_signal(
                        symbol, df, "SELL", "SHORT", "SHORT",
                        r_price, "Resistencia ({})".format(r["touches"]) + " toques",
                        pip_value, digits, pc,
                        {"sr_flip": False, "sr_type": "resistance", "touches": r["touches"]}
                    )

        # ── ESCENARIO 4: Momentum puro (sin S/R cercano pero con fuerte momentum) ──
        if not sr_flips and not supports and not resistances:
            if mtf_direction == "LONG" and self._has_bullish_momentum(df, pc):
                return self._build_signal(
                    symbol, df, "BUY", "LONG", "LONG",
                    current_price, "Momentum puro", pip_value, digits, pc,
                    {"sr_flip": False, "sr_type": "momentum"}
                )
            elif mtf_direction == "SHORT" and self._has_bearish_momentum(df, pc):
                return self._build_signal(
                    symbol, df, "SELL", "SHORT", "SHORT",
                    current_price, "Momentum puro", pip_value, digits, pc,
                    {"sr_flip": False, "sr_type": "momentum"}
                )

        return None

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

    # ═══════════════════════════════════════════════════════════
    #  CONSTRUIR SENAL
    # ═══════════════════════════════════════════════════════════

    def _build_signal(self, symbol, df, signal, direction, sr_direction,
                      sr_level, sr_reason, pip_value, digits, pc, extra):
        current = df.iloc[-1]
        current_price = current['close']

        # SL/TP via ATR (1:1 R:R)
        atr = self._calculate_atr(df, pc["atr_period"])
        atr_pips = atr / pip_value
        sl_pips = max(pc["sl_min"], min(pc["sl_max"], round(atr_pips * pc["atr_multiplier"], 1)))
        tp_pips = sl_pips  # 1:1

        # Calcular SL/TP prices
        if direction == "LONG":
            sl_price = round(current_price - sl_pips * pip_value, digits)
            tp_price = round(current_price + tp_pips * pip_value, digits)
        else:
            sl_price = round(current_price + sl_pips * pip_value, digits)
            tp_price = round(current_price - tp_pips * pip_value, digits)

        # Mecha de rechazo
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
        score = 3 if is_flip else 2  # Flip = mejor score

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
        }

        return {
            "signal": signal,
            "direction": direction,
            "score": score,
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
        }

    # ═══════════════════════════════════════════════════════════
    #  MTF — M5 confirma direccion
    # ═══════════════════════════════════════════════════════════

    def _check_mtf_direction(self, symbol: str, pc: dict):
        mtf_tf = pc["mtf_timeframe"]
        if not mtf_tf:
            return None, 0

        try:
            df_mtf = self.data_feed.get_ohlc(symbol, num_candles=100, timeframe=mtf_tf)
            if df_mtf is None or len(df_mtf) < 50:
                return None, 0

            pip_value = self.params.get("pip_values", {}).get(symbol, 0.0001)

            ema_fast = df_mtf['close'].ewm(span=pc["mtf_ema_fast"], adjust=False).mean()
            ema_slow = df_mtf['close'].ewm(span=pc["mtf_ema_slow"], adjust=False).mean()

            bullish = ema_fast.iloc[-1] > ema_slow.iloc[-1]
            bearish = ema_fast.iloc[-1] < ema_slow.iloc[-1]

            slope = (ema_fast.iloc[-1] - ema_fast.iloc[-5]) / pip_value
            slope_up = slope > 1.0
            slope_down = slope < -1.0

            price_change = (df_mtf.iloc[-1]['close'] - df_mtf.iloc[-6]['close']) / pip_value
            price_up = price_change > 3.0
            price_down = price_change < -3.0

            rh = df_mtf['high'].iloc[-10:]
            rl = df_mtf['low'].iloc[-10:]
            hh_hl = rh.iloc[-1] > rh.iloc[-3] and rl.iloc[-1] > rl.iloc[-3]
            lh_ll = rh.iloc[-1] < rh.iloc[-3] and rl.iloc[-1] < rl.iloc[-3]

            up_score = (1 if bullish else 0) + (1 if slope_up else 0) + (1 if price_up else 0) + (1 if hh_hl else 0)
            down_score = (1 if bearish else 0) + (1 if slope_down else 0) + (1 if price_down else 0) + (1 if lh_ll else 0)

            if up_score >= 2 and up_score > down_score:
                return "LONG", up_score
            elif down_score >= 2 and down_score > up_score:
                return "SHORT", down_score

            return None, 0

        except Exception as e:
            logger.error("Error MTF {}: {}".format(symbol, e))
            return None, 0

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
