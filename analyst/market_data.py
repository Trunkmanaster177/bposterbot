import requests
import time

CC_API      = "https://min-api.cryptocompare.com/data"
BINANCE_API = "https://api.binance.com/api/v3"
HEADERS     = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
STABLECOINS = {"USDT", "USDC", "BUSD", "DAI", "TUSD", "USD1", "FDUSD", "USDS", "PYUSD"}

# Core futures coins — high-liquidity trading pairs
TOP_FUTURES_COINS = [
    "BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA",
    "AVAX", "MATIC", "DOT", "LINK", "ARB", "OP", "INJ",
    "SUI", "APT", "TRX", "PEPE", "WIF", "BONK",
    "TON", "NEAR", "FIL", "ATOM", "LTC", "UNI", "AAVE",
]

# Promising altcoins to always monitor for breakouts
ALTCOIN_WATCHLIST = [
    "JUP", "JTO", "PYTH", "BOME", "MEME", "ORDI", "SATS",
    "1000SHIB", "FLOKI", "TURBO", "NEIRO", "EIGEN", "CATI",
    "HMSTR", "DOGS", "RENDER", "FET", "AGIX", "OCEAN",
    "GRT", "LPT", "API3", "BAND", "RLC",
    "IMX", "MANTA", "ALT", "PIXEL", "PORTAL",
    "STRK", "DYM", "TIA", "SEI", "BLUR",
]


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


def get_top_spot_coins(limit=5):
    """Top coins by 24h volume — SPOT market."""
    data = safe_get(f"{CC_API}/top/totalvolfull", {"limit": 20, "tsym": "USD"})
    if not data:
        return []
    coins = []
    for item in data.get("Data", []):
        info = item.get("CoinInfo", {})
        raw  = item.get("RAW", {}).get("USD", {})
        sym  = info.get("Name", "")
        if sym and sym not in STABLECOINS:
            coins.append(_build_coin(sym, raw, "SPOT"))
        if len(coins) >= limit:
            break
    return coins


def get_top_futures_coins(limit=5):
    """Top futures coins by volume — pick from curated high-liquidity list."""
    syms = ",".join(TOP_FUTURES_COINS[:20])
    data = safe_get(f"{CC_API}/pricemultifull", {"fsyms": syms, "tsyms": "USD"})
    if not data:
        return []

    raw_data = data.get("RAW", {})
    coins = []
    for sym in TOP_FUTURES_COINS:
        raw = raw_data.get(sym, {}).get("USD", {})
        if raw and raw.get("PRICE", 0) > 0:
            coins.append(_build_coin(sym, raw, "FUTURES"))

    coins.sort(key=lambda x: x["volume"], reverse=True)
    return coins[:limit]


