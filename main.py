# ═══════════════════════════════════════════════════════════════
#  TRADING BOT HIBRIDO — MAIN ENGINE v8.1
#  Orquestador — Momentum ICT + XAUUSD M1 + 1:1 R:R
#  Compatible con TelegramBot v7.0 (emojis + canal)
# ═══════════════════════════════════════════════════════════════

import time
import logging
import sys
from datetime import datetime, date
from pytz import timezone

import config
from data_feed import MT5Connection, DataFeed
from strategy import StrategyEngine, get_pair_config
from ai_vision import AIVision
from risk_manager import RiskManager
from telegram_bot import TelegramBot
from trade_logger import TradeLogger
from copy_trading import CopyTradingManager
from chart_generator import ChartGenerator

# ─── Logging ─────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log', encoding='utf-8'),
    ]
)

logger = logging.getLogger("TradingBot")

# ─── Config ──────────────────────────────────────────────────
FOREX_PAIRS = config.FOREX_PAIRS
BOT = config.BOT
AI_VISION = config.AI_VISION
OPENROUTER_API_KEY = config.OPENROUTER_API_KEY
STRATEGY = config.STRATEGY

# Telegram
TELEGRAM_BOT_TOKEN = config.TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID = config.TELEGRAM_CHAT_ID
TELEGRAM_CHANNEL_ID = getattr(config, 'TELEGRAM_CHANNEL_ID', None)


