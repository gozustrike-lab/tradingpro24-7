"""
TradingPro24-7 - Config Template v8.0
ESTRATEGIA: Momentum Following
SI SUBE → COMPRA | SI BAJA → VENDE
R:R 1:1 | Win Rate 70-80% | Ganancias consistentes
"""

import os

# ─── API KEYS ─────────────────────────────────────────────────
OPENROUTER_API_KEY = "TU_API_KEY_AQUI"
TELEGRAM_BOT_TOKEN = "TU_BOT_TOKEN_AQUI"
TELEGRAM_CHAT_ID = "TU_CHAT_ID_AQUI"
# TELEGRAM_CHANNEL_ID = "-100TU_CHANNEL_ID_AQUI"

AI_MODEL = "google/gemma-4-31b-it"

# ─── PARES DE DIVISAS ────────────────────────────────────────
FOREX_PAIRS = [
    "EURUSD", "GBPUSD", "USDJPY",
    "AUDUSD", "USDCAD", "USDCHF",
]

TIMEFRAME = "M15"
MT5_TIMEFRAME = 15

# ═══════════════════════════════════════════════════════════════
#  ESTRATEGIA v8.0 — MOMENTUM FOLLOWING
#  ═══════════════════════════════════════════════════════════════
# FILOSOFIA:
#   - Si el precio SUBE → BUSCAR COMPRAR (a favor de la tendencia)
#   - Si el precio BAJA → BUSCAR VENDER (a favor de la tendencia)
#   - R:R 1:1 (mismo riesgo que ganancia)
#   - Win rate objetivo: 70-80%
#   - Ganancias cortas pero consistentes: 10-25 pips
#   - Muchas operaciones: 3-8 por dia
# ═══════════════════════════════════════════════════════════════

STRATEGY = {
    "ema_fast": 20,
    "ema_slow": 50,

    # ═══ MOMENTUM (modo principal) ═══
    "momentum_tp_pips": 15,
    "momentum_sl_pips": 15,
    "momentum_lookback": 10,
    "min_direction_candles": 6,

    # ═══ ICT SWEEP (modo secundario) ═══
    "trend_sl_pips": 18,
    "trend_tp_pips": 45,
    "wick_min_pips": 5,
    "wick_ratio_min": 2.0,
    "close_percentile": 75,
    "min_score": 4,
    "pullback_candles": 3,
    "pullback_min_pips": 10,
    "lookback_candles": 20,

    # Killzones
    "killzones": {
        "enabled": True,
        "zones": {
            "london_open": {"start": 7, "end": 10},
            "ny_open": {"start": 12, "end": 15},
            "london_close": {"start": 15, "end": 17},
        }
    },

    "fvg_min_pips": 3,
    "ob_lookback": 15,
    "ob_min_body_pips": 5,
    "multi_tf_enabled": True,

    "pip_values": {
        "EURUSD": 0.0001, "GBPUSD": 0.0001, "USDJPY": 0.01,
        "AUDUSD": 0.0001, "USDCAD": 0.0001, "USDCHF": 0.0001,
    },
    "digits": {
        "EURUSD": 5, "GBPUSD": 5, "USDJPY": 3,
        "AUDUSD": 5, "USDCAD": 5, "USDCHF": 5,
    },

    # ═══ RANGO/LATERAL ═══
    "range_mode": {
        "sr_lookback": 30,
        "zone_pips": 5,
        "min_range_pips": 20,
        "wick_min_pips": 3,
        "close_percentile": 70,
        "min_score": 4,
        "tp_pips": 15,
        "sl_pips": 15,
    },
}

# ─── RIESGO v8.0 ═══ R:R 1:1, mas trades permitidos ═══
RISK = {
    "risk_percent": 1.0,
    "risk_percent_max": 2.0,
    "sl_pips": 15,
    "tp_pips": 15,
    "rr_ratio": 1.0,
    "max_daily_trades": 8,
    "max_open_trades": 2,
    "daily_loss_limit": 4.0,
}

RISK_PER_PAIR = {
    "EURUSD": {"sl_pips": 15, "tp_pips": 15},
    "GBPUSD": {"sl_pips": 18, "tp_pips": 18},
    "USDJPY": {"sl_pips": 15, "tp_pips": 15},
    "AUDUSD": {"sl_pips": 15, "tp_pips": 15},
    "USDCAD": {"sl_pips": 15, "tp_pips": 15},
    "USDCHF": {"sl_pips": 15, "tp_pips": 15},
}

SESSIONS = {
    "london": {"start": 7, "end": 16},
    "new_york": {"start": 12, "end": 21},
}

PAIR_SESSIONS = {
    "EURUSD": ["london", "new_york"],
    "GBPUSD": ["london", "new_york"],
    "USDJPY": ["london", "new_york"],
    "AUDUSD": ["london", "new_york"],
    "USDCAD": ["london", "new_york"],
    "USDCHF": ["london", "new_york"],
}

AI_VISION = {
    "enabled": True,
    "min_confidence": 0.65,
    "max_daily_calls": 50,
    "timeout_seconds": 30,
}

BOT = {
    "check_interval": 60,
    "min_timeframe_between_signals": 180,
    "log_file": "signals_log.json",
    "trade_log_file": "trades_log.json",
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = os.path.join(BASE_DIR, "logs")
SCREENSHOTS_DIR = os.path.join(BASE_DIR, "screenshots")
DATA_DIR = os.path.join(BASE_DIR, "data")

for directory in [LOGS_DIR, SCREENSHOTS_DIR, DATA_DIR]:
    os.makedirs(directory, exist_ok=True)
