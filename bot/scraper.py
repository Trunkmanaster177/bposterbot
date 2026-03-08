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

        try:
            # Go directly to profile page
            page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(8000)

            html = page.content()

            # Get ALL post IDs from this profile page
            post_ids = re.findall(r"/en/square/post/(\d+)", html)
            if not post_ids:
                print(f"[scraper] ❌ No post IDs found on {username} profile")
                browser.close()
                return None

            # Sort descending — latest first
            post_ids = sorted(set(post_ids), key=lambda x: int(x), reverse=True)
            latest_id = post_ids[0]
            print(f"[scraper] {username} post IDs: {post_ids[:5]}")

            # Navigate to the actual post page to get content + verify owner
            post_url = f"https://www.binance.com/en/square/post/{latest_id}"
            print(f"[scraper] Loading post: {post_url}")
            page.goto(post_url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(5000)

            post_html = page.content()

            # Verify this post belongs to the expected creator
            if username.lower() not in post_html.lower():
                print(f"[scraper] ⚠️ Post {latest_id} doesn't seem to belong to {username}, checking next...")
                # Try the next post ID
                for pid in post_ids[1:4]:
                    post_url2 = f"https://www.binance.com/en/square/post/{pid}"
                    page.goto(post_url2, wait_until="domcontentloaded", timeout=15000)
                    page.wait_for_timeout(3000)
                    post_html2 = page.content()
                    if username.lower() in post_html2.lower():
                        latest_id = pid
                        post_html = post_html2
                        print(f"[scraper] ✅ Found correct post {pid} for {username}")
                        break

            # Extract content
            content = ""
            og = re.search(r'property="og:description"\s+content="([^"]+)"', post_html)
            if not og:
                og = re.search(r'content="([^"]+)"\s+property="og:description"', post_html)
            if og:
                content = og.group(1).strip()

            # Extract images
            images = []
            # og:image
            og_img = re.search(r'property="og:image"\s+content="([^"]+)"', post_html)
            if not og_img:
                og_img = re.search(r'content="([^"]+)"\s+property="og:image"', post_html)
            if og_img:
                img_url = og_img.group(1).strip()
                # Only add if it looks like a post image (not logo/default)
                if img_url.startswith("http") and any(x in img_url for x in ["feed", "post", "upload", "content"]):
                    images.append(img_url)

            # __NEXT_DATA__ for more content/images
            nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', post_html, re.DOTALL)
            if nd:
                try:
                    nd_str = nd.group(1)
                    if not content:
                        texts = re.findall(r'"content"\s*:\s*"((?:[^"\\]|\\.){30,})"', nd_str)
                        if texts:
                            content = max(texts, key=len)
                    # Images from JSON
                    img_urls = re.findall(
                        r'https?://[^\s"\']+\.(?:jpg|jpeg|png|gif|webp)(?:\?[^\s"\']*)?',
                        nd_str, re.IGNORECASE
                    )
                    for u in img_urls:
                        if u not in images and any(x in u for x in ["feed", "post", "upload", "content", "live-admin"]):
                            if not any(x in u.lower() for x in ["logo", "icon", "avatar", "coin", "flag"]):
                                images.append(u)
                except Exception:
                    pass

            print(f"[scraper] ✅ {username} | post={latest_id} | chars={len(content)} | images={len(images)}")
            browser.close()
            return {
                "id": latest_id,
                "content": content,
                "images": images[:9],
                "username": username
            }

        except PWTimeout:
            print(f"[scraper] Timeout for {username}")
            browser.close()
            return None
        except Exception as e:
            print(f"[scraper] Error for {username}: {e}")
            browser.close()
            return None


def get_all_new_posts():
    """
    Check all creators and return ONLY genuinely new posts.
    Each creator is checked independently — same post ID for different
    creators is treated as separate posts only if both are actually new.
    """
    new_posts = []
    last_ids = load_all_last_ids()

    # Track post IDs already queued this run to avoid duplicate posting
    queued_ids = set()

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
            # Genuine new post for this creator
            if current_id in queued_ids:
                # Same post ID already queued from another creator
                # This means it's likely a shared/reposted content
                # Still post it but mark as from this creator
                print(f"[scraper] 🆕 New post from {username} (shared content): {current_id}")
            else:
                print(f"[scraper] 🆕 New post from {username}! {current_id} (was: {last_id})")

            queued_ids.add(current_id)
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
