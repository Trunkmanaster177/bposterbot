import os
import json

SQUARE_API_KEY = os.environ.get("SQUARE_API_KEY", "")

# The exact endpoint discovered from the scraper's intercepted calls
# We'll call it from inside the browser context (with cookies) via page.evaluate()
POST_ENDPOINTS = [
    "https://www.binance.com/bapi/feed/v1/friendly/feed/post/create",
    "https://www.binance.com/bapi/feed/v1/private/feed/post/create",
    "https://www.binance.com/bapi/composite/v1/friendly/pgc/feed/post/create",
    "https://www.binance.com/bapi/feed/v2/friendly/feed/post/create",
]

SQUARE_URL = "https://www.binance.com/en/square"


def post_to_square(content: str) -> bool:
    """
    Post content to Binance Square using Playwright browser.
    Calls the API from inside the browser context so Binance cookies/auth are included.
    """
    if not content.strip():
        print("[poster] Empty content, skipping.")
        return False

    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    print(f"[poster] Launching browser to post ({len(content)} chars)...")

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
            # Load Binance Square so browser has all cookies/session
            print("[poster] Loading Binance Square to get session...")
            page.goto(SQUARE_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(5000)

            # Try each endpoint from inside the browser (cookies included automatically)
            for endpoint in POST_ENDPOINTS:
                print(f"[poster] Trying: {endpoint.split('/')[-1]}...")

                body_variants = [
                    {"content": content, "type": 1},
                    {"content": content, "postType": 1},
                    {"content": content, "type": 1, "apiKey": SQUARE_API_KEY},
                    {"content": content, "type": 1, "api_key": SQUARE_API_KEY},
                ]

                for body in body_variants:
                    try:
                        result = page.evaluate(f"""
                            async () => {{
                                const resp = await fetch('{endpoint}', {{
                                    method: 'POST',
                                    headers: {{
                                        'Content-Type': 'application/json',
                                        'Accept': 'application/json',
                                        'apiKey': '{SQUARE_API_KEY}',
                                        'x-api-key': '{SQUARE_API_KEY}',
                                        'Referer': 'https://www.binance.com/en/square',
                                    }},
                                    body: JSON.stringify({json.dumps(body)})
                                }});
                                const text = await resp.text();
                                return {{ status: resp.status, body: text }};
                            }}
                        """)

                        status = result.get("status", 0)
                        body_resp = result.get("body", "")
                        print(f"[poster] [{status}] {body_resp[:150]}")

                        if status in [200, 201]:
                            try:
                                data = json.loads(body_resp)
                                code = str(data.get("code", ""))
                                if code in ["000000", "0", "200"] or data.get("success") or data.get("data"):
                                    print(f"[poster] ✅ Post published successfully!")
                                    browser.close()
                                    return True
                            except Exception:
                                # 200 with non-JSON is still likely success
                                print(f"[poster] ✅ Got 200 response, assuming success!")
                                browser.close()
                                return True

                        # Save any non-403 response for debugging
                        if status not in [403, 404, 405]:
                            print(f"[poster] ⭐ Promising response at {endpoint}")

                    except Exception as e:
                        print(f"[poster] Fetch error: {e}")
                        continue

            # Last resort: try UI automation to click "Create Post"
            print("[poster] API attempts failed, trying UI automation...")
            success = try_ui_post(page, content)
            browser.close()
            return success

        except Exception as e:
            print(f"[poster] Error: {e}")
            browser.close()
            return False


def try_ui_post(page, content: str) -> bool:
    """Click the Create Post button in the UI as last resort."""
    from playwright.sync_api import TimeoutError as PWTimeout
    try:
        print("[poster] Looking for post creation input...")

        selectors = [
            '[placeholder*="Share" i]',
            '[placeholder*="What" i]',
            '[placeholder*="post" i]',
            'div[contenteditable="true"]',
            '[class*="create" i] textarea',
            '[class*="editor" i]',
            'textarea',
        ]

        input_el = None
        for sel in selectors:
            try:
                el = page.locator(sel).first
                el.wait_for(state="visible", timeout=3000)
                input_el = el
                print(f"[poster] Found input: {sel}")
                break
            except PWTimeout:
                continue

        if not input_el:
            print("[poster] ❌ Could not find post input via UI.")
            page.screenshot(path="poster_debug.png")
            return False

        input_el.click()
        page.wait_for_timeout(500)
        input_el.fill(content)
        page.wait_for_timeout(1000)

        # Find submit button
        for sel in ['button:has-text("Post")', 'button:has-text("Publish")', 'button:has-text("Submit")', 'button[type="submit"]']:
            try:
                btn = page.locator(sel).last
                btn.wait_for(state="visible", timeout=3000)
                btn.click()
                print(f"[poster] ✅ Clicked submit button!")
                page.wait_for_timeout(3000)
                return True
            except PWTimeout:
                continue

        print("[poster] ❌ Could not find submit button.")
        page.screenshot(path="poster_debug.png")
        return False

    except Exception as e:
        print(f"[poster] UI post error: {e}")
        return False
