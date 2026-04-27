# ═══════════════════════════════════════════════════════════════
#  TRADING BOT HÍBRIDO — RISK MANAGER
#  Calcula tamaño de posición y gestión de riesgo
# ═══════════════════════════════════════════════════════════════

import logging
from datetime import datetime, date
from config import RISK, RISK_PER_PAIR

logger = logging.getLogger(__name__)


class RiskManager:
    """Gestor de riesgo para el trading bot."""

    def __init__(self):
        self.risk_config = RISK
        self.daily_trade_count = 0
        self.daily_pnl = 0.0
        self.last_trade_date = date.today()
        self.open_trades = []
        self.max_risk_per_trade = self.risk_config["risk_percent_max"]

    def reset_daily_counters(self):
        """Resetea contadores diarios."""
        today = date.today()
        if today != self.last_trade_date:
            self.daily_trade_count = 0
            self.daily_pnl = 0.0
            self.last_trade_date = today
            self.open_trades = []
            logger.info("Contadores diarios reseteados")

    def can_trade(self, balance: float) -> dict:
        """
        Verifica si es seguro abrir una nueva operación.

        Returns:
            dict con 'allowed', 'reason'
        """
        self.reset_daily_counters()

        # Verificar límite diario de operaciones
        if self.daily_trade_count >= self.risk_config["max_daily_trades"]:
            return {
                "allowed": False,
                "reason": f"Límite diario alcanzado ({self.daily_trade_count}/{self.risk_config['max_daily_trades']})"
            }

        # Verificar operaciones abiertas simultáneas
        if len(self.open_trades) >= self.risk_config["max_open_trades"]:
            return {
                "allowed": False,
                "reason": f"Máx operaciones abiertas ({len(self.open_trades)}/{self.risk_config['max_open_trades']})"
            }

        # Verificar límite de pérdida diaria
        if self.daily_pnl < 0:
            daily_loss_pct = abs(self.daily_pnl) / balance * 100
            if daily_loss_pct >= self.risk_config["daily_loss_limit"]:
                return {
                    "allowed": False,
                    "reason": f"Límite pérdida diaria ({daily_loss_pct:.1f}%/{self.risk_config['daily_loss_limit']}%)"
                }

        return {"allowed": True, "reason": "OK"}

    def calculate_position_size(self, balance: float, symbol: str, sl_pips: float = None) -> dict:
        """
        Calcula el tamaño de posición basado en riesgo porcentual.

        Args:
            balance: Balance actual de la cuenta
            symbol: Par de divisas
            sl_pips: Stop loss en pips (usa default si None)

        Returns:
            dict con 'lots', 'risk_amount', 'sl_pips', 'tp_pips'
        """
        pair_risk = RISK_PER_PAIR.get(symbol, {})
        sl_pips = sl_pips or pair_risk.get("sl_pips", self.risk_config["sl_pips"])
        tp_pips = pair_risk.get("tp_pips", self.risk_config["tp_pips"])

        # Cantidad a arriesgar
        risk_percent = min(self.risk_config["risk_percent"], self.max_risk_per_trade)
        risk_amount = balance * (risk_percent / 100)

        # Pip value por par (valor de 1 pip por 1 lote estándar)
        pip_value_usd = {
            "EURUSD": 10.0,
            "GBPUSD": 10.0,
            "USDJPY": 6.50,
            "AUDUSD": 10.0,
            "USDCAD": 7.50,
            "USDCHF": 11.0,
        }

        pip_value = pip_value_usd.get(symbol, 10.0)

        # Calcular lotes
        if sl_pips > 0 and pip_value > 0:
            lots = risk_amount / (sl_pips * pip_value)
            # Redondear a 0.01
            lots = round(lots, 2)
            # Mínimo 0.01 lotes
            lots = max(0.01, lots)
        else:
            lots = 0.01

        return {
            "lots": lots,
            "risk_amount": round(risk_amount, 2),
            "risk_percent": risk_percent,
            "sl_pips": sl_pips,
            "tp_pips": tp_pips,
            "pip_value_usd": pip_value,
        }

    def calculate_sl_tp(self, current_price: float, signal: str, symbol: str) -> dict:
        """
        Calcula niveles de SL y TP.

        Args:
            current_price: Precio actual
            signal: "BUY" o "SELL"
            symbol: Par de divisas

        Returns:
            dict con 'sl_price', 'tp_price', 'sl_pips', 'tp_pips'
        """
        pair_risk = RISK_PER_PAIR.get(symbol, {})
        sl_pips = pair_risk.get("sl_pips", self.risk_config["sl_pips"])
        tp_pips = pair_risk.get("tp_pips", self.risk_config["tp_pips"])

        digits = {
            "EURUSD": 5, "GBPUSD": 5, "USDJPY": 3,
            "AUDUSD": 5, "USDCAD": 5, "USDCHF": 5,
        }
        pip_value = {
            "EURUSD": 0.0001, "GBPUSD": 0.0001, "USDJPY": 0.01,
            "AUDUSD": 0.0001, "USDCAD": 0.0001, "USDCHF": 0.0001,
        }

        pip = pip_value.get(symbol, 0.0001)
        dec = digits.get(symbol, 5)

        if signal == "BUY":
            sl_price = round(current_price - (sl_pips * pip), dec)
            tp_price = round(current_price + (tp_pips * pip), dec)
        else:  # SELL
            sl_price = round(current_price + (sl_pips * pip), dec)
            tp_price = round(current_price - (tp_pips * pip), dec)

        return {
            "sl_price": sl_price,
            "tp_price": tp_price,
            "sl_pips": sl_pips,
            "tp_pips": tp_pips,
            "direction": signal,
        }

    def register_trade(self, trade_info: dict):
        """Registra una operación abierta."""
        self.open_trades.append({
            **trade_info,
            "opened_at": datetime.now().isoformat(),
        })
        self.daily_trade_count += 1

    def close_trade(self, symbol: str, pnl: float):
        """Registra el cierre de una operación."""
        self.daily_pnl += pnl
        self.open_trades = [t for t in self.open_trades if t.get("symbol") != symbol]

        status = "✅ GANANCIA" if pnl >= 0 else "❌ PÉRDIDA"
        logger.info(f"Operación cerrada: {symbol} {status} ${pnl:.2f} | PnL diario: ${self.daily_pnl:.2f}")

    def get_status(self) -> dict:
        """Retorna el estado actual del gestor de riesgo."""
        return {
            "daily_trades": self.daily_trade_count,
            "daily_pnl": round(self.daily_pnl, 2),
            "open_trades": len(self.open_trades),
            "max_daily": self.risk_config["max_daily_trades"],
            "max_open": self.risk_config["max_open_trades"],
        }