def get_trending_altcoins(limit=8):
    """
    Fetch trending/high-momentum altcoins from Binance directly.
    Picks coins with biggest 24h volume surge from the altcoin watchlist
    plus any coin on Binance with unusually high volume ratio.
    """
    trending = []

    # ── Strategy 1: Check watchlist coins for volume spikes via Binance ──
    try:
        resp = requests.get(f"{BINANCE_API}/ticker/24hr", headers=HEADERS, timeout=20)
        if resp.status_code == 200:
            all_tickers = resp.json()
            # Build lookup: symbol -> ticker
            ticker_map = {t["symbol"]: t for t in all_tickers if t["symbol"].endswith("USDT")}

            # Score each watchlist coin
            candidates = []
            for sym in ALTCOIN_WATCHLIST:
                ticker = ticker_map.get(f"{sym}USDT")
                if not ticker:
                    continue
                try:
                    price       = float(ticker["lastPrice"])
                    vol_usdt    = float(ticker["quoteVolume"])   # volume in USDT
                    change_24h  = float(ticker["priceChangePercent"])
                    count       = int(ticker["count"])           # number of trades

                    if price <= 0 or vol_usdt < 500_000:        # skip micro-caps
                        continue

                    # Score: combo of volume and trade count (momentum proxy)
                    score = vol_usdt * (1 + abs(change_24h) / 100)
                    candidates.append({
                        "symbol":    f"{sym}USDT",
                        "coin":      sym,
                        "price":     price,
                        "volume":    vol_usdt,
                        "change_24h": change_24h,
                        "high":      float(ticker["highPrice"]),
                        "low":       float(ticker["lowPrice"]),
                        "market":    "SPOT",
                        "score":     score,
                    })
                except Exception:
                    continue

            # Sort by score, take top N
            candidates.sort(key=lambda x: x["score"], reverse=True)
            trending = candidates[:limit]
            print(f"[market] Got {len(trending)} trending altcoins from watchlist")

    except Exception as e:
        print(f"[market] Binance altcoin fetch error: {e}")

    # ── Strategy 2: If Binance fails, fall back to CryptoCompare ──────
    if not trending:
        try:
            syms = ",".join(ALTCOIN_WATCHLIST[:25])
            data = safe_get(f"{CC_API}/pricemultifull", {"fsyms": syms, "tsyms": "USD"})
            if data:
                raw_data = data.get("RAW", {})
                for sym in ALTCOIN_WATCHLIST[:25]:
                    raw = raw_data.get(sym, {}).get("USD", {})
                    if raw and raw.get("PRICE", 0) > 0:
                        trending.append(_build_coin(sym, raw, "SPOT"))
                trending.sort(key=lambda x: x["volume"], reverse=True)
                trending = trending[:limit]
                print(f"[market] Got {len(trending)} altcoins from CryptoCompare fallback")
        except Exception as e:
            print(f"[market] CryptoCompare altcoin fallback error: {e}")

    return trending


