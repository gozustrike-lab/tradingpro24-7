# ═══════════════════════════════════════════════════════════════
#  TRADINGPRO24-7 — MAIN ENGINE v8.3 ICT PRO (FINAL)
#  ═══ S/R Automatico + Auto-ejecucion MT5 ═══
#  ═══ MTF: M5 + M1 para XAUUSD ═══
#  ═══ Deteccion mercado: ALCISTA / BAJISTA / LATERAL ═══
#  ═══ Abre operaciones automaticamente en tu cuenta MT5 ═══
# ═══════════════════════════════════════════════════════════════

import time
import logging
import sys
from datetime import datetime
from pytz import timezone

import MetaTrader5 as mt5

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

# ─── Auto-trading config ─────────────────────────────────────
AUTO_TRADE = getattr(config, 'AUTO_TRADE', True)
AUTO_TRADE_VOLUME = getattr(config, 'AUTO_TRADE_VOLUME', 0.01)


class TradingBot:
    """Bot TradingPro24-7 v8.3 — S/R + MTF + Mercado adaptativo + Auto-trade."""

    def __init__(self):
        logger.info("=" * 60)
        logger.info("  TRADINGPRO24-7 — BOT v8.3 ICT PRO")
        logger.info("  S/R Automatico + S/R Flip + Pullback Entry")
        logger.info("  Deteccion: ALCISTA / BAJISTA / LATERAL")
        logger.info("  XAUUSD: M5 dir + M1 entrada + S/R zones")
        logger.info("  Auto-ejecucion MT5: {}".format("ACTIVADA" if AUTO_TRADE else "DESACTIVADA"))
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
        self.trades_executed = 0
        self.cycle_count = 0

    def initialize(self):
        logger.info("Iniciando bot v8.3...")

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
            logger.warning("AI Vision deshabilitado (falta API key o esta desactivado)")

        # Info de pares
        pair_info = []
        for p in FOREX_PAIRS:
            pc = get_pair_config(p)
            tf = pc["timeframe"]
            mtf = pc.get("mtf_timeframe", "")
            if mtf:
                pair_info.append("{}({}→{})".format(p, mtf, tf))
            else:
                pair_info.append("{}({})".format(p, tf))

        auto_status = "AUTO-TRADE ON ({} lotes)".format(AUTO_TRADE_VOLUME) if AUTO_TRADE else "SOLO SENALES (manual)"
        channel_status = "Canal activo" if TELEGRAM_CHANNEL_ID else "Canal no configurado"

        startup_msg = (
            "TradingPro24-7 v8.3 ICT PRO — INICIADO\n"
            "{}\n"
            "S/R Automatico + Flip + Pullback\n"
            "Mercado adaptativo: ALCISTA/BAJISTA/LATERAL\n"
            "Pares: {}\n"
            "XAUUSD: M5 dir + M1 entrada + S/R zones\n"
            "{}\n"
            "Sin limite de perdidas (pruebas)\n"
            "{}"
        ).format(
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ", ".join(pair_info),
            auto_status,
            channel_status
        )
        self.telegram.enviar_status(startup_msg)

        logger.info("Bot v8.3 inicializado")
        logger.info("Pares: {}".format(", ".join(pair_info)))
        logger.info("Auto-trade: {}".format(auto_status))
        logger.info("Estrategia: S/R + Flip + Mercado Adaptativo")
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
                    logger.info("Ciclo #{} | {} pares | {} senales | {} trades".format(
                        self.cycle_count, len(FOREX_PAIRS),
                        self.signals_sent_today, self.trades_executed))
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
        direction = signal.get("signal")
        current_price = signal.get("current_price", 0)
        mtf_tf = signal.get("mtf_timeframe", "")
        market_condition = signal.get("market_condition", "NORMAL")

        if not current_price or not direction:
            return

        logger.info("SENAL: {} {} [{}] Mercado:{} S/R={:.2f} Flip={}".format(
            symbol, direction, timeframe, market_condition,
            signal.get("sr_level", 0), signal.get("sr_is_flip", False)))

        # Generar grafico CON niveles S/R
        df = self.data_feed.get_ohlc(symbol, num_candles=100, timeframe=timeframe)
        chart_levels = signal.get("chart_levels", {})

        chart_signal_data = {
            "type": direction,
            "sl": signal.get("sl_price"),
            "tp": signal.get("tp_price"),
            "entry": current_price,
            "mode": "SR_FLIP" if signal.get("sr_is_flip") else "SR_PULLBACK",
            "market_condition": market_condition,
            "mtf_direction": signal.get("mtf_direction", ""),
        }

        chart_path = self.charts.generate_candlestick_chart(
            df, symbol, timeframe,
            signal=chart_signal_data,
            chart_levels=chart_levels
        )

        # Niveles SL/TP
        sl_price = signal.get("sl_price")
        tp_price = signal.get("tp_price")
        sl_pips = signal.get("sl_pips")
        tp_pips = signal.get("tp_pips")

        if not sl_price or not tp_price:
            return

        # Confirmacion AI
        ai_confirmation = {"confirmed": True, "confidence": 1.0, "comment": "AI no disponible"}

        if self.ai and chart_path:
            ai_confirmation = self.ai.analyze_chart(chart_path, signal)
            if not ai_confirmation.get("confirmed") and not ai_confirmation.get("skipped"):
                logger.info("AI rechazo: {} ({:.0%})".format(symbol, ai_confirmation.get("confidence", 0)))
                return

        # Enviar senal a Telegram
        self.signals_sent_today += 1
        self.signals_confirmed_today += 1

        tf_label = "{}→{}".format(mtf_tf, timeframe) if mtf_tf else timeframe
        sr_info = signal.get("sr_reason", "")

        conds_list = []
        conds = signal.get("conditions", {})
        for key, val in conds.items():
            if isinstance(val, dict):
                conds_list.append((val.get("passed", False), val.get("detail", key)))

        telegram_signal = {
            "type": direction,
            "mode": "SR_FLIP" if signal.get("sr_is_flip") else "SR_PULLBACK",
            "symbol": symbol,
            "timeframe": tf_label,
            "entry": current_price,
            "sl": sl_price,
            "tp": tp_price,
            "sl_pips": sl_pips,
            "tp_pips": tp_pips,
            "rr": 1.0,
            "score": signal.get("score", 0),
            "ai_confidence": int(ai_confirmation.get("confidence", 0) * 100),
            "ai_comment": ai_confirmation.get("comment", ""),
            "conditions": conds_list,
            "killzone": self._get_current_killzone(),
            "adx_value": 0,
            # Nuevos campos v8.3
            "market_condition": market_condition,
            "sr_reason": sr_info,
            "mtf_direction": signal.get("mtf_direction", ""),
        }

        self.telegram.enviar_senal(telegram_signal, chart_path)
        self.logger.log_signal(signal)

        # ═══ AUTO-EJECUCION EN MT5 ═══
        if AUTO_TRADE:
            logger.info("Ejecutando trade automatico: {} {} @ {}".format(symbol, direction, current_price))
            trade_result = self._execute_trade(symbol, direction, current_price, sl_price, tp_price)
            if trade_result:
                self.trades_executed += 1
                order_id = trade_result.get("order", 0)
                msg = (
                    "TRADE EJECUTADO\n"
                    "{} {} @ {}\n"
                    "SL: {}\n"
                    "TP: {}\n"
                    "Mercado: {}\n"
                    "Ticket: {}\n"
                    "Lotes: {}".format(
                        symbol, direction, current_price,
                        sl_price, tp_price, market_condition,
                        order_id, AUTO_TRADE_VOLUME
                    )
                )
                self.telegram.enviar_status(msg)
                logger.info("TRADE MT5 OK: {} {} @ {} | Ticket: {}".format(
                    symbol, direction, current_price, order_id))
            else:
                logger.warning("Trade fallo: {} {} @ {}".format(symbol, direction, current_price))
                self.telegram.enviar_status("Trade fallo: {} {} | Revisar MT5".format(symbol, direction))

    def _execute_trade(self, symbol, direction, price, sl, tp):
        """Ejecuta la operacion directamente en MT5."""
        try:
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                logger.error("Simbolo no encontrado: {}".format(symbol))
                return None

            # Verificar que el simbolo esta disponible para trading
            if not symbol_info.visible:
                logger.info("Haciendo visible el simbolo: {}".format(symbol))
                if not mt5.symbol_select(symbol, True):
                    logger.error("No se pudo habilitar simbolo: {}".format(symbol))
                    return None

            # Re-obtener info despues de seleccionar
            symbol_info = mt5.symbol_info(symbol)
            digits = symbol_info.digits
            price = round(price, digits)
            sl = round(sl, digits)
            tp = round(tp, digits)

            # Tipo de orden
            if direction == "BUY":
                order_type = mt5.ORDER_TYPE_BUY
                price = mt5.symbol_info_tick(symbol).ask
            else:
                order_type = mt5.ORDER_TYPE_SELL
                price = mt5.symbol_info_tick(symbol).bid

            sl = round(sl, digits)
            tp = round(tp, digits)

            # Request
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": AUTO_TRADE_VOLUME,
                "type": order_type,
                "price": price,
                "sl": sl,
                "tp": tp,
                "deviation": 20,
                "magic": 24701,
                "comment": "TP247_v83",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }

            result = mt5.order_send(request)

            if result is None:
                error = mt5.last_error()
                logger.error("Error enviando orden MT5: {} | Retcode: {}".format(error, error))
                return None

            if result.retcode != mt5.TRADE_RETCODE_DONE:
                logger.error("Orden rechazada: {} - {}".format(result.retcode, result.comment))
                return None

            logger.info("Orden ejecutada: {} {} @ {} | SL={} TP={} | Ticket={}".format(
                symbol, direction, price, sl, tp, result.order))
            return {"order": result.order, "price": result.price}

        except Exception as e:
            logger.error("Error ejecutando trade: {}".format(e))
            return None

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
            "RESUMEN DIARIO v8.3\n"
            "Senales enviadas: {}\n"
            "Trades ejecutados: {}\n"
            "Win rate: {:.0%}\n"
            "Bot TradingPro24-7 v8.3 ICT PRO"
        ).format(
            self.signals_sent_today,
            self.trades_executed,
            stats.get("win_rate", 0)
        )
        self.telegram.enviar_status(summary)


# ═══════════════════════════════════════════════════════════════
#  PUNTO DE ENTRADA
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    bot = TradingBot()
    bot.run()
