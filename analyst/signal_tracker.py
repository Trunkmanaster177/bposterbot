"""
Tracks posted signals and monitors TP/SL hits.
Stores state in signal_state.json in repo root.
"""
import os
import json
import time
import requests

STATE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "signal_state.json"
)
HEADERS = {"User-Agent": "Mozilla/5.0"}
CC_API  = "https://min-api.cryptocompare.com/data"


def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {"posted": {}, "active": {}}
    try:
        return json.load(open(STATE_FILE))
    except Exception:
        return {"posted": {}, "active": {}}


def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def can_post_coin(symbol: str, market: str, interval_hours=12) -> bool:
    """Return True if coin+market hasn't been posted in interval_hours."""
    key   = f"{symbol}_{market}"
    state = load_state()
    last  = state.get("posted", {}).get(key)
    if not last:
        return True
    elapsed = (time.time() - last) / 3600
    if elapsed < interval_hours:
        print(f"[tracker] ⏳ {symbol} ({market}) posted {elapsed:.1f}h ago — skip (wait {interval_hours - elapsed:.1f}h)")
        return False
    return True


def record_posted_signal(signal: dict):
    """Record a posted signal for TP/SL tracking."""
    state  = load_state()
    symbol = signal["symbol"]
    market = signal.get("market", "SPOT")
    key    = f"{symbol}_{market}"

    state.setdefault("posted", {})[key] = time.time()
    state.setdefault("active", {})[key] = {
        "symbol":    symbol,
        "market":    market,
        "signal":    signal["signal"],
        "entry":     float(signal["entry"]),
        "tp1":       float(signal["tp1"]),
        "tp2":       float(signal["tp2"]),
        "tp3":       float(signal["tp3"]),
        "sl":        float(signal["sl"]),
        "leverage":  signal.get("leverage"),
        "tp1_hit":   False,
        "tp2_hit":   False,
        "tp3_hit":   False,
        "sl_hit":    False,
        "posted_at": time.time(),
    }

    save_state(state)
    print(f"[tracker] Recorded {symbol} ({market}) signal")


def get_current_price(coin: str) -> float:
    """Get price with validation — tries multiple sources."""
    # Try CryptoCompare first
    try:
        resp = requests.get(
            f"{CC_API}/price",
            params={"fsym": coin, "tsyms": "USD"},
            headers=HEADERS, timeout=10
        )
        data = resp.json()
        price = float(data.get("USD", 0))
        if price > 0:
            return price
    except Exception:
        pass

    # Fallback: Binance public price API (no geo restriction for price endpoint)
    try:
        resp = requests.get(
            f"https://api.binance.com/api/v3/ticker/price",
            params={"symbol": coin + "USDT"},
            headers=HEADERS, timeout=10
        )
        if resp.status_code == 200:
            return float(resp.json().get("price", 0))
    except Exception:
        pass

    return 0


def calc_roi(entry: float, target: float, direction: str, leverage) -> str:
    """Calculate ROI % for a TP hit."""
    if not entry or not target:
        return ""
    try:
        pct = ((target - entry) / entry) * 100
        if direction == "SELL":
            pct = -pct
        lev = float(leverage) if leverage else 1
        roi = pct * lev
        lev_str = f" (x{int(lev)} leverage)" if lev > 1 else ""
        sign = "+" if roi >= 0 else ""
        return f"{sign}{roi:.1f}%{lev_str}"
    except Exception:
        return ""


