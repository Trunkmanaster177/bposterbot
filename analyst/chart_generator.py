import os
import math
import tempfile
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend for server use
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyArrowPatch
from datetime import datetime, timedelta

# Dark theme colors matching crypto chart aesthetics
BG_COLOR     = "#0d1117"
GRID_COLOR   = "#21262d"
TEXT_COLOR   = "#c9d1d9"
GREEN        = "#26a641"
RED          = "#f85149"
YELLOW       = "#d29922"
BLUE         = "#388bfd"
PURPLE       = "#a371f7"
ORANGE       = "#e3b341"


def generate_signal_chart(coin: dict, signal: dict) -> str | None:
    """
    Generate a price chart with signal markers and save to temp file.
    Returns file path or None if failed.
    """
    try:
        candles   = coin.get("candles", [])
        symbol    = signal["symbol"]
        action    = signal["signal"]
        entry     = float(signal["entry"])
        tp1       = float(signal["tp1"])
        tp2       = float(signal["tp2"])
        tp3       = float(signal["tp3"])
        sl        = float(signal["sl"])
        market    = signal.get("market", "SPOT")
        ind       = coin.get("indicators_1h", {})
        rsi       = ind.get("rsi", 0)
        ema9      = ind.get("ema9", 0)
        ema21     = ind.get("ema21", 0)

        if not candles or len(candles) < 5:
            print("[chart] Not enough candle data — generating simplified chart")
            return _generate_simple_chart(signal)

        fig, (ax1, ax2) = plt.subplots(
            2, 1, figsize=(12, 8),
            gridspec_kw={"height_ratios": [3, 1]},
            facecolor=BG_COLOR
        )

        # ── Candlestick chart ─────────────────────────────────────────────
        ax1.set_facecolor(BG_COLOR)
        closes = [c["close"] for c in candles]
        highs  = [c["high"]  for c in candles]
        lows   = [c["low"]   for c in candles]
        opens  = [c["open"]  for c in candles]
        x      = list(range(len(candles)))

        for i, c in enumerate(candles):
            color = GREEN if c["close"] >= c["open"] else RED
            # Candle body
            ax1.bar(i, abs(c["close"] - c["open"]),
                    bottom=min(c["open"], c["close"]),
                    color=color, width=0.7, alpha=0.9)
            # Wick
            ax1.plot([i, i], [c["low"], c["high"]], color=color, linewidth=0.8, alpha=0.7)

        # EMA lines
        if ema9:
            ax1.axhline(ema9,  color=BLUE,   linewidth=1.2, linestyle="--", alpha=0.8, label=f"EMA9: {ema9:.2f}")
        if ema21:
            ax1.axhline(ema21, color=ORANGE, linewidth=1.2, linestyle="--", alpha=0.8, label=f"EMA21: {ema21:.2f}")

        # Signal levels
        color_action = GREEN if action == "BUY" else RED

        ax1.axhline(entry, color=YELLOW, linewidth=1.5, linestyle="-",  alpha=0.9, label=f"Entry: {entry}")
        ax1.axhline(tp1,   color=GREEN,  linewidth=1.2, linestyle=":",  alpha=0.9, label=f"TP1: {tp1}")
        ax1.axhline(tp2,   color=GREEN,  linewidth=1.2, linestyle=":",  alpha=0.8, label=f"TP2: {tp2}")
        ax1.axhline(tp3,   color=GREEN,  linewidth=1.2, linestyle=":",  alpha=0.7, label=f"TP3: {tp3}")
        ax1.axhline(sl,    color=RED,    linewidth=1.5, linestyle="-",  alpha=0.9, label=f"SL: {sl}")

        # Label the levels on right side
        right = len(candles) - 0.3
        price_range = max(highs) - min(lows)
        offset = price_range * 0.008

        for val, label, color, style in [
            (tp3,   f"TP3 {tp3}",   GREEN,  {}),
            (tp2,   f"TP2 {tp2}",   GREEN,  {}),
            (tp1,   f"TP1 {tp1}",   GREEN,  {}),
            (entry, f"Entry {entry}", YELLOW, {"fontweight": "bold"}),
            (sl,    f"SL {sl}",     RED,    {}),
        ]:
            ax1.text(right, val + offset, label, color=color,
                     fontsize=7.5, va="bottom", ha="right", **style)

        # Signal arrow
        arrow_x = len(candles) * 0.15
        arrow_y = closes[int(len(closes) * 0.15)]
        arrow_dy = price_range * (0.08 if action == "BUY" else -0.08)
        ax1.annotate(
            f"{'▲ BUY' if action == 'BUY' else '▼ SELL'}",
            xy=(arrow_x, arrow_y),
            fontsize=11, color=color_action, fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.3", facecolor=BG_COLOR, edgecolor=color_action, alpha=0.9)
        )

        # Styling
        ax1.set_facecolor(BG_COLOR)
        ax1.tick_params(colors=TEXT_COLOR, labelsize=8)
        ax1.spines[:].set_color(GRID_COLOR)
        ax1.yaxis.tick_right()
        ax1.grid(color=GRID_COLOR, linewidth=0.5, alpha=0.5)
        ax1.legend(loc="upper left", fontsize=7, facecolor=BG_COLOR,
                   labelcolor=TEXT_COLOR, edgecolor=GRID_COLOR, framealpha=0.8)

        # Title
        leverage_str = f" | {signal.get('leverage')}x Leverage" if signal.get("leverage") and market == "FUTURES" else ""
        ax1.set_title(
            f"{symbol}  •  {market}{leverage_str}  •  {action} SIGNAL  •  1H Chart",
            color=TEXT_COLOR, fontsize=13, fontweight="bold", pad=10
        )

        # ── RSI Panel ─────────────────────────────────────────────────────
        ax2.set_facecolor(BG_COLOR)
        if len(closes) >= 14:
            rsi_values = _calc_rsi_series(closes)
            rsi_x = list(range(len(closes) - len(rsi_values), len(closes)))
            ax2.plot(rsi_x, rsi_values, color=PURPLE, linewidth=1.5)
            ax2.fill_between(rsi_x, rsi_values, 50, alpha=0.15,
                             where=[r > 50 for r in rsi_values], color=GREEN)
            ax2.fill_between(rsi_x, rsi_values, 50, alpha=0.15,
                             where=[r < 50 for r in rsi_values], color=RED)
            ax2.axhline(70, color=RED,   linewidth=0.8, linestyle="--", alpha=0.6)
            ax2.axhline(30, color=GREEN, linewidth=0.8, linestyle="--", alpha=0.6)
            ax2.axhline(50, color=GRID_COLOR, linewidth=0.6, alpha=0.5)
            ax2.text(0.01, 0.85, f"RSI(14): {rsi:.1f}", transform=ax2.transAxes,
                     color=PURPLE, fontsize=8, fontweight="bold")
            ax2.set_ylim(0, 100)
            ax2.set_yticks([30, 50, 70])

        ax2.set_facecolor(BG_COLOR)
        ax2.tick_params(colors=TEXT_COLOR, labelsize=7)
        ax2.spines[:].set_color(GRID_COLOR)
        ax2.yaxis.tick_right()
        ax2.grid(color=GRID_COLOR, linewidth=0.5, alpha=0.4)
        ax2.set_ylabel("RSI", color=TEXT_COLOR, fontsize=8)

        # Watermark
        fig.text(0.98, 0.01, "Binance Square • AI Signals",
                 color=GRID_COLOR, fontsize=7, ha="right", va="bottom")

        plt.tight_layout(rect=[0, 0, 1, 1])

        # Save to temp file
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        plt.savefig(tmp.name, dpi=150, bbox_inches="tight",
                    facecolor=BG_COLOR, edgecolor="none")
        plt.close(fig)
        print(f"[chart] ✅ Chart saved: {tmp.name}")
        return tmp.name

    except Exception as e:
        print(f"[chart] Error generating chart: {e}")
        import traceback; traceback.print_exc()
        return None


