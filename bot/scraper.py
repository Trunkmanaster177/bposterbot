import requests
import json
import os
import re
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET

TARGET_USERNAME = "ict_bull"
LAST_POST_FILE = "last_post_id.txt"

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.binance.com/en/square",
    "Origin": "https://www.binance.com",
})


# ── Strategy 1: Binance Square sitemap XML ───────────────────────────────────
def try_sitemap():
    """
    Binance exposes a sitemap with all post IDs.
    We grab page 1 (newest posts) and find ict_bull's posts.
    """
    for page in range(1, 4):
        url = f"https://www.binance.com/en/square/sitemap/post/{page}"
        try:
            resp = SESSION.get(url, timeout=15)
            print(f"[scraper] Sitemap page {page} → {resp.status_code}")
            if resp.status_code != 200:
                continue

            # Try XML parse
            try:
                root = ET.fromstring(resp.content)
                ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
                urls = [loc.text for loc in root.findall(".//sm:loc", ns)]
                if urls:
                    ids = [re.search(r"/post/(\d+)", u).group(1) for u in urls if re.search(r"/post/(\d+)", u)]
                    if ids:
                        print(f"[scraper] Found {len(ids)} post IDs in sitemap")
                        return sorted(ids, key=lambda x: int(x), reverse=True)
            except ET.ParseError:
                pass

            # Fallback: regex on raw text
            ids = re.findall(r"/en/square/post/(\d+)", resp.text)
            if ids:
                print(f"[scraper] Found {len(ids)} post IDs via regex")
                return sorted(set(ids), key=lambda x: int(x), reverse=True)

        except Exception as e:
            print(f"[scraper] Sitemap page {page} error: {e}")
    return []


# ── Strategy 2: Binance Square internal GraphQL / REST ───────────────────────
def try_internal_api():
    """Try Binance's internal bapi endpoints with various auth patterns."""
    endpoints = [
        f"https://www.binance.com/bapi/feed/v1/friendly/feed/profile/timeline?username={TARGET_USERNAME}&pageSize=10",
        f"https://www.binance.com/bapi/feed/v1/friendly/square/profile/post/list?username={TARGET_USERNAME}&pageSize=10",
        f"https://www.binance.com/bapi/asset/v2/public/square/feed/list?username={TARGET_USERNAME}",
        f"https://www.binance.com/bapi/feed/v1/public/feed/profile/posts?username={TARGET_USERNAME}&pageSize=5",
        f"https://www.binance.com/bapi/feed/v1/friendly/feed/user/posts?username={TARGET_USERNAME}&pageSize=5&pageIndex=1",
        f"https://www.binance.com/bapi/composite/v1/public/square/profile/feed?username={TARGET_USERNAME}",
    ]
    for url in endpoints:
        try:
            resp = SESSION.get(url, timeout=12)
            print(f"[scraper] {url.split('?')[0].split('/')[-3:]} → {resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                # Walk the response tree looking for post arrays
                posts = _find_posts_in_json(data)
                if posts:
                    print(f"[scraper] ✅ Found {len(posts)} posts via internal API")
                    return posts
        except Exception:
            pass
    return []


def _find_posts_in_json(data, depth=0):
    """Recursively search JSON for a list of post objects."""
    if depth > 5:
        return []
    if isinstance(data, list) and len(data) > 0:
        first = data[0]
        if isinstance(first, dict) and any(k in first for k in ["id", "postId", "content", "body"]):
            return data
    if isinstance(data, dict):
        for v in data.values():
            result = _find_posts_in_json(v, depth + 1)
            if result:
                return result
    return []


# ── Strategy 3: Fetch individual post page content ───────────────────────────
def fetch_post_content(post_id):
    """Fetch content from a post's og:description meta tag."""
    url = f"https://www.binance.com/en/square/post/{post_id}"
    try:
        resp = SESSION.get(url, timeout=15)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            # og:description has the post text
            for attr in [("property", "og:description"), ("name", "description"), ("property", "og:title")]:
                tag = soup.find("meta", {attr[0]: attr[1]})
                if tag and tag.get("content", "").strip():
                    return tag["content"].strip()
            # __NEXT_DATA__ JSON
            nd = soup.find("script", {"id": "__NEXT_DATA__"})
            if nd:
                try:
                    page_json = json.loads(nd.string)
                    text = json.dumps(page_json)
                    # Find content fields
                    matches = re.findall(r'"content"\s*:\s*"((?:[^"\\]|\\.){20,})"', text)
                    if matches:
                        return max(matches, key=len).encode().decode("unicode_escape")
                except Exception:
                    pass
    except Exception as e:
        print(f"[scraper] Post content fetch error: {e}")
    return ""


# ── Strategy 4: RSS feed ─────────────────────────────────────────────────────
def try_rss():
    """Some Binance Square profiles expose RSS."""
    urls = [
        f"https://www.binance.com/en/square/profile/{TARGET_USERNAME}/rss",
        f"https://www.binance.com/en/square/rss/{TARGET_USERNAME}",
        f"https://www.binance.com/bapi/feed/v1/public/rss/{TARGET_USERNAME}",
    ]
    for url in urls:
        try:
            resp = SESSION.get(url, timeout=10)
            print(f"[scraper] RSS {url} → {resp.status_code}")
            if resp.status_code == 200 and "<item>" in resp.text:
                root = ET.fromstring(resp.content)
                items = root.findall(".//item")
                if items:
                    first = items[0]
                    title = first.findtext("title", "")
                    desc = first.findtext("description", "")
                    link = first.findtext("link", "")
                    post_id = re.search(r"/post/(\d+)", link)
                    pid = post_id.group(1) if post_id else "rss_0"
                    content = desc or title
                    content = re.sub(r"<[^>]+>", "", content).strip()
                    return {"id": pid, "content": content}
        except Exception:
            pass
    return None


# ── Main entry point ─────────────────────────────────────────────────────────
def get_latest_post():
    """Try all strategies to get the latest post from ict_bull."""

    # Try RSS first (cleanest)
    print("[scraper] Strategy 1: RSS feed...")
    rss = try_rss()
    if rss:
        print(f"[scraper] ✅ Got post via RSS: {rss['id']}")
        return rss

    # Try internal API
    print("[scraper] Strategy 2: Internal API endpoints...")
    posts = try_internal_api()
    if posts:
        p = posts[0]
        pid = str(p.get("id") or p.get("postId") or "")
        content = re.sub(r"<[^>]+>", "", p.get("content") or p.get("body") or p.get("text") or "").strip()
        if pid:
            return {"id": pid, "content": content}

    # Try sitemap to get post IDs, then fetch content
    print("[scraper] Strategy 3: Sitemap + post content...")
    post_ids = try_sitemap()
    if post_ids:
        latest_id = post_ids[0]
        print(f"[scraper] Latest sitemap post ID: {latest_id}, fetching content...")
        content = fetch_post_content(latest_id)
        return {"id": latest_id, "content": content}

    print("[scraper] ❌ All strategies exhausted.")
    return None


# ── State helpers ─────────────────────────────────────────────────────────────
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
        print(f"[scraper] First run — saving baseline: {current_id}")
        save_last_post_id(current_id)
        return False
    if current_id != last_id:
        print(f"[scraper] 🆕 New post detected! {current_id} (was: {last_id})")
        return True
    print(f"[scraper] No new posts. Current: {current_id}")
    return False
