"""
TradingPro24-7 - Chart Generator FIX (Windows Compatible)
Genera candlestick charts con anotaciones ICT para analisis AI vision.
Compatible con Windows - usa fuentes por defecto de matplotlib.
"""

import os
import matplotlib
matplotlib.use('Agg')

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class ChartGenerator:
    """Genera graficos de velas con anotaciones de estrategia ICT."""

    def __init__(self, output_dir="screenshots"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        plt.rcParams['axes.unicode_minus'] = False

        self.style_config = {
            'figure.facecolor': '#1a1a2e',
            'axes.facecolor': '#16213e',
            'axes.edgecolor': '#e2e8f0',
            'axes.labelcolor': '#e2e8f0',
            'text.color': '#e2e8f0',
            'xtick.color': '#94a3b8',
            'ytick.color': '#94a3b8',
            'grid.color': '#334155',
            'grid.alpha': 0.5,
            'font.size': 10,
        }
        for key, val in self.style_config.items():
            plt.rcParams[key] = val

    def generate_candlestick_chart(self, df, symbol, timeframe, signal=None, levels=None):
        try:
            chart_df = df.copy()
            chart_df = chart_df.rename(columns={
                'time': 'Date', 'open': 'Open', 'high': 'High',
                'low': 'Low', 'close': 'Close'
            })
            if not pd.api.types.is_datetime64_any_dtype(chart_df['Date']):
                chart_df['Date'] = pd.to_datetime(chart_df['Date'])
            chart_df = chart_df.set_index('Date')
            chart_df = chart_df.tail(60)

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            signal_tag = ""
            if signal:
                signal_tag = "_{}_{}".format(signal['type'], signal['mode'])
            filename = "{}_{}_{}{}.png".format(symbol, timeframe, timestamp, signal_tag)
            filepath = os.path.join(self.output_dir, filename)

            fig, ax = plt.subplots(figsize=(12, 7), facecolor='#1a1a2e')
            ax.set_facecolor('#16213e')

            for i, (idx, row) in enumerate(chart_df.iterrows()):
                color = '#22c55e' if row['Close'] >= row['Open'] else '#ef4444'
                body_bottom = min(row['Open'], row['Close'])
                body_height = abs(row['Close'] - row['Open'])
                ax.bar(i, body_height, bottom=body_bottom, width=0.6, color=color, edgecolor=color)
                ax.plot([i, i], [row['Low'], row['High']], color=color, linewidth=1)

            if len(chart_df) >= 50:
                ema20 = chart_df['Close'].ewm(span=20, adjust=False).mean()
                ema50 = chart_df['Close'].ewm(span=50, adjust=False).mean()
                ax.plot(range(len(chart_df)), ema20.values, color='#3b82f6', linewidth=1.2, label='EMA 20')
                ax.plot(range(len(chart_df)), ema50.values, color='#f59e0b', linewidth=1.2, label='EMA 50')

            if signal:
                mode_emoji = "TENDENCIA" if signal['mode'] == 'TENDENCIA' else "RANGO"
                title = "TradingPro24-7 | {} | {} | {} | {}".format(symbol, timeframe, mode_emoji, signal['type'])
                if 'tp' in signal and signal['tp']:
                    ax.axhline(y=signal['tp'], color='#22c55e', linestyle='--', linewidth=1.5)
                    ax.text(len(chart_df)-1, signal['tp'], " TP: {:.5f}".format(signal['tp']),
                            color='#22c55e', fontsize=8, fontweight='bold', va='bottom')
                if 'sl' in signal and signal['sl']:
                    ax.axhline(y=signal['sl'], color='#ef4444', linestyle='--', linewidth=1.5)
                    ax.text(len(chart_df)-1, signal['sl'], " SL: {:.5f}".format(signal['sl']),
                            color='#ef4444', fontsize=8, fontweight='bold', va='top')
            else:
                title = "TradingPro24-7 | {} | {}".format(symbol, timeframe)

            if levels:
                for lvl_name, lvl_price in levels.items():
                    if lvl_price is not None:
                        clr = '#ef4444' if 'resist' in lvl_name.lower() or 'high' in lvl_name.lower() else '#22c55e'
                        ax.axhline(y=lvl_price, color=clr, linestyle=':', linewidth=1, alpha=0.7)

            ax.set_title(title, color='#e2e8f0', fontsize=12, fontweight='bold', pad=10)
            ax.set_xlabel('Candles', color='#94a3b8')
            ax.set_ylabel('Price', color='#94a3b8')
            ax.tick_params(colors='#94a3b8')
            if len(chart_df) >= 50:
                ax.legend(loc='best', facecolor='#1a1a2e', edgecolor='#334155', labelcolor='#e2e8f0')
            ax.grid(True, color='#334155', alpha=0.5, linestyle='--')
            for spine in ax.spines.values():
                spine.set_color('#334155')

            plt.tight_layout()
            fig.savefig(filepath, dpi=150, bbox_inches='tight', facecolor='#1a1a2e')
            plt.close(fig)

            logger.info("Chart saved: {}".format(filepath))
            return filepath

        except Exception as e:
            logger.error("Error generating chart: {}".format(e))
            return None

    def generate_sweep_alert_chart(self, df, symbol, timeframe, sweep_info):
        try:
            chart_df = df.tail(60).copy()

            fig, ax = plt.subplots(figsize=(12, 7), facecolor='#1a1a2e')
            ax.set_facecolor('#16213e')

            for i, (idx, row) in enumerate(chart_df.iterrows()):
                color = '#22c55e' if row['close'] >= row['open'] else '#ef4444'
                body_bottom = min(row['open'], row['close'])
                body_height = abs(row['close'] - row['open'])
                ax.bar(i, body_height, bottom=body_bottom, width=0.6, color=color, edgecolor=color)
                ax.plot([i, i], [row['low'], row['high']], color=color, linewidth=1)

            level = sweep_info.get('level', 0)
            sweep_low = sweep_info.get('sweep_low', level)
            sweep_high = sweep_info.get('sweep_high', level)

            ax.axhline(y=level, color='#f59e0b', linestyle='--', linewidth=2, alpha=0.8,
                       label='Liquidity Level: {:.5f}'.format(level))
            ax.axhspan(sweep_low, sweep_high, alpha=0.15, color='#f59e0b')

            last_i = len(chart_df) - 1
            ax.annotate(
                'SWEEP!',
                xy=(last_i, sweep_high),
                xytext=(last_i - 8, sweep_high * 1.001),
                fontsize=11, fontweight='bold', color='#f59e0b', ha='center',
                arrowprops=dict(arrowstyle='->', color='#f59e0b', lw=2),
                bbox=dict(boxstyle='round,pad=0.3', facecolor='#f59e0b', alpha=0.3)
            )

            if len(chart_df) >= 50:
                ema20 = chart_df['close'].ewm(span=20, adjust=False).mean()
                ema50 = chart_df['close'].ewm(span=50, adjust=False).mean()
                ax.plot(range(len(chart_df)), ema20.values, color='#3b82f6', linewidth=1.2, label='EMA 20')
                ax.plot(range(len(chart_df)), ema50.values, color='#f59e0b', linewidth=1.2, alpha=0.5, label='EMA 50')

            direction = sweep_info.get('direction', 'UNKNOWN')
            title = "TradingPro24-7 | SWEEP ALERT | {} | {}\n{} Sweep @ {:.5f}".format(
                symbol, timeframe, direction, level)

            ax.set_title(title, color='#e2e8f0', fontsize=12, fontweight='bold', pad=10)
            ax.set_xlabel('Candles', color='#94a3b8')
            ax.set_ylabel('Price', color='#94a3b8')
            ax.tick_params(colors='#94a3b8')
            ax.legend(loc='best', facecolor='#1a1a2e', edgecolor='#334155', labelcolor='#e2e8f0')
            ax.grid(True, color='#334155', alpha=0.5, linestyle='--')
            for spine in ax.spines.values():
                spine.set_color('#334155')

            plt.tight_layout()

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = "SWEEP_{}_{}_{}.png".format(symbol, timeframe, timestamp)
            filepath = os.path.join(self.output_dir, filename)

            fig.savefig(filepath, dpi=150, bbox_inches='tight', facecolor='#1a1a2e')
            plt.close(fig)

            logger.info("Sweep alert chart saved: {}".format(filepath))
            return filepath

        except Exception as e:
            logger.error("Error generating sweep chart: {}".format(e))
            return None
