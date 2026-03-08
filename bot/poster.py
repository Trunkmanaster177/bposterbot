import os
import json
import time

SQUARE_API_KEY = os.environ.get("SQUARE_API_KEY", "")
BINANCE_COOKIES = os.environ.get("BINANCE_COOKIES", "")  # full JSON array

SQUARE_URL = "https://www.binance.com/en/square"


def post_to_square(content: str) -> bool:
    if not content.strip():
        print("[poster] Empty content, skipping.")
        return False

    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    print(f"[poster] Starting browser ({len(content)} chars)...")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
        )

        # Inject cookies
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
                print(f"[poster] ✅ Injected {len(playwright_cookies)} cookies")
            except Exception as e:
                print(f"[poster] Cookie error: {e}")
        else:
            print("[poster] ❌ BINANCE_COOKIES secret not found! Please add it in GitHub Secrets.")
            browser.close()
            return False

        page = context.new_page()

        # Intercept ALL POST requests to find the real create endpoint
        create_request_captured = {}

        def on_request(request):
            if request.method == "POST" and "binance.com" in request.url:
                url = request.url
                if any(k in url for k in ["create", "post", "publish", "feed", "square"]):
                    print(f"[poster] 📡 POST intercepted: {url}")
                    try:
                        create_request_captured["url"] = url
                        create_request_captured["headers"] = dict(request.headers)
                        create_request_captured["body"] = request.post_data
                    except Exception:
                        pass

        def on_response(response):
            if response.request.method == "POST" and "binance.com" in response.url:
                url = response.url
                if any(k in url for k in ["create", "post", "publish", "feed", "square"]):
                    try:
                        body = response.body()
                        print(f"[poster] 📡 POST response [{response.status}]: {url}")
                        print(f"[poster]   Body: {body[:200]}")
                        if response.status in [200, 201]:
                            create_request_captured["success_response"] = body.decode()
                    except Exception:
                        pass

        page.on("request", on_request)
        page.on("response", on_response)

        try:
            print("[poster] Loading Binance Square...")
            page.goto(SQUARE_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(5000)

            # Check login status
            html = page.content()
            if "Share your thoughts" in html or "logined" in html:
                print("[poster] ✅ Logged in!")
            else:
                print("[poster] ⚠️ Might not be logged in")
                page.screenshot(path="login_check.png")

            # Try clicking the post input box
            print("[poster] Looking for post input...")
            input_found = False
            for sel in [
                'div[class*="createPost"] div[contenteditable]',
                'div[contenteditable="true"]',
                '[placeholder*="Share" i]',
                '[placeholder*="thought" i]',
                '[placeholder*="What" i]',
                'textarea',
                'div[class*="editor"]',
                'div[class*="input"]',
            ]:
                try:
                    el = page.locator(sel).first
                    el.wait_for(state="visible", timeout=3000)
                    el.click()
                    page.wait_for_timeout(1000)
                    print(f"[poster] Found input: {sel}")
                    input_found = True

                    # Type content
                    page.keyboard.type(content[:500], delay=10)
                    page.wait_for_timeout(2000)

                    # Take screenshot to see current state
                    page.screenshot(path="before_submit.png")

                    # Find and click Post/Submit button
                    for btn_sel in [
                        'button:has-text("Post")',
                        'button:has-text("Publish")',
                        'button:has-text("Submit")',
                        'div:has-text("Post") >> button',
                        '[class*="submit"]',
                        '[class*="publish"]',
                        'button[type="submit"]',
                    ]:
                        try:
                            btn = page.locator(btn_sel).last
                            btn.wait_for(state="visible", timeout=3000)
                            if btn.is_enabled():
                                print(f"[poster] Clicking: {btn_sel}")
                                btn.click()
                                page.wait_for_timeout(5000)

                                # Check if post succeeded
                                if create_request_captured.get("success_response"):
                                    print("[poster] ✅ Post submitted successfully!")
                                    browser.close()
                                    return True

                                # Check for success indicators on page
                                new_html = page.content()
                                if "success" in new_html.lower() or content[:20] in new_html:
                                    print("[poster] ✅ Post appears successful!")
                                    browser.close()
                                    return True

                                page.screenshot(path="after_submit.png")
                                print("[poster] Submitted — check after_submit.png artifact")
                                browser.close()
                                return True
                        except PWTimeout:
                            continue

                    print("[poster] Could not find submit button")
                    page.screenshot(path="no_submit_btn.png")
                    break

                except PWTimeout:
                    continue

            if not input_found:
                print("[poster] ❌ Could not find post input")
                page.screenshot(path="no_input.png")

            # Log all intercepted requests for debugging
            if create_request_captured:
                print(f"[poster] Captured request info: {json.dumps({k: v for k, v in create_request_captured.items() if k != 'headers'}, indent=2)[:300]}")

            browser.close()
            return False

        except Exception as e:
            print(f"[poster] Error: {e}")
            try:
                page.screenshot(path="poster_error.png")
            except Exception:
                pass
            browser.close()
            return False
