# ═══════════════════════════════════════════════════════════════
#  TRADING BOT HÍBRIDO — TRADE LOGGER
#  Registro de señales y operaciones para backtesting
# ═══════════════════════════════════════════════════════════════

import json
import os
import logging
from datetime import datetime, date
from config import LOGS_DIR

logger = logging.getLogger(__name__)


class TradeLogger:
    """Registra todas las señales y operaciones."""

    def __init__(self):
        self.signals_file = os.path.join(LOGS_DIR, "signals_log.json")
        self.trades_file = os.path.join(LOGS_DIR, "trades_log.json")
        self.performance_file = os.path.join(LOGS_DIR, "performance_log.json")

    def log_signal(self, signal_data: dict):
        """Guarda una señal generada."""
        record = {
            **signal_data,
            "logged_at": datetime.now().isoformat(),
        }

        signals = self._load_json(self.signals_file)
        signals.append(record)
        self._save_json(self.signals_file, signals)

        logger.info(f"Señal guardada: {signal_data.get('symbol')} {signal_data.get('signal')}")

    def log_trade(self, trade_data: dict):
        """Guarda una operación ejecutada."""
        record = {
            **trade_data,
            "logged_at": datetime.now().isoformat(),
        }

        trades = self._load_json(self.trades_file)
        trades.append(record)
        self._save_json(self.trades_file, trades)

        logger.info(f"Operación guardada: {trade_data.get('symbol')} PnL=${trade_data.get('pnl', 0):.2f}")

    def log_performance(self, perf_data: dict):
        """Guarda métricas de rendimiento diario."""
        record = {
            **perf_data,
            "date": date.today().isoformat(),
            "logged_at": datetime.now().isoformat(),
        }

        perf = self._load_json(self.performance_file)
        perf.append(record)
        self._save_json(self.performance_file, perf)

    def get_today_signals(self) -> list:
        """Retorna señales del día de hoy."""
        signals = self._load_json(self.signals_file)
        today = date.today().isoformat()

        return [
            s for s in signals
            if s.get("timestamp", "").startswith(today)
            or s.get("logged_at", "").startswith(today)
        ]

    def get_today_trades(self) -> list:
        """Retorna operaciones del día de hoy."""
        trades = self._load_json(self.trades_file)
        today = date.today().isoformat()

        return [
            t for t in trades
            if t.get("logged_at", "").startswith(today)
        ]

    def get_stats(self) -> dict:
        """Calcula estadísticas generales."""
        trades = self._load_json(self.trades_file)

        if not trades:
            return {
                "total_trades": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0,
                "total_pnl": 0,
                "avg_win": 0,
                "avg_loss": 0,
                "profit_factor": 0,
            }

        wins = [t for t in trades if t.get("pnl", 0) > 0]
        losses = [t for t in trades if t.get("pnl", 0) <= 0]

        total_wins = sum(t.get("pnl", 0) for t in wins)
        total_losses = abs(sum(t.get("pnl", 0) for t in losses))

        avg_win = total_wins / len(wins) if wins else 0
        avg_loss = total_losses / len(losses) if losses else 0
        profit_factor = total_wins / total_losses if total_losses > 0 else 0

        return {
            "total_trades": len(trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": len(wins) / len(trades) if trades else 0,
            "total_pnl": total_wins - total_losses,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "profit_factor": profit_factor,
        }

    def _load_json(self, filepath: str) -> list:
        """Carga JSON desde archivo."""
        if not os.path.exists(filepath):
            return []

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error cargando {filepath}: {e}")
            return []

    def _save_json(self, filepath: str, data: list):
        """Guarda JSON a archivo."""
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        except IOError as e:
            logger.error(f"Error guardando {filepath}: {e}")
