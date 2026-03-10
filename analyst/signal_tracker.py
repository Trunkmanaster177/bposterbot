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


def can_post_coin(symbol: str, interval_hours=12) -> bool:
    """Return True if coin hasn't been posted in the last interval_hours."""
    state = load_state()
    last = state.get("posted", {}).get(symbol)
    if not last:
        return True
    elapsed = (time.time() - last) / 3600
    if elapsed < interval_hours:
        print(f"[tracker] ⏳ {symbol} posted {elapsed:.1f}h ago — skipping (wait {interval_hours - elapsed:.1f}h more)")
        return False
    return True


def record_posted_signal(signal: dict):
    """Record a posted signal for TP/SL tracking."""
    state = load_state()
    symbol = signal["symbol"]

    # Mark as posted with timestamp
    state.setdefault("posted", {})[symbol] = time.time()

    # Track active signal for TP monitoring
    state.setdefault("active", {})[symbol] = {
        "signal":    signal["signal"],      # BUY or SELL
        "entry":     signal["entry"],
        "tp1":       signal["tp1"],
        "tp2":       signal["tp2"],
        "tp3":       signal["tp3"],
        "sl":        signal["sl"],
        "tp1_hit":   False,
        "tp2_hit":   False,
        "tp3_hit":   False,
        "sl_hit":    False,
        "posted_at": time.time(),
        "market":    signal.get("market", "SPOT"),
    }

    save_state(state)
    print(f"[tracker] Recorded signal for {symbol}")


def get_current_price(coin: str) -> float:
    """Get current price from CryptoCompare."""
    try:
        resp = requests.get(f"{CC_API}/price", params={"fsym": coin, "tsyms": "USD"},
                            headers=HEADERS, timeout=10)
        return resp.json().get("USD", 0)
    except Exception:
        return 0


def check_tp_sl_hits() -> list:
    """
    Check all active signals for TP/SL hits.
    Returns list of hit announcements to post.
    """
    state   = load_state()
    active  = state.get("active", {})
    updates = []

    for symbol, sig in list(active.items()):
        coin  = symbol.replace("USDT", "")
        price = get_current_price(coin)
        if not price:
            continue

        direction = sig["signal"]  # BUY or SELL
        changed   = False

        def hit(target):
            if direction == "BUY":
                return price >= target
            else:  # SELL
                return price <= target

        def sl_hit(target):
            if direction == "BUY":
                return price <= target
            else:
                return price >= target

        # Check TPs
        for tp_key, label in [("tp1", "TP1"), ("tp2", "TP2"), ("tp3", "TP3")]:
            if not sig.get(f"{tp_key}_hit") and hit(sig[tp_key]):
                sig[f"{tp_key}_hit"] = True
                changed = True
                updates.append({
                    "type":    "TP",
                    "symbol":  symbol,
                    "label":   label,
                    "price":   price,
                    "target":  sig[tp_key],
                    "signal":  direction,
                    "market":  sig.get("market", "SPOT"),
                    "tp1":     sig["tp1"],
                    "tp2":     sig["tp2"],
                    "tp3":     sig["tp3"],
                    "tp1_hit": sig.get("tp1_hit", False),
                    "tp2_hit": sig.get("tp2_hit", False),
                    "tp3_hit": sig.get("tp3_hit", False),
                })
                print(f"[tracker] 🎯 {symbol} {label} HIT at {price}!")

        # Check SL
        if not sig.get("sl_hit") and sl_hit(sig["sl"]):
            sig["sl_hit"] = True
            changed = True
            updates.append({
                "type":   "SL",
                "symbol": symbol,
                "price":  price,
                "target": sig["sl"],
                "signal": direction,
                "market": sig.get("market", "SPOT"),
            })
            print(f"[tracker] 🛑 {symbol} SL HIT at {price}")

        # Remove signal if all TPs hit or SL hit
        if sig.get("sl_hit") or (sig.get("tp1_hit") and sig.get("tp2_hit") and sig.get("tp3_hit")):
            del active[symbol]
            print(f"[tracker] Removed completed signal for {symbol}")
        elif changed:
            active[symbol] = sig

        time.sleep(0.5)

    state["active"] = active
    save_state(state)
    return updates


def format_tp_hit(update: dict) -> str:
    symbol  = update["symbol"]
    label   = update["label"]
    price   = update["price"]
    target  = update["target"]
    signal  = update["signal"]
    market  = update.get("market", "SPOT")
    coin    = symbol.replace("USDT", "")

    # Build TP progress
    tp_lines = []
    for tp_key, tp_label in [("tp1", "TP1"), ("tp2", "TP2"), ("tp3", "TP3")]:
        hit = update.get(f"{tp_key}_hit", False)
        tp_val = update.get(tp_key, "")
        icon = "✅" if hit else "⬜"
        tp_lines.append(f"{icon} {tp_label}: {tp_val}")

    direction_emoji = "🟢" if signal == "BUY" else "🔴"
    market_tag = "📈 SPOT" if market == "SPOT" else "⚡ FUTURES"

    lines = [
        f"🎯 TARGET HIT! ${symbol}",
        f"{direction_emoji} {label} REACHED at {price}",
        f"{market_tag}",
        "",
        "📊 Progress:",
    ] + tp_lines + [
        "",
        f"💰 Congrats to everyone who followed this signal!",
        "",
        f"#{coin} #{symbol} #CryptoSignals #TargetHit #BinanceSquare #Crypto",
    ]
    return "\n".join(lines)


def format_sl_hit(update: dict) -> str:
    symbol = update["symbol"]
    price  = update["price"]
    signal = update["signal"]
    market = update.get("market", "SPOT")
    coin   = symbol.replace("USDT", "")
    market_tag = "📈 SPOT" if market == "SPOT" else "⚡ FUTURES"

    lines = [
        f"🛑 STOP LOSS HIT — ${symbol}",
        f"{market_tag}",
        "",
        f"SL triggered at {price}",
        "",
        "Risk management is key in crypto trading.",
        "Cut losses, protect capital, next signal incoming! 💪",
        "",
        f"#{coin} #{symbol} #CryptoSignals #RiskManagement #BinanceSquare",
    ]
    return "\n".join(lines)
