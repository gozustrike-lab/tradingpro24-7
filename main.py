# ═══════════════════════════════════════════════════════════════
#  TRADING BOT HÍBRIDO — MAIN ENGINE v7.0
#  Orquestador principal — OHLC + Sweep Alerts + AI Vision
#  Compatible con TelegramBot v7.0 (emojis + canal)
# ═══════════════════════════════════════════════════════════════

import time
import logging
import sys
from datetime import datetime, date
from pytz import timezone

import config
from data_feed import MT5Connection, DataFeed
from strategy import StrategyEngine
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
    """Bot de Trading Hibrido — Motor principal."""

    def __init__(self):
        logger.info("=" * 60)
        logger.info("  TRADINGPRO24-7 — BOT HIBRIDO v7.0")
        logger.info("  Estrategia: ICT Liquidity Sweep + Rango")
        logger.info("  Modo: OHLC + Sweep Alerts + AI Vision + Canal")
        logger.info("=" * 60)

        self.mt5 = MT5Connection()
        self.data_feed = None
        self.strategy = None
        self.ai = None
        self.risk = RiskManager()
        self.charts = ChartGenerator()
        self.logger = TradeLogger()
        self.copy_trading = CopyTradingManager()

        # TelegramBot v7.0 con token, chat_id y channel_id
        self.telegram = TelegramBot(
            token=TELEGRAM_BOT_TOKEN,
            chat_id=TELEGRAM_CHAT_ID,
            channel_id=TELEGRAM_CHANNEL_ID
        )

        self.running = False
        self.signals_sent_today = 0
        self.signals_confirmed_today = 0
        self.sweeps_detected_today = 0
        self.trades_today = 0
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

        # Mensaje de inicio
        channel_status = "Canal activo" if TELEGRAM_CHANNEL_ID else "Canal no configurado"
        startup_msg = (
            "TradingPro24-7 Pro v7.0 - INICIADO\n"
            "{}\n"
            "Modo: ICT Sweep + Rango + FVG + OB + Killzones\n"
            "Monitoreando {} pares en M15\n"
            "Killzones: London Open, NY Open, London Close\n"
            "FVG Detection: Activo\n"
            "Order Blocks: Activo\n"
            "Multi-TF (M15+H1): Activo\n"
            "Graficos con cada senal\n"
            "{}"
        ).format(
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            len(FOREX_PAIRS),
            channel_status
        )
        self.telegram.enviar_status(startup_msg)

        logger.info("Bot inicializado correctamente")
        logger.info("Monitoreando {} pares: {}".format(
            len(FOREX_PAIRS), ", ".join(FOREX_PAIRS)))
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
                    logger.info("Ciclo #{} — Monitoreando activo...".format(self.cycle_count))
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
        """Detecta sweep en curso y envia alerta temprana."""
        sweep = self.strategy.detect_sweep(symbol)
        if sweep is None:
            return

        logger.info("Sweep detectado: {} {} ({})".format(
            symbol, sweep.get("direction"), sweep.get("sweep_level")))

        self.sweeps_detected_today += 1

        # Generar grafico
        df = self.data_feed.get_ohlc(symbol, num_candles=100)
        chart_path = self.charts.generate_sweep_alert_chart(
            df, symbol, "M15", sweep)

        # Enviar alerta al chat privado (no al canal)
        self.telegram.enviar_sweep_alert(symbol, "M15", sweep, chart_path)

    def _analyze_pair(self, symbol, balance):
        """Analiza un par buscando senales completas."""
        signal = self.strategy.analyze(symbol)
        if signal is None or not signal.get("passed"):
            return

        logger.info("Senal detectada: {} {} ({}/{})".format(
            symbol, signal.get("signal"),
            signal.get("score"), signal.get("max_score")))

        # Generar grafico
        df = self.data_feed.get_ohlc(symbol, num_candles=100)
        chart_path = self.charts.generate_candlestick_chart(
            df, symbol, "M15", signal)

        # Calcular SL/TP
        current_price = signal.get("current_price", 0)
        direction = signal.get("signal")
        market_mode = signal.get("market_mode", "TENDENCIA")

        if not current_price or not direction:
            return

        if market_mode == "RANGO" and signal.get("sl_pips") and signal.get("tp_pips"):
            pip_value = STRATEGY["pip_values"].get(symbol, 0.0001)
            if direction == "BUY":
                sl_price = round(current_price - signal["sl_pips"] * pip_value, 5)
                tp_price = round(current_price + signal["tp_pips"] * pip_value, 5)
            else:
                sl_price = round(current_price + signal["sl_pips"] * pip_value, 5)
                tp_price = round(current_price - signal["tp_pips"] * pip_value, 5)
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
                    logger.info("AI rechazo la senal: {} ({:.0%})".format(
                        symbol, ai_confirmation.get("confidence", 0)))
                return
        elif not self.ai:
            if signal.get("score", 0) < 5:
                logger.info("Sin AI, score perfecto requerido (5/5) para {}".format(symbol))
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

        # Enviar senal profesional con emojis al chat Y al canal
        self.signals_sent_today += 1
        self.signals_confirmed_today += 1

        # Construir signal dict para telegram_bot
        telegram_signal = {
            "type": direction,
            "mode": market_mode,
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
            "adx_value": signal.get("adx_value", 0),
            "conditions": [
                (True, "EMA20>50" if signal.get("ema_trend") == "bullish" else "EMA20<50"),
                (signal.get("sweep_passed", False), "Sweep {} pips bajo previo".format(signal.get("sweep_pips", 0))),
                (signal.get("wick_passed", False), "Mecha {:.1f}x sup (min: 2.0x)".format(signal.get("wick_ratio", 0))),
                (signal.get("close_passed", False), "Cierre {:.1f}% del rango".format(signal.get("close_range_pct", 0))),
                (signal.get("pullback_passed", True), "Pullback OK"),
            ]
        }

        self.telegram.enviar_senal(telegram_signal, chart_path)

        self.logger.log_signal(signal)

        logger.info("SENAL ENVIADA: {} {} | SL={} TP={} | Lotes={} | AI={:.0%}".format(
            symbol, direction, levels["sl_price"], levels["tp_price"],
            position["lots"], ai_confirmation.get("confidence", 0)))

        # Copy trading
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
        """Retorna la killzone ICT actual."""
        try:
            utc_now = datetime.now(timezone("UTC"))
            hour = utc_now.hour
            if 2 <= hour <= 5:
                return "Asian Session"
            elif 7 <= hour <= 10:
                return "London Open"
            elif 13 <= hour <= 16:
                return "New York Open"
            elif 19 <= hour <= 21:
                return "London Close"
            return "Fuera de killzone"
        except:
            return "Fuera de killzone"

    def _send_daily_summary(self):
        """Envia resumen diario."""
        stats = self.logger.get_stats()
        summary = (
            "RESUMEN DIARIO\n"
            "Senales enviadas: {}\n"
            "Senales confirmadas: {}\n"
            "Sweeps detectados: {}\n"
            "Win rate: {:.0%}\n"
            "Bot TradingPro24-7 v7.0"
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
