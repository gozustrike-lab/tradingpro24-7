# ═══════════════════════════════════════════════════════════════
#  TRADING BOT — DATA FEED (MT5 Connection) v8.1
#  Soporte timeframe por par: M1 para XAUUSD, M15 para Forex
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
    """Maneja la conexion con MetaTrader 5."""

    def __init__(self):
        self.connected = False
        self.account_info = None

    def initialize(self):
        try:
            if not mt5.initialize():
                error_code, error_msg = mt5.last_error()
                logger.error("MT5 init fallida: {} - {}".format(error_code, error_msg))
                return False
            self.connected = True
            self.account_info = mt5.account_info()
            if self.account_info:
                logger.info(
                    "MT5 conectado — Cuenta: {}, Balance: ${:.2f}, Broker: {}".format(
                        self.account_info.login,
                        self.account_info.balance,
                        self.account_info.server
                    )
                )
            else:
                logger.warning("MT5 conectado pero sin info de cuenta")
            return True
        except Exception as e:
            logger.error("Error conectando a MT5: {}".format(e))
            return False

    def shutdown(self):
        if self.connected:
            mt5.shutdown()
            self.connected = False
            logger.info("MT5 desconectado")

    def reconnect(self):
        self.shutdown()
        time.sleep(2)
        return self.initialize()

    def get_account_balance(self):
        if not self.connected:
            return None
        account = mt5.account_info()
        return account.balance if account else None

    def get_account_equity(self):
        if not self.connected:
            return None
        account = mt5.account_info()
        return account.equity if account else None


class DataFeed:
    """Extrae datos OHLC de MT5 con soporte timeframe por par."""

    def __init__(self, connection):
        self.conn = connection
        self.mt5_timeframe = self._get_mt5_timeframe()

    def _get_mt5_timeframe(self):
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

    def _string_to_timeframe(self, tf_str):
        tf_map = {
            "M1": mt5.TIMEFRAME_M1,
            "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15,
            "M30": mt5.TIMEFRAME_M30,
            "H1": mt5.TIMEFRAME_H1,
            "H4": mt5.TIMEFRAME_H4,
            "D1": mt5.TIMEFRAME_D1,
        }
        return tf_map.get(tf_str.upper(), self.mt5_timeframe)

    def get_ohlc(self, symbol, num_candles=100, timeframe=None):
        """Obtiene datos OHLC con timeframe opcional por par."""
        if not self.conn.connected:
            return None
        try:
            if timeframe is not None:
                tf = self._string_to_timeframe(timeframe)
            else:
                tf = self.mt5_timeframe

            rates = mt5.copy_rates_from_pos(symbol, tf, 0, num_candles)
            if rates is None or len(rates) == 0:
                return None
            df = pd.DataFrame(rates)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            df = df[['time', 'open', 'high', 'low', 'close', 'tick_volume']]
            return df
        except Exception as e:
            logger.error("Error OHLC {}: {}".format(symbol, e))
            return None

    def get_ohlcv(self, symbol, num_candles=100, timeframe=None):
        """Alias de get_ohlc."""
        return self.get_ohlc(symbol, num_candles, timeframe)

    def get_current_price(self, symbol):
        if not self.conn.connected:
            return None
        tick = mt5.symbol_info_tick(symbol)
        if tick:
            return tick.ask, tick.bid
        return None

    def get_symbol_info(self, symbol):
        if not self.conn.connected:
            return None
        return mt5.symbol_info(symbol)

    def get_current_spread(self, symbol):
        if not self.conn.connected:
            return None
        tick = mt5.symbol_info_tick(symbol)
        info = mt5.symbol_info(symbol)
        if tick and info:
            spread_points = (tick.ask - tick.bid) / info.point
            return spread_points * 0.1
        return None

    def save_historical_data(self, symbol, num_candles=1000):
        if not self.conn.connected:
            return None
        try:
            rates = mt5.copy_rates_from_pos(symbol, self.mt5_timeframe, 0, num_candles)
            if rates is None or len(rates) == 0:
                return None
            df = pd.DataFrame(rates)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            return df
        except Exception as e:
            logger.error("Error guardando datos {}: {}".format(symbol, e))
            return None

    def is_market_open(self, symbol=None):
        if not self.conn.connected:
            return False
        try:
            now_utc = datetime.now(pytz.utc)
            day = now_utc.weekday()
            if day >= 5:
                return False
            return True
        except Exception:
            return True
