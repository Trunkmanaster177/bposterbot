import os
import re
import json

TARGET_USERNAME = "ict_bull"
LAST_POST_FILE = "last_post_id.txt"
PROFILE_URL = f"https://www.binance.com/en/square/profile/{TARGET_USERNAME}"


def get_latest_post():
    """Use Playwright to scrape ict_bull's latest post (JS-rendered page)."""
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

        # Intercept API responses to grab post data directly
        captured_posts = []

        def handle_response(response):
            url = response.url
            if "feed" in url and ("profile" in url or "posts" in url or "feeds" in url):
                try:
                    data = response.json()
                    posts = _find_posts_in_json(data)
                    if posts:
                        print(f"[scraper] 🎯 Intercepted API: {url.split('?')[0][-60:]}")
                        captured_posts.extend(posts)
                except Exception:
                    pass

        page.on("response", handle_response)

        try:
            print(f"[scraper] Loading profile: {PROFILE_URL}")
            page.goto(PROFILE_URL, wait_until="networkidle", timeout=30000)

            # Wait for posts to render
            try:
                page.wait_for_selector(
                    '[class*="post"], [class*="Post"], [class*="feed"], article',
                    timeout=15000
                )
            except PWTimeout:
                print("[scraper] Selector timeout — trying to read DOM anyway...")

            # If we captured API responses, use those
            if captured_posts:
                p0 = captured_posts[0]
                post_id = str(p0.get("id") or p0.get("postId") or "")
                content = re.sub(r"<[^>]+>", "",
                    p0.get("content") or p0.get("body") or p0.get("text") or ""
                ).strip()
                print(f"[scraper] ✅ Got post {post_id} via intercepted API")
                browser.close()
                return {"id": post_id, "content": content}

            # Fallback: parse rendered DOM
            print("[scraper] Parsing rendered DOM...")
            html = page.content()

            # Extract post IDs from rendered HTML
            post_ids = re.findall(r"/en/square/post/(\d+)", html)
            if post_ids:
                post_ids = sorted(set(post_ids), key=lambda x: int(x), reverse=True)
                latest_id = post_ids[0]
                print(f"[scraper] Found post IDs in DOM: {post_ids[:3]}")

                # Try to get content from the page DOM
                content = _extract_content_from_dom(page, latest_id)

                # If no DOM content, navigate to the post page
                if not content:
                    post_url = f"https://www.binance.com/en/square/post/{latest_id}"
                    print(f"[scraper] Loading post page: {post_url}")
                    page.goto(post_url, wait_until="networkidle", timeout=20000)
                    html2 = page.content()
                    # og:description
                    og = re.search(r'<meta[^>]+property="og:description"[^>]+content="([^"]+)"', html2)
                    if og:
                        content = og.group(1).strip()
                    if not content:
                        # __NEXT_DATA__
                        nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html2, re.DOTALL)
                        if nd:
                            try:
                                page_json = json.loads(nd.group(1))
                                texts = re.findall(r'"content"\s*:\s*"((?:[^"\\]|\\.){30,})"', json.dumps(page_json))
                                if texts:
                                    content = max(texts, key=len)
                            except Exception:
                                pass

                browser.close()
                return {"id": latest_id, "content": content or ""}

            print("[scraper] ❌ No post IDs found in rendered DOM.")
            browser.close()
            return None

        except Exception as e:
            print(f"[scraper] Browser error: {e}")
            try:
                page.screenshot(path="scraper_debug.png")
                print("[scraper] Screenshot saved: scraper_debug.png")
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


def _extract_content_from_dom(page, post_id):
    """Try to extract post text from rendered DOM near the post link."""
    try:
        # Find elements containing the post link
        el = page.locator(f'a[href*="/square/post/{post_id}"]').first
        if el:
            parent = page.evaluate("""(el) => {
                let node = el;
                for (let i = 0; i < 5; i++) {
                    node = node.parentElement;
                    if (node && node.innerText && node.innerText.length > 50) {
                        return node.innerText;
                    }
                }
                return '';
            }""", el.element_handle())
            if parent and len(parent) > 30:
                return parent.strip()
    except Exception:
        pass
    return ""


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
        print(f"[scraper] 🆕 New post! {current_id} (was: {last_id})")
        return True
    print(f"[scraper] No new posts. Current: {current_id}")
    return False
