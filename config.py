# ═══════════════════════════════════════════════════════════════
#  TRADINGPRO24-7 — CONFIGURACION v8.4 ICT PRO
#  ═══ XAUUSD M1 + Forex M15 + S/R + Ondas + Reentrada ═══
#  ═══ IMPORTANTE: actualizar.py NO toca este archivo ═══
# ═══════════════════════════════════════════════════════════════

import os

# ─── API KEYS ─────────────────────────────────────────────────
OPENROUTER_API_KEY = "TU_API_KEY_AQUÍ"

# Telegram
TELEGRAM_BOT_TOKEN = "TU_BOT_TOKEN_AQUÍ"
TELEGRAM_CHAT_ID = "TU_CHAT_ID_AQUÍ"
TELEGRAM_CHANNEL_ID = None  # O tu channel ID como "-1003937741525"

# ─── MODELO AI VISION ────────────────────────────────────────
AI_MODEL = "google/gemma-4-31b-it"

# ─── PARES DE DIVISAS (XAUUSD incluido) ─────────────────────
FOREX_PAIRS = [
    "EURUSD",
    "GBPUSD",
    "USDJPY",
    "AUDUSD",
    "USDCAD",
    "USDCHF",
    "XAUUSD",
]

# ─── TIMEFRAMES ──────────────────────────────────────────────
TIMEFRAME = "M15"
MT5_TIMEFRAME = 15

# ─── PARAMETROS DE ESTRATEGIA v8.1 ──────────────────────────
STRATEGY = {
    "ema_fast": 20,
    "ema_slow": 50,
    "pip_values": {
        "EURUSD": 0.0001, "GBPUSD": 0.0001, "USDJPY": 0.01,
        "AUDUSD": 0.0001, "USDCAD": 0.0001, "USDCHF": 0.0001,
        "XAUUSD": 0.10,
    },
    "digits": {
        "EURUSD": 5, "GBPUSD": 5, "USDJPY": 3,
        "AUDUSD": 5, "USDCAD": 5, "USDCHF": 5,
        "XAUUSD": 2,
    },
}

# ─── GESTION DE RIESGO v8.1 ─────────────────────────────────
RISK = {
    "risk_percent": 1.0,
    "risk_percent_max": 2.0,
    "sl_pips": 18,
    "tp_pips": 45,
    "rr_ratio": 1.0,
    "max_daily_trades": 15,
    "max_open_trades": 3,
    "daily_loss_limit": 999.0,   # SIN LIMITE (modo pruebas)
}

RISK_PER_PAIR = {
    "EURUSD": {"sl_pips": 15, "tp_pips": 15},
    "GBPUSD": {"sl_pips": 18, "tp_pips": 18},
    "USDJPY": {"sl_pips": 15, "tp_pips": 15},
    "AUDUSD": {"sl_pips": 15, "tp_pips": 15},
    "USDCAD": {"sl_pips": 15, "tp_pips": 15},
    "USDCHF": {"sl_pips": 15, "tp_pips": 15},
    "XAUUSD": {"sl_pips": 25, "tp_pips": 25},
}

# ─── SESIONES DE TRADING ─────────────────────────────────────
SESSIONS = {
    "london": {"start": 7, "end": 20},
    "new_york": {"start": 12, "end": 21},
    "asian": {"start": 0, "end": 9},
}

PAIR_SESSIONS = {
    "EURUSD": ["london", "new_york"],
    "GBPUSD": ["london", "new_york"],
    "USDJPY": ["london", "new_york", "asian"],
    "AUDUSD": ["london", "new_york", "asian"],
    "USDCAD": ["london", "new_york"],
    "USDCHF": ["london", "new_york"],
    "XAUUSD": ["london", "new_york"],
}

# ─── AI VISION CONFIG ────────────────────────────────────────
AI_VISION = {
    "enabled": True,
    "min_confidence": 0.65,
    "max_daily_calls": 50,
    "timeout_seconds": 30,
}

# ─── AUTO-TRADING CONFIG v8.4 ─────────────────────────────
AUTO_TRADE = True              # Activar ejecucion automatica en MT5
AUTO_TRADE_VOLUME = 0.01       # Lotes por operacion

# ─── REENTRADA AUTOMATICA v8.4 ─────────────────────────────
# Abre UNA operacion extra cuando el precio se devuelve
# un poco (pullback) y muestra mecha de rechazo
# → Reentrar al precio de descuento!
REENTRY_ENABLED = True
REENTRY_MIN_PULLBACK_PIPS = 3    # Minimo pips de pullback (descuento)
REENTRY_MAX_PULLBACK_PIPS = 20   # Maximo pips de pullback (no mas)
REENTRY_COOLDOWN_SECS = 90       # Segundos minimo despues de entrada
REENTRY_MAX_PER_SIGNAL = 1        # Maximo re-entradas por senal
REENTRY_WICK_MIN_RATIO = 1.5     # Minimo ratio mecha/cuerpo para rechazo

# ─── BOT CONFIG v8.4 ────────────────────────────────────────
BOT = {
    "check_interval": 30,
    "min_timeframe_between_signals": 120,
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
