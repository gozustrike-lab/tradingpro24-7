# ═══════════════════════════════════════════════════════════════
#  TRADING BOT HÍBRIDO — TELEGRAM BOT
#  Envía señales de trading y alertas por Telegram
# ═══════════════════════════════════════════════════════════════

import requests
import logging
from datetime import datetime
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)


class TelegramBot:
    """Bot de Telegram para enviar señales y alertas."""

    BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

    def __init__(self):
        self.token = TELEGRAM_BOT_TOKEN
        self.chat_id = TELEGRAM_CHAT_ID
        self.enabled = bool(self.token and self.chat_id and
                            "TU_" not in str(self.token) and
                            "TU_" not in str(self.chat_id))

    def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """
        Envía un mensaje de texto por Telegram.

        Args:
            text: Texto del mensaje
            parse_mode: "HTML" o "Markdown"

        Returns:
            True si se envió correctamente
        """
        if not self.enabled:
            logger.warning("Telegram no configurado (faltan credenciales)")
            return False

        url = f"{self.BASE_URL}/sendMessage"

        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }

        try:
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                logger.debug("Mensaje enviado a Telegram")
                return True
            else:
                logger.error(f"Telegram error {response.status_code}: {response.text[:200]}")
                return False

        except requests.exceptions.RequestException as e:
            logger.error(f"Error enviando mensaje Telegram: {e}")
            return False

    def send_signal(self, signal_data: dict) -> bool:
        """
        Envía una señal de trading formateada por Telegram.

        Args:
            signal_data: dict con toda la info de la señal
        """
        symbol = signal_data.get("symbol", "???")
        direction = signal_data.get("signal", "???")
        score = signal_data.get("score", 0)
        max_score = signal_data.get("max_score", 5)

        # Emoji según dirección
        if direction == "BUY":
            dir_emoji = "🟢"
            dir_text = "COMPRA (BUY)"
        else:
            dir_emoji = "🔴"
            dir_text = "VENTA (SELL)"

        # Precio y niveles
        price = signal_data.get("current_price", 0)
        sl = signal_data.get("sl_price", 0)
        tp = signal_data.get("tp_price", 0)
        lots = signal_data.get("lots", 0)

        # AI confirmation
        ai = signal_data.get("ai_confirmation", {})
        ai_conf = ai.get("confidence", 0)
        ai_status = "✅" if ai.get("confirmed") else "❌"
        ai_sweep = ai.get("sweep_quality", "N/A")
        ai_rejection = ai.get("rejection_strength", "N/A")

        # Calcular R:R
        if sl and tp and price:
            if direction == "BUY":
                sl_dist = abs(price - sl)
                tp_dist = abs(tp - price)
            else:
                sl_dist = abs(sl - price)
                tp_dist = abs(price - tp)
            rr = tp_dist / sl_dist if sl_dist > 0 else 0
        else:
            rr = 0

        # Timestamp
        now = datetime.now().strftime("%H:%M:%S")

        # Construir mensaje
        message = f"""
<b>🚀 SEÑAL DE TRADING</b>

{dir_emoji} <b>{dir_text}</b>
📊 <b>Par:</b> {symbol}
⏰ <b>Hora:</b> {now}

<b>🎯 Niveles:</b>
💰 Entrada: <code>{price}</code>
🛑 Stop Loss: <code>{sl}</code>
📈 Take Profit: <code>{tp}</code>
📏 R:R: <b>1:{rr:.1f}</b>
📦 Lotes: <b>{lots}</b>

<b>📊 Score OHLC:</b> {score}/{max_score}
🤖 <b>AI Vision:</b> {ai_status} ({ai_conf:.0%})
    Sweep: {ai_sweep} | Rechazo: {ai_rejection}

<b>⚡ Condiciones:</b>"""

        conditions = signal_data.get("conditions", {})
        for key, cond in conditions.items():
            emoji = "✅" if cond.get("passed") else "❌"
            detail = cond.get("detail", "")
            message += f"\n{emoji} {detail}"

        message += f"\n\n<i>Bot TradingPro24-7 — ICT Liquidity Sweep</i>"

        return self.send_message(message.strip())

    def send_alert(self, title: str, message: str, alert_type: str = "INFO") -> bool:
        """
        Envía una alerta genérica.

        Args:
            title: Título de la alerta
            message: Mensaje
            alert_type: "INFO", "WARNING", "ERROR"
        """
        emojis = {
            "INFO": "ℹ️",
            "WARNING": "⚠️",
            "ERROR": "🚨",
            "SUCCESS": "✅",
        }

        emoji = emojis.get(alert_type, "📢")
        now = datetime.now().strftime("%H:%M:%S")

        text = f"""
{emoji} <b>{title}</b>
⏰ {now}

{message}

<i>TradingPro24-7 Bot</i>"""

        return self.send_message(text.strip())

    def send_daily_summary(self, summary: dict) -> bool:
        """Envía resumen diario de operaciones."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        message = f"""
<b>📊 Resumen Diario — {now}</b>

📈 Señales generadas: {summary.get('signals_sent', 0)}
✅ Señales confirmadas AI: {summary.get('signals_confirmed', 0)}
📦 Operaciones: {summary.get('trades_taken', 0)}

💰 PnL del día: <b>${summary.get('daily_pnl', 0):.2f}</b>
🎯 Win rate: {summary.get('win_rate', 0):.0%}
📊 Mejor operación: ${summary.get('best_trade', 0):.2f}
📉 Peor operación: ${summary.get('worst_trade', 0):.2f}

<i>TradingPro24-7 Bot — Resumen automático</i>"""

        return self.send_message(message.strip())

    def send_startup_message(self) -> bool:
        """Envía mensaje de inicio del bot."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message = f"""
<b>🤖 Bot TradingPro24-7 — INICIADO</b>
⏰ {now}
📊 Modo: Híbrido (OHLC + AI Vision)
📡 Monitoreando pares activos...

<i>El bot está analizando el mercado cada 60 segundos.</i>"""

        return self.send_message(message.strip())
