import os
import re
import json
from playwright.sync_api import sync_playwright

LAST_POST_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pf_last_id.txt"
)
TG_URL = "https://t.me/s/freepfsignals"

HASHTAGS = "#ProfitFarmers #CryptoSignals #TradingSignals #BinanceSquare #Crypto #Trading"


def load_last_id():
    if not os.path.exists(LAST_POST_FILE):
        return None
    try:
        return open(LAST_POST_FILE).read().strip()
    except Exception:
        return None


def save_last_id(post_id):
    with open(LAST_POST_FILE, "w") as f:
        f.write(str(post_id))
    print(f"[pf] Saved last ID: {post_id}")


def format_post(text: str) -> str:
    """Clean up and add hashtags to ProfitFarmers signal."""
    text = text.strip()
    # Add hashtags at the end
    return f"{text}\n\n{HASHTAGS}"


def get_new_posts():
    """Scrape t.me/s/freepfsignals and return new posts since last run."""
    last_id = load_last_id()
    print(f"[pf] Last seen ID: {last_id}")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()

        try:
            print(f"[pf] Loading {TG_URL}...")
            page.goto(TG_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(5000)

            # Extract all messages
            posts = page.evaluate("""
                () => {
                    const results = [];
                    const messages = document.querySelectorAll('.tgme_widget_message_wrap');

                    messages.forEach(msg => {
                        // Get message ID from data-post attribute e.g. "freepfsignals/123"
                        const bubble = msg.querySelector('.tgme_widget_message');
                        if (!bubble) return;

                        const postAttr = bubble.getAttribute('data-post') || '';
                        const idMatch = postAttr.match(/(\\d+)$/);
                        if (!idMatch) return;
                        const id = idMatch[1];

                        // Get text content
                        const textEl = msg.querySelector('.tgme_widget_message_text');
                        const text = textEl ? textEl.innerText.trim() : '';

                        // Get images
                        const images = [];
                        msg.querySelectorAll('.tgme_widget_message_photo_wrap').forEach(img => {
                            const style = img.getAttribute('style') || '';
                            const urlMatch = style.match(/url\\(['"]?([^'"\\)]+)['"]?\\)/);
                            if (urlMatch) images.push(urlMatch[1]);
                        });

                        if (text || images.length > 0) {
                            results.push({ id, text, images });
                        }
                    });

                    return results;
                }
            """)

            print(f"[pf] Found {len(posts)} messages on page")

            if not posts:
                browser.close()
                return []

            # Get the latest post ID
            latest_id = posts[-1]["id"] if posts else None

            # First run — save baseline
            if last_id is None:
                print(f"[pf] First run — saving baseline: {latest_id}")
                save_last_id(latest_id)
                browser.close()
                return []

            # Find new posts (IDs greater than last_id)
            new_posts = [p for p in posts if int(p["id"]) > int(last_id)]
            print(f"[pf] New posts: {len(new_posts)}")

            if new_posts:
                # Save the latest ID
                save_last_id(new_posts[-1]["id"])

            browser.close()
            return new_posts

        except Exception as e:
            print(f"[pf] Error: {e}")
            browser.close()
            return []
