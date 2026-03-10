#!/usr/bin/env python3
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bot"))
sys.path.insert(0, os.path.dirname(__file__))

from market_data import get_market_snapshot
from ai_analyst import analyse_and_generate_signal, format_signal_post
from poster import post_to_square


def main():
    print("=" * 50)
    print("🤖 AI Crypto Analyst Bot")
    print("=" * 50)

    # Get top volume coins + indicators
    print("\n[main] Scanning market for high volume coins...")
    coins = get_market_snapshot()
    print(f"[main] Analyzing {len(coins)} coins...")

    signals_posted = 0

    for coin in coins:
        symbol = coin["symbol"]
        vol_ratio = coin.get("indicators_1h", {}).get("volume_ratio", 1)
        print(f"\n[main] {symbol} | Volume surge: {vol_ratio}x | Change 2h: {coin.get('indicators_1h', {}).get('change_2h', 0)}%")

        # Only analyze coins with significant volume surge
        if vol_ratio < 1.3:
            print(f"[main] Skipping {symbol} — no significant volume surge")
            continue

        # Ask Claude AI for signal
        print(f"[main] Asking AI to analyze {symbol}...")
        signal = analyse_and_generate_signal(coin)

        if not signal:
            print(f"[main] No clear signal for {symbol}")
            continue

        # Format and post
        content = format_signal_post(signal)
        print(f"\n[main] Signal for {symbol}:\n{content}\n")

        success = post_to_square(content, images=[])
        if success:
            print(f"[main] ✅ Posted signal for {symbol}!")
            signals_posted += 1
        else:
            print(f"[main] ❌ Failed to post signal for {symbol}")

    print(f"\n[main] Done! Posted {signals_posted} signal(s) this run.")
    if signals_posted == 0:
        print("[main] No strong signals found this hour — market may be ranging.")


if __name__ == "__main__":
    main()
