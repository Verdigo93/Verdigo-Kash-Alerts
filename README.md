# Verdigo Kash Alerts

An English-language Telegram bot for tracking Kash prediction markets (read-only).

## Features
- Personal 15 / 30 / 60 minute alerts before Kash's `freezeAt` (last trading time)
- High-volume threshold-crossing alerts and unusual volume-change alerts
- Direct links to market pages on `app.kash.bot/markets/<UUID>`
- Separate settings for every Telegram subscriber
- Top markets by **lifetime USDC volume** (`/top`)
- No trading, no wallet connection, no write-capable Kash key

## Try it on Windows (Python 3.11+)

1. Download ZIP from this repository (Code → Download ZIP), then extract.
2. Double-click `START_LOCAL.cmd`.
3. Paste your **BotFather Telegram token** and **read-only Kash API key** in the two private pop-up dialogs. These values are not saved to disk.
4. Open [@VerdigoKashAlertsBot](https://t.me/VerdigoKashAlertsBot) in Telegram, send `/start`, and then `/status` or `/top`.
5. Keep the command window open while testing. Close it to stop the bot.

Never paste keys into GitHub, Telegram chats, screenshots, or the Windows command line. Kash key only needs `markets:read`.

**Local mode is only for testing**: the bot runs while this PC and the command window stay on. For 24/7 operation use a continuously running worker/VPS and persistent state storage.

## How it works

- Kash authenticated REST `GET https://api.kash.bot/v1/markets`: market list, `freezeAt`, `tradeable`, cursor paging
- Kash public read-only `GET https://app.kash.bot/api/markets/state?ids=...`: lifetime volume in atomic USDC (converted to USDC by dividing by 1,000,000)
- Telegram Bot API long polling, one worker, JSON state in `data/state.json`

This is a beta. Volume data can be unavailable if the public API is down. The bot continues closing-time alerts in that case. Notifications are informational, not trading advice.

Docs: [Kash REST Markets](https://docs.kash.bot/developer-docs/rest-api/endpoints/markets) · [Kash API Pagination](https://docs.kash.bot/developer-docs/rest-api/pagination) · [Kash Public Market State](https://docs.kash.bot/developer-docs/public-embed-api/endpoints/markets-state)
