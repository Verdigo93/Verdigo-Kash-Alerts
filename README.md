# Verdigo Kash Alerts

An English-language Telegram bot for tracking Kash prediction markets (read-only).

## Features
- Next Closings button and /soon command show upcoming trading freezes within two hours
- Improved closing alerts catch missed scan windows without sending several outdated reminders
- Personal 15 / 30 / 60 minute alerts before Kash's `freezeAt` (last trading time)
- High-volume threshold-crossing alerts and unusual volume-change alerts
- Direct links to market pages on `app.kash.bot/markets/<UUID>`
- Separate settings for every Telegram subscriber
- Top markets by **lifetime USDC volume** (`/top`): choose Top 5, 10, 15 or 20 per Telegram user; navigate in pages of five markets in a single editable message with clickable market links
- Inline **Volume Filter** with presets: under $10, $10–$100, $100+, $1,000+, $10,000+, or all
- **Custom** volume range by replying with a regular message (`250`, `<10`, `50-500`, `100+`); no slash command required
- Show up to five active matching markets with **Show matching markets** or `/markets`
- Resilient multi-user delivery: a blocked Telegram user (HTTP 403) cannot interrupt other subscribers' alerts
- `/status` shows last successful Kash fetch and whether the latest Kash request failed
- No trading, no wallet connection, no write-capable Kash key

## Try it on Windows (Python 3.11+)

1. Download ZIP from this repository (Code → Download ZIP), then extract.
2. Double-click `START_LOCAL.cmd`.
3. Paste your **BotFather Telegram token** and **read-only Kash API key** in the two private pop-up dialogs. These values are not saved to disk.
4. Open [@VerdigoKashAlertsBot](https://t.me/VerdigoKashAlertsBot) in Telegram, send `/start`, and then `/settings`, `/soon`, `/status`, or `/top`. Tap **Top Markets**, choose 5/10/15/20, then use **Next** and **Previous**; `/top 20` opens a list directly.
5. Keep the command window open while testing. Close it to stop the bot.

Never paste keys into GitHub, Telegram chats, screenshots, or the Windows command line. Kash key only needs `markets:read`.

**Local mode is only for testing**: the bot runs while this PC and the command window stay on. For 24/7 operation use a continuously running worker/VPS and persistent state storage.

## How it works

- Kash authenticated REST `GET https://api.kash.bot/v1/markets`: market list, `freezeAt`, `tradeable`, cursor paging
- Kash public read-only `GET https://app.kash.bot/api/markets/state?ids=...`: lifetime volume in atomic USDC (converted to USDC by dividing by 1,000,000)
- Telegram Bot API long polling, one worker, JSON state in `data/state.json`

**Troubleshooting 403:** An HTTP 403 in old logs could originate from either Telegram delivery (user blocked bot) or Kash market retrieval. New logs distinguish these sources. A Telegram 403 disables deliveries only to that subscriber until they interact with the bot again; the other subscribers keep receiving alerts. A Kash API 403 means fresh market data is unavailable; inspect `/status` for the last successful update. Tokens are never printed into error logs. Deploy the updated `bot.py` to your server and restart its process to apply this fix; GitHub changes alone do not update a running host.

The market volume filter applies to volume-based alerts and the matching-markets view, **not** the 15/30/60-minute closing alerts or unusual-activity alerts. On the first run, it learns an initial market-volume baseline instead of sending a flood of existing market alerts; after that, it alerts about newly observed markets in the range or changes crossing into it, at most five volume notifications per subscriber per scan. Selecting a different filter does not immediately alert about all existing markets in that range.

This is a beta. Volume data can be unavailable if the public API is down. The bot continues closing-time alerts in that case. Notifications are informational, not trading advice.

Docs: [Kash REST Markets](https://docs.kash.bot/developer-docs/rest-api/endpoints/markets) · [Kash API Pagination](https://docs.kash.bot/developer-docs/rest-api/pagination) · [Kash Public Market State](https://docs.kash.bot/developer-docs/public-embed-api/endpoints/markets-state)
