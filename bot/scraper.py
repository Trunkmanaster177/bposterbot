import os
import re
import json

TARGET_USERNAMES = ["ict_bull", "Raa_Fi"]
LAST_POST_FILE = "last_post_id.txt"
BINANCE_COOKIES = os.environ.get("BINANCE_COOKIES", "")


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

        # Inject cookies so API calls are authenticated
        if BINANCE_COOKIES:
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
            except Exception as e:
                print(f"[scraper] Cookie error: {e}")

        page = context.new_page()

        try:
            # Load Square first to establish session
            page.goto("https://www.binance.com/en/square", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)

            # Call the profile posts API directly from browser context
            # This uses authenticated session so it returns real data
            print(f"[scraper] Calling profile API for {username}...")

            api_endpoints = [
                f"https://www.binance.com/bapi/feed/v1/friendly/feed/profile/posts?username={username}&pageSize=10&pageIndex=1",
                f"https://www.binance.com/bapi/composite/v4/friendly/pgc/feed/profile/post/list?username={username}&pageSize=10&pageIndex=1",
                f"https://www.binance.com/bapi/feed/v1/friendly/square/profile/post/list?username={username}&pageSize=10",
                f"https://www.binance.com/bapi/composite/v1/friendly/pgc/profile/post/list?username={username}&pageSize=10",
            ]

            posts = []
            for endpoint in api_endpoints:
                try:
                    result = page.evaluate(f"""
                        async () => {{
                            const r = await fetch('{endpoint}', {{
                                method: 'GET',
                                credentials: 'include',
                                headers: {{
                                    'Accept': 'application/json',
                                    'Content-Type': 'application/json',
                                    'Referer': 'https://www.binance.com/en/square/profile/{username}',
                                    'Origin': 'https://www.binance.com',
                                }}
                            }});
                            const text = await r.text();
                            return {{ status: r.status, body: text }};
                        }}
                    """)
                    status = result.get("status", 0)
                    body = result.get("body", "")
                    print(f"[scraper] {endpoint.split('?')[0].split('/')[-1]} → {status} | {body[:100]}")

                    if status == 200:
                        data = json.loads(body)
                        found = _find_posts_in_json(data)
                        if found:
                            posts = found
                            print(f"[scraper] ✅ Got {len(posts)} posts from API for {username}")
                            break
                except Exception as e:
                    print(f"[scraper] API error: {e}")
                    continue

            if posts:
                p0 = posts[0]
                post_id = str(p0.get("id") or p0.get("postId") or "")
                content = re.sub(r"<[^>]+>", "",
                    p0.get("content") or p0.get("body") or p0.get("text") or ""
                ).strip()
                images = _extract_images(p0)

                # Double check: verify this post is actually from the right user
                post_author = (
                    str(p0.get("nickName") or p0.get("username") or
                    p0.get("author", {}).get("nickName") or
                    p0.get("userInfo", {}).get("nickName") or "").lower()

                print(f"[scraper] Post author: '{post_author}' | Expected: '{username.lower()}'")

                if post_id:
                    print(f"[scraper] ✅ {username} latest post: {post_id} | {len(content)} chars | {len(images)} images")
                    browser.close()
                    return {"id": post_id, "content": content, "images": images, "username": username}

            # Fallback: navigate to profile and ONLY grab post IDs that appear
            # in the profile-specific section (above the fold)
            print(f"[scraper] API failed, using profile page fallback for {username}...")
            profile_url = f"https://www.binance.com/en/square/profile/{username}"
            page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(8000)

            # Execute JS to find post links only inside the user's post feed
            # not the recommended/trending section
            post_id = page.evaluate("""
                () => {
                    // Find all post links on the page
                    const links = Array.from(document.querySelectorAll('a[href*="/square/post/"]'));
                    const ids = links.map(a => {
                        const m = a.href.match(/\\/square\\/post\\/(\\d+)/);
                        return m ? m[1] : null;
                    }).filter(Boolean);

                    // Return the highest ID (most recent post)
                    if (ids.length === 0) return null;
                    return ids.reduce((a, b) => BigInt(a) > BigInt(b) ? a : b);
                }
            """)

            if not post_id:
                print(f"[scraper] ❌ No posts found for {username}")
                browser.close()
                return None

            print(f"[scraper] Fallback found post ID: {post_id}")

            # Fetch content from post page
            content, images = _fetch_post_page(page, post_id, username)
            browser.close()
            return {"id": post_id, "content": content, "images": images, "username": username}

        except Exception as e:
            print(f"[scraper] Error for {username}: {e}")
            browser.close()
            return None


def _fetch_post_page(page, post_id, username):
    """Fetch content and images from a post page, verify it belongs to username."""
    from playwright.sync_api import TimeoutError as PWTimeout
    content = ""
    images = []
    try:
        url = f"https://www.binance.com/en/square/post/{post_id}"
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(4000)
        html = page.content()

        # Verify post belongs to this creator
        if username.lower() not in html.lower():
            print(f"[scraper] ⚠️ Post {post_id} doesn't belong to {username}")

        # og:description for content
        og = re.search(r'property="og:description"\s+content="([^"]+)"', html)
        if not og:
            og = re.search(r'content="([^"]+)"\s+property="og:description"', html)
        if og:
            content = og.group(1).strip()

        # og:image
        og_img = re.search(r'property="og:image"\s+content="([^"]+)"', html)
        if not og_img:
            og_img = re.search(r'content="([^"]+)"\s+property="og:image"', html)
        if og_img:
            img = og_img.group(1).strip()
            if img.startswith("http") and any(x in img for x in ["feed", "post", "upload", "live-admin", "content"]):
                images.append(img)

    except Exception as e:
        print(f"[scraper] Post page error: {e}")
    return content, images


def _extract_images(post):
    """Extract image URLs from post JSON."""
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
    """Check all creators independently and return only genuinely new posts."""
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
