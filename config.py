# ═══════════════════════════════════════════════════════════════
#  TRADING BOT HÍBRIDO — CONFIGURACIÓN (TEMPLATE)
#  Copia este archivo como config.py y configura tus keys
# ═══════════════════════════════════════════════════════════════

import os

# ─── API KEYS ─────────────────────────────────────────────────
# OpenRouter API Key (gratis con Gemma 4 31B)
# Consíguela en: https://openrouter.ai/keys
OPENROUTER_API_KEY = "TU_API_KEY_AQUÍ"

# Telegram Bot Token
# Consíguelo en: @BotFather → /newbot
TELEGRAM_BOT_TOKEN = "TU_BOT_TOKEN_AQUÍ"

# Telegram Chat ID
# Consíguelo en: @userinfobot → /start
TELEGRAM_CHAT_ID = "TU_CHAT_ID_AQUÍ"

# ─── MODELO AI VISION ────────────────────────────────────────
AI_MODEL = "google/gemma-4-31b-it"

# ─── PARES DE DIVISAS ────────────────────────────────────────
FOREX_PAIRS = [
    "EURUSD",
    "GBPUSD",
    "USDJPY",
    "AUDUSD",
    "USDCAD",
    "USDCHF",
]

# ─── TIMEFRAME ───────────────────────────────────────────────
TIMEFRAME = "M15"
MT5_TIMEFRAME = 15

# ─── PARÁMETROS DE LA ESTRATEGIA ─────────────────────────────
STRATEGY = {
    "ema_fast": 20,
    "ema_slow": 50,
    "pullback_candles": 3,
    "pullback_min_pips": 10,
    "lookback_candles": 20,
    "sweep_pip_tolerance": 2,
    "wick_ratio_min": 2.0,
    "close_percentile": 75,
    "min_score": 4,
    "pip_values": {
        "EURUSD": 0.0001, "GBPUSD": 0.0001, "USDJPY": 0.01,
        "AUDUSD": 0.0001, "USDCAD": 0.0001, "USDCHF": 0.0001,
    },
    "digits": {
        "EURUSD": 5, "GBPUSD": 5, "USDJPY": 3,
        "AUDUSD": 5, "USDCAD": 5, "USDCHF": 5,
    },
}

# ─── GESTIÓN DE RIESGO ───────────────────────────────────────
RISK = {
    "risk_percent": 1.0,
    "risk_percent_max": 2.0,
    "sl_pips": 18,
    "tp_pips": 45,
    "rr_ratio": 2.5,
    "max_daily_trades": 3,
    "max_open_trades": 2,
    "daily_loss_limit": 3.0,
}

RISK_PER_PAIR = {
    "EURUSD": {"sl_pips": 18, "tp_pips": 45},
    "GBPUSD": {"sl_pips": 20, "tp_pips": 50},
    "USDJPY": {"sl_pips": 18, "tp_pips": 45},
    "AUDUSD": {"sl_pips": 18, "tp_pips": 45},
    "USDCAD": {"sl_pips": 18, "tp_pips": 45},
    "USDCHF": {"sl_pips": 18, "tp_pips": 45},
}

# ─── SESIONES DE TRADING ─────────────────────────────────────
SESSIONS = {
    "london": {"start": 7, "end": 16},
    "new_york": {"start": 12, "end": 21},
}

PAIR_SESSIONS = {
    "EURUSD": ["london", "new_york"],
    "GBPUSD": ["london"],
    "USDJPY": ["new_york"],
    "AUDUSD": ["london"],
    "USDCAD": ["new_york"],
    "USDCHF": ["london"],
}

# ─── AI VISION CONFIG ────────────────────────────────────────
AI_VISION = {
    "enabled": True,
    "min_confidence": 0.70,
    "max_daily_calls": 30,
    "timeout_seconds": 30,
}

# ─── BOT CONFIG ──────────────────────────────────────────────
BOT = {
    "check_interval": 60,
    "min_timeframe_between_signals": 300,
    "log_file": "signals_log.json",
    "trade_log_file": "trades_log.json",
}

# ─── PATHS ───────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = os.path.join(BASE_DIR, "logs")
SCREENSHOTS_DIR = os.path.join(BASE_DIR, "screenshots")
DATA_DIR = os.path.join(BASE_DIR, "data")

for directory in [LOGS_DIR, SCREENSHOTS_DIR, DATA_DIR]:
    os.makedirs(directory, exist_ok=True)
