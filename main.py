#!/usr/bin/env python3
"""
Binance Square Mirror Bot
Monitors ict_bull on Binance Square and reposts to your account.
"""

import sys
import os

# Add bot directory to path
sys.path.insert(0, os.path.dirname(__file__))

from scraper import get_latest_post, is_new_post, save_last_post_id
from poster import post_to_square


def main():
    print("=" * 50)
    print("🤖 Binance Square Mirror Bot")
    print("=" * 50)

    # Step 1: Fetch latest post from ict_bull
    print("\n[bot] Fetching latest post from ict_bull...")
    post = get_latest_post()

    if post is None:
        print("[bot] ❌ Failed to fetch posts. Exiting.")
        sys.exit(1)

    print(f"[bot] Latest post ID: {post['id']}")
    print(f"[bot] Content preview: {post['content'][:100]}...")

    # Step 2: Check if it's a new post
    if not is_new_post(post):
        print("[bot] ✅ No new posts. Nothing to do.")
        sys.exit(0)

    # Step 3: Post the content as-is to your Binance Square
    content = post["content"]
    if not content:
        print("[bot] ⚠️ Post has no text content (might be image-only). Skipping.")
        save_last_post_id(post["id"])
        sys.exit(0)

    print(f"\n[bot] 📝 Posting content ({len(content)} chars)...")
    print("-" * 40)
    print(content[:300] + ("..." if len(content) > 300 else ""))
    print("-" * 40)

    success = post_to_square(content)

    if success:
        save_last_post_id(post["id"])
        print(f"\n[bot] ✅ Successfully mirrored post {post['id']}!")
    else:
        print(f"\n[bot] ❌ Failed to post. Will retry next run.")
        sys.exit(1)


if __name__ == "__main__":
    main()
