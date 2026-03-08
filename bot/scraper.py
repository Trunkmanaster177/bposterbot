import os
import re
import json

TARGET_USERNAMES = ["ict_bull", "Raa_Fi"]
LAST_POST_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "last_post_id.txt")
BINANCE_COOKIES = os.environ.get("BINANCE_COOKIES", "")


def _inject_cookies(context):
    if not BINANCE_COOKIES:
        return
    try:
        cookies_raw = json.loads(BINANCE_COOKIES)
        playwright_cookies = []
        for c in cookies_raw:
            cookie = {
                "name": c["name"],
                "value": c["value"],
                "domain": c["domain"],
                "path": c.get("path", "/"),
                "secure": c.get("secure", False),
                "httpOnly": c.get("httpOnly", False),
            }
            if "expirationDate" in c:
                cookie["expires"] = int(c["expirationDate"])
            samesite = c.get("sameSite", "")
            if samesite and samesite.lower() not in ["unspecified", ""]:
                ss = samesite.capitalize()
                if ss in ["Strict", "Lax", "None"]:
                    cookie["sameSite"] = ss
            playwright_cookies.append(cookie)
        context.add_cookies(playwright_cookies)
        print(f"[scraper] Injected {len(playwright_cookies)} cookies")
    except Exception as e:
        print(f"[scraper] Cookie inject error: {e}")


def get_latest_post_for_user(username):
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

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
        _inject_cookies(context)
        page = context.new_page()

        # Intercept all JSON responses that contain this user's posts
        intercepted_posts = []

        def on_response(response):
            url = response.url
            if "bapi" not in url:
                return
            if response.status != 200:
                return
            try:
                ct = response.headers.get("content-type", "")
                if "json" not in ct:
                    return
                data = response.json()
                raw = json.dumps(data)
                # Only capture if response contains the username
                if username.lower() in raw.lower():
                    found = _find_posts_in_json(data)
                    if found:
                        print(f"[scraper] 🎯 Intercepted: {url.split('?')[0][-55:]}")
                        intercepted_posts.extend(found)
            except Exception:
                pass

        page.on("response", on_response)

        try:
            profile_url = f"https://www.binance.com/en/square/profile/{username}"
            print(f"[scraper] Loading profile: {profile_url}")
            page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(10000)  # Wait for API calls to fire

            # Use intercepted API data (most reliable — profile-specific)
            if intercepted_posts:
                p0 = intercepted_posts[0]
                post_id = str(p0.get("id") or p0.get("postId") or "")
                content = extract_plain_text(p0.get("content") or p0.get("body") or p0.get("text") or "")
                images = _extract_images(p0)
                if post_id:
                    print(f"[scraper] ✅ {username} → post {post_id} | {len(content)} chars | {len(images)} imgs")
                    browser.close()
                    return {"id": post_id, "content": content, "images": images, "username": username}

            # Fallback: try authenticated API calls from browser context
            print(f"[scraper] Trying authenticated API calls for {username}...")
            api_urls = [
                f"https://www.binance.com/bapi/feed/v1/friendly/feed/profile/posts?username={username}&pageSize=10&pageIndex=1",
                f"https://www.binance.com/bapi/composite/v4/friendly/pgc/feed/profile/post/list?username={username}&pageSize=10&pageIndex=1",
                f"https://www.binance.com/bapi/feed/v1/friendly/square/profile/post/list?username={username}&pageSize=10",
                f"https://www.binance.com/bapi/composite/v1/friendly/pgc/profile/post/list?username={username}&pageSize=10",
            ]
            for api_url in api_urls:
                try:
                    result = page.evaluate(f"""
                        async () => {{
                            const r = await fetch('{api_url}', {{
                                method: 'GET',
                                credentials: 'include',
                                headers: {{
                                    'Accept': 'application/json',
                                    'Referer': 'https://www.binance.com/en/square/profile/{username}',
                                }}
                            }});
                            return {{ status: r.status, body: await r.text() }};
                        }}
                    """)
                    status = result.get("status", 0)
                    body = result.get("body", "")
                    short_name = api_url.split("?")[0].split("/")[-1]
                    print(f"[scraper] {short_name} → {status} | {body[:80]}")
                    if status == 200:
                        data = json.loads(body)
                        found = _find_posts_in_json(data)
                        if found:
                            p0 = found[0]
                            post_id = str(p0.get("id") or p0.get("postId") or "")
                            content = extract_plain_text(p0.get("content") or p0.get("body") or p0.get("text") or "")
                            images = _extract_images(p0)
                            if post_id:
                                print(f"[scraper] ✅ Got {post_id} via API")
                                browser.close()
                                return {"id": post_id, "content": content, "images": images, "username": username}
                except Exception as e:
                    print(f"[scraper] API call error: {e}")

            # Last resort: parse HTML for post IDs, verify each belongs to username
            print(f"[scraper] Last resort: verifying post IDs for {username}...")
            html = page.content()
            all_ids = re.findall(r"/en/square/post/(\d+)", html)
            if not all_ids:
                print(f"[scraper] ❌ No post IDs in HTML for {username}")
                browser.close()
                return None

            # Sort descending and check each post to find one that belongs to this user
            sorted_ids = sorted(set(all_ids), key=lambda x: int(x), reverse=True)
            print(f"[scraper] Checking {len(sorted_ids[:5])} post IDs for {username} ownership...")

            for pid in sorted_ids[:5]:
                post_url = f"https://www.binance.com/en/square/post/{pid}"
                try:
                    page.goto(post_url, wait_until="domcontentloaded", timeout=15000)
                    page.wait_for_timeout(3000)
                    post_html = page.content()

                    # Check if this post belongs to the target user
                    if username.lower() in post_html.lower():
                        content = ""
                        images = []
                        og = re.search(r'property="og:description"\s+content="([^"]+)"', post_html)
                        if not og:
                            og = re.search(r'content="([^"]+)"\s+property="og:description"', post_html)
                        if og:
                            content = og.group(1).strip()

                        og_img = re.search(r'property="og:image"\s+content="([^"]+)"', post_html)
                        if og_img:
                            img = og_img.group(1).strip()
                            if any(x in img for x in ["feed", "post", "upload", "live-admin"]):
                                images.append(img)

                        print(f"[scraper] ✅ Verified post {pid} belongs to {username}")
                        browser.close()
                        return {"id": pid, "content": content, "images": images, "username": username}
                    else:
                        print(f"[scraper] Post {pid} ≠ {username}, skipping...")
                except Exception:
                    continue

            print(f"[scraper] ❌ Could not find verified post for {username}")
            browser.close()
            return None

        except Exception as e:
            print(f"[scraper] Error for {username}: {e}")
            browser.close()
            return None


