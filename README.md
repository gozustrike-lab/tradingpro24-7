# TradingPro24-7 — Trading Bot Híbrido

Bot de trading semi-automatizado basado en la estrategia **ICT Liquidity Sweep**.

## Arquitectura

```
OHLC Filters (5 condiciones) ──► AI Vision (Gemma 4) ──► Telegram Alert
        │                              │
        ▼                              ▼
   DataFeed (MT5)              Confirmación Visual
```

## Módulos

| Archivo | Función |
|---------|---------|
| `config.py` | Configuración general (API keys, pares, estrategia) |
| `data_feed.py` | Conexión MT5 y extracción de datos OHLC |
| `strategy.py` | Motor de estrategia (5 condiciones + scoring) |
| `ai_vision.py` | Confirmación visual con IA (OpenRouter/Gemma 4) |
| `risk_manager.py` | Gestión de riesgo (1-2% por operación) |
| `telegram_bot.py` | Alertas y señales por Telegram |
| `trade_logger.py` | Registro de señales y operaciones |
| `copy_trading.py` | Portafolio para MQL5 Signals |
| `chart_generator.py` | Generación de gráficos |
| `main.py` | Motor principal del bot |
| `setup.py` | Diagnóstico del sistema |

## Instalación

```bash
# 1. Instalar Python 3.12
# 2. Crear entorno virtual
py -3.12 -m venv venv
venv\Scripts\activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar API keys en config.py:
#    - OpenRouter API Key (https://openrouter.ai/keys)
#    - Telegram Bot Token (@BotFather)
#    - Telegram Chat ID (@userinfobot)

# 5. Ejecutar diagnóstico
python setup.py

# 6. Iniciar bot
python main.py
```

## Estrategia — ICT Liquidity Sweep

5 condiciones OHLC:
1. **Tendencia**: EMA(20) > EMA(50) para LONG
2. **Pullback**: Mínimo 10 pips en últimas 3 velas
3. **Sweep**: Precio barrió un low/high previo (20 velas)
4. **Rechazo**: Mecha 2x mayor al cierre
5. **Cierre**: En top 75% del rango de la vela

Mínimo 4/5 para generar señal, AI Vision confirma visualmente.

## Risk Management

- Riesgo: 1% del balance por operación
- Stop Loss: 18-20 pips
- Take Profit: 45-50 pips
- R:R ratio: 1:2.5
- Máximo 3 operaciones/día
- Corte de pérdidas: 3% diario

## Broker Recomendado

IC Markets Raw Spread:
- Spread: 0.0 pips
- Comisión: $3.50/lote/lado
- Plataforma: MetaTrader 5
- Copy Trading: MQL5 Signals

## Requisitos

- Python 3.11 o 3.12
- MetaTrader 5 (64-bit)
- Cuenta en IC Markets (Raw Spread)
- OpenRouter API Key (gratuita)
- Telegram Bot Token + Chat ID
