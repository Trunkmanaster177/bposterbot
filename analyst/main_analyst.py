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

        # Filter: only analyze if RSI is not neutral AND some price movement
        if 45 <= rsi <= 55 and abs(change_2h) < 1:
            print(f"[main] Skipping {symbol} — RSI neutral, no clear momentum")
            continue

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
            signals_posted += 1
        else:
            print(f"[main] ❌ Failed to post for {symbol}")

    print(f"\n[main] Done! Posted {signals_posted} signal(s) this run.")
    if signals_posted == 0:
        print("[main] No strong signals found this hour.")


if __name__ == "__main__":
    main()
