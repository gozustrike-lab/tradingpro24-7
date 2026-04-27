# ═══════════════════════════════════════════════════════════════
#  TRADING BOT HÍBRIDO — CONFIGURACIÓN v5.0
#  MODO 1: ICT Sweep (tendencia)
#  MODO 2: Rango/Lateral (soporte/resistencia)
# ═══════════════════════════════════════════════════════════════

import os

# ─── API KEYS ─────────────────────────────────────────────────
# OpenRouter API Key (gratis con Gemma 4 31B)
# Consíguela en: https://openrouter.ai/keys
OPENROUTER_API_KEY = "TU_API_KEY_AQUÍ"

# Telegram Bot Token
# Consíguelo en: @BotFather → /newbot
TELEGRAM_BOT_TOKEN = "TU_BOT_TOKEN_AQUÍ"

# Telegram Chat ID (tu chat privado para sweep alerts)
# Consíguelo en: @userinfobot → /start
TELEGRAM_CHAT_ID = "TU_CHAT_ID_AQUÍ"

# Telegram Channel ID (canal privado para señales confirmadas)
# Ejemplo: "-1001234567890" — se necesita agregar el bot como admin al canal
# TELEGRAM_CHANNEL_ID = "-100TU_CHANNEL_ID_AQUÍ"

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
# Compartidos entre ambos modos
STRATEGY = {
    "ema_fast": 20,
    "ema_slow": 50,
    "pullback_candles": 3,
    "pullback_min_pips": 10,
    "lookback_candles": 20,
    "wick_min_pips": 5,
    "wick_ratio_min": 2.0,
    "close_percentile": 75,
    "min_score": 4,

    # TP/SL para modo TENDENCIA (grande)
    "trend_sl_pips": 18,
    "trend_tp_pips": 45,

    "pip_values": {
        "EURUSD": 0.0001, "GBPUSD": 0.0001, "USDJPY": 0.01,
        "AUDUSD": 0.0001, "USDCAD": 0.0001, "USDCHF": 0.0001,
    },
    "digits": {
        "EURUSD": 5, "GBPUSD": 5, "USDJPY": 3,
        "AUDUSD": 5, "USDCAD": 5, "USDCHF": 5,
    },

    # ═══ MODO RANGO/LATERAL ═══
    # Se activa automáticamente cuando no hay tendencia
    "range_mode": {
        # Cuántas velas mirar para encontrar soporte/resistencia
        "sr_lookback": 30,
        # Zona de detección: cuántos pips cerca de S/R para señalar
        "zone_pips": 5,
        # Rango mínimo en pips para considerar que hay rango válido
        "min_range_pips": 20,
        # Mecha mínima para confirmar rechazo en S/R
        "wick_min_pips": 3,
        # Cierre fuerte mínimo en porcentaje
        "close_percentile": 70,
        # Score mínimo de 5 para activar señal
        "min_score": 4,
        # TP y SL para operaciones de rango (1:1 ratio)
        "tp_pips": 20,
        "sl_pips": 15,
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
