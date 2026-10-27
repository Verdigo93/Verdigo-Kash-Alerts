# Verdigo Kash Alerts v0.5 — Local test and deployment

## Local Windows test
1. Download and extract the repository ZIP.
2. Double-click START_LOCAL.cmd (needs Python 3.11+ and built-in Tkinter).
3. Enter rotated Telegram BotFather token and Kash API key with **only markets:read** scope in masked dialogs.
4. Open https://t.me/VerdigoKashAlertsBot, send /start, /settings, /soon, /top. Use the Volume Filter button for presets and custom ranges.
5. Leave CMD open; closing it stops the bot. Secrets are passed only as process environment and not persisted.

## Verified Kash API contract
- Authenticated GET https://api.kash.bot/v1/markets, X-API-Key, X-Kash-Api-Version 2026-08-19.
- GET list returns { data: [markets], pagination: { cursor, hasMore, limit }, _meta }.
- Market fields: id, title, status, tradeable, freezeAt. Only tradeable markets with a freezeAt are monitored.
- Direct market URLs: https://app.kash.bot/markets/<UUID>.
- REST market-list endpoint has no volume fields. Public read-only endpoint https://app.kash.bot/api/markets/state?ids=<comma separated UUIDs> returns totalVolume in atomic USDC (6 decimal places). Uses at most 200 IDs per request. If it fails, closing alerts continue.
- Local authenticated HTTP 200 and five returned markets were confirmed by the project owner on October 27, 2026. The owner also confirmed receiving a real automated Telegram freeze-time notification and opening linked markets. Volume range UI in v0.5 still requires manual verification.

## Altare / Pterodactyl Python hosting (private test setup)

1. Use the **Generic - Python** image. Place the latest `bot.py` inside `/home/container/`.
2. In Startup > Variables, set `PY_FILE` to `bot.py`. Leave the default startup shell command unchanged.
3. In the server file manager, create `data/`. Add `data/secrets.json` **privately on the server**, with the following two keys (replace placeholders in the private editor, not in GitHub or chat):
   ```json
   {
     "TELEGRAM_BOT_TOKEN": "REPLACE_WITH_PRIVATE_BOTFATHER_TOKEN",
     "KASH_API_KEY": "REPLACE_WITH_PRIVATE_KASH_MARKETS_READ_KEY"
   }
   ```
4. Stop the previous local Telegram bot before moving to the cloud (only one polling process per token). Copy the latest local `data/state.json` to server `data/state.json` so subscribers/settings/dedup history persist. Never put that file in GitHub.
5. Start the server and verify the log prints a market count and subscriber count; test `/ping` and `/settings` in Telegram. The token is not printed in the logs.
6. Keep `data/` persistent across host restarts/reinstalls; enable backups where possible. Hosting admins can access files on their infrastructure, so use dedicated, least-privilege credentials and rotate if the host cannot be trusted.

Environment variables `TELEGRAM_BOT_TOKEN` and `KASH_API_KEY` take priority over private `data/secrets.json`. Never paste secrets into the public repo, command line, screenshots, or chat. The file is loaded by `bot.py` using only the standard library; no pip packages are needed.

## 24/7 hosting (not yet deployed)
- One continuously running instance only, as Telegram long polling conflicts with multiple workers.
- Environment variables TELEGRAM_BOT_TOKEN and KASH_API_KEY are **host secrets**; never store them in source control.
- Mount persistent private storage to /app/data or set STATE_FILE to a persistent path. Contains subscriber chat IDs/settings.
- Railway/Render background workers may require payment; Render free sleeping web services do not guarantee timed alerts.
- Check rate limiting and backoff in production; this is a beta, not a production SLA.
- The bot never trades, accesses wallets, or calls write endpoints.

## Volume filter behavior
- Per-subscriber Volume Filter inline keyboard: preset under $10, $10–$100, $100+, $1,000+, $10,000+, all, or custom.
- Custom amount may be entered in a normal Telegram text message: 100, <10, 10-100, 100+ (USDC). No slash command necessary.
- Applies to *total lifetime reported volume* of the **whole market** in USDC, not individual trade sizes.
- Only volume alerts and the matching-market preview are filtered; trading-freeze alerts (60/30/15min) remain unchanged.
- On the initial successful scan, preexisting market volumes are stored as a baseline, so changing the filter does not flood the user with historic alerts. New markets and changes entering the chosen volume range can trigger volume alerts (up to five per scan per user).
- User settings live in data/state.json. To switch versions on one PC, stop the old process, **copy data folder** into the new directory, then start exactly one process with START_LOCAL.cmd. Do not upload data/state.json to GitHub.

For now, use START_LOCAL.cmd to verify Telegram /start, Volume Filter, and /soon before renting any cloud server.
