# ═══════════════════════════════════════════════════════════════
#  TRADINGPRO24-7 — MAIN ENGINE v8.4 ICT PRO + REENTRADA
#  ═══ S/R Automatico + Auto-ejecucion MT5 ═══
#  ═══ MTF: M5 + M1 para XAUUSD ═══
#  ═══ Deteccion mercado: ALCISTA / BAJISTA / LATERAL ═══
#  ═══ Pattern Recognition: Ondas / Montañitas ═══
#  ═══ REENTRADA AUTOMATICA (1 extra a favor) ═══
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

# ─── Re-entrada config (PULLBACK / DESCUENTO) ──────────────
REENTRY_ENABLED = getattr(config, 'REENTRY_ENABLED', True)
REENTRY_MIN_PULLBACK_PIPS = getattr(config, 'REENTRY_MIN_PULLBACK_PIPS', 3)
REENTRY_MAX_PULLBACK_PIPS = getattr(config, 'REENTRY_MAX_PULLBACK_PIPS', 20)
REENTRY_COOLDOWN_SECS = getattr(config, 'REENTRY_COOLDOWN_SECS', 90)
REENTRY_MAX_PER_SIGNAL = getattr(config, 'REENTRY_MAX_PER_SIGNAL', 1)
REENTRY_WICK_MIN_RATIO = getattr(config, 'REENTRY_WICK_MIN_RATIO', 1.5)

MAGIC_NUMBER = 24701


