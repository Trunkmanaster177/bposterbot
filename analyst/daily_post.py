import os
import json
import random
import requests
from datetime import datetime

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL   = "llama-3.3-70b-versatile"

# Rotate topics daily — covers all high-engagement categories
TOPIC_ROTATION = [
    # DeFi & Staking (Very High engagement)
    {"type": "defi",     "topic": "How DeFi Yield Farming Works — and How to Avoid Getting Rekt"},
    {"type": "defi",     "topic": "Liquidity Pools Explained: What Are Impermanent Losses?"},
    {"type": "defi",     "topic": "Staking vs Yield Farming: Which Earns More in 2025?"},
    {"type": "defi",     "topic": "Top 5 DeFi Protocols You Should Know About"},
    {"type": "defi",     "topic": "How to Use DeFi Safely: Avoiding Rug Pulls and Scams"},
    {"type": "wallet",   "topic": "Hot Wallet vs Cold Wallet: Which Should You Use?"},
    {"type": "wallet",   "topic": "How to Secure Your Crypto: The Ultimate Wallet Guide"},
    {"type": "wallet",   "topic": "What is a Seed Phrase and Why It's Your Most Important Asset"},
    # Market Analysis (High engagement)
    {"type": "analysis", "topic": "Bitcoin Dominance and What It Means for Altcoins"},
    {"type": "analysis", "topic": "How to Read Crypto Market Cycles Like a Pro"},
    {"type": "analysis", "topic": "On-Chain Metrics Every Crypto Trader Should Track"},
    {"type": "analysis", "topic": "Understanding Support and Resistance in Crypto Markets"},
    {"type": "analysis", "topic": "How to Use RSI and MACD for Crypto Trading"},
    {"type": "analysis", "topic": "Fear & Greed Index: How to Use Market Sentiment"},
    # News & Opinion (Medium engagement)
    {"type": "news",     "topic": "What Bitcoin ETF Approval Means for Crypto Prices"},
    {"type": "news",     "topic": "Why Institutional Adoption is the Biggest Crypto Catalyst"},
    {"type": "news",     "topic": "Crypto Regulation: What Traders Need to Know in 2025"},
    {"type": "news",     "topic": "The Future of Stablecoins: USDT, USDC and CBDCs"},
    # Education
    {"type": "education","topic": "What is Layer 2? How Ethereum Scaling Solutions Work"},
    {"type": "education","topic": "Gas Fees Explained: Why They Matter and How to Save"},
    {"type": "education","topic": "What is a DAO and How Does It Work?"},
    {"type": "education","topic": "NFTs in 2025: Are They Still Relevant?"},
    {"type": "education","topic": "Understanding Tokenomics: What Makes a Good Crypto Project"},
    {"type": "education","topic": "How to DYOR (Do Your Own Research) in Crypto"},
    {"type": "education","topic": "Crypto Tax Basics: What Every Trader Should Know"},
    {"type": "education","topic": "What is Web3 and Why Does It Matter?"},
    {"type": "education","topic": "Smart Contracts Explained in Simple Terms"},
    {"type": "education","topic": "The Difference Between Coins and Tokens"},
    {"type": "education","topic": "How Crypto Exchanges Work: CEX vs DEX"},
]

TYPE_HASHTAGS = {
    "defi":      "#DeFi #YieldFarming #Staking #BinanceSquare #Crypto #Web3",
    "wallet":    "#CryptoSecurity #Wallet #SAFU #BinanceSquare #Crypto",
    "analysis":  "#CryptoAnalysis #Bitcoin #MarketAnalysis #BinanceSquare #Trading",
    "news":      "#CryptoNews #Bitcoin #BinanceSquare #Crypto #Blockchain",
    "education": "#CryptoEducation #LearnCrypto #BinanceSquare #Blockchain #Web3",
}


def get_todays_topic() -> dict:
    """Pick today's topic based on day of year so it rotates daily."""
    day = datetime.utcnow().timetuple().tm_yday
    return TOPIC_ROTATION[day % len(TOPIC_ROTATION)]


def generate_educational_post(topic_data: dict) -> str:
    """Use Groq AI to write a detailed, high-quality educational post."""
    topic     = topic_data["topic"]
    post_type = topic_data["type"]

    type_instructions = {
        "defi":      "Focus on practical DeFi concepts. Explain how it works, risks, and opportunities. Use simple analogies.",
        "wallet":    "Focus on security best practices. Be practical and actionable. Warn about common mistakes.",
        "analysis":  "Provide deep market insight. Use data, patterns, and expert-level analysis.",
        "news":      "Write a sharp, opinionated take on the topic. Give clear perspective on what it means for traders.",
        "education": "Break down the concept simply. Use bullet points and examples. Make it beginner-friendly.",
    }

    instruction = type_instructions.get(post_type, type_instructions["education"])

    prompt = f"""You are an expert crypto content creator writing for Binance Square.

Write a detailed, high-quality post about: "{topic}"

Instructions:
- {instruction}
- Length: 300-450 words
- Start with a STRONG hook (first line must grab attention)
- Use emojis naturally throughout (not excessively)
- Include 3-5 key points or sections
- End with a thought-provoking question or call to action to encourage comments
- Write in a confident, knowledgeable but approachable tone
- DO NOT add hashtags (they will be added separately)
- DO NOT use markdown headers (##) — use emojis as section markers instead
- Make it genuinely educational and insightful — not generic fluff

Write only the post content, nothing else."""

    try:
        resp = requests.post(
            GROQ_API_URL,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type":  "application/json",
            },
            json={
                "model":       GROQ_MODEL,
                "messages":    [{"role": "user", "content": prompt}],
                "temperature": 0.8,
                "max_tokens":  1000,
            },
            timeout=30
        )

        if resp.status_code != 200:
            print(f"[daily] Groq error {resp.status_code}: {resp.text[:150]}")
            return ""

        content = resp.json()["choices"][0]["message"]["content"].strip()
        return content

    except Exception as e:
        print(f"[daily] Generation error: {e}")
        return ""


def build_daily_post() -> str:
    """Generate and format the full daily educational post."""
    topic_data = get_todays_topic()
    print(f"[daily] Today's topic ({topic_data['type']}): {topic_data['topic']}")

    content = generate_educational_post(topic_data)
    if not content:
        return ""

    hashtags = TYPE_HASHTAGS.get(topic_data["type"], "#Crypto #BinanceSquare")

    full_post = f"{content}\n\n{hashtags}"
    return full_post