def get_new_listings(limit=5):
    """
    Fetch recently listed coins on Binance SPOT.
    Picks USDT pairs with low market cap proxy (low volume but positive momentum).
    """
    new_coins = []
    try:
        resp = requests.get(f"{BINANCE_API}/exchangeInfo", headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            return []

        all_symbols = resp.json().get("symbols", [])

        # Filter: USDT pairs that are TRADING
        usdt_pairs = [
            s for s in all_symbols
            if s["quoteAsset"] == "USDT"
            and s["status"] == "TRADING"
            and s["baseAsset"] not in STABLECOINS
        ]

        # Get 24hr tickers for all USDT pairs
        ticker_resp = requests.get(f"{BINANCE_API}/ticker/24hr", headers=HEADERS, timeout=20)
        if ticker_resp.status_code != 200:
            return []

        ticker_map = {t["symbol"]: t for t in ticker_resp.json()}

        candidates = []
        for sym_info in usdt_pairs:
            full_sym = sym_info["symbol"]
            ticker   = ticker_map.get(full_sym)
            if not ticker:
                continue
            try:
                price      = float(ticker["lastPrice"])
                vol_usdt   = float(ticker["quoteVolume"])
                change_24h = float(ticker["priceChangePercent"])
                count      = int(ticker["count"])

                # New/small coins: moderate volume, high trade activity, positive momentum
                if (
                    price > 0
                    and 100_000 < vol_usdt < 50_000_000   # not mega-cap
                    and count > 5_000                      # active trading
                    and change_24h > 2                     # positive momentum
                ):
                    base = sym_info["baseAsset"]
                    candidates.append({
                        "symbol":    full_sym,
                        "coin":      base,
                        "price":     price,
                        "volume":    vol_usdt,
                        "change_24h": change_24h,
                        "high":      float(ticker["highPrice"]),
                        "low":       float(ticker["lowPrice"]),
                        "market":    "SPOT",
                        "score":     change_24h * (count / 10_000),
                    })
            except Exception:
                continue

        # Sort by momentum score
        candidates.sort(key=lambda x: x["score"], reverse=True)
        new_coins = candidates[:limit]
        print(f"[market] Got {len(new_coins)} new/emerging coins from Binance")

    except Exception as e:
        print(f"[market] New listings fetch error: {e}")

    return new_coins


def _build_coin(sym, raw, market):
    return {
        "symbol":     sym + "USDT",
        "coin":       sym,
        "price":      raw.get("PRICE", 0),
        "volume":     raw.get("TOTALVOLUME24HTO", 0),
        "change_24h": raw.get("CHANGEPCT24HOUR", 0),
        "high":       raw.get("HIGH24HOUR", 0),
        "low":        raw.get("LOW24HOUR", 0),
        "market":     market,
    }


def get_hourly_candles(symbol, limit=24):
    # Try Binance first (more accurate)
    try:
        resp = requests.get(
            f"{BINANCE_API}/klines",
            params={"symbol": f"{symbol}USDT", "interval": "1h", "limit": limit},
            headers=HEADERS, timeout=15
        )
        if resp.status_code == 200:
            raw = resp.json()
            candles = [{
                "open":   float(c[1]),
                "high":   float(c[2]),
                "low":    float(c[3]),
                "close":  float(c[4]),
                "volume": float(c[5]),
            } for c in raw if float(c[4]) > 0]
            if candles:
                return candles
    except Exception:
        pass

    # Fallback: CryptoCompare
    data = safe_get(f"{CC_API}/histohour", {"fsym": symbol, "tsym": "USD", "limit": limit})
    if not data or data.get("Response") == "Error":
        return []
    raw = data.get("Data", [])
    if isinstance(raw, dict):
        raw = raw.get("Data", [])
    return [{
        "open":   c["open"],
        "high":   c["high"],
        "low":    c["low"],
        "close":  c["close"],
        "volume": c["volumefrom"],
    } for c in raw if isinstance(c, dict) and c.get("close", 0) > 0]


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

        def ema(data, period):
            k = 2 / (period + 1)
            val = sum(data[:period]) / period
            for p in data[period:]:
                val = p * k + val * (1 - k)
            return round(val, 6)

        ema9  = ema(closes, 9)  if len(closes) >= 9  else closes[-1]
        ema21 = ema(closes, 21) if len(closes) >= 21 else closes[-1]

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
    print("[market] Fetching top SPOT coins...")
    spot = get_top_spot_coins(5)
    print(f"[market] Got {len(spot)} spot coins")

    print("[market] Fetching top FUTURES coins...")
    futures = get_top_futures_coins(5)
    print(f"[market] Got {len(futures)} futures coins")

    print("[market] Fetching trending altcoins...")
    alts = get_trending_altcoins(8)
    print(f"[market] Got {len(alts)} trending altcoins")

    print("[market] Fetching new/emerging coins...")
    new_coins = get_new_listings(5)
    print(f"[market] Got {len(new_coins)} new/emerging coins")

    # Combine all — deduplicate by symbol+market
    seen = set()
    all_coins = []
    for coin in spot + futures + alts + new_coins:
        key = f"{coin['symbol']}_{coin['market']}"
        if key not in seen:
            seen.add(key)
            all_coins.append(coin)

    print(f"[market] Total unique: {len(all_coins)} coins "
          f"({len(spot)} SPOT + {len(futures)} FUTURES + {len(alts)} ALTS + {len(new_coins)} NEW)")

    for i, coin in enumerate(all_coins):
        if i > 0:
            time.sleep(0.5)
        sym     = coin["coin"]
        candles = get_hourly_candles(sym, limit=24)
        ind     = calculate_indicators(candles)
        coin["indicators_1h"]  = ind
        coin["indicators_15m"] = ind
        coin["candles"]        = candles

        if ind:
            if not coin["price"] and ind.get("current"):
                coin["price"] = ind["current"]
            print(f"[market] {coin['symbol']} ({coin['market']}) | RSI: {ind.get('rsi','?')} | "
                  f"Vol: {ind.get('volume_ratio','?')}x | 2h: {ind.get('change_2h','?')}%")
        else:
            print(f"[market] {coin['symbol']} ({coin['market']}) | No data")

    return all_coins
                                                    