class TradingBot:
    """Bot TradingPro24-7 v8.4 — S/R + Ondas + Reentrada automatica."""

    def __init__(self):
        logger.info("=" * 60)
        logger.info("  TRADINGPRO24-7 — BOT v8.4 ICT PRO + REENTRADA")
        logger.info("  S/R Automatico + S/R Flip + Pullback Entry")
        logger.info("  Pattern Recognition: Ondas / Montañitas")
        logger.info("  Deteccion: ALCISTA / BAJISTA / LATERAL")
        logger.info("  XAUUSD: M5 dir + M1 entrada + S/R zones")
        logger.info("  Auto-ejecucion MT5: {}".format("ACTIVADA" if AUTO_TRADE else "DESACTIVADA"))
        logger.info("  Re-entrada auto: {}".format("ACTIVADA (pullback {}-{} pips)".format(REENTRY_MIN_PULLBACK_PIPS, REENTRY_MAX_PULLBACK_PIPS) if REENTRY_ENABLED else "DESACTIVADA"))
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
        self.reentries_executed = 0
        self.cycle_count = 0

        # Tracking de trades para re-entrada
        # {symbol: {direction, entry_price, ticket, timestamp, reentry_done}}
        self.active_trades = {}

    def initialize(self):
        logger.info("Iniciando bot v8.4...")

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

        # Cargar trades abiertos existentes del bot
        self._load_existing_trades()

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
        reentry_status = "REENTRADA ON (pullback {}-{} pips + mecha)".format(
            REENTRY_MIN_PULLBACK_PIPS, REENTRY_MAX_PULLBACK_PIPS) if REENTRY_ENABLED else "REENTRADA OFF"
        channel_status = "Canal activo" if TELEGRAM_CHANNEL_ID else "Canal no configurado"

        startup_msg = (
            "TradingPro24-7 v8.4 ICT PRO — INICIADO\n"
            "{}\n"
            "S/R + Flip + Ondas + Mercado Adaptativo\n"
            "Lateral / Alcista / Bajista\n"
            "Pares: {}\n"
            "XAUUSD: M5 dir + M1 entrada + S/R\n"
            "{}\n"
            "{}\n"
            "{}"
        ).format(
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ", ".join(pair_info),
            auto_status, reentry_status, channel_status
        )
        self.telegram.enviar_status(startup_msg)

        logger.info("Bot v8.4 inicializado")
        logger.info("Pares: {}".format(", ".join(pair_info)))
        logger.info("Auto-trade: {}".format(auto_status))
        logger.info("Re-entrada: {}".format(reentry_status))
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
                    logger.info("Ciclo #{} | {} pares | {} senales | {} trades | {} reentradas".format(
                        self.cycle_count, len(FOREX_PAIRS),
                        self.signals_sent_today, self.trades_executed,
                        self.reentries_executed))
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

        # Limpiar trades cerrados del tracking
        self._cleanup_closed_trades()

        for symbol in FOREX_PAIRS:
            try:
                self._analyze_pair(symbol, balance)
            except Exception as e:
                logger.error("Error analizando {}: {}".format(symbol, e))

            # Verificar re-entrada para trades activos
            if REENTRY_ENABLED and AUTO_TRADE:
                try:
                    self._check_reentry(symbol)
                except Exception as e:
                    logger.error("Error re-entrada {}: {}".format(symbol, e))

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

        # Si ya hay un trade activo en este par, no abrir otro (esperar re-entrada)
        if symbol in self.active_trades:
            logger.debug("[{}] Trade activo existente, saltando nueva senal".format(symbol))
            return

        logger.info("SENAL: {} {} [{}] Mercado:{} S/R={:.2f} Flip={}".format(
            symbol, direction, timeframe, market_condition,
            signal.get("sr_level", 0), signal.get("sr_is_flip", False)))

        # Generar grafico CON niveles S/R y ondas
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

        wave_data = signal.get("wave_pattern", {})

        chart_path = self.charts.generate_candlestick_chart(
            df, symbol, timeframe,
            signal=chart_signal_data,
            chart_levels=chart_levels,
            wave_data=wave_data
        )

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
            "market_condition": market_condition,
            "sr_reason": sr_info,
            "mtf_direction": signal.get("mtf_direction", ""),
            "wave_pattern": signal.get("wave_pattern", ""),
            "wave_repetitions": wave_data.get("repetitions", 0),
            "wave_exhaustion": wave_data.get("exhaustion", False),
            "wave_move_type": wave_data.get("move_type", ""),
        }

        self.telegram.enviar_senal(telegram_signal, chart_path)
        self.logger.log_signal(signal)

        # ═══ AUTO-EJECUCION EN MT5 ═══
        if AUTO_TRADE:
            logger.info("Ejecutando trade automatico: {} {} @ {}".format(symbol, direction, current_price))
            trade_result = self._execute_trade(symbol, direction, current_price, sl_price, tp_price, is_reentry=False)
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

                # Registrar trade activo para re-entrada
                self.active_trades[symbol] = {
                    "direction": direction,
                    "entry_price": trade_result.get("price", current_price),
                    "ticket": order_id,
                    "timestamp": datetime.now(),
                    "reentry_done": False,
                    "reentry_count": 0,
                    "sl_price": sl_price,
                    "tp_price": tp_price,
                    "signal": signal,
                }
            else:
                logger.warning("Trade fallo: {} {} @ {}".format(symbol, direction, current_price))
                self.telegram.enviar_status("Trade fallo: {} {} | Revisar MT5".format(symbol, direction))

    # ═══════════════════════════════════════════════════════════
    #  REENTRADA AUTOMATICA — PULLBACK / DESCUENTO
    # ═══════════════════════════════════════════════════════════

    def _check_reentry(self, symbol: str):
        """
        Re-entrada cuando el precio se devuelve un poco EN CONTRA
        y muestra señal de rechazo (mecha) en zona de favor.

        Ejemplo:
        - Entrada original: BUY @ 4595
        - Precio sube a 4605
        - Precio se devuelve a 4598 (pullback)
        - En 4598 hay mecha de rechazo (compradores entrando)
        - → REENTRADA BUY @ 4598 (precio de descuento!)

        Condiciones:
        1. Trade activo abierto por el bot
        2. No se ha hecho re-entrada ya
        3. Tiempo minimo desde la entrada (90 seg)
        4. Precio se ha devuelto entre 3-20 pips en contra (pullback)
        5. Vela actual muestra MECHA DE RECHAZO a favor
        6. EMA sigue confirmando la direccion original
        """
        if symbol not in self.active_trades:
            return

        trade = self.active_trades[symbol]

        # Ya se hizo re-entrada para este trade?
        if trade["reentry_count"] >= REENTRY_MAX_PER_SIGNAL:
            return

        # Tiempo minimo desde entrada
        elapsed = (datetime.now() - trade["timestamp"]).total_seconds()
        if elapsed < REENTRY_COOLDOWN_SECS:
            return

        # Obtener datos del trade activo
        direction = trade["direction"]
        entry_price = trade["entry_price"]
        pip_value = STRATEGY.get("pip_values", {}).get(symbol, 0.0001)

        # Precio actual
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return

        current_price = tick.ask if direction == "BUY" else tick.bid

        # ── Calcular pullback (precio devuelto EN CONTRA) ──
        if direction == "BUY":
            pullback_pips = (entry_price - current_price) / pip_value
        else:
            pullback_pips = (current_price - entry_price) / pip_value

        # El pullback debe ser NEGATIVO (precio en contra) pero no demasiado
        # pullback_pips > 0 significa el precio esta debajo de la entrada (para BUY)
        if pullback_pips < REENTRY_MIN_PULLBACK_PIPS:
            # El precio no se ha devuelto lo suficiente, no hay descuento
            return

        if pullback_pips > REENTRY_MAX_PULLBACK_PIPS:
            # El precio se devolvió demasiado, es peligroso reentrar
            logger.debug("[{}] Re-entrada: pullback {} pips excede maximo {}".format(
                symbol, round(pullback_pips, 1), REENTRY_MAX_PULLBACK_PIPS))
            return

        # ── Verificar mecha de rechazo (señal de que el precio rebota) ──
        pc = get_pair_config(symbol)
        df = self.data_feed.get_ohlc(symbol, num_candles=50, timeframe=pc["timeframe"])
        if df is None or len(df) < 5:
            return

        last_candle = df.iloc[-1]
        wick_info = self._check_rejection_wick(last_candle, direction, pip_value)

        if not wick_info["rejected"]:
            # No hay mecha de rechazo, el precio sigue cayendo
            return

        # ── Verificar que EMA sigue confirmando direccion original ──
        if direction == "BUY":
            trend_ok = self._quick_bullish_check(df, pc)
        else:
            trend_ok = self._quick_bearish_check(df, pc)

        if not trend_ok:
            logger.debug("[{}] Re-entrada: EMA no confirma {} despues de pullback".format(
                symbol, direction))
            return

        # ═══ TODAS LAS CONDICIONES CUMPLIDAS — EJECUTAR REENTRADA ═══
        logger.info("REENTRADA: {} {} | Pullback: -{} pips (descuento) | Mecha: {:.1f}x".format(
            symbol, direction, round(pullback_pips, 1), wick_info["ratio"]))

        # SL/TP: ajustar al precio de re-entrada (descuento)
        digits = STRATEGY.get("digits", {}).get(symbol, 5)
        original_sl_pips = abs(entry_price - trade["sl_price"]) / pip_value
        original_tp_pips = abs(trade["tp_price"] - entry_price) / pip_value

        if direction == "BUY":
            new_sl = round(current_price - original_sl_pips * pip_value, digits)
            new_tp = round(current_price + original_tp_pips * pip_value, digits)
        else:
            new_sl = round(current_price + original_sl_pips * pip_value, digits)
            new_tp = round(current_price - original_tp_pips * pip_value, digits)

        trade_result = self._execute_trade(symbol, direction, current_price, new_sl, new_tp, is_reentry=True)
        if trade_result:
            self.reentries_executed += 1
            trade["reentry_count"] += 1
            order_id = trade_result.get("order", 0)

            msg = (
                "REENTRADA EN DESCUENTO\n"
                "{} {} @ {}\n"
                "Original: {} @ {}\n"
                "Pullback: -{} pips (descuento!)\n"
                "Mecha rechazo: {:.1f}x\n"
                "SL: {}\n"
                "TP: {}\n"
                "Ticket: {}\n"
                "Lotes: {}".format(
                    symbol, direction, current_price,
                    direction, entry_price, round(pullback_pips, 1),
                    wick_info["ratio"],
                    new_sl, new_tp, order_id, AUTO_TRADE_VOLUME
                )
            )
            self.telegram.enviar_status(msg)
            logger.info("REENTRADA OK: {} {} @ {} (descuento -{} pips) | Ticket: {}".format(
                symbol, direction, current_price, round(pullback_pips, 1), order_id))
        else:
            logger.warning("Re-entrada fallo: {} {}".format(symbol, direction))

    def _check_rejection_wick(self, candle, direction: str, pip_value: float) -> dict:
        """
        Verifica si la vela actual tiene mecha de rechazo a favor.
        Para BUY: mecha inferior grande = rechazo de vendedores
        Para SELL: mecha superior grande = rechazo de compradores
        """
        o, h, l, c = candle['open'], candle['high'], candle['low'], candle['close']
        body_top = max(o, c)
        body_bottom = min(o, c)
        body_size = body_top - body_bottom

        if direction == "BUY":
            # Mecha inferior (rechazo vendedores)
            lower_wick = body_bottom - l
            upper_wick = h - body_top
            if lower_wick <= 0:
                return {"rejected": False, "ratio": 0, "wick_pips": 0}
            ratio = lower_wick / body_size if body_size > 0 else lower_wick / pip_value
            wick_pips = lower_wick / pip_value
            return {
                "rejected": ratio >= REENTRY_WICK_MIN_RATIO or wick_pips >= 2,
                "ratio": round(ratio, 2),
                "wick_pips": round(wick_pips, 1),
                "type": "lower_wick"
            }
        else:
            # Mecha superior (rechazo compradores)
            upper_wick = h - body_top
            lower_wick = body_bottom - l
            if upper_wick <= 0:
                return {"rejected": False, "ratio": 0, "wick_pips": 0}
            ratio = upper_wick / body_size if body_size > 0 else upper_wick / pip_value
            wick_pips = upper_wick / pip_value
            return {
                "rejected": ratio >= REENTRY_WICK_MIN_RATIO or wick_pips >= 2,
                "ratio": round(ratio, 2),
                "wick_pips": round(wick_pips, 1),
                "type": "upper_wick"
            }

    def _quick_bullish_check(self, df, pc) -> bool:
        """Verificacion rapida de momento alcista."""
        ema_f = df['close'].ewm(span=pc["ema_fast"], adjust=False).mean()
        ema_s = df['close'].ewm(span=pc["ema_slow"], adjust=False).mean()
        return ema_f.iloc[-1] > ema_s.iloc[-1] and ema_f.iloc[-1] > ema_f.iloc[-3]

    def _quick_bearish_check(self, df, pc) -> bool:
        """Verificacion rapida de momento bajista."""
        ema_f = df['close'].ewm(span=pc["ema_fast"], adjust=False).mean()
        ema_s = df['close'].ewm(span=pc["ema_slow"], adjust=False).mean()
        return ema_f.iloc[-1] < ema_s.iloc[-1] and ema_f.iloc[-1] < ema_f.iloc[-3]

    def _load_existing_trades(self):
        """Carga trades abiertos del bot al iniciar (por si se reinicio)."""
        if not AUTO_TRADE:
            return
        try:
            positions = mt5.positions_get()
            if positions is None:
                return

            for pos in positions:
                if pos.magic == MAGIC_NUMBER and pos.symbol in FOREX_PAIRS:
                    direction = "BUY" if pos.type == mt5.ORDER_TYPE_BUY else "SELL"
                    self.active_trades[pos.symbol] = {
                        "direction": direction,
                        "entry_price": pos.price_open,
                        "ticket": pos.ticket,
                        "timestamp": datetime.now(),
                        "reentry_done": False,
                        "reentry_count": 0,
                        "sl_price": pos.sl,
                        "tp_price": pos.tp,
                        "signal": {},
                    }
                    logger.info("Trade activo cargado: {} {} @ {} | Ticket: {}".format(
                        pos.symbol, direction, pos.price_open, pos.ticket))
        except Exception as e:
            logger.error("Error cargando trades: {}".format(e))

    def _cleanup_closed_trades(self):
        """Elimina trades cerrados del tracking."""
        closed = []
        for symbol, trade in self.active_trades.items():
            # Verificar si la posicion sigue abierta
            try:
                pos = mt5.positions_get(ticket=trade["ticket"])
                if pos is None or len(pos) == 0:
                    closed.append(symbol)
                    logger.info("Trade cerrado: {} | Ticket: {}".format(symbol, trade["ticket"]))
            except Exception:
                pass

        for symbol in closed:
            del self.active_trades[symbol]

    # ═══════════════════════════════════════════════════════════
    #  EJECUCION DE TRADES
    # ═══════════════════════════════════════════════════════════

    def _execute_trade(self, symbol, direction, price, sl, tp, is_reentry=False):
        """Ejecuta la operacion directamente en MT5."""
        try:
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                logger.error("Simbolo no encontrado: {}".format(symbol))
                return None

            if not symbol_info.visible:
                logger.info("Haciendo visible el simbolo: {}".format(symbol))
                if not mt5.symbol_select(symbol, True):
                    logger.error("No se pudo habilitar simbolo: {}".format(symbol))
                    return None

            symbol_info = mt5.symbol_info(symbol)
            digits = symbol_info.digits
            price = round(price, digits)
            sl = round(sl, digits)
            tp = round(tp, digits)

            if direction == "BUY":
                order_type = mt5.ORDER_TYPE_BUY
                price = mt5.symbol_info_tick(symbol).ask
            else:
                order_type = mt5.ORDER_TYPE_SELL
                price = mt5.symbol_info_tick(symbol).bid

            sl = round(sl, digits)
            tp = round(tp, digits)

            # Comment diferente para re-entrada
            comment = "TP247_v84_RE" if is_reentry else "TP247_v84"

            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": AUTO_TRADE_VOLUME,
                "type": order_type,
                "price": price,
                "sl": sl,
                "tp": tp,
                "deviation": 20,
                "magic": MAGIC_NUMBER,
                "comment": comment,
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }

            result = mt5.order_send(request)

            if result is None:
                error = mt5.last_error()
                logger.error("Error enviando orden: {}".format(error))
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
            "RESUMEN DIARIO v8.4\n"
            "Senales enviadas: {}\n"
            "Trades ejecutados: {}\n"
            "Reentradas: {}\n"
            "Win rate: {:.0%}\n"
            "Bot TradingPro24-7 v8.4 ICT PRO + Reentrada"
        ).format(
            self.signals_sent_today,
            self.trades_executed,
            self.reentries_executed,
            stats.get("win_rate", 0)
        )
        self.telegram.enviar_status(summary)


# ═══════════════════════════════════════════════════════════════
#  PUNTO DE ENTRADA
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    bot = TradingBot()
    bot.run()
