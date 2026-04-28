# ═══════════════════════════════════════════════════════════════
#  TRADINGPRO24-7 — CHART GENERATOR v8.3
#  ═══ Dibuja lineas S/R + Flip + SL/TP + Condicion mercado ═══
#  ═══ Soporta M1 para XAUUSD + M15 para forex ═══
# ═══════════════════════════════════════════════════════════════

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
    """Genera graficos de velas con S/R levels, flip zones y condicion de mercado."""

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

    def generate_candlestick_chart(self, df, symbol, timeframe, signal=None, chart_levels=None):
        """
        Genera grafico con:
        - Velas japonesas
        - EMAs
        - Lineas S/R (soportes verdes, resistencias rojas)
        - Lineas S/R Flip (amarillas punteadas)
        - SL/TP
        - Condicion de mercado en el titulo
        """
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
                signal_tag = "_{}_{}".format(signal['type'], timeframe)
            filename = "{}_{}_{}{}.png".format(symbol, timeframe, timestamp, signal_tag)
            filepath = os.path.join(self.output_dir, filename)

            fig, ax = plt.subplots(figsize=(14, 8), facecolor='#1a1a2e')
            ax.set_facecolor('#16213e')

            # ── Dibujar velas ──
            for i, (idx, row) in enumerate(chart_df.iterrows()):
                color = '#22c55e' if row['Close'] >= row['Open'] else '#ef4444'
                body_bottom = min(row['Open'], row['Close'])
                body_height = abs(row['Close'] - row['Open'])
                ax.bar(i, body_height, bottom=body_bottom, width=0.6, color=color, edgecolor=color)
                ax.plot([i, i], [row['Low'], row['High']], color=color, linewidth=1)

            # ── EMAs ──
            if symbol == "XAUUSD":
                ema_fast = chart_df['Close'].ewm(span=10, adjust=False).mean()
                ema_slow = chart_df['Close'].ewm(span=25, adjust=False).mean()
                ax.plot(range(len(chart_df)), ema_fast.values, color='#3b82f6', linewidth=1.2, label='EMA 10')
                ax.plot(range(len(chart_df)), ema_slow.values, color='#f59e0b', linewidth=1.2, label='EMA 25')
            else:
                ema_fast = chart_df['Close'].ewm(span=20, adjust=False).mean()
                ema_slow = chart_df['Close'].ewm(span=50, adjust=False).mean()
                ax.plot(range(len(chart_df)), ema_fast.values, color='#3b82f6', linewidth=1.2, label='EMA 20')
                ax.plot(range(len(chart_df)), ema_slow.values, color='#f59e0b', linewidth=1.2, label='EMA 50')

            # ── Dibujar lineas S/R desde chart_levels ──
            if chart_levels:
                # Soportes (verdes)
                for sp in chart_levels.get("supports", []):
                    if sp is not None:
                        ax.axhline(y=sp, color='#22c55e', linestyle='-', linewidth=1.0, alpha=0.6)
                        ax.text(0, sp, " S: {:.2f}".format(sp),
                                color='#22c55e', fontsize=8, fontweight='bold',
                                va='bottom', ha='left',
                                bbox=dict(boxstyle='round,pad=0.2', facecolor='#16213e', edgecolor='#22c55e', alpha=0.8))

                # Resistencias (rojas)
                for rs in chart_levels.get("resistances", []):
                    if rs is not None:
                        ax.axhline(y=rs, color='#ef4444', linestyle='-', linewidth=1.0, alpha=0.6)
                        ax.text(0, rs, " R: {:.2f}".format(rs),
                                color='#ef4444', fontsize=8, fontweight='bold',
                                va='top', ha='left',
                                bbox=dict(boxstyle='round,pad=0.2', facecolor='#16213e', edgecolor='#ef4444', alpha=0.8))

                # S/R Flips (amarillos punteados)
                for fp in chart_levels.get("flips", []):
                    if fp is not None:
                        ax.axhline(y=fp, color='#eab308', linestyle='--', linewidth=1.5, alpha=0.8)
                        ax.text(len(chart_df)-1, fp, " FLIP: {:.2f} ".format(fp),
                                color='#eab308', fontsize=8, fontweight='bold',
                                va='center', ha='right',
                                bbox=dict(boxstyle='round,pad=0.2', facecolor='#16213e', edgecolor='#eab308', alpha=0.9))

            # ── SL/TP lines ──
            if signal:
                signal_type = signal.get('type', '')
                mode_text = signal.get('mode', 'S/R ICT')

                # Condicion de mercado
                market_cond = signal.get('market_condition', '')
                mtf_dir = signal.get('mtf_direction', '')

                title_parts = ["TradingPro24-7", symbol, timeframe]
                if market_cond:
                    title_parts.append(market_cond)
                if mtf_dir:
                    title_parts.append(mtf_dir)
                title_parts.append(mode_text)
                title_parts.append(signal_type)
                title = " | ".join(title_parts)

                # TP line (green dashed)
                if 'tp' in signal and signal['tp']:
                    ax.axhline(y=signal['tp'], color='#22c55e', linestyle='--', linewidth=1.5, alpha=0.9)
                    ax.text(len(chart_df)-1, signal['tp'], " TP: {:.5f}".format(signal['tp']),
                            color='#22c55e', fontsize=9, fontweight='bold', va='bottom')

                # SL line (red dashed)
                if 'sl' in signal and signal['sl']:
                    ax.axhline(y=signal['sl'], color='#ef4444', linestyle='--', linewidth=1.5, alpha=0.9)
                    ax.text(len(chart_df)-1, signal['sl'], " SL: {:.5f}".format(signal['sl']),
                            color='#ef4444', fontsize=9, fontweight='bold', va='top')

                # Entry point marker
                if 'entry' in signal and signal['entry']:
                    entry_y = signal['entry']
                    ax.axhline(y=entry_y, color='#a855f7', linestyle='-.', linewidth=1, alpha=0.7)
                    ax.text(len(chart_df)//2, entry_y, " ENTRY ",
                            color='#a855f7', fontsize=8, fontweight='bold',
                            va='bottom', ha='center')
            else:
                title = "TradingPro24-7 | {} | {}".format(symbol, timeframe)

            ax.set_title(title, color='#e2e8f0', fontsize=11, fontweight='bold', pad=10)
            ax.set_xlabel('Candles', color='#94a3b8')
            ax.set_ylabel('Price', color='#94a3b8')
            ax.tick_params(colors='#94a3b8')
            ax.legend(loc='best', facecolor='#1a1a2e', edgecolor='#334155', labelcolor='#e2e8f0', fontsize=8)
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
        return self.generate_candlestick_chart(df, symbol, timeframe)
