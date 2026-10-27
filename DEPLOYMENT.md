# Verdigo Kash Alerts v0.2 — Deployment

## What works in the code
- English Telegram /start, /settings, /top, /status, /pause, /resume.
- Inline settings buttons for 15/30/60 minute alerts, high volume and activity.
- Independent subscriber settings, alert deduplication, persistent JSON state.
- Single shared Kash market scan; never requests user wallet or API credentials.
- Direct market link buttons ONLY if Kash returns an actual app.kash.bot URL.

## Blocking verification before a public launch
The configured Kash endpoint is a **placeholder pending real API verification**. Confirm the list endpoint, authentication requirements, pagination, whether volume is USD or base units, which timestamp is **last tradable time** (freezeAt vs resolution), and a real per-market URL. Until then, the bot may run but may not send any market alerts. No data is fabricated.

## Hosting
1. Deploy as a single continuously running Docker worker (Railway or a VPS); not a sleeping web service.
2. In host secret environment settings set TELEGRAM_BOT_TOKEN to your **rotated** BotFather token. Never commit it.
3. Set KASH_MARKETS_API to the **verified** market-list endpoint. Set KASH_API_KEY only if necessary, with read-only permission.
4. Mount persistent storage at /app/data; use one replica only to avoid duplicate Telegram long-pollers.
5. Run and check logs; open https://t.me/VerdigoKashAlertsBot and send /start then /status.
6. Do not invite the public until live market link, close time, and volume semantics have been tested.

## Security and reliability
Do not store any secrets in GitHub. State file contains Telegram chat IDs and should stay on the private server. Use backups and retention limits. Telegram token was exposed in an earlier chat and must remain revoked. This project does not trade or connect user accounts.
