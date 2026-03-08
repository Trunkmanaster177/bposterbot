import os
import json
import urllib.request
import tempfile

SQUARE_API_KEY = os.environ.get("SQUARE_API_KEY", "")
BINANCE_COOKIES = os.environ.get("BINANCE_COOKIES", "")

SQUARE_URL = "https://www.binance.com/en/square"


def post_to_square(content: str, images: list = []) -> bool:
    if not content.strip() and not images:
        print("[poster] Empty content and no images, skipping.")
        return False

    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    print(f"[poster] Starting browser ({len(content)} chars, {len(images)} images)...")

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
                browser.close()
                return False
        else:
            print("[poster] ❌ BINANCE_COOKIES not set!")
            browser.close()
            return False

        page = context.new_page()

        try:
            print("[poster] Loading Binance Square...")
            page.goto(SQUARE_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(5000)

            # Verify login
            html = page.content()
            if "Share your thoughts" in html or "logined" in html:
                print("[poster] ✅ Logged in!")
            else:
                print("[poster] ⚠️ Might not be logged in")
                page.screenshot(path="login_check.png")

            # Find post input
            input_found = False
            for sel in [
                'div[contenteditable="true"]',
                '[placeholder*="Share" i]',
                '[placeholder*="thought" i]',
                '[placeholder*="What" i]',
                'textarea',
            ]:
                try:
                    el = page.locator(sel).first
                    el.wait_for(state="visible", timeout=3000)
                    el.click()
                    page.wait_for_timeout(1000)
                    print(f"[poster] Found input: {sel}")
                    input_found = True

                    # Type text content
                    if content.strip():
                        page.keyboard.type(content[:500], delay=10)
                        page.wait_for_timeout(1000)

                    # Upload images if any
                    if images:
                        print(f"[poster] Uploading {len(images)} image(s)...")
                        _upload_images(page, images)
                        page.wait_for_timeout(3000)

                    page.screenshot(path="before_submit.png")

                    # Click Post button
                    for btn_sel in [
                        'button:has-text("Post")',
                        'button:has-text("Publish")',
                        'button:has-text("Submit")',
                        '[class*="submit"]',
                        'button[type="submit"]',
                    ]:
                        try:
                            btn = page.locator(btn_sel).last
                            btn.wait_for(state="visible", timeout=3000)
                            if btn.is_enabled():
                                print(f"[poster] Clicking: {btn_sel}")
                                btn.click()
                                page.wait_for_timeout(5000)
                                page.screenshot(path="after_submit.png")
                                print("[poster] ✅ Post submitted successfully!")
                                browser.close()
                                return True
                        except PWTimeout:
                            continue

                    print("[poster] ❌ Could not find submit button")
                    page.screenshot(path="no_submit.png")
                    break

                except PWTimeout:
                    continue

            if not input_found:
                print("[poster] ❌ Could not find post input")
                page.screenshot(path="no_input.png")

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


def _upload_images(page, image_urls: list):
    """Download images and upload them via the file input."""
    from playwright.sync_api import TimeoutError as PWTimeout

    # Download images to temp files
    temp_files = []
    for url in image_urls[:9]:
        try:
            ext = url.split("?")[0].split(".")[-1].lower()
            if ext not in ["jpg", "jpeg", "png", "gif", "webp"]:
                ext = "jpg"
            tmp = tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False)
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                tmp.write(resp.read())
            tmp.close()
            temp_files.append(tmp.name)
            print(f"[poster] Downloaded image: {url[-50:]}")
        except Exception as e:
            print(f"[poster] Image download failed: {e}")

    if not temp_files:
        print("[poster] No images downloaded successfully")
        return

    # Find image upload button/input
    upload_selectors = [
        'input[type="file"]',
        'input[accept*="image"]',
        '[class*="upload"] input',
        '[class*="image"] input[type="file"]',
    ]

    for sel in upload_selectors:
        try:
            file_input = page.locator(sel).first
            file_input.wait_for(state="attached", timeout=3000)
            file_input.set_files(temp_files)
            print(f"[poster] ✅ Uploaded {len(temp_files)} image(s) via {sel}")
            page.wait_for_timeout(2000)

            # Clean up temp files
            for f in temp_files:
                try:
                    os.unlink(f)
                except Exception:
                    pass
            return
        except PWTimeout:
            continue
        except Exception as e:
            print(f"[poster] Upload error with {sel}: {e}")

    # Try clicking image button to reveal file input
    for btn_sel in [
        '[class*="image-btn"]',
        'button[title*="image" i]',
        'button[aria-label*="image" i]',
        'label[for*="image"]',
        'label[for*="upload"]',
        'svg[class*="image"]',
    ]:
        try:
            btn = page.locator(btn_sel).first
            btn.wait_for(state="visible", timeout=2000)
            btn.click()
            page.wait_for_timeout(1000)

            # Now try file input again
            file_input = page.locator('input[type="file"]').first
            file_input.set_files(temp_files)
            print(f"[poster] ✅ Uploaded via click → {btn_sel}")
            page.wait_for_timeout(2000)

            for f in temp_files:
                try:
                    os.unlink(f)
                except Exception:
                    pass
            return
        except Exception:
            continue

    print("[poster] ⚠️ Could not find image upload input — posting text only")
    for f in temp_files:
        try:
            os.unlink(f)
        except Exception:
            pass
