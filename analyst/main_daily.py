#!/usr/bin/env python3
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bot"))
sys.path.insert(0, os.path.dirname(__file__))

from daily_post import build_daily_post
from poster import post_to_square


def main():
    print("=" * 50)
    print("📚 Daily Educational Post Bot")
    print("=" * 50)

    print("\n[main] Generating today's educational post...")
    content = build_daily_post()

    if not content:
        print("[main] ❌ Failed to generate post")
        sys.exit(1)

    print(f"\n[main] Post preview ({len(content)} chars):\n")
    print(content[:500] + "..." if len(content) > 500 else content)
    print()

    success = post_to_square(content, images=[])

    if success:
        print("[main] ✅ Daily educational post published!")
    else:
        print("[main] ❌ Failed to post")
        sys.exit(1)


if __name__ == "__main__":
    main()