def _generate_simple_chart(signal: dict) -> str | None:
    """Fallback: simple price level diagram when no candle data."""
    try:
        symbol = signal["symbol"]
        action = signal["signal"]
        entry  = float(signal["entry"])
        tp1    = float(signal["tp1"])
        tp2    = float(signal["tp2"])
        tp3    = float(signal["tp3"])
        sl     = float(signal["sl"])

        fig, ax = plt.subplots(figsize=(10, 6), facecolor=BG_COLOR)
        ax.set_facecolor(BG_COLOR)
        ax.set_xlim(0, 10)

        levels = [
            (tp3,   f"TP3  {tp3}",   GREEN,  2.5),
            (tp2,   f"TP2  {tp2}",   GREEN,  2.0),
            (tp1,   f"TP1  {tp1}",   GREEN,  1.5),
            (entry, f"ENTRY  {entry}", YELLOW, 1.0),
            (sl,    f"SL   {sl}",    RED,    0.5),
        ]

        all_prices = [l[0] for l in levels]
        p_min, p_max = min(all_prices), max(all_prices)
        p_range = p_max - p_min if p_max != p_min else 1

        for price, label, color, _ in levels:
            y = (price - p_min) / p_range * 8 + 1
            ax.axhline(y, color=color, linewidth=2.5, alpha=0.9)
            ax.text(9.8, y, label, color=color, fontsize=11,
                    va="center", ha="right", fontweight="bold")

        action_color = GREEN if action == "BUY" else RED
        ax.text(5, 5, f"{'▲ BUY' if action == 'BUY' else '▼ SELL'} SIGNAL",
                color=action_color, fontsize=22, fontweight="bold",
                ha="center", va="center", alpha=0.15)

        ax.set_title(f"{symbol} — {action} SIGNAL", color=TEXT_COLOR,
                     fontsize=14, fontweight="bold", pad=10)
        ax.axis("off")
        fig.text(0.98, 0.01, "Binance Square • AI Signals",
                 color=GRID_COLOR, fontsize=7, ha="right")

        plt.tight_layout()
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        plt.savefig(tmp.name, dpi=150, bbox_inches="tight",
                    facecolor=BG_COLOR, edgecolor="none")
        plt.close(fig)
        print(f"[chart] ✅ Simple chart saved: {tmp.name}")
        return tmp.name

    except Exception as e:
        print(f"[chart] Simple chart error: {e}")
        return None


def _calc_rsi_series(closes, period=14):
    """Calculate RSI for each candle after warmup period."""
    rsi_values = []
    for i in range(period, len(closes)):
        window = closes[i - period:i + 1]
        gains  = [max(window[j] - window[j-1], 0) for j in range(1, len(window))]
        losses = [max(window[j-1] - window[j], 0) for j in range(1, len(window))]
        avg_g  = sum(gains)  / period
        avg_l  = sum(losses) / period
        rs     = avg_g / avg_l if avg_l > 0 else 100
        rsi_values.append(100 - (100 / (1 + rs)))
    return rsi_values
