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
- **Whale Alerts (enabled by default, optional opt-out)** (`/whales`): newly observed large positions and increases in a public trader's invested amount, with independent $20–50, $50–100, $100–500, $500–1,000 and $1,000+ filters. Enabled by default (each user can switch it off).
- Public profiles and primary outcomes appear when Kash exposes them. These do **not** prove a trader is human or that the change is one individual buy.


## Try it on Windows (Python 3.11+)

1. Download ZIP from this repository (Code → Download ZIP), then extract.
2. Double-click `START_LOCAL.cmd`.
3. Paste your **BotFather Telegram token** and **read-only Kash API key** in the two private pop-up dialogs. These values are not saved to disk.
4. Open [@VerdigoKashAlertsBot](https://t.me/VerdigoKashAlertsBot) in Telegram, send /start, then /menu, /settings, /analytics, /about, /news, /watch, /soon, /status, or /top. Tap **Top Markets**, choose 5/10/15/20, then use **Next** and **Previous**; `/top 20` opens a list directly.
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

## Free health check (no terminal required)

Send `/whalestatus` to the Telegram bot to see the active configuration, eligible market count, number of snapshot markets and tracked public positions, time of the last attempted/successful leaderboard read, latest failure code, and any API backoff. This command makes no API requests and never exposes user IDs or API tokens.

## Whale Alerts (beta; enabled by default)

The `/whales` menu has ON/OFF, independently enabled **newly observed positions** and **position increases**, and multiple selectable USDC ranges. The range is applied to the amount **added since the last observation**, not the entire position. Whale Alerts are enabled by default for new and existing subscribers unless they explicitly turn the feature off. All five $20+ ranges are selected initially.

Implementation uses Kash's public market-state `tradeCount` to choose changed markets and requests `/api/markets/{id}/leaderboard?limit=50`. It compares each public `userId`'s `amount` (atomic 6-decimal USDC) across snapshots. **It does not use the `currentValue` field**, which moves with price. The primary outcome in the leaderboard is not necessarily the outcome of the most recent trade.

**Accuracy boundaries:** This is a change in a public leaderboard snapshot, *not* a guaranteed new purchase, an exact account balance, or proof that the account belongs to a person. Changes between scans can be missed, cached leaderboard pages can be late, and only the top 50 entries per market are observed. Entry disappearance/reappearance can also be reported as a newly observed position. It is not a complete trade tape. No trading advice or buy/sell signal is implied.

**Safety & performance:** Whale Alerts make **zero** extra API requests whenever all subscribers explicitly disable them (or none are subscribed). For enabled users, an initial baseline is silently learned (at most **3 extra leaderboard requests per 60-second scan**), so on a busy set of markets this can take several scans. There are at most **5 whale notifications per subscriber per scan**, a read-only HTTP 429/503 backoff, and deduplication via the existing `state.json`. No write API, wallet or additional scopes are required; existing closing and volume alerts remain unchanged.

**Deployment:** Keep whale_alerts.py, kash_hub.py and kash_news.py alongside bot.py. Back up the persistent `state.json`, deploy the updated files, restart one worker, then verify or disable the feature using `/whales`. A stopped old process must not resume with the same Telegram token. The existing `KASH_API_KEY` requires only `markets:read` for the regular markets list; the whale leaderboard is public. Do not upload secrets or `data/` to GitHub.

Docs: [Kash public leaderboard](https://docs.kash.bot/developer-docs/public-embed-api/endpoints/market-leaderboard) · [Kash public market state](https://docs.kash.bot/developer-docs/public-embed-api/endpoints/markets-state)


## Kash Hub — compact menus and read-only extensions

**Main screen:** /start and /menu open a tidy four-section menu. Telegram callbacks edit the same menu message in place when possible, rather than continually sending new menus. Existing alerts and commands remain available.

- **Market Analytics** (/analytics): top 24-hour USDC-volume markets (separate from the lifetime /top list), biggest probability moves over 15m/60m/24h, categories, participant counts, and a resolved-markets preview. Price movements need their requested history interval to elapse after deployment. Cached public market details refresh at most every 10 minutes.
- **Whale and Trader Watchlists** (/whales, /watch): the existing whale scanner works as before. The Follow Trader button on Whale Alerts (when a valid public UUID exists) lets a user follow up to ten public profiles, with tracked investment increases of at least $5. The API only exposes top-50 positions per market, snapshots may lag, and accounts may be automated.
- **Saved Markets** (/watch): save up to 12 active markets directly from Analytics and revisit or remove them.
- **Kash News** (/news): official Kash blog RSS headlines (https://blog.kash.bot/feed.xml) with a 30-minute cache. Automatic alerts are opt-in and silently baseline existing headlines. X and Discord are linked but never scraped.
- **About Kash** (/about): overview, project guide, team, official URLs, public funding announcement and investor list. Kash announced a total $2 million pre-seed on 24 February 2026; individual investments are not verified. Roles may change; the official team page is linked.
- **Alerts & Filters** (/settings): existing 15/30/60-minute closing, volume, activity and Whale settings remain accessible. Optional blog alerts, new-market alerts and a daily digest at 09:00 UTC are disabled by default. New-market alerts learn a first baseline silently and notify on newly discovered tradeable markets only.
- **Recent Resolutions** (/results): on-demand cached public resolved-market results.

New modules use only Python standard library; no wallet or trading permissions. State is persisted in existing STATE_FILE with bounded 25-hour / 5-minute probability history (up to 250 active markets). News and results are cached. External text is HTML-escaped; menu callback IDs respect Telegram's 64-byte limit.

**UI accuracy:** Branded images shown in design mockups are aspirational. Native Telegram inline buttons cannot be arbitrarily colored or animated. These features use actual inline keyboards, HTML-formatted messages and in-place editing. A fully custom animated dashboard would require a Telegram Mini App, not just a chat bot.

**Quote / price impact:** An exact trade price-impact simulator requires an extra Kash markets:quote API scope. It is intentionally not enabled on the current read-only key.

**Safe FadeHost rollout:** Download a fresh backup of /data/state.json before redeploy. Install latest main with one Telegram polling worker using Redeploy (pull latest). Test /menu, /settings, /whales, /whalestatus, /analytics, /news, /about, /watch and /results. Keep the previous working deployment available for rollback.
