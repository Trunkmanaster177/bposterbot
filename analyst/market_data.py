import requests
import time

# CryptoCompare - free, no geo restrictions, no API key needed for basic use
CC_API = "https://min-api.cryptocompare.com/data"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

# Top coins to always analyze (skip stablecoins)
STABLECOINS = {"USDT", "USDC", "BUSD", "DAI", "TUSD", "USD1", "FDUSD"}
TOP_COINS = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "AVAX", "MATIC", "DOT"]


def safe_get(url, params=None):
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=20)
        if resp.status_code == 200:
            return resp.json()
        print(f"[market] ⚠️ {url.split('/')[-1]} → {resp.status_code}: {resp.text[:80]}")
        return None
    except Exception as e:
        print(f"[market] Request error: {e}")
        return None


def get_hourly_candles(symbol, limit=24):
    """Get last 24 hourly candles for a coin."""
    data = safe_get(f"{CC_API}/histohour", {
        "fsym":  symbol,
        "tsym":  "USD",
        "limit": limit,
    })
    if not data or data.get("Response") == "Error":
        print(f"[market] No candles for {symbol}: {data.get('Message', '') if data else ''}")
        return []
    return [{
        "open":   c["open"],
        "high":   c["high"],
        "low":    c["low"],
        "close":  c["close"],
        "volume": c["volumefrom"],
    } for c in data.get("Data", {}).get("Data", []) if c["close"] > 0]


def get_top_coins_by_volume():
    """Get top coins sorted by 24h volume."""
    data = safe_get(f"{CC_API}/top/totalvolfull", {
        "limit": 20,
        "tsym":  "USD",
    })
    if not data:
        return TOP_COINS[:8]

    coins = []
    for item in data.get("Data", []):
        info = item.get("CoinInfo", {})
        raw  = item.get("RAW", {}).get("USD", {})
        sym  = info.get("Name", "")
        if sym and sym not in STABLECOINS:
            coins.append({
                "symbol":     sym + "USDT",
                "coin":       sym,
                "price":      raw.get("PRICE", 0),
                "volume":     raw.get("TOTALVOLUME24HTO", 0),
                "change_24h": raw.get("CHANGEPCT24HOUR", 0),
                "high":       raw.get("HIGH24HOUR", 0),
                "low":        raw.get("LOW24HOUR", 0),
                "market":     "SPOT",
            })
    return coins[:8] if coins else [{"symbol": s + "USDT", "coin": s, "price": 0,
                                      "volume": 0, "change_24h": 0, "high": 0,
                                      "low": 0, "market": "SPOT"} for s in TOP_COINS[:8]]


def calculate_indicators(candles):
    if len(candles) < 14:
        return {}
    try:
        closes = [c["close"]  for c in candles]
        highs  = [c["high"]   for c in candles]
        lows   = [c["low"]    for c in candles]
        vols   = [c["volume"] for c in candles]

        # RSI 14
        gains  = [max(closes[i] - closes[i-1], 0) for i in range(1, 15)]
        losses = [max(closes[i-1] - closes[i], 0) for i in range(1, 15)]
        avg_g  = sum(gains) / 14
        avg_l  = sum(losses) / 14
        rs     = avg_g / avg_l if avg_l > 0 else 100
        rsi    = round(100 - (100 / (1 + rs)), 1)

        # EMA
        def ema(data, period):
            k = 2 / (period + 1)
            val = sum(data[:period]) / period
            for p in data[period:]:
                val = p * k + val * (1 - k)
            return round(val, 6)

        ema9  = ema(closes, 9)  if len(closes) >= 9  else closes[-1]
        ema21 = ema(closes, 21) if len(closes) >= 21 else closes[-1]

        # Volume surge: last 3h vs previous 3h
        vol_recent = sum(vols[-3:]) / 3 if len(vols) >= 3 else vols[-1]
        vol_prev   = sum(vols[-6:-3]) / 3 if len(vols) >= 6 else vol_recent
        vol_ratio  = round(vol_recent / vol_prev, 2) if vol_prev > 0 else 1.0

        return {
            "rsi":          rsi,
            "ema9":         ema9,
            "ema21":        ema21,
            "volume_ratio": vol_ratio,
            "support":      round(min(lows[-6:]),  6),
            "resistance":   round(max(highs[-6:]), 6),
            "current":      round(closes[-1],      6),
            "change_2h":    round(((closes[-1] - closes[-3]) / closes[-3]) * 100, 2) if len(closes) >= 3 else 0,
            "change_5h":    round(((closes[-1] - closes[-6]) / closes[-6]) * 100, 2) if len(closes) >= 6 else 0,
        }
    except Exception as e:
        print(f"[market] Indicator error: {e}")
        return {}


def get_market_snapshot():
    print("[market] Fetching top volume coins...")
    coins = get_top_coins_by_volume()
    print(f"[market] Got {len(coins)} coins: {[c['symbol'] for c in coins]}")

    for i, coin in enumerate(coins):
        if i > 0:
            time.sleep(1)  # gentle rate limiting
        sym = coin["coin"]
        candles = get_hourly_candles(sym, limit=24)
        coin["indicators_1h"]  = calculate_indicators(candles)
        coin["indicators_15m"] = coin["indicators_1h"]  # reuse for now

        ind = coin["indicators_1h"]
        if ind:
            # Fill price from candles if missing
            if not coin["price"] and ind.get("current"):
                coin["price"] = ind["current"]
            print(f"[market] {coin['symbol']} | RSI: {ind.get('rsi','?')} | "
                  f"Vol: {ind.get('volume_ratio','?')}x | "
                  f"2h: {ind.get('change_2h','?')}%")
        else:
            print(f"[market] {coin['symbol']} | No indicator data")

    return coins
