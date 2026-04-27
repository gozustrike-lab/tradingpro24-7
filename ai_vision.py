# ═══════════════════════════════════════════════════════════════
#  TRADING BOT HÍBRIDO — AI VISION CONFIRMATION
#  Confirma señales con IA visual (Gemma 4 31B via OpenRouter)
# ═══════════════════════════════════════════════════════════════

import requests
import json
import logging
import base64
import os
from datetime import datetime

from config import OPENROUTER_API_KEY, AI_MODEL, AI_VISION, SCREENSHOTS_DIR

logger = logging.getLogger(__name__)


class AIVision:
    """Confirma señales de trading usando IA visual."""

    def __init__(self):
        self.api_key = OPENROUTER_API_KEY
        self.model = AI_MODEL
        self.daily_calls = 0
        self.last_reset_date = datetime.now().date()
        self.confidence_threshold = AI_VISION["min_confidence"]
        self.max_daily_calls = AI_VISION["max_daily_calls"]
        self.timeout = AI_VISION["timeout_seconds"]

    def _reset_daily_counter(self):
        """Resetea el contador diario."""
        today = datetime.now().date()
        if today != self.last_reset_date:
            self.daily_calls = 0
            self.last_reset_date = today

    def _check_daily_limit(self) -> bool:
        """Verifica si hay llamadas disponibles hoy."""
        self._reset_daily_counter()
        return self.daily_calls < self.max_daily_calls

    def analyze_chart(self, image_path: str, signal_info: dict) -> dict:
        """
        Envía captura de gráfico al AI para confirmación visual.

        Args:
            image_path: Ruta a la imagen del gráfico
            signal_info: Info de la señal OHLC (dirección, par, score)

        Returns:
            dict con confirmación, confianza, detalles
        """
        if not self._check_daily_limit():
            logger.warning("Límite diario de llamadas AI alcanzado")
            return {
                "confirmed": False,
                "confidence": 0,
                "reason": "Límite diario de llamadas AI alcanzado",
                "skipped": True,
            }

        if not os.path.exists(image_path):
            logger.error(f"Imagen no encontrada: {image_path}")
            return {
                "confirmed": False,
                "confidence": 0,
                "reason": f"Imagen no encontrada: {image_path}",
            }

        try:
            # Leer y codificar imagen
            with open(image_path, "rb") as img_file:
                img_base64 = base64.b64encode(img_file.read()).decode("utf-8")

            # Determinar extensión
            ext = os.path.splitext(image_path)[1].lower().lstrip('.')
            mime = f"image/{ext}" if ext in ['png', 'jpg', 'jpeg', 'webp'] else "image/png"

            # Construir prompt
            direction = signal_info.get("direction", "UNKNOWN")
            symbol = signal_info.get("symbol", "UNKNOWN")
            score = signal_info.get("score", 0)

            prompt = self._build_prompt(symbol, direction, score)

            # Llamar API
            result = self._call_api(prompt, img_base64, mime)

            if result:
                self.daily_calls += 1
                logger.info(
                    f"AI Vision #{self.daily_calls}/{self.max_daily_calls} — "
                    f"{symbol} {direction}: {result.get('confidence', 0):.0%} confianza"
                )
                return result

            return {
                "confirmed": False,
                "confidence": 0,
                "reason": "Error en respuesta de AI",
            }

        except Exception as e:
            logger.error(f"Error en AI Vision: {e}")
            return {
                "confirmed": False,
                "confidence": 0,
                "reason": f"Excepción: {str(e)}",
            }

    def _build_prompt(self, symbol: str, direction: str, score: int) -> str:
        """Construye el prompt para el modelo de visión."""
        direction_desc = {
            "LONG": "alcista (compra/BUY)",
            "SHORT": "bajista (venta/SELL)",
            "UNKNOWN": "indefinida"
        }

        return f"""Analiza esta captura de gráfico de {symbol} en timeframe M15.

La estrategia detectó una posible señal de Liquidity Sweep con dirección {direction_desc.get(direction, direction)} y un score de {score}/5.

Responde SOLO con JSON válido (sin markdown, sin backticks):
{{{{"confirmed": true/false, "confidence": 0.0-1.0, "pattern_visible": "descripción del patrón", "rejection_strength": "fuerte/medio/débil", "sweep_quality": "limpio/parcial/dudoso", "reasoning": "explicación breve de 1-2 oraciones"}}}}

Criterios de confirmación:
1. ¿Se ve claramente que el precio barrió un nivel previo de soporte/resistencia?
2. ¿Hay una mecha de rechazo visible (cola de la vela)?
3. ¿El precio cierra en la dirección de la tendencia?
4. ¿El patrón luce limpio y sin mucho ruido?

Responde solo con el JSON."""

    def _call_api(self, prompt: str, img_base64: str, mime: str) -> dict:
        """Hace la llamada a OpenRouter API."""

        url = "https://openrouter.ai/api/v1/chat/completions"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://tradingpro24-7.github.io",
            "X-Title": "TradingBot Hybrid",
        }

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime};base64,{img_base64}"
                            }
                        }
                    ]
                }
            ],
            "temperature": 0.1,
            "max_tokens": 500,
        }

        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=self.timeout
            )

            if response.status_code == 200:
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                return self._parse_response(content)

            elif response.status_code == 429:
                logger.warning("Rate limit de OpenRouter alcanzado")
                return None

            else:
                logger.error(f"OpenRouter error {response.status_code}: {response.text[:200]}")
                return None

        except requests.exceptions.Timeout:
            logger.error("Timeout en llamada a OpenRouter")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Error de red con OpenRouter: {e}")
            return None

    def _parse_response(self, content: str) -> dict:
        """
        Parsea la respuesta del AI con fallbacks robustos.
        """
        import re

        # Intentar 1: Parse directo
        try:
            result = json.loads(content.strip())
            if self._validate_response(result):
                return {
                    "confirmed": result.get("confirmed", False),
                    "confidence": float(result.get("confidence", 0)),
                    "pattern_visible": result.get("pattern_visible", ""),
                    "rejection_strength": result.get("rejection_strength", ""),
                    "sweep_quality": result.get("sweep_quality", ""),
                    "reasoning": result.get("reasoning", ""),
                }
        except json.JSONDecodeError:
            pass

        # Intento 2: Extraer JSON con regex
        try:
            json_match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                if self._validate_response(result):
                    return {
                        "confirmed": result.get("confirmed", False),
                        "confidence": float(result.get("confidence", 0)),
                        "pattern_visible": result.get("pattern_visible", ""),
                        "rejection_strength": result.get("rejection_strength", ""),
                        "sweep_quality": result.get("sweep_quality", ""),
                        "reasoning": result.get("reasoning", ""),
                    }
        except (json.JSONDecodeError, AttributeError):
            pass

        # Intento 3: Parsear keywords de texto
        content_lower = content.lower()
        confirmed = any(kw in content_lower for kw in ["confirmed\": true", "confirmed\":true", '"confirmed": true', '"confirmed":true'])
        confidence = 0.5

        conf_match = re.search(r'confidence["\s:]+(\d+\.?\d*)', content_lower)
        if conf_match:
            confidence = float(conf_match.group(1))
            confidence = min(1.0, max(0.0, confidence))

        return {
            "confirmed": confirmed,
            "confidence": confidence,
            "pattern_visible": "parsed from text",
            "rejection_strength": "unknown",
            "sweep_quality": "unknown",
            "reasoning": f"Raw response: {content[:200]}",
        }

    def _validate_response(self, data: dict) -> bool:
        """Valida que la respuesta tenga los campos necesarios."""
        required = ["confirmed", "confidence"]
        for field in required:
            if field not in data:
                return False
        return True
