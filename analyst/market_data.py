import requests
import json

BINANCE_API  = "https://api.binance.com/api/v3"
FUTURES_API  = "https://fapi.binance.com/fapi/v1"
HEADERS      = {"User-Agent": "Mozilla/5.0"}


def safe_get(url, params=None):
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        print(f"[market] GET {url.split('/')[-1]} → {resp.status_code}")
        data = resp.json()
        # API returned an error dict instead of list
        if isinstance(data, dict):
            print(f"[market] ⚠️ Unexpected response: {str(data)[:100]}")
            return []
        return data
    except Exception as e:
        print(f"[market] Request error: {e}")
        return []


def get_top_volume_spot(limit=5):
    tickers = safe_get(f"{BINANCE_API}/ticker/24hr")
    if not tickers:
        return []
    try:
        usdt = [t for t in tickers
                if isinstance(t, dict)
                and t.get("symbol", "").endswith("USDT")
                and float(t.get("quoteVolume", 0)) > 0]
        usdt.sort(key=lambda x: float(x["quoteVolume"]), reverse=True)
        return [{
            "symbol":  t["symbol"],
            "price":   float(t["lastPrice"]),
            "volume":  float(t["quoteVolume"]),
            "change":  float(t["priceChangePercent"]),
            "high":    float(t["highPrice"]),
            "low":     float(t["lowPrice"]),
            "market":  "SPOT"
        } for t in usdt[:limit]]
    except Exception as e:
        print(f"[market] Spot parse error: {e}")
        return []


def get_top_volume_futures(limit=5):
    tickers = safe_get(f"{FUTURES_API}/ticker/24hr")
    if not tickers:
        return []
    try:
        usdt = [t for t in tickers
                if isinstance(t, dict)
                and t.get("symbol", "").endswith("USDT")
                and float(t.get("quoteVolume", 0)) > 0]
        usdt.sort(key=lambda x: float(x.get("quoteVolume", 0)), reverse=True)
        return [{
            "symbol":  t["symbol"],
            "price":   float(t["lastPrice"]),
            "volume":  float(t.get("quoteVolume", 0)),
            "change":  float(t["priceChangePercent"]),
            "high":    float(t["highPrice"]),
            "low":     float(t["lowPrice"]),
            "market":  "FUTURES"
        } for t in usdt[:limit]]
    except Exception as e:
        print(f"[market] Futures parse error: {e}")
        return []


def get_klines(symbol, interval="1h", limit=24, market="SPOT"):
    base = BINANCE_API if market == "SPOT" else FUTURES_API
    data = safe_get(f"{base}/klines", {"symbol": symbol, "interval": interval, "limit": limit})
    if not data:
        return []
    try:
        return [{
            "open":   float(c[1]),
            "high":   float(c[2]),
            "low":    float(c[3]),
            "close":  float(c[4]),
            "volume": float(c[5]),
        } for c in data if isinstance(c, list)]
    except Exception as e:
        print(f"[market] Klines parse error for {symbol}: {e}")
        return []


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

        # Volume surge
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
    print("[market] Fetching top spot pairs...")
    spot = get_top_volume_spot(5)
    print(f"[market] Got {len(spot)} spot pairs")

    print("[market] Fetching top futures pairs...")
    futures = get_top_volume_futures(5)
    print(f"[market] Got {len(futures)} futures pairs")

    # Combine, deduplicate by symbol
    seen, all_coins = set(), []
    for coin in spot + futures:
        if coin["symbol"] not in seen:
            seen.add(coin["symbol"])
            all_coins.append(coin)

    print(f"[market] Getting indicators for {len(all_coins)} coins...")
    for coin in all_coins:
        coin["indicators_1h"]  = calculate_indicators(
            get_klines(coin["symbol"], "1h",  24, coin["market"]))
        coin["indicators_15m"] = calculate_indicators(
            get_klines(coin["symbol"], "15m", 24, coin["market"]))

    return all_coins
