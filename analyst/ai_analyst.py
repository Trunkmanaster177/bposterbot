import os
import json
import requests

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL   = "llama-3.3-70b-versatile"  # Free, fast, accurate


def analyse_and_generate_signal(coin: dict) -> dict | None:
    """Send coin data to Groq AI and get back a trading signal."""
    if not GROQ_API_KEY:
        print("[ai] ❌ GROQ_API_KEY not set!")
        return None

    ind_1h  = coin.get("indicators_1h", {})
    ind_15m = coin.get("indicators_15m", {})
    market  = coin.get("market", "SPOT")
    symbol  = coin["symbol"]
    price   = coin["price"]

    prompt = f"""You are a professional crypto trader and technical analyst.

Analyze this coin and generate a trading signal based on the data below.

## Coin: {symbol} ({market})
- Current Price: {price}
- 24h Change: {coin.get('change_24h', coin.get('change', 0))}%
- 24h Volume: ${coin['volume']:,.0f}
- 24h High: {coin['high']} | Low: {coin['low']}

## 1H Indicators:
- RSI(14): {ind_1h.get('rsi', 'N/A')}
- EMA9: {ind_1h.get('ema9', 'N/A')} | EMA21: {ind_1h.get('ema21', 'N/A')}
- Volume Ratio (last 3h vs prev 3h): {ind_1h.get('volume_ratio', 'N/A')}x
- 2H Price Change: {ind_1h.get('change_2h', 'N/A')}%
- 5H Price Change: {ind_1h.get('change_5h', 'N/A')}%
- Support: {ind_1h.get('support', 'N/A')} | Resistance: {ind_1h.get('resistance', 'N/A')}

## 15M Indicators:
- RSI(14): {ind_15m.get('rsi', 'N/A')}
- EMA9: {ind_15m.get('ema9', 'N/A')} | EMA21: {ind_15m.get('ema21', 'N/A')}
- Volume Ratio: {ind_15m.get('volume_ratio', 'N/A')}x

Respond ONLY with a JSON object. No markdown, no text outside JSON.

Rules:
- Only generate a signal if there is a CLEAR opportunity (strong volume surge + RSI confirmation + trend alignment)
- If no clear signal, return {{"signal": "NONE"}}
- For SPOT market: set leverage to null
- For FUTURES market: suggest conservative leverage (2x-5x max)
- Entry should be current price or slightly better
- TP targets should be realistic (1-3% steps for spot, 2-5% for futures)
- SL should be below support for BUY, above resistance for SELL

JSON format:
{{
  "signal": "BUY" or "SELL" or "NONE",
  "entry": <number>,
  "tp1": <number>,
  "tp2": <number>,
  "tp3": <number>,
  "sl": <number>,
  "leverage": <number or null>,
  "confidence": "HIGH" or "MEDIUM" or "LOW",
  "explanation": "<2-3 sentences explaining WHY — mention RSI, volume surge, EMA, trend>"
}}"""

    try:
        resp = requests.post(
            GROQ_API_URL,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": GROQ_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 500,
            },
            timeout=30
        )

        if resp.status_code != 200:
            print(f"[ai] Groq error {resp.status_code}: {resp.text[:150]}")
            return None

        raw = resp.json()["choices"][0]["message"]["content"].strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        signal = json.loads(raw)

        if signal.get("signal") == "NONE":
            print(f"[ai] No signal for {symbol}")
            return None

        signal["symbol"] = symbol
        signal["market"] = market
        signal["price"]  = price
        return signal

    except Exception as e:
        print(f"[ai] Error for {symbol}: {e}")
        return None


def format_signal_post(signal: dict) -> str:
    """Format AI signal into a Binance Square post."""
    action     = signal["signal"]
    symbol     = signal["symbol"]
    market     = signal["market"]
    confidence = signal.get("confidence", "MEDIUM")

    emoji      = "🟢" if action == "BUY" else "🔴"
    conf_emoji = {"HIGH": "🔥", "MEDIUM": "✨", "LOW": "⚠️"}.get(confidence, "✨")
    market_tag = "📈 SPOT" if market == "SPOT" else "⚡ FUTURES"
    coin       = symbol.replace("USDT", "")

    lines = [
        f"{emoji} ${symbol} — {action} SIGNAL",
        f"{market_tag} | {conf_emoji} Confidence: {confidence}",
        "",
        f"📍 Entry:  {signal['entry']}",
        f"✅ TP1:   {signal['tp1']}",
        f"✅ TP2:   {signal['tp2']}",
        f"✅ TP3:   {signal['tp3']}",
        f"🛑 SL:    {signal['sl']}",
    ]

    if signal.get("leverage") and market == "FUTURES":
        lines.append(f"⚡ Leverage: {signal['leverage']}x")

    lines += [
        "",
        "🧠 Analysis:",
        signal.get("explanation", ""),
        "",
        "⚠️ DYOR — Not financial advice.",
        "",
        f"#{coin} #{symbol} #CryptoSignals #AITrading #BinanceSquare #Crypto #Trading"
    ]

    return "\n".join(lines)