class TradingBot:
    """Bot de Trading Hibrido v8.1 — Momentum ICT + XAUUSD M1."""

    def __init__(self):
        logger.info("=" * 60)
        logger.info("  TRADINGPRO24-7 — BOT MOMENTUM ICT v8.1")
        logger.info("  Estrategia: Momentum + 1:1 R:R Dinamico")
        logger.info("  Pares: Forex M15 + XAUUSD M1")
        logger.info("=" * 60)

        self.mt5 = MT5Connection()
        self.data_feed = None
        self.strategy = None
        self.ai = None
        self.risk = RiskManager()
        self.charts = ChartGenerator()
        self.logger = TradeLogger()
        self.copy_trading = CopyTradingManager()

        # TelegramBot v7.0
        self.telegram = TelegramBot(
            token=TELEGRAM_BOT_TOKEN,
            chat_id=TELEGRAM_CHAT_ID,
            channel_id=TELEGRAM_CHANNEL_ID
        )

        self.running = False
        self.signals_sent_today = 0
        self.signals_confirmed_today = 0
        self.sweeps_detected_today = 0
        self.daily_pnl = 0.0
        self.cycle_count = 0

    def initialize(self):
        """Inicializa todos los componentes del bot."""
        logger.info("Iniciando bot...")

        if not self.mt5.initialize():
            logger.error("No se pudo conectar a MetaTrader 5")
            logger.error("Soluciones: (1) Ejecutar como Admin, (2) MT5 64-bit, (3) Mover fuera de OneDrive")
            return False

        self.data_feed = DataFeed(self.mt5)
        self.strategy = StrategyEngine(self.data_feed)

        if AI_VISION["enabled"] and "TU_" not in OPENROUTER_API_KEY:
            self.ai = AIVision()
            logger.info("AI Vision habilitado (Gemma 4 31B)")
        else:
            self.ai = None
            logger.warning("AI Vision deshabilitado (sin API key)")

        # Mostrar info de pares con timeframe
        pair_info = []
        for p in FOREX_PAIRS:
            pc = get_pair_config(p)
            tf = pc["timeframe"]
            sl = pc["sl_min"]
            pair_info.append(f"{p}({tf})")

        channel_status = "\u2705 Canal activo" if TELEGRAM_CHANNEL_ID else "\u274c Canal no configurado"
        startup_msg = (
            "TradingPro24-7 v8.1 Momentum ICT \u2014 INICIADO\n"
            "\U0001F552 {}\n"
            "\U0001F1EE\U0001F1F9 Estrategia: Momentum + 1:1 R:R Dinamico\n"
            "\U0001F4CA Pares: {}\n"
            "\U0001F4C8 Timeframes: Forex M15 + XAUUSD M1\n"
            "\U0001F3AF Killzones: 5-20 UTC (XAUUSD) / 6-19 UTC (Forex)\n"
            "\U0001F4A7 FVG + OB: Bonus de score\n"
            "\U0001F50D AI Vision: Confirmacion de cada señal\n"
            "\u2705 {}"
        ).format(
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ", ".join(pair_info),
            channel_status
        )
        self.telegram.enviar_status(startup_msg)

        logger.info("Bot inicializado correctamente")
        logger.info("Pares: {} ({})".format(
            len(FOREX_PAIRS), ", ".join(pair_info)))
        logger.info("Canal: {}".format(channel_status))
        return True

    def run(self):
        """Bucle principal del bot."""
        if not self.initialize():
            logger.error("No se pudo inicializar el bot.")
            return

        self.running = True
        logger.info("Bot en ejecucion... Presiona Ctrl+C para detener.")

        try:
            while self.running:
                self._check_cycle()
                self.cycle_count += 1
                if self.cycle_count % 10 == 0:
                    logger.info("Ciclo #{} — Monitoreando {} pares...".format(
                        self.cycle_count, len(FOREX_PAIRS)))
                else:
                    print(".", end="", flush=True)
                time.sleep(BOT["check_interval"])

        except KeyboardInterrupt:
            logger.info("Bot detenido por el usuario")

        finally:
            self._send_daily_summary()
            self.mt5.shutdown()
            logger.info("Bot apagado correctamente")

    def _check_cycle(self):
        """Ejecuta un ciclo de analisis."""
        if not self.data_feed.is_market_open():
            return

        balance = self.mt5.get_account_balance()
        if balance is None:
            balance = 0

        for symbol in FOREX_PAIRS:
            try:
                self._detect_sweep_alert(symbol, balance)
                self._analyze_pair(symbol, balance)
            except Exception as e:
                logger.error("Error analizando {}: {}".format(symbol, e))

    def _detect_sweep_alert(self, symbol, balance):
        """Detecta sweep y envia alerta temprana."""
        sweep = self.strategy.detect_sweep(symbol)
        if sweep is None:
            return

        logger.info("Sweep detectado: {} {} ({})".format(
            symbol, sweep.get("direction"), sweep.get("sweep_level")))

        self.sweeps_detected_today += 1

        pc = get_pair_config(symbol)
        df = self.data_feed.get_ohlc(symbol, num_candles=100, timeframe=pc["timeframe"])
        chart_path = self.charts.generate_sweep_alert_chart(
            df, symbol, pc["timeframe"], sweep)

        self.telegram.enviar_sweep_alert(symbol, pc["timeframe"], sweep, chart_path)

    def _analyze_pair(self, symbol, balance):
        """Analiza un par buscando señales momentum."""
        signal = self.strategy.analyze(symbol)
        if signal is None or not signal.get("passed"):
            return

        timeframe = signal.get("timeframe", "M15")
        logger.info("Senal detectada: {} {} ({}/{}) [{}]".format(
            symbol, signal.get("signal"),
            signal.get("score"), signal.get("max_score"), timeframe))

        # Generar grafico con timeframe correcto
        pc = get_pair_config(symbol)
        df = self.data_feed.get_ohlc(symbol, num_candles=100, timeframe=timeframe)
        chart_path = self.charts.generate_candlestick_chart(
            df, symbol, timeframe, signal)

        # Calcular SL/TP — siempre de la estrategia (1:1)
        current_price = signal.get("current_price", 0)
        direction = signal.get("signal")

        if not current_price or not direction:
            return

        # v8.1: SL/TP siempre de la estrategia
        if signal.get("sl_pips") and signal.get("tp_pips"):
            pip_value = STRATEGY.get("pip_values", {}).get(symbol, 0.0001)
            digits = STRATEGY.get("digits", {}).get(symbol, 5)
            if direction == "BUY":
                sl_price = round(current_price - signal["sl_pips"] * pip_value, digits)
                tp_price = round(current_price + signal["tp_pips"] * pip_value, digits)
            else:
                sl_price = round(current_price + signal["sl_pips"] * pip_value, digits)
                tp_price = round(current_price - signal["tp_pips"] * pip_value, digits)
            levels = {"sl_price": sl_price, "tp_price": tp_price,
                      "sl_pips": signal["sl_pips"], "tp_pips": signal["tp_pips"]}
        else:
            levels = self.risk.calculate_sl_tp(current_price, direction, symbol)

        position = self.risk.calculate_position_size(balance, symbol, levels["sl_pips"])

        # Confirmacion AI Vision
        ai_confirmation = {"confirmed": False, "confidence": 0}

        if self.ai and chart_path:
            ai_confirmation = self.ai.analyze_chart(chart_path, signal)
            signal["ai_confirmation"] = ai_confirmation

            if not ai_confirmation.get("confirmed"):
                if not ai_confirmation.get("skipped"):
                    logger.info("AI rechazo la senal: {} ({:.0%}) [{}]".format(
                        symbol, ai_confirmation.get("confidence", 0), timeframe))
                return
        elif not self.ai:
            max_score = signal.get("max_score", 4)
            if signal.get("score", 0) < max_score:
                logger.info("Sin AI, score perfecto ({}/{}) para {} [{}]".format(
                    signal.get("score", 0), max_score, symbol, timeframe))
                return
            ai_confirmation = {
                "confirmed": True, "confidence": 1.0,
                "sweep_quality": "N/A (sin AI)",
                "rejection_strength": "N/A (sin AI)"
            }

        # Verificar riesgo
        risk_check = self.risk.can_trade(balance)
        if not risk_check["allowed"]:
            logger.warning("Riesgo bloquea operacion: {}".format(risk_check["reason"]))
            return

        # Enviar señal
        self.signals_sent_today += 1
        self.signals_confirmed_today += 1

        telegram_signal = {
            "type": direction,
            "mode": "MOMENTUM",
            "symbol": symbol,
            "entry": current_price,
            "sl": levels["sl_price"],
            "tp": levels["tp_price"],
            "sl_pips": levels["sl_pips"],
            "tp_pips": levels["tp_pips"],
            "rr": round(levels["tp_pips"] / max(levels["sl_pips"], 1), 1),
            "score": signal.get("score", 0),
            "ai_confidence": int(ai_confirmation.get("confidence", 0) * 100),
            "ai_comment": ai_confirmation.get("comment", ""),
            "sweep_pips": signal.get("sweep_pips", 0),
            "wick_ratio": signal.get("wick_ratio", 0),
            "close_range_pct": signal.get("close_range_pct", 0),
            "pullback_pips": signal.get("pullback_pips", 0),
            "rejection": ai_confirmation.get("rejection_strength", "fuerte"),
            "killzone": self._get_current_killzone(),
            "conditions": [
                (True, "EMA{}>{}".format(pc["ema_fast"], pc["ema_slow"]) if signal.get("ema_trend") == "bullish" else "EMA{}<{}".format(pc["ema_fast"], pc["ema_slow"])),
                (signal.get("sweep_passed", False), "Sweep {} pips".format(signal.get("sweep_pips", 0))),
                (signal.get("wick_passed", False), "Mecha {:.1f}x".format(signal.get("wick_ratio", 0))),
                (signal.get("close_passed", False), "Cierre {:.1f}%".format(signal.get("close_range_pct", 0))),
                (signal.get("pullback_passed", True), "Pullback OK"),
            ]
        }

        self.telegram.enviar_senal(telegram_signal, chart_path)
        self.logger.log_signal(signal)

        logger.info("SENAL ENVIADA: {} {} [{}] | SL={} TP={} | 1:1 | AI={:.0%}".format(
            symbol, direction, timeframe, levels["sl_price"], levels["tp_price"],
            ai_confirmation.get("confidence", 0)))

        self.copy_trading.add_trade_to_portfolio({
            "symbol": symbol,
            "signal": direction,
            "entry": current_price,
            "sl": levels["sl_price"],
            "tp": levels["tp_price"],
            "lots": position["lots"],
            "ai_confidence": ai_confirmation.get("confidence", 0),
            "score": signal.get("score", 0),
        })

    def _get_current_killzone(self):
        """Killzone actual v8.1."""
        try:
            utc_now = datetime.now(timezone("UTC"))
            hour = utc_now.hour
            if 5 <= hour < 12:
                return "London Open"
            elif 12 <= hour < 17:
                return "NY Open"
            elif 15 <= hour < 20:
                return "London Close"
            return "Fuera de killzone"
        except Exception:
            return "Fuera de killzone"

    def _send_daily_summary(self):
        """Resumen diario."""
        stats = self.logger.get_stats()
        summary = (
            "RESUMEN DIARIO v8.1\n"
            "Senales enviadas: {}\n"
            "Senales confirmadas: {}\n"
            "Sweeps detectados: {}\n"
            "Win rate: {:.0%}\n"
            "Bot TradingPro24-7 v8.1 Momentum ICT"
        ).format(
            self.signals_sent_today,
            self.signals_confirmed_today,
            self.sweeps_detected_today,
            stats.get("win_rate", 0)
        )
        self.telegram.enviar_status(summary)


# ═══════════════════════════════════════════════════════════════
#  PUNTO DE ENTRADA
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    bot = TradingBot()
    bot.run()
