# ═══════════════════════════════════════════════════════════════
#  TRADINGPRO24-7 — MAIN ENGINE v8.2 MOMENTUM ICT + MTF
#  ═══ XAUUSD: M5 confirma + M1 entra ═══
#  ═══ Forex: M15 directo ═══
#  ═══ SIN limite de perdidas (modo pruebas) ═══
# ═════════════════════════════════════════════════════════════════

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

TELEGRAM_BOT_TOKEN = config.TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID = config.TELEGRAM_CHAT_ID
TELEGRAM_CHANNEL_ID = getattr(config, 'TELEGRAM_CHANNEL_ID', None)


class TradingBot:
    """Bot TradingPro24-7 v8.2 — Momentum ICT + Multi-Timeframe."""

    def __init__(self):
        logger.info("=" * 60)
        logger.info("  TRADINGPRO24-7 — BOT v8.2 MOMENTUM ICT + MTF")
        logger.info("  XAUUSD: M5 direccion + M1 entrada (precicion maxima)")
        logger.info("  Forex: M15 directo")
        logger.info("  SIN limite de perdidas (modo pruebas)")
        logger.info("=" * 60)

        self.mt5 = MT5Connection()
        self.data_feed = None
        self.strategy = None
        self.ai = None
        self.risk = RiskManager()
        self.charts = ChartGenerator()
        self.logger = TradeLogger()
        self.copy_trading = CopyTradingManager()

        self.telegram = TelegramBot(
            token=TELEGRAM_BOT_TOKEN,
            chat_id=TELEGRAM_CHAT_ID,
            channel_id=TELEGRAM_CHANNEL_ID
        )

        self.running = False
        self.signals_sent_today = 0
        self.signals_confirmed_today = 0
        self.cycle_count = 0

    def initialize(self):
        logger.info("Iniciando bot v8.2...")

        if not self.mt5.initialize():
            logger.error("No se pudo conectar a MetaTrader 5")
            return False

        self.data_feed = DataFeed(self.mt5)
        self.strategy = StrategyEngine(self.data_feed)

        if AI_VISION["enabled"] and "TU_" not in OPENROUTER_API_KEY:
            self.ai = AIVision()
            logger.info("AI Vision habilitado (Gemma 4 31B)")
        else:
            self.ai = None
            logger.warning("AI Vision deshabilitado (sin API key)")

        # Info de pares con timeframe
        pair_info = []
        for p in FOREX_PAIRS:
            pc = get_pair_config(p)
            tf = pc["timeframe"]
            mtf = pc.get("mtf_timeframe", "")
            if mtf:
                pair_info.append("{}({}->{})".format(p, mtf, tf))
            else:
                pair_info.append("{}({})".format(p, tf))

        channel_status = "Canal activo" if TELEGRAM_CHANNEL_ID else "Canal no configurado"
        startup_msg = (
            "TradingPro24-7 v8.2 MTF \u2014 INICIADO\n"
            "\U0001F552 {}\n"
            "\U0001F7E9 XAUUSD: M5 direccion + M1 entrada (precicion)\n"
            "\U0001F4CA Pares: {}\n"
            "\U0001F4F6 Score min: 2/4 | R:R: 1:1\n"
            "\U0001F3AF Killzones: 15h (5-20 UTC)\n"
            "\u26A0\uFE0F MODO PRUEBAS: Sin limite de perdidas\n"
            "\u2705 {}"
        ).format(
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ", ".join(pair_info),
            channel_status
        )
        self.telegram.enviar_status(startup_msg)

        logger.info("Bot v8.2 inicializado")
        logger.info("Pares: {}".format(", ".join(pair_info)))
        return True

    def run(self):
        if not self.initialize():
            logger.error("No se pudo inicializar el bot.")
            return

        self.running = True
        logger.info("Bot en ejecucion... Ctrl+C para detener.")

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
        if not self.data_feed.is_market_open():
            return

        balance = self.mt5.get_account_balance()
        if balance is None:
            balance = 0

        for symbol in FOREX_PAIRS:
            try:
                self._analyze_pair(symbol, balance)
            except Exception as e:
                logger.error("Error analizando {}: {}".format(symbol, e))

    def _analyze_pair(self, symbol, balance):
        signal = self.strategy.analyze(symbol)
        if signal is None or not signal.get("passed"):
            return

        pc = get_pair_config(symbol)
        timeframe = signal.get("timeframe", pc["timeframe"])
        mtf_tf = signal.get("mtf_timeframe", "")

        logger.info("SENAL: {} {} ({}/4) [{}{}→{}]".format(
            symbol, signal.get("signal"),
            signal.get("score"),
            mtf_tf + "+" if mtf_tf else "",
            mtf_tf if mtf_tf else "",
            timeframe))

        # Generar grafico
        df = self.data_feed.get_ohlc(symbol, num_candles=100, timeframe=timeframe)
        chart_path = self.charts.generate_candlestick_chart(
            df, symbol, timeframe, {
                "type": signal["signal"],
                "sl": signal.get("sl_price"),
                "tp": signal.get("tp_price"),
            })

        current_price = signal.get("current_price", 0)
        direction = signal.get("signal")

        if not current_price or not direction:
            return

        # SL/TP desde estrategia (1:1)
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
                    logger.info("AI rechazo: {} ({:.0%})".format(
                        symbol, ai_confirmation.get("confidence", 0)))
                return
        elif not self.ai:
            # Sin AI, aceptar si score >= 2
            ai_confirmation = {
                "confirmed": True, "confidence": 1.0,
                "comment": "Sin AI (score >= 2)"
            }

        # Verificar riesgo
        risk_check = self.risk.can_trade(balance)
        if not risk_check["allowed"]:
            logger.warning("Riesgo bloquea: {}".format(risk_check["reason"]))
            return

        # Enviar senal
        self.signals_sent_today += 1
        self.signals_confirmed_today += 1

        # Construir condiciones para Telegram
        conds_list = []
        conds = signal.get("conditions", {})

        # Agregar MTF como primera condicion
        if mtf_tf:
            mtf_dir = signal.get("mtf_direction", "")
            mtf_score = signal.get("mtf_score", 0)
            conds_list.append((True, "M5 confirma {} ({}/4)".format(mtf_dir, mtf_score)))

        for key, val in conds.items():
            if isinstance(val, dict) and key != "mtf_confirm":
                conds_list.append((val.get("passed", False), val.get("detail", key)))

        # Timeframe label para Telegram
        tf_label = "{}+{}→{}".format(mtf_tf, timeframe, timeframe) if mtf_tf else timeframe

        telegram_signal = {
            "type": direction,
            "mode": "MOMENTUM",
            "symbol": symbol,
            "timeframe": tf_label,
            "entry": current_price,
            "sl": levels["sl_price"],
            "tp": levels["tp_price"],
            "sl_pips": levels["sl_pips"],
            "tp_pips": levels["tp_pips"],
            "rr": 1.0,
            "score": signal.get("score", 0),
            "ai_confidence": int(ai_confirmation.get("confidence", 0) * 100),
            "ai_comment": ai_confirmation.get("comment", ""),
            "conditions": conds_list,
            "killzone": self._get_current_killzone(),
            "adx_value": 0,
        }

        self.telegram.enviar_senal(telegram_signal, chart_path)
        self.logger.log_signal(signal)

        logger.info("ENVIADA: {} {} | SL={} TP={} | 1:1 | AI={:.0%}".format(
            symbol, direction, levels["sl_price"], levels["tp_price"],
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
        stats = self.logger.get_stats()
        summary = (
            "RESUMEN DIARIO v8.2 MTF\n"
            "Senales enviadas: {}\n"
            "Senales confirmadas: {}\n"
            "Win rate: {:.0%}\n"
            "Bot TradingPro24-7 v8.2"
        ).format(
            self.signals_sent_today,
            self.signals_confirmed_today,
            stats.get("win_rate", 0)
        )
        self.telegram.enviar_status(summary)


# ═══════════════════════════════════════════════════════════════
#  PUNTO DE ENTRADA
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    bot = TradingBot()
    bot.run()
