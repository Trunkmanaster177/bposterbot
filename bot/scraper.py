import os
import re
import json

TARGET_USERNAMES = ["ict_bull", "Raa_Fi"]
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
            url = response.url.lower()
            if username.lower() not in url:
                return
            try:
                if "json" in response.headers.get("content-type", ""):
                    data = response.json()
                    posts = _find_posts_in_json(data)
                    if posts:
                        print(f"[scraper] 🎯 User-specific API: {response.url.split('?')[0][-60:]}")
                        captured_posts.extend(posts)
            except Exception:
                pass

        page.on("response", handle_response)

        try:
            page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(8000)

            # Strategy 1: user-specific intercepted API (has full data including images)
            if captured_posts:
                p0 = captured_posts[0]
                post_id = str(p0.get("id") or p0.get("postId") or "")
                content = re.sub(r"<[^>]+>", "",
                    p0.get("content") or p0.get("body") or p0.get("text") or ""
                ).strip()
                images = extract_images_from_post_json(p0)
                if post_id:
                    print(f"[scraper] ✅ Got post {post_id} from {username} | images: {len(images)}")
                    browser.close()
                    return {"id": post_id, "content": content, "images": images, "username": username}

            # Strategy 2: DOM scraping
            print(f"[scraper] Parsing DOM for {username}...")
            html = page.content()
            post_ids = re.findall(r"/en/square/post/(\d+)", html)

            if post_ids:
                post_ids = sorted(set(post_ids), key=lambda x: int(x), reverse=True)
                latest_id = post_ids[0]
                print(f"[scraper] Found post IDs: {post_ids[:5]}")
                content, images = fetch_post_content_and_images(page, latest_id)
                browser.close()
                return {"id": latest_id, "content": content, "images": images, "username": username}

            # Strategy 3: direct API via browser fetch
            print(f"[scraper] Trying direct API for {username}...")
            direct_posts = try_direct_api(page, username)
            if direct_posts:
                p0 = direct_posts[0]
                post_id = str(p0.get("id") or p0.get("postId") or "")
                content = re.sub(r"<[^>]+>", "",
                    p0.get("content") or p0.get("body") or p0.get("text") or ""
                ).strip()
                images = extract_images_from_post_json(p0)
                if post_id:
                    browser.close()
                    return {"id": post_id, "content": content, "images": images, "username": username}

            print(f"[scraper] ❌ No posts found for {username}")
            browser.close()
            return None

        except PWTimeout:
            print(f"[scraper] Timeout for {username}")
            try:
                html = page.content()
                post_ids = re.findall(r"/en/square/post/(\d+)", html)
                if post_ids:
                    latest_id = sorted(post_ids, key=lambda x: int(x), reverse=True)[0]
                    browser.close()
                    return {"id": latest_id, "content": "", "images": [], "username": username}
            except Exception:
                pass
            browser.close()
            return None

        except Exception as e:
            print(f"[scraper] Error for {username}: {e}")
            browser.close()
            return None


def extract_images_from_post_json(post):
    """Extract image URLs from a post JSON object."""
    images = []
    raw = json.dumps(post)

    # Common image fields in Binance Square post JSON
    for field in ["imageList", "images", "imgList", "mediaList", "attachments", "imageUrls"]:
        val = post.get(field)
        if isinstance(val, list):
            for item in val:
                if isinstance(item, str) and item.startswith("http"):
                    images.append(item)
                elif isinstance(item, dict):
                    url = item.get("url") or item.get("imageUrl") or item.get("src") or ""
                    if url.startswith("http"):
                        images.append(url)

    # Fallback: regex extract image URLs from raw JSON
    if not images:
        urls = re.findall(r'https?://[^\s"\']+\.(?:jpg|jpeg|png|gif|webp)(?:\?[^\s"\']*)?', raw, re.IGNORECASE)
        # Filter out logos/icons, keep only content images
        images = [u for u in urls if not any(x in u.lower() for x in ["logo", "icon", "avatar", "coin", "flag"])]

    print(f"[scraper] Found {len(images)} image(s)")
    return images[:9]  # Binance Square max is 9 images per post


def fetch_post_content_and_images(page, post_id):
    """Fetch content and images from individual post page."""
    content = ""
    images = []
    try:
        post_url = f"https://www.binance.com/en/square/post/{post_id}"
        page.goto(post_url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(5000)

        post_html = page.content()

        # Get text content
        og = re.search(r'property="og:description"\s+content="([^"]+)"', post_html)
        if not og:
            og = re.search(r'content="([^"]+)"\s+property="og:description"', post_html)
        if og:
            content = og.group(1).strip()

        # Get og:image
        og_img = re.search(r'property="og:image"\s+content="([^"]+)"', post_html)
        if not og_img:
            og_img = re.search(r'content="([^"]+)"\s+property="og:image"', post_html)
        if og_img:
            img_url = og_img.group(1).strip()
            if img_url.startswith("http") and "bnbstatic" in img_url:
                images.append(img_url)

        # Try __NEXT_DATA__ for more images
        nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', post_html, re.DOTALL)
        if nd:
            try:
                page_json_str = nd.group(1)
                if not content:
                    texts = re.findall(r'"content"\s*:\s*"((?:[^"\\]|\\.){30,})"', page_json_str)
                    if texts:
                        content = max(texts, key=len)
                # Extract images from JSON
                img_urls = re.findall(r'https?://[^\s"\']+\.(?:jpg|jpeg|png|gif|webp)(?:\?[^\s"\']*)?', page_json_str, re.IGNORECASE)
                for u in img_urls:
                    if u not in images and not any(x in u.lower() for x in ["logo", "icon", "avatar", "coin"]):
                        images.append(u)
            except Exception:
                pass

        print(f"[scraper] Post {post_id}: {len(content)} chars, {len(images)} images")
    except Exception as e:
        print(f"[scraper] Content fetch error: {e}")

    return content, images[:9]


def try_direct_api(page, username):
    endpoints = [
        f"https://www.binance.com/bapi/feed/v1/friendly/feed/profile/posts?username={username}&pageSize=5&pageIndex=1",
        f"https://www.binance.com/bapi/feed/v1/friendly/square/profile/post/list?username={username}&pageSize=5",
        f"https://www.binance.com/bapi/composite/v4/friendly/pgc/feed/profile/list?username={username}&pageSize=5",
    ]
    for url in endpoints:
        try:
            result = page.evaluate(f"""
                async () => {{
                    const r = await fetch('{url}', {{
                        headers: {{ 'Accept': 'application/json' }}
                    }});
                    return await r.json();
                }}
            """)
            posts = _find_posts_in_json(result)
            if posts:
                return posts
        except Exception:
            pass
    return []


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


def get_all_new_posts():
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
    if not os.path.exists(LAST_POST_FILE):
        return {}
    try:
        with open(LAST_POST_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def save_last_post_id(username, post_id):
    ids = load_all_last_ids()
    ids[username] = str(post_id)
    with open(LAST_POST_FILE, "w") as f:
        json.dump(ids, f, indent=2)
    print(f"[scraper] Saved {username}: {post_id}")