def check_tp_sl_hits() -> list:
    """Check all active signals for TP/SL hits."""
    state   = load_state()
    active  = state.get("active", {})
    updates = []

    for key, sig in list(active.items()):
        # Use symbol and market directly from stored sig — fixes the wrong coin bug
        symbol    = sig["symbol"]
        market    = sig.get("market", "SPOT")
        direction = sig["signal"]
        entry     = float(sig["entry"])
        leverage  = sig.get("leverage")
        coin      = symbol.replace("USDT", "")

        price = get_current_price(coin)
        if not price:
            print(f"[tracker] Could not get price for {symbol}")
            continue

        # Sanity check: price should be within 50% of entry
        # If not, we probably got wrong coin price
        if entry > 0 and (price > entry * 3 or price < entry * 0.1):
            print(f"[tracker] ⚠️ Price sanity fail for {symbol}: price={price}, entry={entry} — skipping")
            continue

        print(f"[tracker] {symbol} ({market}) | Price: {price} | Entry: {entry}")

        changed = False

        # Use explicit functions with local scope — fixes closure bug
        def is_tp_hit(p, t, d):
            return p >= t if d == "BUY" else p <= t

        def is_sl_hit(p, s, d):
            return p <= s if d == "BUY" else p >= s

        # Check each TP
        for tp_key, label in [("tp1", "TP1"), ("tp2", "TP2"), ("tp3", "TP3")]:
            if sig.get(f"{tp_key}_hit"):
                continue
            tp_val = float(sig[tp_key])
            if is_tp_hit(price, tp_val, direction):
                sig[f"{tp_key}_hit"] = True
                changed = True
                roi_str = calc_roi(entry, tp_val, direction, leverage)
                updates.append({
                    "type":     "TP",
                    "symbol":   symbol,
                    "market":   market,
                    "label":    label,
                    "price":    price,
                    "target":   tp_val,
                    "signal":   direction,
                    "entry":    entry,
                    "roi":      roi_str,
                    "leverage": leverage,
                    "tp1":      sig["tp1"],
                    "tp2":      sig["tp2"],
                    "tp3":      sig["tp3"],
                    "tp1_hit":  sig.get("tp1_hit", False),
                    "tp2_hit":  sig.get("tp2_hit", False),
                    "tp3_hit":  sig.get("tp3_hit", False),
                })
                print(f"[tracker] 🎯 {symbol} {label} HIT at {price}! ROI: {roi_str}")

        # Check SL
        if not sig.get("sl_hit") and is_sl_hit(price, float(sig["sl"]), direction):
            sig["sl_hit"] = True
            changed = True
            roi_str = calc_roi(entry, float(sig["sl"]), direction, leverage)
            updates.append({
                "type":     "SL",
                "symbol":   symbol,
                "market":   market,
                "price":    price,
                "target":   sig["sl"],
                "signal":   direction,
                "entry":    entry,
                "roi":      roi_str,
            })
            print(f"[tracker] 🛑 {symbol} SL HIT at {price}! Loss: {roi_str}")

        # Remove completed signals
        if sig.get("sl_hit") or (sig.get("tp1_hit") and sig.get("tp2_hit") and sig.get("tp3_hit")):
            del active[key]
            print(f"[tracker] Removed completed signal: {symbol} ({market})")
        elif changed:
            active[key] = sig

        time.sleep(0.5)

    state["active"] = active
    save_state(state)
    return updates


def format_tp_hit(update: dict) -> str:
    symbol   = update["symbol"]
    label    = update["label"]
    price    = update["price"]
    signal   = update["signal"]
    market   = update.get("market", "SPOT")
    roi      = update.get("roi", "")
    coin     = symbol.replace("USDT", "")
    market_tag = "📈 SPOT" if market == "SPOT" else "⚡ FUTURES"
    dir_emoji  = "🟢" if signal == "BUY" else "🔴"

    tp_lines = []
    for tp_key, tp_label in [("tp1", "TP1"), ("tp2", "TP2"), ("tp3", "TP3")]:
        hit    = update.get(f"{tp_key}_hit", False)
        tp_val = update.get(tp_key, "")
        icon   = "✅" if hit else "⬜"
        tp_lines.append(f"{icon} {tp_label}: {tp_val}")

    lines = [
        f"🎯 TARGET HIT! ${symbol}",
        f"{dir_emoji} {label} REACHED at {price}",
        f"{market_tag}",
        "",
    ]
    if roi:
        lines.append(f"💰 ROI: {roi}")
        lines.append("")
    lines += [
        "📊 Progress:",
    ] + tp_lines + [
        "",
        "💪 Congrats to everyone who followed this signal!",
        "",
        f"#{coin} #{symbol} #CryptoSignals #TargetHit #BinanceSquare #Crypto",
    ]
    return "\n".join(lines)


def format_sl_hit(update: dict) -> str:
    symbol     = update["symbol"]
    price      = update["price"]
    signal     = update["signal"]
    market     = update.get("market", "SPOT")
    roi        = update.get("roi", "")
    coin       = symbol.replace("USDT", "")
    market_tag = "📈 SPOT" if market == "SPOT" else "⚡ FUTURES"

    lines = [
        f"🛑 STOP LOSS HIT — ${symbol}",
        f"{market_tag}",
        "",
        f"SL triggered at {price}",
    ]
    if roi:
        lines.append(f"📉 Loss: {roi}")
    lines += [
        "",
        "Risk management is key in crypto trading.",
        "Cut losses, protect capital, next signal incoming! 💪",
        "",
        f"#{coin} #{symbol} #CryptoSignals #RiskManagement #BinanceSquare",
    ]
    return "\n".join(lines)
