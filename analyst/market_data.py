import requests

# CoinGecko free API — no geo restrictions, no API key needed
COINGECKO_API = "https://api.coingecko.com/api/v3"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}


def safe_get(url, params=None):
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=20)
        print(f"[market] GET {url.split('/')[-1]} → {resp.status_code}")
        if resp.status_code != 200:
            print(f"[market] ⚠️ Error: {resp.text[:100]}")
            return None
        return resp.json()
    except Exception as e:
        print(f"[market] Request error: {e}")
        return None


def get_top_volume_coins(limit=8):
    """Get top coins by 24h volume from CoinGecko."""
    data = safe_get(f"{COINGECKO_API}/coins/markets", {
        "vs_currency":    "usd",
        "order":          "volume_desc",
        "per_page":       limit,
        "page":           1,
        "sparkline":      False,
        "price_change_percentage": "1h,24h",
    })
    if not data:
        return []

    coins = []
    for c in data:
        coins.append({
            "symbol":    c["symbol"].upper() + "USDT",
            "id":        c["id"],
            "name":      c["name"],
            "price":     c["current_price"],
            "volume":    c["total_volume"],
            "change_24h": c.get("price_change_percentage_24h") or 0,
            "change_1h":  c.get("price_change_percentage_1h_in_currency") or 0,
            "high":      c.get("high_24h") or c["current_price"],
            "low":       c.get("low_24h")  or c["current_price"],
            "market":    "SPOT",
            "market_cap": c.get("market_cap") or 0,
        })
    return coins


def get_ohlc(coin_id, days=2):
    """Get OHLC candles for a coin (CoinGecko returns 1h candles for 2 days)."""
    data = safe_get(f"{COINGECKO_API}/coins/{coin_id}/ohlc", {
        "vs_currency": "usd",
        "days": days,
    })
    if not data or not isinstance(data, list):
        return []
    # Each item: [timestamp, open, high, low, close]
    return [{
        "open":   c[1],
        "high":   c[2],
        "low":    c[3],
        "close":  c[4],
        "volume": 0,  # OHLC endpoint doesn't include volume
    } for c in data]


def get_volume_chart(coin_id, days=2):
    """Get volume data separately."""
    data = safe_get(f"{COINGECKO_API}/coins/{coin_id}/market_chart", {
        "vs_currency": "usd",
        "days":        days,
        "interval":    "hourly",
    })
    if not data:
        return []
    return [v[1] for v in data.get("total_volumes", [])]


def calculate_indicators(candles, volumes=None):
    if len(candles) < 14:
        return {}
    try:
        closes = [c["close"] for c in candles]
        highs  = [c["high"]  for c in candles]
        lows   = [c["low"]   for c in candles]

        # RSI 14
        gains  = [max(closes[i] - closes[i-1], 0) for i in range(1, 15)]
        losses = [max(closes[i-1] - closes[i], 0) for i in range(1, 15)]
        avg_g  = sum(gains)  / 14
        avg_l  = sum(losses) / 14
        rs     = avg_g / avg_l if avg_l > 0 else 100
        rsi    = round(100 - (100 / (1 + rs)), 1)

        # EMA
        def ema(data, period):
            k = 2 / (period + 1)
            val = sum(data[:period]) / period
            for price in data[period:]:
                val = price * k + val * (1 - k)
            return val

        ema9  = round(ema(closes, 9),  6) if len(closes) >= 9  else closes[-1]
        ema21 = round(ema(closes, 21), 6) if len(closes) >= 21 else closes[-1]

        # Volume surge from external volume data
        vol_ratio = 1.0
        if volumes and len(volumes) >= 6:
            vol_recent = sum(volumes[-3:]) / 3
            vol_prev   = sum(volumes[-6:-3]) / 3
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
    print("[market] Fetching top volume coins from CoinGecko...")
    coins = get_top_volume_coins(8)
    print(f"[market] Got {len(coins)} coins")

    if not coins:
        return []

    print(f"[market] Getting OHLC + volume data...")
    import time
    for i, coin in enumerate(coins):
        # CoinGecko free tier: 10-30 req/min — add small delay
        if i > 0:
            time.sleep(2)

        candles = get_ohlc(coin["id"], days=2)
        volumes = get_volume_chart(coin["id"], days=2)
        coin["indicators_1h"] = calculate_indicators(candles, volumes)

        # Use 1h change as volume ratio fallback if API fails
        if not coin["indicators_1h"].get("volume_ratio"):
            coin["indicators_1h"]["volume_ratio"] = 1.0

        # No separate 15m data on free CoinGecko — reuse 1h
        coin["indicators_15m"] = coin["indicators_1h"]

        print(f"[market] {coin['symbol']} | RSI: {coin['indicators_1h'].get('rsi','?')} | Vol ratio: {coin['indicators_1h'].get('volume_ratio','?')}x")

    return coins
