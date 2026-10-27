# Verdigo Kash Alerts v0.3 — Local test and deployment

## Local Windows test
1. Download and extract the repository ZIP.
2. Double-click START_LOCAL.cmd (needs Python 3.11+ and built-in Tkinter).
3. Enter rotated Telegram BotFather token and Kash API key with **only markets:read** scope in masked dialogs.
4. Open https://t.me/VerdigoKashAlertsBot, send /start, /status, /top.
5. Leave CMD open; closing it stops the bot. Secrets are passed only as process environment and not persisted.

## Verified Kash API contract
- Authenticated GET https://api.kash.bot/v1/markets, X-API-Key, X-Kash-Api-Version 2026-08-19.
- GET list returns { data: [markets], pagination: { cursor, hasMore, limit }, _meta }.
- Market fields: id, title, status, tradeable, freezeAt. Only tradeable markets with a freezeAt are monitored.
- Direct market URLs: https://app.kash.bot/markets/<UUID>.
- REST market-list endpoint has no volume fields. Public read-only endpoint https://app.kash.bot/api/markets/state?ids=<comma separated UUIDs> returns totalVolume in atomic USDC (6 decimal places). Uses at most 200 IDs per request. If it fails, closing alerts continue.
- Local authenticated HTTP 200 and five returned markets were confirmed by the project owner on October 27, 2026. Live Telegram delivery and public volume endpoint still require end-to-end verification.

## 24/7 hosting (not yet deployed)
- One continuously running instance only, as Telegram long polling conflicts with multiple workers.
- Environment variables TELEGRAM_BOT_TOKEN and KASH_API_KEY are **host secrets**; never store them in source control.
- Mount persistent private storage to /app/data or set STATE_FILE to a persistent path. Contains subscriber chat IDs/settings.
- Railway/Render background workers may require payment; Render free sleeping web services do not guarantee timed alerts.
- Check rate limiting and backoff in production; this is a beta, not a production SLA.
- The bot never trades, accesses wallets, or calls write endpoints.

For now, use START_LOCAL.cmd to verify Telegram /start and /status before renting any cloud server.
