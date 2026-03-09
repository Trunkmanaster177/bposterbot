import os
import json
import re
import urllib.request
import urllib.error
import base64

GITHUB_TOKEN   = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO    = os.environ.get("GITHUB_REPO", "Trunkmanaster177/bposterbot")
SIGNALS_FOLDER = "cornix_signals"

SIGNAL_EMOJIS = {
    "buy":   "🟢",
    "long":  "🟢",
    "sell":  "🔴",
    "short": "🔴",
    "close": "⚪",
    "tp":    "✅",
    "sl":    "🛑",
}

HASHTAGS = "#CryptoSignals #TradingSignals #BinanceSquare #Crypto #Trading"


def github_api(method, path, data=None):
    url = f"https://api.github.com{path}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method=method
    )
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        body = e.read()
        try:
            return json.loads(body), e.code
        except Exception:
            return {"error": body.decode()}, e.code


def fetch_pending_signals():
    """Read all signal JSON files from the GitHub repo signals folder."""
    if not GITHUB_TOKEN:
        print("[cornix] ❌ GITHUB_TOKEN not set!")
        return []

    # List files in signals folder
    data, status = github_api("GET", f"/repos/{GITHUB_REPO}/contents/{SIGNALS_FOLDER}")

    if status == 404:
        print(f"[cornix] No signals folder yet — nothing to do.")
        return []

    if status != 200:
        print(f"[cornix] GitHub API error {status}: {data}")
        return []

    signal_files = [f for f in data if f["name"].endswith(".json")]
    print(f"[cornix] Found {len(signal_files)} pending signal file(s)")

    signals = []
    for f in signal_files:
        # Get file content
        file_data, fstatus = github_api("GET", f"/repos/{GITHUB_REPO}/contents/{f['path']}")
        if fstatus != 200:
            continue
        try:
            content = json.loads(base64.b64decode(file_data["content"]).decode())
            signals.append({"signal": content, "sha": file_data["sha"], "path": f["path"]})
        except Exception as e:
            print(f"[cornix] Parse error for {f['name']}: {e}")

    return signals


def delete_signal_file(path, sha):
    """Delete a signal file from GitHub after processing."""
    data, status = github_api(
        "DELETE",
        f"/repos/{GITHUB_REPO}/contents/{path}",
        {
            "message": f"signal: processed [skip ci]",
            "sha": sha,
        }
    )
    if status in (200, 204):
        print(f"[cornix] ✅ Deleted {path}")
    else:
        print(f"[cornix] ⚠️ Could not delete {path}: {status}")


def format_signal(signal: dict) -> str:
    """Format a Cornix signal into a nice Binance Square post."""
    pair     = signal.get("pair") or signal.get("symbol") or signal.get("coin") or "?"
    action   = (signal.get("action") or signal.get("type") or signal.get("side") or "SIGNAL").upper()
    exchange = signal.get("exchange") or signal.get("market") or "Binance"
    entry    = signal.get("entry") or signal.get("entryPrice") or signal.get("price") or ""
    targets  = signal.get("targets") or signal.get("tp") or []
    sl       = signal.get("stopLoss") or signal.get("sl") or signal.get("stop") or ""
    leverage = signal.get("leverage") or signal.get("lev") or ""
    note     = signal.get("note") or signal.get("message") or signal.get("comment") or ""

    emoji = SIGNAL_EMOJIS.get(action.lower(), "📊")
    lines = []

    lines.append(f"{emoji} {pair} — {action} SIGNAL")
    lines.append(f"🏦 Exchange: {exchange}")
    lines.append("")

    if entry:
        if isinstance(entry, list):
            entry_str = f"{entry[0]} – {entry[-1]}" if len(entry) > 1 else str(entry[0])
        else:
            entry_str = str(entry)
        lines.append(f"📍 Entry: {entry_str}")

    if targets:
        if isinstance(targets, list):
            for i, tp in enumerate(targets, 1):
                tp_val = tp if not isinstance(tp, dict) else tp.get("price") or tp.get("value") or str(tp)
                lines.append(f"✅ TP{i}: {tp_val}")
        else:
            lines.append(f"✅ TP: {targets}")

    if sl:
        lines.append(f"🛑 SL: {sl}")

    if leverage:
        lines.append(f"⚡ Leverage: {leverage}x")

    if note:
        lines.append("")
        lines.append(f"📝 {note}")

    lines.append("")
    clean_pair = re.sub(r"[^A-Z0-9]", "", pair.upper())
    coin = re.sub(r"(USDT|BUSD|BTC|ETH|BNB)$", "", clean_pair)
    lines.append(f"#{coin} #{clean_pair} {HASHTAGS}")

    return "\n".join(lines)
