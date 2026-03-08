import os
import time
import random
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

BINANCE_EMAIL = os.environ.get("BINANCE_EMAIL", "")
BINANCE_PASSWORD = os.environ.get("BINANCE_PASSWORD", "")
BINANCE_TOTP_SECRET = os.environ.get("BINANCE_TOTP_SECRET", "")  # optional 2FA

SQUARE_HOME = "https://www.binance.com/en/square"
LOGIN_URL = "https://accounts.binance.com/en/login"
COOKIES_FILE = "binance_cookies.json"


def get_totp_code():
    """Generate TOTP code if secret is provided."""
    if not BINANCE_TOTP_SECRET:
        return None
    try:
        import pyotp
        totp = pyotp.TOTP(BINANCE_TOTP_SECRET)
        return totp.now()
    except ImportError:
        print("[poster] pyotp not installed, skipping 2FA")
        return None


def human_delay(min_s=0.8, max_s=2.2):
    """Random human-like delay."""
    time.sleep(random.uniform(min_s, max_s))


def login_to_binance(page):
    """Log in to Binance account."""
    print("[poster] Navigating to login page...")
    page.goto(LOGIN_URL, wait_until="domcontentloaded")
    human_delay(2, 3)

    # Enter email
    email_input = page.locator('input[type="text"], input[name="email"], input[placeholder*="email" i]').first
    email_input.wait_for(state="visible", timeout=10000)
    email_input.click()
    human_delay()
    email_input.fill(BINANCE_EMAIL)
    human_delay()

    # Enter password
    pass_input = page.locator('input[type="password"]').first
    pass_input.click()
    human_delay()
    pass_input.fill(BINANCE_PASSWORD)
    human_delay()

    # Click login button
    login_btn = page.locator('button[type="submit"]').first
    login_btn.click()
    print("[poster] Submitted login form, waiting...")
    human_delay(3, 5)

    # Handle 2FA if needed
    totp = get_totp_code()
    if totp:
        try:
            totp_input = page.locator('input[placeholder*="authenticator" i], input[placeholder*="code" i], input[data-bn-type="input"]').first
            totp_input.wait_for(state="visible", timeout=8000)
            totp_input.fill(totp)
            human_delay()
            confirm_btn = page.locator('button[type="submit"]').first
            confirm_btn.click()
            human_delay(3, 5)
            print("[poster] 2FA submitted.")
        except PlaywrightTimeout:
            print("[poster] No 2FA prompt detected, continuing...")

    # Check login success
    page.wait_for_url("**/square**", timeout=20000)
    print("[poster] Login successful!")


def save_cookies(context):
    """Save browser cookies to file for reuse."""
    import json
    cookies = context.cookies()
    with open(COOKIES_FILE, "w") as f:
        json.dump(cookies, f)
    print(f"[poster] Saved {len(cookies)} cookies.")


def load_cookies(context):
    """Load saved cookies into browser context."""
    import json
    if not os.path.exists(COOKIES_FILE):
        return False
    with open(COOKIES_FILE, "r") as f:
        cookies = json.load(f)
    context.add_cookies(cookies)
    print(f"[poster] Loaded {len(cookies)} cookies.")
    return True


def check_logged_in(page):
    """Check if we're already logged in."""
    page.goto(SQUARE_HOME, wait_until="domcontentloaded")
    human_delay(2, 3)
    # Look for post button or avatar which indicates login
    try:
        page.locator('[data-bn-type="avatar"], .create-post-btn, [class*="avatar"], [class*="Avatar"]').first.wait_for(
            state="visible", timeout=8000
        )
        print("[poster] Already logged in via cookies.")
        return True
    except PlaywrightTimeout:
        return False


def post_to_square(content: str) -> bool:
    """
    Use Playwright to post content to Binance Square.
    Returns True on success.
    """
    if not content.strip():
        print("[poster] Empty content, skipping post.")
        return False

    if not BINANCE_EMAIL or not BINANCE_PASSWORD:
        print("[poster] ERROR: BINANCE_EMAIL or BINANCE_PASSWORD not set in environment.")
        return False

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="en-US",
        )
        page = context.new_page()

        try:
            # Try cookie-based auth first
            cookies_loaded = load_cookies(context)
            if cookies_loaded and check_logged_in(page):
                pass  # Already logged in
            else:
                login_to_binance(page)
                save_cookies(context)

            # Navigate to Square
            print("[poster] Navigating to Binance Square...")
            page.goto(SQUARE_HOME, wait_until="domcontentloaded")
            human_delay(2, 4)

            # Click the "Create Post" / write box
            print("[poster] Looking for post creation area...")
            create_selectors = [
                '[placeholder*="Share" i]',
                '[placeholder*="What" i]',
                '[placeholder*="post" i]',
                '[class*="create-post" i]',
                '[class*="CreatePost" i]',
                '[class*="postInput" i]',
                'div[contenteditable="true"]',
                'textarea',
            ]
            post_input = None
            for sel in create_selectors:
                try:
                    el = page.locator(sel).first
                    el.wait_for(state="visible", timeout=4000)
                    post_input = el
                    print(f"[poster] Found input with selector: {sel}")
                    break
                except PlaywrightTimeout:
                    continue

            if post_input is None:
                print("[poster] Could not find post input. Taking screenshot for debug...")
                page.screenshot(path="debug_screenshot.png")
                return False

            post_input.click()
            human_delay(1, 2)

            # Type the content (chunk it to seem human)
            print(f"[poster] Typing content ({len(content)} chars)...")
            post_input.fill(content)
            human_delay(1, 2)

            # Find and click Submit/Post button
            submit_selectors = [
                'button:has-text("Post")',
                'button:has-text("Submit")',
                'button:has-text("Publish")',
                '[class*="submit" i]',
                '[class*="publish" i]',
                'button[type="submit"]',
            ]
            submitted = False
            for sel in submit_selectors:
                try:
                    btn = page.locator(sel).last
                    btn.wait_for(state="visible", timeout=4000)
                    btn.click()
                    print(f"[poster] Clicked submit with selector: {sel}")
                    submitted = True
                    break
                except PlaywrightTimeout:
                    continue

            if not submitted:
                print("[poster] Could not find submit button. Taking screenshot...")
                page.screenshot(path="debug_submit.png")
                return False

            human_delay(3, 5)
            print("[poster] ✅ Post submitted successfully!")
            save_cookies(context)  # Refresh cookies
            return True

        except Exception as e:
            print(f"[poster] ERROR: {e}")
            try:
                page.screenshot(path="debug_error.png")
            except Exception:
                pass
            return False
        finally:
            browser.close()