def _extract_images(post):
    images = []
    raw = json.dumps(post)
    for field in ["imageList", "images", "imgList", "mediaList", "attachments"]:
        val = post.get(field)
        if isinstance(val, list):
            for item in val:
                url = item if isinstance(item, str) else item.get("url") or item.get("imageUrl") or ""
                if url.startswith("http"):
                    images.append(url)
    if not images:
        urls = re.findall(r'https?://[^\s"\']+\.(?:jpg|jpeg|png|gif|webp)(?:\?[^\s"\']*)?', raw, re.IGNORECASE)
        images = [u for u in urls if not any(x in u.lower() for x in ["logo", "icon", "avatar", "coin", "flag"])]
    return images[:9]




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

def _is_post(item):
    """Check if a dict looks like a real post (not user profile or other data)."""
    if not isinstance(item, dict):
        return False
    has_content = any(k in item for k in ["content", "body", "text"])
    raw_id = str(item.get("id") or item.get("postId") or "")
    # Real post IDs are 10+ digits; user IDs are small numbers like 27
    has_post_id = raw_id.isdigit() and len(raw_id) >= 10
    return has_content and has_post_id


def _find_posts_in_json(data, depth=0):
    if depth > 6:
        return []
    if isinstance(data, list) and len(data) > 0:
        if all(_is_post(item) for item in data[:3]):
            return data
        for item in data:
            result = _find_posts_in_json(item, depth + 1)
            if result:
                return result
    if isinstance(data, dict):
        for v in data.values():
            result = _find_posts_in_json(v, depth + 1)
            if result:
                return result
    return []


def extract_plain_text(raw_content):
    """
    Extract plain text from Binance Square rich text JSON format.
    Handles both plain strings and the JSON rich text format.
    """
    if not raw_content:
        return ""

    # If it doesn't look like JSON, return as-is (already plain text)
    stripped = raw_content.strip()
    if not stripped.startswith("{") and not stripped.startswith("["):
        # Strip HTML tags if any
        return re.sub(r"<[^>]+>", "", stripped).strip()

    # Parse the rich text JSON
    try:
        data = json.loads(stripped)

        texts = []

        def walk(node):
            if isinstance(node, str):
                texts.append(node)
                return
            if isinstance(node, list):
                for item in node:
                    walk(item)
                return
            if isinstance(node, dict):
                # Direct text content fields
                for key in ["content", "text", "value"]:
                    val = node.get(key)
                    if isinstance(val, str) and val.strip():
                        texts.append(val.strip())
                    elif isinstance(val, (list, dict)):
                        walk(val)
                # Walk all other values too
                for key, val in node.items():
                    if key not in ["content", "text", "value"] and isinstance(val, (list, dict)):
                        walk(val)

        walk(data)

        # Deduplicate while preserving order
        seen = set()
        unique = []
        for t in texts:
            if t not in seen and len(t) > 1:
                seen.add(t)
                unique.append(t)

        result = "\n".join(unique).strip()
        return result if result else re.sub(r"<[^>]+>", "", stripped).strip()

    except (json.JSONDecodeError, Exception):
        # Not valid JSON — strip HTML and return
        return re.sub(r"<[^>]+>", "", stripped).strip()
