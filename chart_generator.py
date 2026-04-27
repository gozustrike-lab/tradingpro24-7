# ═══════════════════════════════════════════════════════════════
#  TRADING BOT HÍBRIDO — CHART GENERATOR
#  Genera capturas de gráficos y reportes visuales
# ═══════════════════════════════════════════════════════════════

import matplotlib
matplotlib.use('Agg')  # Sin GUI
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.font_manager as fm
import pandas as pd
import numpy as np
import os
import logging
from datetime import datetime

from config import SCREENSHOTS_DIR, LOGS_DIR, STRATEGY

# Configurar fuentes
fm.fontManager.addfont('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
plt.rcParams['font.sans-serif'] = ['DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

logger = logging.getLogger(__name__)


class ChartGenerator:
    """Generador de gráficos para el bot de trading."""

    def __init__(self):
        os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

    def generate_chart(self, df: pd.DataFrame, symbol: str, signal_data: dict = None) -> str:
        """
        Genera una imagen del gráfico OHLC con la señal marcada.

        Args:
            df: DataFrame con datos OHLC
            symbol: Par de divisas
            signal_data: Info de la señal (opcional)

        Returns:
            str: Ruta a la imagen generada
        """
        if df is None or len(df) < 10:
            logger.warning("Datos insuficientes para generar gráfico")
            return None

        try:
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8),
                                            gridspec_kw={'height_ratios': [3, 1]},
                                            sharex=True)

            # ─── Gráfico de velas ───
            self._plot_candles(ax1, df)

            # ─── EMAs ───
            self._plot_emas(ax1, df)

            # ─── Señales ───
            if signal_data:
                self._plot_signal(ax1, df, signal_data, symbol)

            ax1.set_title(f'{symbol} — M15 — ICT Liquidity Sweep',
                         fontsize=14, fontweight='bold')
            ax1.set_ylabel('Precio')
            ax1.grid(True, alpha=0.3)

            # ─── Volumen ───
            self._plot_volume(ax2, df)
            ax2.set_ylabel('Volumen')
            ax2.grid(True, alpha=0.3)

            # Formato fecha
            ax2.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
            plt.xticks(rotation=45)

            plt.tight_layout()

            # Guardar
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{symbol}_{timestamp}.png"
            filepath = os.path.join(SCREENSHOTS_DIR, filename)
            plt.savefig(filepath, dpi=150, bbox_inches='tight')
            plt.close(fig)

            logger.info(f"Gráfico generado: {filepath}")
            return filepath

        except Exception as e:
            logger.error(f"Error generando gráfico: {e}")
            plt.close('all')
            return None

    def generate_performance_chart(self) -> str:
        """
        Genera gráfico de rendimiento del bot.

        Returns:
            str: Ruta a la imagen generada
        """
        try:
            import json

            trades_file = os.path.join(LOGS_DIR, "trades_log.json")
            if not os.path.exists(trades_file):
                return None

            with open(trades_file, "r", encoding="utf-8") as f:
                trades = json.load(f)

            if not trades:
                return None

            fig, axes = plt.subplots(2, 2, figsize=(14, 10))

            # 1. Equity Curve
            ax = axes[0, 0]
            cum_pnl = np.cumsum([t.get("pnl", 0) for t in trades])
            ax.plot(range(len(cum_pnl)), cum_pnl, 'b-', linewidth=1.5)
            ax.fill_between(range(len(cum_pnl)), cum_pnl, alpha=0.3)
            ax.axhline(y=0, color='r', linestyle='--', alpha=0.5)
            ax.set_title('Equity Curve', fontweight='bold')
            ax.set_ylabel('PnL ($)')
            ax.grid(True, alpha=0.3)

            # 2. Win/Loss Distribution
            ax = axes[0, 1]
            wins = [t.get("pnl", 0) for t in trades if t.get("pnl", 0) > 0]
            losses = [t.get("pnl", 0) for t in trades if t.get("pnl", 0) <= 0]
            if wins:
                ax.hist(wins, bins=20, color='green', alpha=0.7, label='Wins')
            if losses:
                ax.hist(losses, bins=20, color='red', alpha=0.7, label='Losses')
            ax.set_title('Distribución PnL', fontweight='bold')
            ax.set_xlabel('PnL ($)')
            ax.legend(loc='best')
            ax.grid(True, alpha=0.3)

            # 3. Trades por par
            ax = axes[1, 0]
            from collections import Counter
            pair_counts = Counter(t.get("symbol", "Unknown") for t in trades)
            pairs = list(pair_counts.keys())
            counts = list(pair_counts.values())
            colors = ['#2196F3' if c > 5 else '#FF9800' for c in counts]
            ax.bar(pairs, counts, color=colors)
            ax.set_title('Operaciones por Par', fontweight='bold')
            ax.set_ylabel('Cantidad')
            ax.grid(True, alpha=0.3, axis='y')

            # 4. Métricas resumen
            ax = axes[1, 1]
            ax.axis('off')
            total = len(trades)
            wins_count = len(wins)
            total_pnl = sum(t.get("pnl", 0) for t in trades)
            win_rate = wins_count / total if total > 0 else 0
            avg_win = np.mean(wins) if wins else 0
            avg_loss = np.mean(losses) if losses else 0

            metrics_text = f"""
            Estadísticas del Bot

            Total operaciones: {total}
            Ganadoras: {wins_count} ({win_rate:.1%})
            Perdedoras: {total - wins_count}

            PnL Total: ${total_pnl:.2f}
            Ganancia promedio: ${avg_win:.2f}
            Pérdida promedio: ${avg_loss:.2f}

            Profit Factor: {abs(total_pnl) / abs(sum(losses)):.2f}
            """

            ax.text(0.1, 0.5, metrics_text, transform=ax.transAxes,
                   fontsize=12, verticalalignment='center',
                   bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

            plt.tight_layout()

            filepath = os.path.join(SCREENSHOTS_DIR, "performance_report.png")
            plt.savefig(filepath, dpi=150, bbox_inches='tight')
            plt.close(fig)

            logger.info(f"Reporte de rendimiento generado: {filepath}")
            return filepath

        except Exception as e:
            logger.error(f"Error generando reporte: {e}")
            plt.close('all')
            return None

    def _plot_candles(self, ax, df: pd.DataFrame):
        """Dibuja velas japonesas."""
        up = df[df['close'] >= df['open']]
        down = df[df['close'] < df['open']]

        # Velas alcistas (verdes)
        ax.bar(up.index, up['close'] - up['open'], bottom=up['open'],
               width=0.6, color='#26a69a', edgecolor='#26a69a')
        # Mechas alcistas
        ax.bar(up.index, up['high'] - up['close'], bottom=up['close'],
               width=0.1, color='#26a69a')
        ax.bar(up.index, up['open'] - up['low'], bottom=up['low'],
               width=0.1, color='#26a69a')

        # Velas bajistas (rojas)
        ax.bar(down.index, down['close'] - down['open'], bottom=down['open'],
               width=0.6, color='#ef5350', edgecolor='#ef5350')
        # Mechas bajistas
        ax.bar(down.index, down['high'] - down['open'], bottom=down['open'],
               width=0.1, color='#ef5350')
        ax.bar(down.index, down['close'] - down['low'], bottom=down['low'],
               width=0.1, color='#ef5350')

    def _plot_emas(self, ax, df: pd.DataFrame):
        """Dibuja las EMAs de tendencia."""
        ema_fast = df['close'].ewm(span=STRATEGY["ema_fast"], adjust=False).mean()
        ema_slow = df['close'].ewm(span=STRATEGY["ema_slow"], adjust=False).mean()

        ax.plot(df.index, ema_fast, color='#FF9800', linewidth=1.5,
                label=f'EMA {STRATEGY["ema_fast"]}')
        ax.plot(df.index, ema_slow, color='#2196F3', linewidth=1.5,
                label=f'EMA {STRATEGY["ema_slow"]}')
        ax.legend(loc='best', fontsize=9)

    def _plot_signal(self, ax, df: pd.DataFrame, signal_data: dict, symbol: str):
        """Marca la señal en el gráfico."""
        signal = signal_data.get("signal")
        last_idx = df.index[-1]
        price = df.iloc[-1]['close']

        if signal == "BUY":
            ax.annotate('▲ BUY', xy=(last_idx, price),
                       xytext=(last_idx, price * 0.9990),
                       fontsize=12, fontweight='bold', color='green',
                       arrowprops=dict(arrowstyle='->', color='green', lw=2))
        elif signal == "SELL":
            ax.annotate('▼ SELL', xy=(last_idx, price),
                       xytext=(last_idx, price * 1.0010),
                       fontsize=12, fontweight='bold', color='red',
                       arrowprops=dict(arrowstyle='->', color='red', lw=2))

        # Niveles SL/TP
        sl_price = signal_data.get("sl_price")
        tp_price = signal_data.get("tp_price")

        if sl_price and tp_price:
            ax.axhline(y=sl_price, color='red', linestyle='--', alpha=0.7, linewidth=1)
            ax.axhline(y=tp_price, color='green', linestyle='--', alpha=0.7, linewidth=1)

            # Labels
            y_range = ax.get_ylim()
            y_pos = y_range[1] - (y_range[1] - y_range[0]) * 0.05
            ax.text(df.index[0], sl_price, f'SL: {sl_price}',
                   color='red', fontsize=9, fontweight='bold')
            ax.text(df.index[0], tp_price, f'TP: {tp_price}',
                   color='green', fontsize=9, fontweight='bold')

    def _plot_volume(self, ax, df: pd.DataFrame):
        """Dibuja gráfico de volumen."""
        colors = ['#26a69a' if c >= o else '#ef5350'
                  for c, o in zip(df['close'], df['open'])]
        ax.bar(df.index, df['tick_volume'], color=colors, alpha=0.6, width=0.6)
