# ═══════════════════════════════════════════════════════════════
#  TRADING BOT HÍBRIDO — MAIN ENGINE
#  Orquestador principal del sistema
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
        logger.info("  Modo: OHLC Filters + AI Vision Confirmation")
        logger.info("=" * 60)

        # Componentes
        self.mt5 = MT5Connection()
        self.data_feed = None
        self.strategy = None
        self.ai = None
        self.risk = RiskManager()
        self.telegram = TelegramBot()
        self.logger = TradeLogger()
        self.copy_trading = CopyTradingManager()
        self.charts = ChartGenerator()

        # Estado
        self.running = False
        self.signals_sent_today = 0
        self.signals_confirmed_today = 0
        self.trades_today = 0
        self.daily_pnl = 0.0

    def initialize(self) -> bool:
        """Inicializa todos los componentes del bot."""
        logger.info("Iniciando bot...")

        # 1. Conectar MT5
        if not self.mt5.initialize():
            logger.error("No se pudo conectar a MetaTrader 5")
            logger.error("Soluciones: (1) Ejecutar como Admin, (2) MT5 64-bit, (3) Mover fuera de OneDrive")
            return False

        # 2. Inicializar data feed
        self.data_feed = DataFeed(self.mt5)

        # 3. Inicializar estrategia
        self.strategy = StrategyEngine(self.data_feed)

        # 4. Inicializar AI Vision (si está configurado)
        if AI_VISION["enabled"] and "TU_" not in OPENROUTER_API_KEY:
            self.ai = AIVision()
            logger.info("AI Vision habilitado (Gemma 4 31B)")
        else:
            self.ai = None
            logger.warning("AI Vision deshabilitado (sin API key)")

        # 5. Notificar inicio por Telegram
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

        try:
            while self.running:
                self._check_cycle()
                time.sleep(BOT["check_interval"])

        except KeyboardInterrupt:
            logger.info("Bot detenido por el usuario")

        finally:
            self._send_daily_summary()
            self.mt5.shutdown()
            logger.info("Bot apagado correctamente")

    def _check_cycle(self):
        """Ejecuta un ciclo de análisis."""
        # Verificar mercado abierto
        if not self.data_feed.is_market_open():
            return

        balance = self.mt5.get_account_balance()
        if balance is None:
            balance = 0

        # Analizar cada par
        for symbol in FOREX_PAIRS:
            try:
                self._analyze_pair(symbol, balance)
            except Exception as e:
                logger.error(f"Error analizando {symbol}: {e}")

    def _analyze_pair(self, symbol: str, balance: float):
        """Analiza un par de divisas buscando señales."""

        # 1. Ejecutar estrategia OHLC
        signal = self.strategy.analyze(symbol)

        if signal is None or not signal.get("passed"):
            return  # No hay señal

        logger.info(
            f"Señal detectada: {symbol} {signal.get('signal')} "
            f"({signal.get('score')}/{signal.get('max_score')})"
        )

        # 2. Generar gráfico
        df = self.data_feed.get_ohlc(symbol, num_candles=100)
        chart_path = self.charts.generate_chart(df, symbol, signal)

        # 3. Calcular SL/TP y posición
        current_price = signal.get("current_price", 0)
        direction = signal.get("signal")

        if not current_price or not direction:
            return

        levels = self.risk.calculate_sl_tp(current_price, direction, symbol)
        position = self.risk.calculate_position_size(balance, symbol, levels["sl_pips"])

        # Agregar info a la señal
        signal.update({
            "symbol": symbol,
            "sl_price": levels["sl_price"],
            "tp_price": levels["tp_price"],
            "lots": position["lots"],
            "risk_amount": position["risk_amount"],
        })

        # 4. Confirmación AI Vision
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
                return  # AI no confirmó, no enviar señal
        elif not self.ai:
            # Sin AI, enviar si score >= 5 (máximo)
            if signal.get("score", 0) < 5:
                logger.info(f"Sin AI, se requiere score perfecto (5/5) para {symbol}")
                return
            ai_confirmation = {"confirmed": True, "confidence": 1.0, "sweep_quality": "N/A (sin AI)", "rejection_strength": "N/A (sin AI)"}

        # 5. Verificar riesgo
        risk_check = self.risk.can_trade(balance)
        if not risk_check["allowed"]:
            logger.warning(f"Riesgo bloquea operación: {risk_check['reason']}")
            return

        # 6. Enviar señal
        self.signals_sent_today += 1
        self.signals_confirmed_today += 1

        # Enviar por Telegram
        if self.telegram.enabled:
            self.telegram.send_signal(signal)

        # Log
        self.logger.log_signal(signal)

        logger.info(
            f"SEÑAL ENVIADA: {symbol} {direction} | "
            f"SL={levels['sl_price']} TP={levels['tp_price']} | "
            f"Lotes={position['lots']} | "
            f"AI={ai_confirmation.get('confidence', 0):.0%}"
        )

        # 7. Registrar en portafolio copy trading
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
        portfolio = self.copy_trading.get_portfolio_summary()
        readiness = self.copy_trading.is_ready_for_signals()

        summary = {
            "signals_sent": self.signals_sent_today,
            "signals_confirmed": self.signals_confirmed_today,
            "trades_taken": self.trades_today,
            "daily_pnl": self.daily_pnl,
            "win_rate": stats.get("win_rate", 0),
            "best_trade": 0,
            "worst_trade": 0,
        }

        self.telegram.send_daily_summary(summary)

        if readiness["ready"]:
            self.telegram.send_alert(
                "MQL5 SIGNALS READY",
                "Tu portafolio tiene suficientes datos para publicar como señal en MQL5. "
                "Los inversores pueden copiar tus operaciones automáticamente.",
                "SUCCESS"
            )


# ═══════════════════════════════════════════════════════════════
#  PUNTO DE ENTRADA
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    bot = TradingBot()
    bot.run()
