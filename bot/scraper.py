import os
import re
import json

TARGET_USERNAMES = ["ict_bull", "Raa_Fi"]  # Add more creators here anytime
LAST_POST_FILE = "last_post_id.txt"


def get_latest_post_for_user(username):
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    profile_url = f"https://www.binance.com/en/square/profile/{username}"
    print(f"[scraper] Checking {username}...")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="en-US",
        )
        page = context.new_page()

        captured_posts = []

        def handle_response(response):
            url = response.url
            if "feed" in url or "square" in url:
                try:
                    if "json" in response.headers.get("content-type", ""):
                        data = response.json()
                        posts = _find_posts_in_json(data)
                        if posts:
                            print(f"[scraper] 🎯 Intercepted: {url.split('?')[0][-50:]}")
                            captured_posts.extend(posts)
                except Exception:
                    pass

        page.on("response", handle_response)

        try:
            page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(8000)

            if captured_posts:
                p0 = captured_posts[0]
                post_id = str(p0.get("id") or p0.get("postId") or "")
                content = re.sub(r"<[^>]+>", "",
                    p0.get("content") or p0.get("body") or p0.get("text") or ""
                ).strip()
                if post_id:
                    print(f"[scraper] ✅ Got post {post_id} from {username} via intercepted API")
                    browser.close()
                    return {"id": post_id, "content": content, "username": username}

            # Fallback: extract post IDs from rendered HTML
            print(f"[scraper] Parsing DOM for {username}...")
            html = page.content()
            post_ids = re.findall(r"/en/square/post/(\d+)", html)

            if post_ids:
                post_ids = sorted(set(post_ids), key=lambda x: int(x), reverse=True)
                latest_id = post_ids[0]
                print(f"[scraper] Found post IDs: {post_ids[:3]}")

                post_url = f"https://www.binance.com/en/square/post/{latest_id}"
                page.goto(post_url, wait_until="domcontentloaded", timeout=20000)
                page.wait_for_timeout(5000)

                post_html = page.content()
                content = ""

                og = re.search(r'property="og:description"\s+content="([^"]+)"', post_html)
                if not og:
                    og = re.search(r'content="([^"]+)"\s+property="og:description"', post_html)
                if og:
                    content = og.group(1).strip()

                if not content:
                    nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', post_html, re.DOTALL)
                    if nd:
                        try:
                            texts = re.findall(r'"content"\s*:\s*"((?:[^"\\]|\\.){30,})"', nd.group(1))
                            if texts:
                                content = max(texts, key=len)
                        except Exception:
                            pass

                browser.close()
                return {"id": latest_id, "content": content, "username": username}

            print(f"[scraper] ❌ No posts found for {username}")
            browser.close()
            return None

        except PWTimeout as e:
            print(f"[scraper] Timeout for {username}: {e}")
            try:
                html = page.content()
                post_ids = re.findall(r"/en/square/post/(\d+)", html)
                if post_ids:
                    latest_id = sorted(post_ids, key=lambda x: int(x), reverse=True)[0]
                    browser.close()
                    return {"id": latest_id, "content": "", "username": username}
            except Exception:
                pass
            browser.close()
            return None

        except Exception as e:
            print(f"[scraper] Error for {username}: {e}")
            browser.close()
            return None


def get_all_new_posts():
    """Check all creators and return list of new posts."""
    new_posts = []
    last_ids = load_all_last_ids()

    for username in TARGET_USERNAMES:
        post = get_latest_post_for_user(username)
        if not post:
            continue

        last_id = last_ids.get(username)
        current_id = str(post["id"])

        if last_id is None:
            print(f"[scraper] First run for {username} — saving baseline: {current_id}")
            save_last_post_id(username, current_id)
        elif current_id != last_id:
            print(f"[scraper] 🆕 New post from {username}! {current_id} (was: {last_id})")
            new_posts.append(post)
        else:
            print(f"[scraper] No new posts from {username}. Current: {current_id}")

    return new_posts


def load_all_last_ids():
    """Load last post IDs for all creators from file."""
    if not os.path.exists(LAST_POST_FILE):
        return {}
    try:
        with open(LAST_POST_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def save_last_post_id(username, post_id):
    """Save last post ID for a specific creator."""
    ids = load_all_last_ids()
    ids[username] = str(post_id)
    with open(LAST_POST_FILE, "w") as f:
        json.dump(ids, f, indent=2)
    print(f"[scraper] Saved {username}: {post_id}")


def _find_posts_in_json(data, depth=0):
    if depth > 6:
        return []
    if isinstance(data, list) and len(data) > 0:
        if isinstance(data[0], dict) and any(k in data[0] for k in ["id", "postId", "content", "body"]):
            return data
    if isinstance(data, dict):
        for v in data.values():
            result = _find_posts_in_json(v, depth + 1)
            if result:
                return result
    return []
