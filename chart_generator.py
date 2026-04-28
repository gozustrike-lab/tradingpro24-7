# ═══════════════════════════════════════════════════════════════
#  TRADINGPRO24-7 — CHART GENERATOR v8.4
#  ═══ Lineas S/R + Flip + Ondas/Montañitas + SL/TP ═══
#  ═══ Numeracion de ondas + patron repetitivo ═══
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
    """Genera graficos con velas + S/R + Flip + Ondas numeradas."""

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

    def generate_candlestick_chart(self, df, symbol, timeframe, signal=None, chart_levels=None, wave_data=None):
        """
        Genera grafico con:
        - Velas japonesas
        - EMAs
        - Lineas S/R (soportes verdes, resistencias rojas)
        - Lineas S/R Flip (amarillas punteadas)
        - Ondas numeradas (swing points conectados)
        - SL/TP
        - Info de patron y condicion de mercado
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

            # ── Lineas S/R ──
            if chart_levels:
                for sp in chart_levels.get("supports", []):
                    if sp is not None:
                        ax.axhline(y=sp, color='#22c55e', linestyle='-', linewidth=1.0, alpha=0.6)
                        ax.text(0, sp, " S: {:.2f}".format(sp),
                                color='#22c55e', fontsize=7, fontweight='bold', va='bottom', ha='left',
                                bbox=dict(boxstyle='round,pad=0.2', facecolor='#16213e', edgecolor='#22c55e', alpha=0.8))

                for rs in chart_levels.get("resistances", []):
                    if rs is not None:
                        ax.axhline(y=rs, color='#ef4444', linestyle='-', linewidth=1.0, alpha=0.6)
                        ax.text(0, rs, " R: {:.2f}".format(rs),
                                color='#ef4444', fontsize=7, fontweight='bold', va='top', ha='left',
                                bbox=dict(boxstyle='round,pad=0.2', facecolor='#16213e', edgecolor='#ef4444', alpha=0.8))

                for fp in chart_levels.get("flips", []):
                    if fp is not None:
                        ax.axhline(y=fp, color='#eab308', linestyle='--', linewidth=1.5, alpha=0.8)
                        ax.text(len(chart_df)-1, fp, " FLIP: {:.2f} ".format(fp),
                                color='#eab308', fontsize=8, fontweight='bold', va='center', ha='right',
                                bbox=dict(boxstyle='round,pad=0.2', facecolor='#16213e', edgecolor='#eab308', alpha=0.9))

            # ── Dibujar ondas/montañitas numeradas ──
            if wave_data and wave_data.get("swing_points"):
                swing_points = wave_data["swing_points"]
                if len(swing_points) >= 2:
                    # Mapear swing points a posiciones del grafico
                    # Los swing_points son del dataframe completo (200 velas),
                    # necesitamos mapear a los 60 velas del chart
                    wave_positions = []
                    for sp_type, sp_price in swing_points:
                        # Encontrar la vela mas cercana al precio del swing
                        for i, (idx, row) in enumerate(chart_df.iterrows()):
                            if sp_type == "HIGH" and abs(row['High'] - sp_price) < 0.01:
                                wave_positions.append((i, sp_price, sp_type))
                                break
                            elif sp_type == "LOW" and abs(row['Low'] - sp_price) < 0.01:
                                wave_positions.append((i, sp_price, sp_type))
                                break

                    # Dibujar lineas conectando swing points
                    if len(wave_positions) >= 2:
                        xs = [wp[0] for wp in wave_positions]
                        ys = [wp[1] for wp in wave_positions]
                        ax.plot(xs, ys, color='#a78bfa', linewidth=1.0, alpha=0.6, linestyle='-', zorder=3)

                        # Numerar los swing points
                        wave_num = 1
                        for i, (wp_x, wp_y, wp_type) in enumerate(wave_positions):
                            if wp_type == "HIGH":
                                # Pico (montañita arriba)
                                marker_color = '#c084fc'
                                label = str(wave_num)
                                wave_num += 1
                            else:
                                # Valle
                                marker_color = '#67e8f9'
                                label = str(wave_num)
                                wave_num += 1

                            ax.plot(wp_x, wp_y, 'o', color=marker_color, markersize=5, zorder=4)
                            offset = 0.3 if wp_type == "HIGH" else -0.6
                            ax.text(wp_x + 1, wp_y + offset * (chart_df['Close'].max() - chart_df['Close'].min()) * 0.01,
                                    label, color=marker_color, fontsize=7, fontweight='bold', ha='center')

            # ── Info de patron en esquina superior ──
            if wave_data and wave_data.get("pattern_type") != "INSUFICIENTE" and wave_data.get("pattern_type") != "N/A":
                pattern_text = wave_data.get("pattern_type", "")
                reps = wave_data.get("repetitions", 0)
                move = wave_data.get("move_type", "")
                exhaustion = wave_data.get("exhaustion", False)

                info_parts = []
                if reps >= 2:
                    info_parts.append("Rep: {}x".format(reps))
                if move and move != "NEUTRAL":
                    info_parts.append(move.replace("_", " "))
                if exhaustion:
                    info_parts.append("AGOTADO!")

                if info_parts:
                    info_text = " | ".join(info_parts)
                    ax.text(0.02, 0.95, info_text, transform=ax.transAxes,
                            color='#fbbf24', fontsize=8, fontweight='bold',
                            va='top', ha='left',
                            bbox=dict(boxstyle='round,pad=0.3', facecolor='#1a1a2e',
                                      edgecolor='#fbbf24', alpha=0.9))

            # ── SL/TP lines ──
            if signal:
                signal_type = signal.get('type', '')
                mode_text = signal.get('mode', 'S/R ICT')
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

                if 'tp' in signal and signal['tp']:
                    ax.axhline(y=signal['tp'], color='#22c55e', linestyle='--', linewidth=1.5, alpha=0.9)
                    ax.text(len(chart_df)-1, signal['tp'], " TP: {:.5f}".format(signal['tp']),
                            color='#22c55e', fontsize=9, fontweight='bold', va='bottom')

                if 'sl' in signal and signal['sl']:
                    ax.axhline(y=signal['sl'], color='#ef4444', linestyle='--', linewidth=1.5, alpha=0.9)
                    ax.text(len(chart_df)-1, signal['sl'], " SL: {:.5f}".format(signal['sl']),
                            color='#ef4444', fontsize=9, fontweight='bold', va='top')

                if 'entry' in signal and signal['entry']:
                    entry_y = signal['entry']
                    ax.axhline(y=entry_y, color='#a855f7', linestyle='-.', linewidth=1, alpha=0.7)
                    ax.text(len(chart_df)//2, entry_y, " ENTRY ",
                            color='#a855f7', fontsize=8, fontweight='bold', va='bottom', ha='center')
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
