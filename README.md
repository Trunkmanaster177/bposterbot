# 🤖 Binance Square Mirror Bot

Automatically monitors **ict_bull** on Binance Square and reposts their latest content to your own account — running 100% on GitHub Actions (no server needed).

---

## 🔧 How It Works

1. **Every 30 minutes**, GitHub Actions triggers the bot
2. Bot **scrapes** `binance.com/en/square/profile/ict_bull` for the latest post
3. If a **new post is detected** (compared to `last_post_id.txt`), it logs into your Binance account via Playwright (headless browser)
4. Bot **posts the content as-is** to your Binance Square
5. `last_post_id.txt` is committed back to the repo to track state

---

## 🚀 Setup Instructions

### Step 1: Fork / Clone This Repo

```bash
git clone https://github.com/YOUR_USERNAME/binance-square-bot.git
cd binance-square-bot
```

Or click **"Use this template"** on GitHub to fork it.

---

### Step 2: Add GitHub Secrets

Go to your repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

Add these secrets:

| Secret Name | Value | Required |
|---|---|---|
| `BINANCE_EMAIL` | Your Binance login email | ✅ Yes |
| `BINANCE_PASSWORD` | Your Binance login password | ✅ Yes |
| `BINANCE_TOTP_SECRET` | Your Google Authenticator secret key (the text code, not QR) | ⚡ Only if you have 2FA |

> **How to get your TOTP secret:** When setting up 2FA on Binance, they show you a QR code AND a text key. Use that text key (looks like `JBSWY3DPEHPK3PXP`). If you already set up 2FA, you'll need to disable and re-enable it to see the key.

---

### Step 3: Enable GitHub Actions

1. Go to **Actions** tab in your repo
2. Click **"I understand my workflows, go ahead and enable them"**
3. The bot runs every 30 min automatically

---

### Step 4: First Run (Manual Test)

Trigger it manually to test:
- Go to **Actions** → **Binance Square Mirror Bot** → **Run workflow**

On first run, the bot **won't post** — it just records the current latest post ID as a baseline. The **second run** onwards will detect and post new content.

---

## 📁 File Structure

```
binance-square-bot/
├── .github/
│   └── workflows/
│       └── bot.yml          ← GitHub Actions schedule
├── bot/
│   ├── main.py              ← Entry point / orchestrator
│   ├── scraper.py           ← Fetches posts from ict_bull
│   └── poster.py            ← Logs in & posts via Playwright
├── last_post_id.txt         ← Tracks last posted ID (auto-updated)
├── requirements.txt
└── README.md
```

---

## ⚙️ Configuration

To monitor a **different user**, edit `bot/scraper.py`:

```python
TARGET_USERNAME = "ict_bull"  # ← change this
```

To change the **polling interval**, edit `.github/workflows/bot.yml`:

```yaml
- cron: "*/30 * * * *"   # every 30 min
# - cron: "*/15 * * * *" # every 15 min
# - cron: "0 * * * *"    # every hour
```

---

## ⚠️ Important Notes

- **This uses browser automation** (Playwright), not an official Binance API — Binance Square has no public posting API.
- **Use a dedicated Binance account** for posting, not your main trading account.
- Binance may occasionally show CAPTCHA challenges — if posts stop working, check the debug screenshots in the Actions artifacts.
- GitHub Actions free tier gives **2,000 minutes/month** — running every 30 min uses ~1,440 min/month (within limits).
- Never share your `BINANCE_EMAIL`, `BINANCE_PASSWORD`, or `BINANCE_TOTP_SECRET` publicly.

---

## 🐛 Debugging

If a run fails, GitHub Actions will upload **debug screenshots** as artifacts. Download them from the failed workflow run to see what the browser saw.

Common issues:
- **CAPTCHA** → Binance flagged the automated login. Try logging in manually once, then saving cookies (advanced setup).
- **"No post input found"** → Binance updated their UI. Open an issue and I'll update the selectors.
- **2FA failed** → Double check your `BINANCE_TOTP_SECRET` is the raw base32 key, not the QR code URL.
