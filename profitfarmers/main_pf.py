#!/usr/bin/env python3
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bot"))
sys.path.insert(0, os.path.dirname(__file__))

from pf_scraper import get_new_posts, format_post
from poster import post_to_square


def main():
    print("=" * 50)
    print("📡 ProfitFarmers → Binance Square Bot")
    print("=" * 50)

    new_posts = get_new_posts()

    if not new_posts:
        print("[main] ✅ No new signals. Nothing to do.")
        sys.exit(0)

    print(f"[main] Found {len(new_posts)} new signal(s)!")

    for i, post in enumerate(new_posts, 1):
        print(f"\n[main] Signal {i}/{len(new_posts)} (ID: {post['id']}):")
        print(f"  Text: {post['text'][:120]}")

        content = format_post(post["text"])
        images = post.get("images", [])

        print(f"\n[main] Post preview:\n{content}\n")

        success = post_to_square(content, images=images)

        if success:
            print(f"[main] ✅ Posted signal {post['id']} successfully!")
        else:
            print(f"[main] ❌ Failed to post signal {post['id']}")
            sys.exit(1)


if __name__ == "__main__":
    main()
