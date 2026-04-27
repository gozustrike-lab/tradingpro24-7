# ═══════════════════════════════════════════════════════════════
#  TRADING BOT HÍBRIDO — COPY TRADING MANAGER
#  Prepara el portafolio para MQL5 Signals / Copy Trading
# ═══════════════════════════════════════════════════════════════

import logging
import json
import os
from datetime import datetime, date
from config import LOGS_DIR

logger = logging.getLogger(__name__)


class CopyTradingManager:
    """Gestor para preparar portafolio de copy trading."""

    def __init__(self):
        self.portfolio_file = os.path.join(LOGS_DIR, "copy_trading_portfolio.json")
        self.subscribers = 0
        self.min_trades_for_signals = 30
        self.min_win_rate_for_signals = 0.55

    def add_trade_to_portfolio(self, trade_data: dict):
        """
        Agrega una operación al portafolio de copy trading.

        Args:
            trade_data: dict con symbol, signal, entry, sl, tp, lots, result, pnl
        """
        portfolio = self._load_portfolio()

        # Calcular métricas
        portfolio["trades"].append({
            **trade_data,
            "timestamp": datetime.now().isoformat(),
        })

        # Actualizar métricas
        total = len(portfolio["trades"])
        wins = sum(1 for t in portfolio["trades"] if t.get("pnl", 0) > 0)
        total_pnl = sum(t.get("pnl", 0) for t in portfolio["trades"])

        portfolio["metrics"] = {
            "total_trades": total,
            "wins": wins,
            "losses": total - wins,
            "win_rate": wins / total if total > 0 else 0,
            "total_pnl": round(total_pnl, 2),
            "avg_pnl": round(total_pnl / total, 2) if total > 0 else 0,
            "profit_factor": self._calc_profit_factor(portfolio["trades"]),
            "max_drawdown": self._calc_max_drawdown(portfolio["trades"]),
        }

        portfolio["updated_at"] = datetime.now().isoformat()
        portfolio["last_trade"] = trade_data.get("symbol", "")

        self._save_portfolio(portfolio)

        logger.info(
            f"Portafolio actualizado: {total} trades, "
            f"WR={wins/total:.1%}, PnL=${total_pnl:.2f}"
        )

    def is_ready_for_signals(self) -> dict:
        """
        Verifica si el portafolio está listo para publicar como señal MQL5.

        Returns:
            dict con 'ready', 'requirements', 'metrics'
        """
        portfolio = self._load_portfolio()
        metrics = portfolio.get("metrics", {})
        trades = len(portfolio.get("trades", []))

        requirements = {
            "min_trades": {
                "met": trades >= self.min_trades_for_signals,
                "current": trades,
                "required": self.min_trades_for_signals,
            },
            "min_win_rate": {
                "met": metrics.get("win_rate", 0) >= self.min_win_rate_for_signals,
                "current": f"{metrics.get('win_rate', 0):.1%}",
                "required": f"{self.min_win_rate_for_signals:.0%}",
            },
            "positive_pnl": {
                "met": metrics.get("total_pnl", 0) > 0,
                "current": f"${metrics.get('total_pnl', 0):.2f}",
                "required": ">$0",
            },
        }

        all_met = all(r["met"] for r in requirements.values())

        return {
            "ready": all_met,
            "requirements": requirements,
            "metrics": metrics,
        }

    def get_portfolio_summary(self) -> dict:
        """Retorna resumen del portafolio."""
        portfolio = self._load_portfolio()
        return {
            **portfolio.get("metrics", {}),
            "total_trades": len(portfolio.get("trades", [])),
            "ready_for_signals": self.is_ready_for_signals()["ready"],
        }

    def export_for_mql5(self) -> str:
        """
        Exporta datos en formato compatible para publicar como señal MQL5.

        Returns:
            str con formato de reporte
        """
        portfolio = self._load_portfolio()
        metrics = portfolio.get("metrics", {})
        readiness = self.is_ready_for_signals()

        report = []
        report.append("=" * 50)
        report.append("REPORTE DE SEÑAL — TradingPro24-7")
        report.append("=" * 50)
        report.append(f"Fecha: {date.today().isoformat()}")
        report.append(f"Total de operaciones: {metrics.get('total_trades', 0)}")
        report.append(f"Win Rate: {metrics.get('win_rate', 0):.1%}")
        report.append(f"Profit Factor: {metrics.get('profit_factor', 0):.2f}")
        report.append(f"PnL Total: ${metrics.get('total_pnl', 0):.2f}")
        report.append(f"Max Drawdown: ${metrics.get('max_drawdown', 0):.2f}")
        report.append(f"Lista para MQL5 Signals: {'✅ SÍ' if readiness['ready'] else '❌ NO'}")
        report.append("")

        if not readiness["ready"]:
            report.append("Requisitos pendientes:")
            for req, status in readiness["requirements"].items():
                icon = "✅" if status["met"] else "❌"
                report.append(f"  {icon} {req}: {status['current']}/{status['required']}")

        return "\n".join(report)

    def _calc_profit_factor(self, trades: list) -> float:
        """Calcula el profit factor."""
        wins = sum(t.get("pnl", 0) for t in trades if t.get("pnl", 0) > 0)
        losses = abs(sum(t.get("pnl", 0) for t in trades if t.get("pnl", 0) < 0))
        return round(wins / losses, 2) if losses > 0 else 0

    def _calc_max_drawdown(self, trades: list) -> float:
        """Calcula el máximo drawdown."""
        if not trades:
            return 0

        peak = 0
        max_dd = 0
        running = 0

        for trade in trades:
            running += trade.get("pnl", 0)
            if running > peak:
                peak = running
            dd = peak - running
            if dd > max_dd:
                max_dd = dd

        return round(max_dd, 2)

    def _load_portfolio(self) -> dict:
        """Carga el portafolio desde archivo."""
        if not os.path.exists(self.portfolio_file):
            return {"trades": [], "metrics": {}}

        try:
            with open(self.portfolio_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {"trades": [], "metrics": {}}

    def _save_portfolio(self, portfolio: dict):
        """Guarda el portafolio a archivo."""
        try:
            with open(self.portfolio_file, "w", encoding="utf-8") as f:
                json.dump(portfolio, f, indent=2, ensure_ascii=False, default=str)
        except IOError as e:
            logger.error(f"Error guardando portafolio: {e}")
