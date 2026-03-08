import requests
import json
import os
import re
from bs4 import BeautifulSoup

TARGET_USERNAME = "ict_bull"
LAST_POST_FILE = "last_post_id.txt"

# Realistic browser headers to avoid 403
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.binance.com/en/square",
    "Origin": "https://www.binance.com",
    "sec-ch-ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "Connection": "keep-alive",
    "TE": "trailers",
}

# Multiple API endpoints to try
API_ENDPOINTS = [
    {
        "url": "https://www.binance.com/bapi/feed/v1/friendly/feed/profile/posts",
        "params": {"username": TARGET_USERNAME, "pageSize": 5, "pageIndex": 1},
        "method": "GET",
    },
    {
        "url": "https://www.binance.com/bapi/feed/v1/friendly/feed/square/profile/posts",
        "params": {"username": TARGET_USERNAME, "pageSize": 5, "pageIndex": 1},
        "method": "GET",
    },
    {
        "url": "https://www.binance.com/bapi/feed/v2/friendly/feed/profile/posts",
        "params": {"username": TARGET_USERNAME, "pageSize": 5, "pageIndex": 1},
        "method": "GET",
    },
    {
        "url": "https://www.binance.com/bapi/feed/v1/friendly/feed/profile/posts",
        "params": {"username": TARGET_USERNAME, "pageSize": 5, "pageIndex": 1, "type": 0},
        "method": "GET",
    },
]

# Sitemap-based approach — Binance exposes post IDs via sitemap
SITEMAP_URL = f"https://www.binance.com/en/square/sitemap/post/1"
PROFILE_URL = f"https://www.binance.com/en/square/profile/{TARGET_USERNAME}"


def get_session():
    """Create a requests session that mimics a real browser."""
    session = requests.Session()
    session.headers.update(HEADERS)
    # First visit homepage to get cookies
    try:
        session.get("https://www.binance.com/en/square", timeout=10)
    except Exception:
        pass
    return session


def try_api_endpoints(session):
    """Try all known API endpoints."""
    for ep in API_ENDPOINTS:
        try:
            resp = session.get(ep["url"], params=ep["params"], timeout=15)
            print(f"[scraper] {ep['url']} → {resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                posts = (
                    data.get("data", {}).get("feeds")
                    or data.get("data", {}).get("list")
                    or data.get("data", {}).get("posts")
                    or []
                )
                if posts:
                    return posts
        except Exception as e:
            print(f"[scraper] Endpoint failed: {e}")
    return []


def try_post_page(session, post_id):
    """Fetch a specific post page to extract content."""
    url = f"https://www.binance.com/en/square/post/{post_id}"
    try:
        resp = session.get(url, timeout=15)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            # Try meta description first (usually has post content)
            meta = soup.find("meta", {"name": "description"}) or \
                   soup.find("meta", {"property": "og:description"})
            if meta and meta.get("content"):
                return meta["content"].strip()
            # Try main content area
            for sel in ["article", "main", '[class*="post-content"]', '[class*="content"]']:
                el = soup.select_one(sel)
                if el:
                    text = el.get_text(separator="\n", strip=True)
                    if len(text) > 20:
                        return text
    except Exception as e:
        print(f"[scraper] Post page fetch failed: {e}")
    return ""


def get_latest_post_id_from_sitemap(session):
    """Get latest post IDs from Binance Square sitemap."""
    try:
        resp = session.get(SITEMAP_URL, timeout=15)
        if resp.status_code == 200:
            # Extract post IDs from sitemap
            ids = re.findall(r"/en/square/post/(\d+)", resp.text)
            if ids:
                return str(max(int(i) for i in ids))
    except Exception as e:
        print(f"[scraper] Sitemap failed: {e}")
    return None


def get_post_ids_from_profile(session):
    """Scrape profile page for post IDs."""
    try:
        resp = session.get(PROFILE_URL, timeout=20)
        print(f"[scraper] Profile page → {resp.status_code}")
        if resp.status_code == 200:
            ids = re.findall(r"/en/square/post/(\d+)", resp.text)
            if ids:
                # Return sorted descending (latest first)
                return sorted(set(ids), key=lambda x: int(x), reverse=True)
            # Also try JSON embedded in page (Next.js __NEXT_DATA__)
            match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', resp.text, re.DOTALL)
            if match:
                try:
                    page_data = json.loads(match.group(1))
                    page_str = json.dumps(page_data)
                    ids = re.findall(r'"(?:id|postId)"\s*:\s*"?(\d{10,})"?', page_str)
                    if ids:
                        return sorted(set(ids), key=lambda x: int(x), reverse=True)
                except Exception:
                    pass
    except Exception as e:
        print(f"[scraper] Profile scrape failed: {e}")
    return []


def get_latest_post():
    """Main function — fetch the latest post from ict_bull."""
    session = get_session()

    # Strategy 1: Try official API endpoints
    print("[scraper] Strategy 1: Trying API endpoints...")
    posts = try_api_endpoints(session)
    if posts:
        latest = posts[0]
        post_id = str(latest.get("id") or latest.get("postId") or "")
        content = re.sub(r"<[^>]+>", "", 
            latest.get("content") or latest.get("body") or latest.get("text") or ""
        ).strip()
        if post_id:
            print(f"[scraper] ✅ Got post {post_id} via API")
            return {"id": post_id, "content": content}

    # Strategy 2: Scrape profile page for post IDs
    print("[scraper] Strategy 2: Scraping profile page...")
    post_ids = get_post_ids_from_profile(session)
    if post_ids:
        latest_id = post_ids[0]
        print(f"[scraper] Found post IDs: {post_ids[:3]}")
        # Fetch the actual post content
        content = try_post_page(session, latest_id)
        print(f"[scraper] ✅ Got post {latest_id} via profile scrape")
        return {"id": latest_id, "content": content}

    # Strategy 3: Sitemap
    print("[scraper] Strategy 3: Trying sitemap...")
    latest_id = get_latest_post_id_from_sitemap(session)
    if latest_id:
        content = try_post_page(session, latest_id)
        print(f"[scraper] ✅ Got post {latest_id} via sitemap")
        return {"id": latest_id, "content": content}

    print("[scraper] ❌ All strategies failed.")
    return None


def get_last_post_id():
    if os.path.exists(LAST_POST_FILE):
        with open(LAST_POST_FILE, "r") as f:
            return f.read().strip()
    return None


def save_last_post_id(post_id):
    with open(LAST_POST_FILE, "w") as f:
        f.write(str(post_id))
    print(f"[scraper] Saved last post ID: {post_id}")


def is_new_post(post):
    if not post:
        return False
    last_id = get_last_post_id()
    current_id = str(post["id"])
    if last_id is None:
        print(f"[scraper] First run — saving baseline post ID: {current_id}")
        save_last_post_id(current_id)
        return False
    if current_id != last_id:
        print(f"[scraper] 🆕 New post! {current_id} (was: {last_id})")
        return True
    print(f"[scraper] No new posts. Current: {current_id}")
    return False
