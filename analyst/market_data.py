import requests
import json

BINANCE_API = "https://api.binance.com/api/v3"
FUTURES_API = "https://fapi.binance.com/fapi/v1"
HEADERS = {"User-Agent": "Mozilla/5.0"}


def get_top_volume_spot(limit=5):
    """Get top volume spot pairs from Binance (last 24h)."""
    try:
        resp = requests.get(f"{BINANCE_API}/ticker/24hr", headers=HEADERS, timeout=15)
        tickers = resp.json()

        # Filter USDT pairs only, sort by quote volume
        usdt = [t for t in tickers if t["symbol"].endswith("USDT") and float(t["quoteVolume"]) > 0]
        usdt.sort(key=lambda x: float(x["quoteVolume"]), reverse=True)
        top = usdt[:limit]

        return [{"symbol": t["symbol"], "price": float(t["lastPrice"]),
                 "volume": float(t["quoteVolume"]), "change": float(t["priceChangePercent"]),
                 "high": float(t["highPrice"]), "low": float(t["lowPrice"]),
                 "market": "SPOT"} for t in top]
    except Exception as e:
        print(f"[market] Spot error: {e}")
        return []


def get_top_volume_futures(limit=5):
    """Get top volume futures pairs from Binance."""
    try:
        resp = requests.get(f"{FUTURES_API}/ticker/24hrVolume", headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            # Try alternative endpoint
            resp = requests.get(f"{FUTURES_API}/ticker/24hr", headers=HEADERS, timeout=15)
        tickers = resp.json()

        usdt = [t for t in tickers if t["symbol"].endswith("USDT") and float(t.get("quoteVolume", 0)) > 0]
        usdt.sort(key=lambda x: float(x.get("quoteVolume", 0)), reverse=True)
        top = usdt[:limit]

        return [{"symbol": t["symbol"], "price": float(t["lastPrice"]),
                 "volume": float(t.get("quoteVolume", 0)), "change": float(t["priceChangePercent"]),
                 "high": float(t["highPrice"]), "low": float(t["lowPrice"]),
                 "market": "FUTURES"} for t in top]
    except Exception as e:
        print(f"[market] Futures error: {e}")
        return []


def get_klines(symbol, interval="1h", limit=24, market="SPOT"):
    """Get candlestick data for a symbol."""
    try:
        base = BINANCE_API if market == "SPOT" else FUTURES_API
        resp = requests.get(
            f"{base}/klines",
            params={"symbol": symbol, "interval": interval, "limit": limit},
            headers=HEADERS, timeout=15
        )
        candles = resp.json()
        # [open_time, open, high, low, close, volume, ...]
        return [{
            "open": float(c[1]),
            "high": float(c[2]),
            "low": float(c[3]),
            "close": float(c[4]),
            "volume": float(c[5]),
        } for c in candles]
    except Exception as e:
        print(f"[market] Klines error for {symbol}: {e}")
        return []


def calculate_indicators(candles):
    """Calculate RSI, EMA, support/resistance from candles."""
    if len(candles) < 14:
        return {}

    closes = [c["close"] for c in candles]
    highs  = [c["high"] for c in candles]
    lows   = [c["low"] for c in candles]
    vols   = [c["volume"] for c in candles]

    # RSI (14)
    gains, losses = [], []
    for i in range(1, 14):
        diff = closes[i] - closes[i-1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains) / 14
    avg_loss = sum(losses) / 14
    rs = avg_gain / avg_loss if avg_loss > 0 else 100
    rsi = 100 - (100 / (1 + rs))

    # EMA 9 and 21
    def ema(data, period):
        k = 2 / (period + 1)
        result = [sum(data[:period]) / period]
        for price in data[period:]:
            result.append(price * k + result[-1] * (1 - k))
        return result

    ema9  = ema(closes, 9)[-1]  if len(closes) >= 9  else closes[-1]
    ema21 = ema(closes, 21)[-1] if len(closes) >= 21 else closes[-1]

    # Volume trend (last 3h vs previous 3h)
    vol_recent = sum(vols[-3:]) / 3 if len(vols) >= 3 else vols[-1]
    vol_prev   = sum(vols[-6:-3]) / 3 if len(vols) >= 6 else vol_recent
    vol_ratio  = vol_recent / vol_prev if vol_prev > 0 else 1

    # Support / Resistance (recent swing lows/highs)
    support    = min(lows[-6:])
    resistance = max(highs[-6:])
    current    = closes[-1]

    return {
        "rsi": round(rsi, 1),
        "ema9": round(ema9, 6),
        "ema21": round(ema21, 6),
        "volume_ratio": round(vol_ratio, 2),
        "support": round(support, 6),
        "resistance": round(resistance, 6),
        "current": round(current, 6),
        "change_2h": round(((closes[-1] - closes[-3]) / closes[-3]) * 100, 2) if len(closes) >= 3 else 0,
        "change_5h": round(((closes[-1] - closes[-6]) / closes[-6]) * 100, 2) if len(closes) >= 6 else 0,
    }


def get_market_snapshot():
    """Get full market snapshot: top coins + their indicators."""
    print("[market] Fetching top spot pairs...")
    spot = get_top_volume_spot(5)

    print("[market] Fetching top futures pairs...")
    futures = get_top_volume_futures(5)

    # Combine and deduplicate
    seen = set()
    all_coins = []
    for coin in spot + futures:
        if coin["symbol"] not in seen:
            seen.add(coin["symbol"])
            all_coins.append(coin)

    # Get indicators for each
    print(f"[market] Getting indicators for {len(all_coins)} coins...")
    for coin in all_coins:
        candles_1h = get_klines(coin["symbol"], "1h", 24, coin["market"])
        candles_15m = get_klines(coin["symbol"], "15m", 24, coin["market"])
        coin["indicators_1h"]  = calculate_indicators(candles_1h)
        coin["indicators_15m"] = calculate_indicators(candles_15m)

    return all_coins
