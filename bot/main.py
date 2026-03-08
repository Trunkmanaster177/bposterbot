#!/usr/bin/env python3
"""
Binance Square Mirror Bot
Monitors multiple creators and reposts to your account.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from scraper import get_all_new_posts, save_last_post_id
from poster import post_to_square


def main():
    print("=" * 50)
    print("🤖 Binance Square Mirror Bot")
    print("=" * 50)

    print("\n[bot] Checking all creators for new posts...")
    new_posts = get_all_new_posts()

    if not new_posts:
        print("[bot] ✅ No new posts from any creator. Nothing to do.")
        sys.exit(0)

    print(f"\n[bot] Found {len(new_posts)} new post(s) to mirror!")

    for post in new_posts:
        username = post.get("username", "unknown")
        content = post.get("content", "")
        post_id = post["id"]

        print(f"\n[bot] 📝 Posting from {username} (ID: {post_id})")
        print(f"[bot] Content preview: {content[:100]}...")

        if not content:
            print(f"[bot] ⚠️ No text content (image-only post?). Skipping.")
            save_last_post_id(username, post_id)
            continue

        success = post_to_square(content)

        if success:
            save_last_post_id(username, post_id)
            print(f"[bot] ✅ Successfully mirrored post from {username}!")
        else:
            print(f"[bot] ❌ Failed to post from {username}. Will retry next run.")


if __name__ == "__main__":
    main()
