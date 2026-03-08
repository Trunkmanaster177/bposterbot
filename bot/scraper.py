import requests
import json
import os
import re
from bs4 import BeautifulSoup

TARGET_USERNAME = "ict_bull"
PROFILE_URL = f"https://www.binance.com/en/square/profile/{TARGET_USERNAME}"
LAST_POST_FILE = "last_post_id.txt"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.binance.com/en/square",
}

# Binance Square internal feed API (reverse-engineered from network tab)
FEED_API_URL = "https://www.binance.com/bapi/feed/v1/friendly/feed/profile/posts"


def get_latest_post():
    """Fetch the latest post from ict_bull via Binance Square feed API."""
    params = {
        "username": TARGET_USERNAME,
        "pageSize": 5,
        "pageIndex": 1,
    }

    try:
        resp = requests.get(FEED_API_URL, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        posts = data.get("data", {}).get("feeds", [])
        if not posts:
            # Fallback: try alternate endpoint
            posts = data.get("data", {}).get("list", [])

        if not posts:
            print("[scraper] No posts found via API. Trying HTML scrape fallback...")
            return scrape_html_fallback()

        latest = posts[0]
        post_id = str(latest.get("id") or latest.get("postId") or "")
        content = (
            latest.get("content")
            or latest.get("body")
            or latest.get("text")
            or ""
        )
        # Strip HTML tags if present
        content = re.sub(r"<[^>]+>", "", content).strip()

        return {"id": post_id, "content": content, "raw": latest}

    except Exception as e:
        print(f"[scraper] API fetch failed: {e}. Falling back to HTML scrape...")
        return scrape_html_fallback()


def scrape_html_fallback():
    """Fallback: scrape the profile page HTML for the latest post text."""
    try:
        resp = requests.get(PROFILE_URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Find post links like /en/square/post/XXXXXXX
        post_links = soup.find_all("a", href=re.compile(r"/en/square/post/(\d+)"))
        if not post_links:
            print("[scraper] No post links found in HTML.")
            return None

        # Get highest post ID (latest)
        post_ids = []
        for link in post_links:
            match = re.search(r"/en/square/post/(\d+)", link["href"])
            if match:
                post_ids.append(int(match.group(1)))

        if not post_ids:
            return None

        latest_id = str(max(post_ids))

        # Try to find the post text near this link
        for link in post_links:
            if latest_id in link.get("href", ""):
                # Walk up to find parent container with text
                parent = link.find_parent()
                for _ in range(5):
                    if parent and parent.get_text(strip=True):
                        text = parent.get_text(separator="\n", strip=True)
                        if len(text) > 30:
                            return {"id": latest_id, "content": text, "raw": {}}
                    parent = parent.find_parent() if parent else None

        return {"id": latest_id, "content": "", "raw": {}}

    except Exception as e:
        print(f"[scraper] HTML fallback failed: {e}")
        return None


def get_last_post_id():
    """Read the last posted post ID from file."""
    if os.path.exists(LAST_POST_FILE):
        with open(LAST_POST_FILE, "r") as f:
            return f.read().strip()
    return None


def save_last_post_id(post_id):
    """Save the latest post ID to file."""
    with open(LAST_POST_FILE, "w") as f:
        f.write(str(post_id))
    print(f"[scraper] Saved last post ID: {post_id}")


def is_new_post(post):
    """Check if this post is newer than the last one we processed."""
    if not post:
        return False
    last_id = get_last_post_id()
    current_id = str(post["id"])
    if last_id is None:
        print(f"[scraper] First run — saving post ID {current_id} as baseline.")
        save_last_post_id(current_id)
        return False  # Don't post on first run, just set baseline
    if current_id != last_id:
        print(f"[scraper] New post detected! ID: {current_id} (prev: {last_id})")
        return True
    print(f"[scraper] No new posts. Latest ID: {current_id}")
    return False
