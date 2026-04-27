# ═══════════════════════════════════════════════════════════════
#  TRADING BOT HÍBRIDO — MAIN ENGINE
#  Orquestador principal — OHLC + Sweep Alerts + AI Vision
# ═══════════════════════════════════════════════════════════════

import time
import logging
import sys
from datetime import datetime, date
from pytz import timezone

from config import (
    FOREX_PAIRS, BOT, AI_VISION,
    OPENROUTER_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
)
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


class TradingBot:
    """Bot de Trading Híbrido — Motor principal."""

    def __init__(self):
        logger.info("=" * 60)
        logger.info("  TRADINGPRO24-7 — BOT HÍBRIDO")
        logger.info("  Estrategia: ICT Liquidity Sweep")
        logger.info("  Modo: OHLC + Sweep Alerts + AI Vision")
        logger.info("=" * 60)

        self.mt5 = MT5Connection()
        self.data_feed = None
        self.strategy = None
        self.ai = None
        self.risk = RiskManager()
        self.telegram = TelegramBot()
        self.logger = TradeLogger()
        self.copy_trading = CopyTradingManager()
        self.charts = ChartGenerator()

        self.running = False
        self.signals_sent_today = 0
        self.signals_confirmed_today = 0
        self.sweeps_detected_today = 0
        self.trades_today = 0
        self.daily_pnl = 0.0
        self.cycle_count = 0

    def initialize(self) -> bool:
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

        if self.telegram.enabled:
            self.telegram.send_startup_message()

        logger.info("Bot inicializado correctamente")
        logger.info(f"Monitoreando {len(FOREX_PAIRS)} pares: {', '.join(FOREX_PAIRS)}")
        return True

    def run(self):
        """Bucle principal del bot."""
        if not self.initialize():
            logger.error("No se pudo inicializar el bot. Verifica la conexión con MT5.")
            return

        self.running = True
        logger.info("Bot en ejecución... Presiona Ctrl+C para detener.")
        logger.info("Buscando: Sweep Alerts + Señales Completas con AI Vision")

        try:
            while self.running:
                self._check_cycle()
                self.cycle_count += 1
                # Heartbeat cada 10 ciclos (10 minutos)
                if self.cycle_count % 10 == 0:
                    logger.info(f"Ciclo #{self.cycle_count} — Monitoreando activo...")
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
        """Ejecuta un ciclo de análisis."""
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
                logger.error(f"Error analizando {symbol}: {e}")

    def _detect_sweep_alert(self, symbol: str, balance: float):
        """Detecta sweep en curso y envía alerta temprana."""
        sweep = self.strategy.detect_sweep(symbol)

        if sweep is None:
            return

        logger.info(
            f"Sweep detectado: {symbol} {sweep.get('direction')} "
            f"(barrió {sweep.get('sweep_level')})"
        )

        self.sweeps_detected_today += 1

        # Generar gráfico para la alerta
        df = self.data_feed.get_ohlc(symbol, num_candles=100)
        chart_path = self.charts.generate_chart(df, symbol, {
            "signal": "SELL" if sweep.get("direction") == "SHORT" else "BUY",
            "current_price": sweep.get("current_price"),
        })

        # Enviar alerta con imagen
        if self.telegram.enabled:
            self.telegram.send_sweep_alert(sweep, chart_path)

    def _analyze_pair(self, symbol: str, balance: float):
        """Analiza un par de divisas buscando señales completas."""

        signal = self.strategy.analyze(symbol)

        if signal is None or not signal.get("passed"):
            return

        logger.info(
            f"Señal detectada: {symbol} {signal.get('signal')} "
            f"({signal.get('score')}/{signal.get('max_score')})"
        )

        # Generar gráfico
        df = self.data_feed.get_ohlc(symbol, num_candles=100)
        chart_path = self.charts.generate_chart(df, symbol, signal)

        # Calcular SL/TP y posición
        current_price = signal.get("current_price", 0)
        direction = signal.get("signal")
        market_mode = signal.get("market_mode", "TENDENCIA")

        if not current_price or not direction:
            return

        # Usar SL/TP según el modo (tendencia o rango)
        if market_mode == "RANGO" and signal.get("sl_pips") and signal.get("tp_pips"):
            # Modo rango: usar SL/TP calculados por la estrategia (proporcionales al rango)
            from config import STRATEGY
            pip_value = STRATEGY["pip_values"].get(symbol, 0.0001)
            if direction == "BUY":
                sl_price = round(current_price - signal["sl_pips"] * pip_value, 5)
                tp_price = round(current_price + signal["tp_pips"] * pip_value, 5)
            else:
                sl_price = round(current_price + signal["sl_pips"] * pip_value, 5)
                tp_price = round(current_price - signal["tp_pips"] * pip_value, 5)
            levels = {"sl_price": sl_price, "tp_price": tp_price, "sl_pips": signal["sl_pips"], "tp_pips": signal["tp_pips"]}
        else:
            # Modo tendencia: usar risk manager estándar
            levels = self.risk.calculate_sl_tp(current_price, direction, symbol)

        position = self.risk.calculate_position_size(balance, symbol, levels["sl_pips"])

        signal.update({
            "symbol": symbol,
            "sl_price": levels["sl_price"],
            "tp_price": levels["tp_price"],
            "lots": position["lots"],
            "risk_amount": position["risk_amount"],
        })

        # Confirmación AI Vision
        ai_confirmation = {"confirmed": False, "confidence": 0}

        if self.ai and chart_path:
            ai_confirmation = self.ai.analyze_chart(chart_path, signal)
            signal["ai_confirmation"] = ai_confirmation

            if not ai_confirmation.get("confirmed"):
                if not ai_confirmation.get("skipped"):
                    logger.info(
                        f"AI rechazó la señal: {symbol} "
                        f"(confianza: {ai_confirmation.get('confidence', 0):.0%})"
                    )
                return
        elif not self.ai:
            if signal.get("score", 0) < 5:
                logger.info(f"Sin AI, se requiere score perfecto (5/5) para {symbol}")
                return
            ai_confirmation = {
                "confirmed": True, "confidence": 1.0,
                "sweep_quality": "N/A (sin AI)",
                "rejection_strength": "N/A (sin AI)"
            }

        # Verificar riesgo
        risk_check = self.risk.can_trade(balance)
        if not risk_check["allowed"]:
            logger.warning(f"Riesgo bloquea operación: {risk_check['reason']}")
            return

        # Enviar señal completa con imagen
        self.signals_sent_today += 1
        self.signals_confirmed_today += 1

        if self.telegram.enabled:
            self.telegram.send_signal_with_chart(signal, chart_path)

        self.logger.log_signal(signal)

        logger.info(
            f"SEÑAL ENVIADA: {symbol} {direction} | "
            f"SL={levels['sl_price']} TP={levels['tp_price']} | "
            f"Lotes={position['lots']} | "
            f"AI={ai_confirmation.get('confidence', 0):.0%}"
        )

        # Registrar en portafolio copy trading
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

    def _send_daily_summary(self):
        """Envía resumen diario al apagar el bot."""
        if not self.telegram.enabled:
            return

        stats = self.logger.get_stats()

        summary = {
            "signals_sent": self.signals_sent_today,
            "signals_confirmed": self.signals_confirmed_today,
            "sweeps_detected": self.sweeps_detected_today,
            "trades_taken": self.trades_today,
            "daily_pnl": self.daily_pnl,
            "win_rate": stats.get("win_rate", 0),
            "best_trade": 0,
            "worst_trade": 0,
        }

        self.telegram.send_daily_summary(summary)


# ═══════════════════════════════════════════════════════════════
#  PUNTO DE ENTRADA
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    bot = TradingBot()
    bot.run()
