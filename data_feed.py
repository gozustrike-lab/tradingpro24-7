# ═══════════════════════════════════════════════════════════════
#  TRADING BOT HÍBRIDO — DATA FEED (MT5 Connection)
#  Extrae datos OHLC de MetaTrader 5
# ═══════════════════════════════════════════════════════════════

import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta
import pytz
import time
import logging

from config import FOREX_PAIRS, MT5_TIMEFRAME, STRATEGY, DATA_DIR

logger = logging.getLogger(__name__)


class MT5Connection:
    """Maneja la conexión con MetaTrader 5."""

    def __init__(self):
        self.connected = False
        self.account_info = None

    def initialize(self):
        """Inicializa la conexión con MT5."""
        try:
            # Intentar inicializar
            if not mt5.initialize():
                error_code, error_msg = mt5.last_error()
                logger.error(f"MT5 inicialización fallida: {error_code} - {error_msg}")
                return False

            self.connected = True
            self.account_info = mt5.account_info()

            if self.account_info:
                logger.info(
                    f"MT5 conectado — Cuenta: {self.account_info.login}, "
                    f"Balance: ${self.account_info.balance:.2f}, "
                    f"Broker: {self.account_info.server}"
                )
            else:
                logger.warning("MT5 conectado pero sin info de cuenta (¿terminal cerrada?)")

            return True

        except Exception as e:
            logger.error(f"Error conectando a MT5: {e}")
            return False

    def shutdown(self):
        """Cierra la conexión con MT5."""
        if self.connected:
            mt5.shutdown()
            self.connected = False
            logger.info("MT5 desconectado")

    def reconnect(self):
        """Intenta reconectar a MT5."""
        self.shutdown()
        time.sleep(2)
        return self.initialize()

    def get_account_balance(self):
        """Retorna el balance actual de la cuenta."""
        if not self.connected:
            return None
        account = mt5.account_info()
        if account:
            return account.balance
        return None

    def get_account_equity(self):
        """Retorna el equity actual de la cuenta."""
        if not self.connected:
            return None
        account = mt5.account_info()
        if account:
            return account.equity
        return None


class DataFeed:
    """Extrae datos OHLC de MT5."""

    def __init__(self, connection: MT5Connection):
        self.conn = connection
        self.mt5_timeframe = self._get_mt5_timeframe()

    def _get_mt5_timeframe(self):
        """Convierte minutos a timeframe de MT5."""
        tf_map = {
            1: mt5.TIMEFRAME_M1,
            5: mt5.TIMEFRAME_M5,
            15: mt5.TIMEFRAME_M15,
            30: mt5.TIMEFRAME_M30,
            60: mt5.TIMEFRAME_H1,
            240: mt5.TIMEFRAME_H4,
            1440: mt5.TIMEFRAME_D1,
        }
        return tf_map.get(MT5_TIMEFRAME, mt5.TIMEFRAME_M15)

    def get_ohlc(self, symbol: str, num_candles: int = 100):
        """
        Obtiene datos OHLC para un par.

        Args:
            symbol: Par de divisas (ej: "EURUSD")
            num_candles: Número de velas a obtener

        Returns:
            DataFrame de pandas con columnas: time, open, high, low, close, tick_volume
            None si hay error
        """
        if not self.conn.connected:
            logger.warning(f"MT5 no conectado, no se pueden obtener datos de {symbol}")
            return None

        try:
            rates = mt5.copy_rates_from_pos(symbol, self.mt5_timeframe, 0, num_candles)

            if rates is None or len(rates) == 0:
                error_code, error_msg = mt5.last_error()
                logger.warning(f"No se obtuvieron datos de {symbol}: {error_code} - {error_msg}")
                return None

            df = pd.DataFrame(rates)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            df = df[['time', 'open', 'high', 'low', 'close', 'tick_volume']]

            logger.debug(f"OHLC {symbol}: {len(df)} velas, última={df.iloc[-1]['time']}")
            return df

        except Exception as e:
            logger.error(f"Error obteniendo OHLC de {symbol}: {e}")
            return None

    def get_current_price(self, symbol: str):
        """
        Obtiene el precio actual (bid/ask) de un par.

        Returns:
            dict con 'bid', 'ask', 'spread' o None
        """
        if not self.conn.connected:
            return None

        try:
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                return None

            pip_value = STRATEGY["pip_values"].get(symbol, 0.0001)
            spread = round((tick.ask - tick.bid) / pip_value, 1)

            return {
                "bid": tick.bid,
                "ask": tick.ask,
                "spread": spread,
                "time": datetime.now(),
            }
        except Exception as e:
            logger.error(f"Error obteniendo precio de {symbol}: {e}")
            return None

    def get_symbol_info(self, symbol: str):
        """Obtiene información del símbolo (digitos, point, trade mode)."""
        if not self.conn.connected:
            return None
        return mt5.symbol_info(symbol)

    def save_historical_data(self, symbol: str, num_candles: int = 1000):
        """Guarda datos históricos en CSV para análisis."""
        df = self.get_ohlc(symbol, num_candles)
        if df is not None:
            filepath = f"{DATA_DIR}/{symbol}_M15.csv"
            df.to_csv(filepath, index=False)
            logger.info(f"Datos guardados: {filepath}")
            return filepath
        return None

    def is_market_open(self, symbol: str = None):
        """Verifica si el mercado está abierto."""
        if not self.conn.connected:
            return False

        # Verificar si es fin de semana
        now_utc = datetime.now(pytz.utc)
        # Sábado todo el día y domingo antes de las 22:00 UTC (mercado cerrado)
        if now_utc.weekday() == 5:  # Sábado
            return False
        if now_utc.weekday() == 6 and now_utc.hour < 22:  # Domingo antes de apertura
            return False

        # Verificar si el símbolo permite trading
        if symbol:
            info = mt5.symbol_info(symbol)
            if info and not info.trade_mode:
                return False

        return True
