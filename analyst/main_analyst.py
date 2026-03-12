#!/usr/bin/env python3
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bot"))
sys.path.insert(0, os.path.dirname(__file__))

from market_data import get_market_snapshot
from ai_analyst import analyse_and_generate_signal, format_signal_post
from chart_generator import generate_signal_chart
from signal_tracker import (can_post_coin, record_posted_signal,
                             check_tp_sl_hits, format_tp_hit, format_sl_hit)
from poster import post_to_square


def main():
    print("=" * 50)
    print("🤖 AI Crypto Analyst Bot")
    print("=" * 50)

    # ── Step 1: Check TP/SL hits on previously posted signals ──────────────
    print("\n[main] Checking TP/SL hits on active signals...")
    hits = check_tp_sl_hits()

    for hit in hits:
        if hit["type"] == "TP":
            content = format_tp_hit(hit)
        else:
            content = format_sl_hit(hit)

        print(f"\n[main] Posting {hit['type']} hit for {hit['symbol']}:\n{content}\n")
        post_to_square(content, images=[])

    # ── Step 2: Scan market for new signals ────────────────────────────────
    print("\n[main] Scanning market for high volume coins...")
    coins = get_market_snapshot()

    if not coins:
        print("[main] ❌ Could not fetch market data.")
        sys.exit(0)

    print(f"[main] Analyzing {len(coins)} coins...")
    signals_posted = 0

    for coin in coins:
        symbol    = coin["symbol"]
        ind       = coin.get("indicators_1h", {})
        rsi       = ind.get("rsi", 50)
        vol_ratio = ind.get("volume_ratio", 1.0)
        change_2h = ind.get("change_2h", 0)

        print(f"\n[main] {symbol} | RSI: {rsi} | Vol: {vol_ratio}x | 2h: {change_2h}%")

        # Skip neutral coins
        if 45 <= rsi <= 55 and abs(change_2h) < 1:
            print(f"[main] Skipping {symbol} — RSI neutral, no momentum")
            continue

        # ── 12h dedup check ──────────────────────────────────────────────
        if not can_post_coin(symbol, coin.get("market", "SPOT"), interval_hours=12):
            continue

        # Get AI signal
        print(f"[main] Asking AI to analyze {symbol}...")
        signal = analyse_and_generate_signal(coin)

        if not signal:
            print(f"[main] No clear signal for {symbol}")
            continue

        content = format_signal_post(signal)
        print(f"\n[main] Signal:\n{content}\n")

        success = post_to_square(content, images=[])
        if success:
            print(f"[main] ✅ Posted signal for {symbol}!")
            record_posted_signal(signal)
            signals_posted += 1
        else:
            print(f"[main] ❌ Failed to post for {symbol}")

    print(f"\n[main] Done! Posted {signals_posted} new signal(s) this run.")


if __name__ == "__main__":
    main()
