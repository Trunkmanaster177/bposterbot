import os
import json

SQUARE_API_KEY = os.environ.get("SQUARE_API_KEY", "")
BINANCE_COOKIES = os.environ.get("BINANCE_COOKIES", "")

SQUARE_URL = "https://www.binance.com/en/square"

POST_ENDPOINTS = [
    "https://www.binance.com/bapi/feed/v1/friendly/feed/post/create",
    "https://www.binance.com/bapi/feed/v1/private/feed/post/create",
    "https://www.binance.com/bapi/feed/v2/friendly/feed/post/create",
]


def post_to_square(content: str) -> bool:
    if not content.strip():
        print("[poster] Empty content, skipping.")
        return False

    from playwright.sync_api import sync_playwright

    print(f"[poster] Starting browser ({len(content)} chars to post)...")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
        )

        # Inject cookies from GitHub Secret
        if BINANCE_COOKIES:
            try:
                cookies_raw = json.loads(BINANCE_COOKIES)
                # Convert cookie-editor format to Playwright format
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
                    if c.get("sameSite") and c["sameSite"] != "unspecified":
                        samesite = c["sameSite"].capitalize()
                        if samesite in ["Strict", "Lax", "None"]:
                            cookie["sameSite"] = samesite
                    playwright_cookies.append(cookie)

                context.add_cookies(playwright_cookies)
                print(f"[poster] ✅ Injected {len(playwright_cookies)} cookies")
            except Exception as e:
                print(f"[poster] Cookie injection error: {e}")
        else:
            print("[poster] ⚠️ No BINANCE_COOKIES secret found!")

        page = context.new_page()

        try:
            # Load Square with injected cookies (authenticated session)
            print("[poster] Loading Binance Square...")
            page.goto(SQUARE_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(4000)

            # Verify we're logged in
            html = page.content()
            if "logined" in html or "Share your thoughts" in html or "Creator" in html:
                print("[poster] ✅ Session authenticated!")
            else:
                print("[poster] ⚠️ May not be logged in, trying anyway...")

            # Try posting via API from inside authenticated browser
            for endpoint in POST_ENDPOINTS:
                for body in [
                    {"content": content, "type": 1},
                    {"content": content, "postType": 1},
                    {"content": content, "type": 1, "apiKey": SQUARE_API_KEY},
                ]:
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
                                return {{ status: resp.status, body: await resp.text() }};
                            }}
                        """)

                        status = result.get("status", 0)
                        resp_body = result.get("body", "")
                        print(f"[poster] [{status}] {endpoint.split('/')[-1]} → {resp_body[:200]}")

                        if status in [200, 201]:
                            try:
                                data = json.loads(resp_body)
                                code = str(data.get("code", ""))
                                if code in ["000000", "0", "200"] or data.get("success") or data.get("data"):
                                    print("[poster] ✅ Post published via API!")
                                    browser.close()
                                    return True
                            except Exception:
                                print("[poster] ✅ Post published (200 response)!")
                                browser.close()
                                return True

                    except Exception as e:
                        print(f"[poster] Fetch error: {e}")

            # Fallback: UI automation
            print("[poster] API failed, trying UI post...")
            success = _ui_post(page, content)
            browser.close()
            return success

        except Exception as e:
            print(f"[poster] Error: {e}")
            try:
                page.screenshot(path="poster_error.png")
            except Exception:
                pass
            browser.close()
            return False


def _ui_post(page, content: str) -> bool:
    from playwright.sync_api import TimeoutError as PWTimeout
    try:
        for sel in ['[placeholder*="Share" i]', '[placeholder*="What" i]', 'div[contenteditable="true"]', 'textarea']:
            try:
                el = page.locator(sel).first
                el.wait_for(state="visible", timeout=3000)
                el.click()
                page.wait_for_timeout(500)
                el.fill(content)
                page.wait_for_timeout(1000)
                for btn_sel in ['button:has-text("Post")', 'button:has-text("Publish")', 'button[type="submit"]']:
                    try:
                        btn = page.locator(btn_sel).last
                        btn.wait_for(state="visible", timeout=3000)
                        btn.click()
                        page.wait_for_timeout(3000)
                        print("[poster] ✅ UI post submitted!")
                        return True
                    except PWTimeout:
                        continue
            except PWTimeout:
                continue
        page.screenshot(path="ui_debug.png")
        print("[poster] ❌ UI post failed.")
        return False
    except Exception as e:
        print(f"[poster] UI error: {e}")
        return False
