#!/usr/bin/env python3
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bot"))
sys.path.insert(0, os.path.dirname(__file__))

from cornix_bot import fetch_pending_signals, delete_signal_file, format_signal
from poster import post_to_square


def main():
    print("=" * 50)
    print("📡 Cornix → Binance Square Bot")
    print("=" * 50)

    pending = fetch_pending_signals()

    if not pending:
        print("[main] ✅ No pending signals. Nothing to do.")
        sys.exit(0)

    print(f"[main] Processing {len(pending)} signal(s)...")

    for i, item in enumerate(pending, 1):
        signal  = item["signal"]
        path    = item["path"]
        sha     = item["sha"]

        print(f"\n[main] Signal {i}/{len(pending)}: {str(signal)[:120]}")

        content = format_signal(signal)
        print(f"\n[main] Post preview:\n{content}\n")

        success = post_to_square(content, images=[])

        if success:
            print(f"[main] ✅ Posted! Deleting signal file...")
            delete_signal_file(path, sha)
        else:
            print(f"[main] ❌ Post failed — keeping signal file for retry")
            sys.exit(1)


if __name__ == "__main__":
    main()
