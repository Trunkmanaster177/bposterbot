import os
import re
import json
import requests
import xml.etree.ElementTree as ET

LAST_POST_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pf_last_id.txt"
)

# Free Telegram → RSS/JSON API (no signup needed)
# Returns last 20 posts from any public channel as JSON
TG_JSON_URL = "https://tg.i-c-a.su/json/freepfsignals"

HASHTAGS = "#ProfitFarmers #CryptoSignals #TradingSignals #BinanceSquare #Crypto #Trading"


def load_last_id():
    if not os.path.exists(LAST_POST_FILE):
        return None
    try:
        return open(LAST_POST_FILE).read().strip()
    except Exception:
        return None


def save_last_id(post_id):
    with open(LAST_POST_FILE, "w") as f:
        f.write(str(post_id))
    print(f"[pf] Saved last ID: {post_id}")


def format_post(text: str) -> str:
    text = text.strip()
    if not text:
        return ""
    return f"{text}\n\n{HASHTAGS}"


def get_new_posts():
    """Fetch latest posts from ProfitFarmers Telegram channel via JSON API."""
    last_id = load_last_id()
    print(f"[pf] Last seen ID: {last_id}")

    try:
        print(f"[pf] Fetching from {TG_JSON_URL}...")
        resp = requests.get(TG_JSON_URL, timeout=15, headers={
            "User-Agent": "Mozilla/5.0"
        })
        print(f"[pf] Response: {resp.status_code}")

        if resp.status_code != 200:
            print(f"[pf] ❌ API returned {resp.status_code}")
            return []

        data = resp.json()
        messages = data if isinstance(data, list) else data.get("messages") or data.get("items") or []
        print(f"[pf] Got {len(messages)} messages")

        if not messages:
            print(f"[pf] No messages returned")
            return []

        # Normalize messages
        posts = []
        for m in messages:
            mid = str(m.get("id") or m.get("message_id") or "")
            text = (m.get("text") or m.get("message") or m.get("content") or "").strip()
            # Extract images
            images = []
            photo = m.get("photo") or m.get("image") or ""
            if photo and isinstance(photo, str) and photo.startswith("http"):
                images.append(photo)
            if mid:
                posts.append({"id": mid, "text": text, "images": images})

        if not posts:
            print(f"[pf] No valid posts found")
            return []

        # Sort by ID
        posts.sort(key=lambda x: int(x["id"]))
        latest_id = posts[-1]["id"]

        # First run — save baseline
        if last_id is None:
            print(f"[pf] First run — saving baseline: {latest_id}")
            save_last_id(latest_id)
            return []

        # Return only new posts
        new_posts = [p for p in posts if int(p["id"]) > int(last_id)]
        print(f"[pf] New posts: {len(new_posts)}")

        if new_posts:
            save_last_id(new_posts[-1]["id"])

        return new_posts

    except Exception as e:
        print(f"[pf] Error: {e}")
        return []
