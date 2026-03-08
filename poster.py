import os
import json
import requests
import time

# ── API Key from Binance Square ──────────────────────────────────────────────
SQUARE_API_KEY = os.environ.get("SQUARE_API_KEY", "")

# ── All known/likely Binance Square POST endpoints ───────────────────────────
ENDPOINTS = [
    "https://www.binance.com/bapi/feed/v1/friendly/feed/post/create",
    "https://www.binance.com/bapi/feed/v1/private/feed/post/create",
    "https://www.binance.com/bapi/feed/v2/friendly/feed/post/create",
    "https://www.binance.com/bapi/feed/v2/private/feed/post/create",
    "https://www.binance.com/bapi/square/v1/post/create",
    "https://www.binance.com/bapi/square/v1/private/post/create",
    "https://www.binance.com/bapi/feed/v1/friendly/feed/square/post",
    "https://www.binance.com/x-api/v1/square/post/create",
    "https://api.binance.com/sapi/v1/square/post/create",
]

BASE_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36",
    "Accept": "application/json",
    "Origin": "https://www.binance.com",
    "Referer": "https://www.binance.com/en/square",
}

# Once working config is discovered, it gets saved here
WORKING_CONFIG_FILE = "working_api_config.json"


def build_headers_variants(api_key):
    """All possible header formats the new Square API might use."""
    return [
        {**BASE_HEADERS, "apiKey": api_key},
        {**BASE_HEADERS, "X-MBX-APIKEY": api_key},
        {**BASE_HEADERS, "Authorization": f"Bearer {api_key}"},
        {**BASE_HEADERS, "Authorization": api_key},
        {**BASE_HEADERS, "api-key": api_key},
        {**BASE_HEADERS, "square-api-key": api_key},
        {**BASE_HEADERS, "x-api-key": api_key},
        {**BASE_HEADERS, "BNC-Square-Api-Key": api_key},
    ]


def build_body_variants(content):
    """All possible request body formats."""
    ts = int(time.time() * 1000)
    return [
        {"content": content, "type": 1},
        {"content": content, "postType": 1},
        {"body": content, "type": 1},
        {"text": content, "type": 1},
        {"content": content, "type": 1, "timestamp": ts},
        {"content": content, "type": "POST"},
        {"content": content},
    ]


def load_working_config():
    """Load previously discovered working endpoint config."""
    if os.path.exists(WORKING_CONFIG_FILE):
        with open(WORKING_CONFIG_FILE) as f:
            return json.load(f)
    return None


def save_working_config(url, header_key, body_keys):
    """Save the working config for optimized future runs."""
    config = {"endpoint": url, "header_key": header_key, "body_keys": body_keys}
    with open(WORKING_CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)
    print(f"[poster] ✅ Saved working config → {WORKING_CONFIG_FILE}")


def is_success(status_code, response_text):
    """Check if API response indicates success."""
    if status_code not in [200, 201]:
        return False
    try:
        data = json.loads(response_text)
        code = str(data.get("code", data.get("status", "")))
        return (
            code in ["000000", "0", "200", "SUCCESS", "success"]
            or data.get("success") is True
            or data.get("data") is not None
        )
    except Exception:
        return status_code in [200, 201]


def post_to_square(content):
    """
    Post content to Binance Square using the API key.
    First tries previously working config, then auto-discovers.
    Returns True on success.
    """
    if not content.strip():
        print("[poster] Empty content, skipping.")
        return False

    api_key = SQUARE_API_KEY
    if not api_key:
        print("[poster] ERROR: SQUARE_API_KEY not set in environment.")
        return False

    print(f"[poster] Using Binance Square API key: {api_key[:8]}****")

    # ── Try previously saved working config first ────────────────────────────
    config = load_working_config()
    if config:
        print(f"[poster] Using saved config: {config['endpoint']}")
        headers = {**BASE_HEADERS, config["header_key"]: api_key}
        body = {k: (content if k in ["content", "body", "text"] else 1)
                for k in config["body_keys"]}
        try:
            resp = requests.post(config["endpoint"], json=body, headers=headers, timeout=12)
            print(f"[poster] [{resp.status_code}] {resp.text[:200]}")
            if is_success(resp.status_code, resp.text):
                print("[poster] ✅ Post published!")
                return True
            else:
                print("[poster] Saved config failed, running discovery...")
        except Exception as e:
            print(f"[poster] Saved config error: {e}, running discovery...")

    # ── Auto-discovery: try all endpoint + header + body combos ─────────────
    print("[poster] Running API endpoint discovery...")
    promising = []

    for url in ENDPOINTS:
        for headers in build_headers_variants(api_key):
            for body in build_body_variants(content):
                try:
                    resp = requests.post(url, json=body, headers=headers, timeout=10)

                    if resp.status_code in [404, 405, 301, 302]:
                        continue

                    print(f"  [{resp.status_code}] {url} | {resp.text[:100]}")

                    if is_success(resp.status_code, resp.text):
                        # Find which extra header key was added
                        extra_keys = [k for k in headers if k not in BASE_HEADERS]
                        header_key = extra_keys[0] if extra_keys else "apiKey"
                        save_working_config(url, header_key, list(body.keys()))
                        print(f"\n[poster] ✅ SUCCESS! Post published via {url}")
                        return True

                    promising.append({
                        "status": resp.status_code,
                        "url": url,
                        "response": resp.text[:200]
                    })

                except requests.exceptions.RequestException:
                    pass

    # ── Report results ───────────────────────────────────────────────────────
    if promising:
        print(f"\n[poster] ⚠️ Got {len(promising)} non-404 responses but no success.")
        print("[poster] Best response:")
        print(json.dumps(promising[0], indent=2))
        print("\n[poster] ACTION NEEDED: Check response above.")
        print("[poster] If you see the correct endpoint in your app's network traffic,")
        print("[poster] create working_api_config.json manually with the endpoint details.")
    else:
        print("\n[poster] ❌ All endpoints returned 404/405.")
        print("[poster] The exact API endpoint is not yet public.")
        print("[poster] Please intercept Binance app traffic to find it (see README).")

    return False
