"""
TradingPro24-7 - Telegram Bot v7.0 (Windows Compatible)
Senales profesionales con emojis reales, imagen, chat + canal.
"""

import os
import json
import urllib.request
import time
import logging

logger = logging.getLogger(__name__)


class TelegramBot:

    def __init__(self, token, chat_id, channel_id=None):
        self.token = token
        self.chat_id = chat_id
        self.channel_id = channel_id
        self.base_url = "https://api.telegram.org/bot{}".format(token)

    def _request(self, method, data=None, files=None):
        url = "{}/{}".format(self.base_url, method)
        try:
            if files:
                boundary = "----Boundary7MA4YWxkTrZu0gW"
                body = b""
                for field, value in data.items():
                    body += "--{}\r\n".format(boundary).encode()
                    body += 'Content-Disposition: form-data; name="{}"\r\n\r\n'.format(field).encode()
                    body += str(value).encode() + b"\r\n"
                for field, (fname, fdata, ftype) in files.items():
                    body += "--{}\r\n".format(boundary).encode()
                    body += 'Content-Disposition: form-data; name="{}"; filename="{}"\r\n'.format(field, fname).encode()
                    body += "Content-Type: {}\r\n\r\n".format(ftype).encode()
                    body += fdata + b"\r\n"
                body += "--{}--\r\n".format(boundary).encode()
                req = urllib.request.Request(url, data=body)
                req.add_header("Content-Type", "multipart/form-data; boundary={}".format(boundary))
            else:
                body = json.dumps(data).encode("utf-8")
                req = urllib.request.Request(url, data=body)
                req.add_header("Content-Type", "application/json")
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            logger.error("Telegram error: {}".format(e))
            return {"ok": False, "description": str(e)}

    def enviar_mensaje(self, texto, chat_id=None):
        return self._request("sendMessage", {"chat_id": chat_id or self.chat_id, "text": texto})

    def enviar_foto(self, foto_path, caption="", chat_id=None):
        dest = chat_id or self.chat_id
        if not os.path.exists(foto_path):
            return self.enviar_mensaje(caption, dest)
        with open(foto_path, "rb") as f:
            fdata = f.read()
        fname = os.path.basename(foto_path)
        return self._request("sendPhoto",
            data={"chat_id": dest, "caption": caption},
            files={"photo": (fname, fdata, "image/png")})

    def enviar_senal(self, signal, chart_path=None):
        """
        Envia senal profesional con emojis al chat Y al canal.
        """
        s = signal
        hora = time.strftime("%H:%M:%S")
        is_buy = s.get("type", "BUY") == "BUY"
        mode = s.get("mode", "TENDENCIA")
        modo_text = "RANGO S/R" if mode == "RANGO" else "TENDENCIA ICT SWEEP"

        # Construir mensaje con emojis
        msg = []
        msg.append("\U0001F680 SE\u00D1AL DE TRADING")

        if is_buy:
            msg.append("\U0001F7E2 COMPRA (BUY)")
        else:
            msg.append("\U0001F534 VENTA (SELL)")

        msg.append("\U0001F4CA Par: {}".format(s.get("symbol", "")))
        msg.append("\U0001F552 Hora: {}".format(hora))
        msg.append("\U0001F7E0 Modo: {}".format(modo_text))
        msg.append("\U0001F522 Niveles:")
        msg.append("\U0001F7E1 Entrada: {}".format(s.get("entry", "")))

        sl_pips = s.get("sl_pips", 0)
        msg.append("\U0001F534 Stop Loss: {} ({} pips)".format(s.get("sl", ""), sl_pips))

        tp_pips = s.get("tp_pips", 0)
        msg.append("\U0001F7E2 Take Profit: {} (+{} pips)".format(s.get("tp", ""), tp_pips))

        rr = s.get("rr", 0)
        msg.append("\U0001F4C8 R:R: 1:{}".format(rr))
        msg.append("\U0001F4F6 Score OHLC: {}/5".format(s.get("score", 0)))

        ai_conf = s.get("ai_confidence", 0)
        ai_comm = s.get("ai_comment", "")
        if ai_conf >= 75:
            ai_txt = "\u2705 ({}%)".format(ai_conf)
        elif ai_conf >= 50:
            ai_txt = "\u26A0\uFE0F ({}%)".format(ai_conf)
        else:
            ai_txt = "\u274C ({}%)".format(ai_conf)
        msg.append("\U0001F916 AI Vision: {} {}".format(ai_txt, ai_comm))

        sweep = s.get("sweep_pips", 0)
        rejection = s.get("rejection", "fuerte")
        msg.append("Sweep: {} pips | Rechazo: {}".format(sweep, rejection))

        msg.append("\u2705 Condiciones:")
        for passed, text in s.get("conditions", []):
            if passed:
                msg.append("\u2705 {}".format(text))
            else:
                msg.append("\u274C {}".format(text))

        kz = s.get("killzone", "Fuera de killzone")
        msg.append("\U0001F3AF Killzone: {}".format(kz))

        adx = s.get("adx_value", 0)
        if adx > 25:
            adx_txt = "{} (fuerte)".format(adx)
        elif adx > 20:
            adx_txt = "{} (moderada)".format(adx)
        else:
            adx_txt = "{} (lateral)".format(adx)
        msg.append("ADX: {}".format(adx_txt))
        msg.append("Bot TradingPro24-7 \u2014 ICT Liquidity Sweep")

        mensaje = "\n".join(msg)

        # Enviar al CHAT PRIVADO con imagen
        try:
            if chart_path and os.path.exists(chart_path):
                self.enviar_foto(chart_path, mensaje, self.chat_id)
                logger.info("Senal enviada al CHAT con imagen")
            else:
                self.enviar_mensaje(mensaje, self.chat_id)
                logger.info("Senal enviada al CHAT")
        except Exception as e:
            logger.error("Error al chat: {}".format(e))

        # Enviar al CANAL con imagen
        if self.channel_id:
            try:
                time.sleep(1)
                if chart_path and os.path.exists(chart_path):
                    self.enviar_foto(chart_path, mensaje, self.channel_id)
                    logger.info("Senal enviada al CANAL con imagen")
                else:
                    self.enviar_mensaje(mensaje, self.channel_id)
                    logger.info("Senal enviada al CANAL")
            except Exception as e:
                logger.error("Error al canal: {}".format(e))

    def enviar_sweep_alert(self, symbol, timeframe, sweep_info, chart_path=None):
        hora = time.strftime("%H:%M:%S")
        msg = (
            "\U0001F6A8 SWEEP DETECTADO\n"
            "\U0001F4CA Par: {}\n"
            "\U0001F552 Hora: {}\n"
            "Direccion: {}\n"
            "Nivel: {}\n"
            "Pips: {}\n"
            "Esperando confirmacion...\n"
            "Bot TradingPro24-7"
        ).format(
            symbol, hora,
            sweep_info.get("direction", ""),
            sweep_info.get("level", 0),
            sweep_info.get("sweep_pips", 0)
        )
        try:
            if chart_path and os.path.exists(chart_path):
                self.enviar_foto(chart_path, msg, self.chat_id)
            else:
                self.enviar_mensaje(msg, self.chat_id)
        except Exception as e:
            logger.error("Error sweep: {}".format(e))

    def enviar_status(self, text):
        try:
            self.enviar_mensaje(text, self.chat_id)
        except Exception as e:
            logger.error("Error status: {}".format(e))

    def enviar_error(self, text):
        try:
            self.enviar_mensaje("\u274C ERROR\n{}".format(text), self.chat_id)
        except Exception as e:
            logger.error("Error: {}".format(e))
