# ═══════════════════════════════════════════════════════════════
#  TRADING BOT HÍBRIDO — TELEGRAM BOT
#  Envía señales, alertas de sweep y gráficos por Telegram
# ═══════════════════════════════════════════════════════════════

import requests
import os
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
        """Envía un mensaje de texto por Telegram."""
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

    def send_photo(self, image_path: str, caption: str = "") -> bool:
        """
        Envía una imagen con caption por Telegram.

        Args:
            image_path: Ruta a la imagen
            caption: Texto opcional debajo de la imagen

        Returns:
            True si se envió correctamente
        """
        if not self.enabled:
            return False

        if not os.path.exists(image_path):
            logger.error(f"Imagen no encontrada: {image_path}")
            return False

        url = f"{self.BASE_URL}/sendPhoto"

        try:
            with open(image_path, "rb") as img_file:
                files = {"photo": img_file}
                data = {
                    "chat_id": self.chat_id,
                    "caption": caption,
                    "parse_mode": "HTML",
                }

                response = requests.post(url, files=files, data=data, timeout=30)

                if response.status_code == 200:
                    logger.info(f"Imagen enviada a Telegram: {os.path.basename(image_path)}")
                    return True
                else:
                    logger.error(f"Telegram photo error {response.status_code}: {response.text[:200]}")
                    # Fallback: enviar solo el texto
                    if caption:
                        self.send_message(caption)
                    return False

        except requests.exceptions.RequestException as e:
            logger.error(f"Error enviando foto Telegram: {e}")
            if caption:
                self.send_message(caption)
            return False

    def send_signal_with_chart(self, signal_data: dict, chart_path: str = None) -> bool:
        """
        Envía una señal de trading completa con gráfico.

        Args:
            signal_data: dict con toda la info de la señal
            chart_path: Ruta a la imagen del gráfico
        """
        # Construir mensaje de la señal
        message = self._format_signal_message(signal_data)

        # Enviar imagen con caption
        if chart_path and os.path.exists(chart_path):
            return self.send_photo(chart_path, caption=message)
        else:
            # Sin imagen, enviar solo texto
            return self.send_message(message)

    def send_sweep_alert(self, sweep_data: dict, chart_path: str = None) -> bool:
        """
        Envía alerta de sweep en curso (antes de confirmación completa).

        Args:
            sweep_data: dict con info del sweep detectado
            chart_path: Ruta a la imagen del gráfico
        """
        symbol = sweep_data.get("symbol", "???")
        direction = sweep_data.get("direction", "???")
        sweep_level = sweep_data.get("sweep_level", 0)
        current_price = sweep_data.get("current_price", 0)
        score = sweep_data.get("score", 0)
        trend = sweep_data.get("trend_detail", "")

        now = datetime.now().strftime("%H:%M:%S")

        if direction == "LONG":
            dir_emoji = "🟢"
            dir_text = "ALCISTA (BUSCA COMPRA)"
            sweep_text = f"Precio barrió low previo: <code>{sweep_level}</code>"
        else:
            dir_emoji = "🔴"
            dir_text = "BAJISTA (BUSCA VENTA)"
            sweep_text = f"Precio barrió high previo: <code>{sweep_level}</code>"

        message = f"""
<b>⚠️ SWEEP DE LIQUIDEZ DETECTADO</b>

{dir_emoji} <b>Dirección:</b> {dir_text}
📊 <b>Par:</b> {symbol}
⏰ <b>Hora:</b> {now}

<b>🔍 Detalles:</b>
{sweep_text}
💰 <b>Precio actual:</b> <code>{current_price}</code>
📈 <b>Tendencia:</b> {trend}
📊 <b>Score parcial:</b> {score}/5

<b>⏳ Esperando confirmación de rechazo...</b>
<i>Observa el gráfico en TradingView.</i>

<i>Bot TradingPro24-7 — ICT Liquidity Sweep</i>"""

        message = message.strip()

        # Enviar imagen con caption
        if chart_path and os.path.exists(chart_path):
            return self.send_photo(chart_path, caption=message)
        else:
            return self.send_message(message)

    def _format_signal_message(self, signal_data: dict) -> str:
        """Formatea el mensaje de señal completo."""
        symbol = signal_data.get("symbol", "???")
        direction = signal_data.get("signal", "???")
        score = signal_data.get("score", 0)
        max_score = signal_data.get("max_score", 5)

        if direction == "BUY":
            dir_emoji = "🟢"
            dir_text = "COMPRA (BUY)"
        else:
            dir_emoji = "🔴"
            dir_text = "VENTA (SELL)"

        price = signal_data.get("current_price", 0)
        sl = signal_data.get("sl_price", 0)
        tp = signal_data.get("tp_price", 0)
        lots = signal_data.get("lots", 0)

        ai = signal_data.get("ai_confirmation", {})
        ai_conf = ai.get("confidence", 0)
        ai_status = "✅" if ai.get("confirmed") else "❌"
        ai_sweep = ai.get("sweep_quality", "N/A")
        ai_rejection = ai.get("rejection_strength", "N/A")

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

        now = datetime.now().strftime("%H:%M:%S")

        message = f"""<b>🚀 SEÑAL DE TRADING</b>

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
        return message.strip()

    def send_alert(self, title: str, message: str, alert_type: str = "INFO") -> bool:
        """Envía una alerta genérica."""
        emojis = {
            "INFO": "ℹ️",
            "WARNING": "⚠️",
            "ERROR": "🚨",
            "SUCCESS": "✅",
        }

        emoji = emojis.get(alert_type, "📢")
        now = datetime.now().strftime("%H:%M:%S")

        text = f"""{emoji} <b>{title}</b>
⏰ {now}

{message}

<i>TradingPro24-7 Bot</i>"""

        return self.send_message(text.strip())

    def send_daily_summary(self, summary: dict) -> bool:
        """Envía resumen diario de operaciones."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        message = f"""<b>📊 Resumen Diario — {now}</b>

📈 Señales generadas: {summary.get('signals_sent', 0)}
⚠️ Sweeps detectados: {summary.get('sweeps_detected', 0)}
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
        message = f"""<b>🤖 Bot TradingPro24-7 — INICIADO</b>
⏰ {now}
📊 Modo: Híbrido (OHLC + AI Vision + Sweep Alerts)
📡 Monitoreando 6 pares en M15...
📸 Los gráficos se envían con cada señal

<i>El bot analiza el mercado cada 60 segundos.</i>"""

        return self.send_message(message.strip())
