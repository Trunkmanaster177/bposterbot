import os
import re
import json

TARGET_USERNAME = "ict_bull"
LAST_POST_FILE = "last_post_id.txt"
PROFILE_URL = f"https://www.binance.com/en/square/profile/{TARGET_USERNAME}"


def get_latest_post():
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    print("[scraper] Launching headless browser...")

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

        # Intercept API responses
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
            print(f"[scraper] Loading profile...")
            # Use domcontentloaded instead of networkidle — much faster
            page.goto(PROFILE_URL, wait_until="domcontentloaded", timeout=30000)

            # Wait a bit for JS/API calls to fire
            page.wait_for_timeout(8000)

            # Check intercepted API data first
            if captured_posts:
                p0 = captured_posts[0]
                post_id = str(p0.get("id") or p0.get("postId") or "")
                content = re.sub(r"<[^>]+>", "",
                    p0.get("content") or p0.get("body") or p0.get("text") or ""
                ).strip()
                if post_id:
                    print(f"[scraper] ✅ Got post {post_id} via intercepted API")
                    browser.close()
                    return {"id": post_id, "content": content}

            # Fallback: extract post IDs from rendered HTML
            print("[scraper] Parsing rendered DOM for post IDs...")
            html = page.content()
            post_ids = re.findall(r"/en/square/post/(\d+)", html)

            if post_ids:
                post_ids = sorted(set(post_ids), key=lambda x: int(x), reverse=True)
                latest_id = post_ids[0]
                print(f"[scraper] Found post IDs: {post_ids[:3]}")

                # Navigate to individual post to get content
                post_url = f"https://www.binance.com/en/square/post/{latest_id}"
                print(f"[scraper] Loading post page: {post_url}")
                page.goto(post_url, wait_until="domcontentloaded", timeout=20000)
                page.wait_for_timeout(5000)

                post_html = page.content()
                content = ""

                # Try og:description
                og = re.search(r'property="og:description"\s+content="([^"]+)"', post_html)
                if not og:
                    og = re.search(r'content="([^"]+)"\s+property="og:description"', post_html)
                if og:
                    content = og.group(1).strip()
                    print(f"[scraper] Got content from og:description ({len(content)} chars)")

                # Try __NEXT_DATA__
                if not content:
                    nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', post_html, re.DOTALL)
                    if nd:
                        try:
                            texts = re.findall(r'"content"\s*:\s*"((?:[^"\\]|\\.){30,})"', nd.group(1))
                            if texts:
                                content = max(texts, key=len)
                                print(f"[scraper] Got content from __NEXT_DATA__ ({len(content)} chars)")
                        except Exception:
                            pass

                browser.close()
                return {"id": latest_id, "content": content}

            print("[scraper] ❌ No post IDs found in DOM.")
            page.screenshot(path="scraper_debug.png")
            browser.close()
            return None

        except PWTimeout as e:
            print(f"[scraper] Timeout: {e}")
            try:
                # Even on timeout, try to read whatever loaded
                html = page.content()
                post_ids = re.findall(r"/en/square/post/(\d+)", html)
                if post_ids:
                    latest_id = sorted(post_ids, key=lambda x: int(x), reverse=True)[0]
                    print(f"[scraper] Got post ID from partial load: {latest_id}")
                    browser.close()
                    return {"id": latest_id, "content": ""}
                page.screenshot(path="scraper_debug.png")
            except Exception:
                pass
            browser.close()
            return None

        except Exception as e:
            print(f"[scraper] Error: {e}")
            try:
                page.screenshot(path="scraper_debug.png")
            except Exception:
                pass
            browser.close()
            return None


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
        print(f"[scraper] 🆕 New post! {current_id} (was: {last_id})")
        return True
    print(f"[scraper] No new posts. Current: {current_id}")
    return False
