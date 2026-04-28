"""
TradingPro24-7 - Telegram Bot v8.3
Senales profesionales con:
- Bloque de codigo copiable (Entry/SL/TP)
- Imagen de analisis con S/R lines
- Condicion de mercado (ALCISTA/BAJISTA/LATERAL)
- Info S/R Flip + niveles
- Emojis + chat + canal
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
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            logger.error("Telegram error: {}".format(e))
            return {"ok": False, "description": str(e)}

    def enviar_mensaje(self, texto, chat_id=None):
        return self._request("sendMessage", {"chat_id": chat_id or self.chat_id, "text": texto})

    def enviar_foto(self, foto_path, caption="", chat_id=None):
        dest = chat_id or self.chat_id
        if not os.path.exists(foto_path):
            logger.warning("Imagen no encontrada: {}".format(foto_path))
            return self.enviar_mensaje(caption, dest)
        with open(foto_path, "rb") as f:
            fdata = f.read()
        fname = os.path.basename(foto_path)
        return self._request("sendPhoto",
            data={"chat_id": dest, "caption": caption},
            files={"photo": (fname, fdata, "image/png")})

    def enviar_senal(self, signal, chart_path=None):
        """
        Envia senal profesional al chat Y al canal.
        Formato: texto + bloque de codigo copiable + imagen
        """
        s = signal
        hora = time.strftime("%H:%M:%S")
        is_buy = s.get("type", "BUY") == "BUY"
        symbol = s.get("symbol", "")
        mode = s.get("mode", "MOMENTUM")
        entry = s.get("entry", "")
        sl = s.get("sl", "")
        tp = s.get("tp", "")
        sl_pips = s.get("sl_pips", 0)
        tp_pips = s.get("tp_pips", 0)
        rr = s.get("rr", 0)

        # ── PARTE 1: Mensaje principal con emojis ──
        msg = []
        msg.append("\U0001F680 SE\u00D1AL DE TRADING")

        if is_buy:
            msg.append("\U0001F7E2 COMPRA (BUY)")
        else:
            msg.append("\U0001F534 VENTA (SELL)")

        msg.append("\U0001F4CA Par: {}".format(symbol))
        msg.append("\U0001F552 Hora: {}".format(hora))
        msg.append("\U0001F7E0 Modo: {}".format(mode))

        # Condicion de mercado
        mc = s.get("market_condition", "")
        mc_icons = {"ALCISTA": "\U0001F4C8", "BAJISTA": "\U0001F4C9", "LATERAL": "\u2194\uFE0F", "NORMAL": "\u2139\uFE0F"}
        if mc:
            msg.append("{} Mercado: {}".format(mc_icons.get(mc, "\u2139\uFE0F"), mc))

        # MTF direction
        mtf_dir = s.get("mtf_direction", "")
        if mtf_dir:
            msg.append("\U0001F504 MTF: {}".format(mtf_dir))

        # S/R info
        sr_reason = s.get("sr_reason", "")
        if sr_reason:
            msg.append("\U0001F3AF {}".format(sr_reason))

        # ── BLOQUE DE CODIGO COPIABLE ──
        msg.append("\U0001F4CB Copiar niveles:")
        code_block = (
            "Entry: {}\n"
            "Stop Loss: {}\n"
            "Take Profit: {}"
        ).format(entry, sl, tp)
        msg.append("```")
        msg.append(code_block)
        msg.append("```")

        # ── INFO DETALLADA ──
        msg.append("\U0001F522 Detalle:")
        msg.append("SL: {} pips | TP: +{} pips".format(sl_pips, tp_pips))
        msg.append("R:R: 1:{}".format(rr))
        msg.append("Score OHLC: {}/4".format(s.get("score", 0)))

        # AI Vision
        ai_conf = s.get("ai_confidence", 0)
        if ai_conf >= 75:
            ai_txt = "\u2705 {}% Confirmada".format(ai_conf)
        elif ai_conf >= 50:
            ai_txt = "\u26A0\uFE0F {}% Moderada".format(ai_conf)
        else:
            ai_txt = "\u274C {}% Baja".format(ai_conf)
        msg.append("\U0001F916 AI Vision: {}".format(ai_txt))

        # Condiciones
        msg.append("\u2705 Condiciones:")
        for passed, text in s.get("conditions", []):
            icon = "\u2705" if passed else "\u274C"
            msg.append("{} {}".format(icon, text))

        # Killzone
        kz = s.get("killzone", "")
        if kz:
            msg.append("\U0001F3AF Killzone: {}".format(kz))

        msg.append("Bot TradingPro24-7 \u2014 v8.3 ICT PRO")

        mensaje = "\n".join(msg)

        # ── ENVIAR AL CHAT PRIVADO ──
        try:
            if chart_path and os.path.exists(chart_path):
                self.enviar_foto(chart_path, mensaje, self.chat_id)
                logger.info("Senal enviada al CHAT con imagen")
            else:
                self.enviar_mensaje(mensaje, self.chat_id)
                logger.info("Senal enviada al CHAT (sin imagen)")
                logger.warning("Ruta de imagen no valida: {}".format(chart_path))
        except Exception as e:
            logger.error("Error al chat: {}".format(e))
            self.enviar_mensaje(mensaje, self.chat_id)

        # ── ENVIAR AL CANAL ──
        if self.channel_id:
            try:
                time.sleep(1)

                # Mensaje al canal con bloque de codigo copiable
                canal_msg = []
                canal_msg.append("\U0001F680 SE\u00D1AL DE TRADING")

                if is_buy:
                    canal_msg.append("\U0001F7E2 COMPRA (BUY)")
                else:
                    canal_msg.append("\U0001F534 VENTA (SELL)")

                canal_msg.append("\U0001F4CA Par: {}".format(symbol))
                canal_msg.append("\U0001F552 Hora: {}".format(hora))

                # Bloque de codigo copiable
                canal_msg.append("```")
                canal_msg.append("Entry: {}".format(entry))
                canal_msg.append("Stop Loss: {}".format(sl))
                canal_msg.append("Take Profit: {}".format(tp))
                canal_msg.append("SL: {} pips | TP: +{} pips".format(sl_pips, tp_pips))
                canal_msg.append("R:R: 1:{}".format(rr))
                canal_msg.append("```")

                canal_msg.append("\U0001F916 AI: {}%".format(ai_conf))
                if mc:
                    canal_msg.append("{} {}".format(mc_icons.get(mc, ""), mc))
                if sr_reason:
                    canal_msg.append("\U0001F3AF {}".format(sr_reason))
                canal_msg.append("\U0001F3AF {}".format(kz))

                canal_mensaje = "\n".join(canal_msg)

                if chart_path and os.path.exists(chart_path):
                    self.enviar_foto(chart_path, canal_mensaje, self.channel_id)
                    logger.info("Senal enviada al CANAL con imagen")
                else:
                    self.enviar_mensaje(canal_mensaje, self.channel_id)
                    logger.info("Senal enviada al CANAL (sin imagen)")
                    logger.warning("Imagen no encontrada para canal: {}".format(chart_path))
            except Exception as e:
                logger.error("Error al canal: {}".format(e))
                self.enviar_mensaje(canal_mensaje, self.channel_id)

    def enviar_sweep_alert(self, symbol, timeframe, sweep_info, chart_path=None):
        hora = time.strftime("%H:%M:%S")
        msg = (
            "\U0001F6A8 SWEEP DETECTADO\n"
            "\U0001F4CA Par: {}\n"
            "\U0001F552 Hora: {}\n"
            "\U0001F4C8 Timeframe: {}\n"
            "Direccion: {}\n"
            "Nivel: {}\n"
            "Pips: {}\n"
            "Esperando confirmacion...\n"
            "Bot TradingPro24-7 v8.1"
        ).format(
            symbol, hora, timeframe,
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
