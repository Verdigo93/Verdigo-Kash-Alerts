"""Verdigo Kash Alerts v0.4 — English-only, multi-user Telegram alerts.
Python 3.11+; standard library only. No trading endpoints or wallet access.
"""
import datetime as dt
import html
import json
import logging
import os
import pathlib
import time
import urllib.error
import urllib.parse
import urllib.request

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
KASH_API = os.environ.get("KASH_MARKETS_API", "https://api.kash.bot/v1/markets").strip()
KASH_KEY = os.environ.get("KASH_API_KEY", "").strip()
STATE = pathlib.Path(os.environ.get("STATE_FILE", "data/state.json"))
POLL = max(60, int(os.environ.get("POLL_SECONDS", "60")))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

def http_json(url, params=None, payload=None, headers=None):
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    h = {"Accept": "application/json", "User-Agent": "VerdigoKashAlerts/0.4"}
    if body is not None:
        h["Content-Type"] = "application/json"
    h.update(headers or {})
    req = urllib.request.Request(url, data=body, headers=h)
    with urllib.request.urlopen(req, timeout=25) as response:
        return json.load(response)

def telegram(method, data):
    return http_json("https://api.telegram.org/bot" + TOKEN + "/" + method, payload=data)

def defaults():
    return {"thresholds": [15, 30, 60], "volume": True, "activity": True,
            "min_volume": 10000, "paused": False}

def load():
    try:
        data = json.loads(STATE.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("users"), dict):
            return data
    except (OSError, ValueError):
        pass
    return {"users": {}, "sent": {}, "history": {}, "offset": 0}

def save(state):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    tmp.replace(STATE)

def user(state, chat_id):
    return state["users"].setdefault(str(chat_id), defaults())

def timestamp(value):
    if isinstance(value, (int, float)):
        return value / 1000 if value > 1e11 else float(value)
    if isinstance(value, str):
        try:
            return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None

def numeric(value):
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None

def normalize(item):
    market_id = str(item.get("id") or item.get("marketId") or "").strip()
    title = str(item.get("title") or item.get("question") or "").strip()
    close = None
    for field in ("freezeAt", "freeze_at", "tradingEndAt", "trading_end_at"):
        close = timestamp(item.get(field))
        if close is not None:
            break
    volume = None
    for field in ("volume24h", "volume_24h", "totalVolume", "total_volume", "volume"):
        volume = numeric(item.get(field))
        if volume is not None:
            break
    url = next((item[k] for k in ("url", "marketUrl", "market_url", "shareUrl")
                if isinstance(item.get(k), str) and item[k]), None)
    if url and url.startswith("/"):
        url = "https://app.kash.bot" + url
    parsed = urllib.parse.urlparse(url or "")
    if parsed.scheme != "https" or parsed.netloc != "app.kash.bot" or not parsed.path.startswith("/markets/"):
        url = None
    # Kash market pages use /markets/<UUID>. Construct a link only for a valid UUID.
    if url is None and market_id:
        import uuid
        try:
            market_uuid = uuid.UUID(market_id)
            if str(market_uuid) == market_id.lower():
                url = "https://app.kash.bot/markets/" + str(market_uuid)
        except ValueError:
            pass
    return {"id": market_id, "title": title, "close": close, "volume": volume,
            "url": url, "status": str(item.get("status") or "").upper(),
            "tradeable": item.get("tradeable") is True}

def fetch_markets():
    if not KASH_KEY:
        raise ValueError("KASH_API_KEY is required. Set it as a secret environment variable.")
    headers = {"X-API-Key": KASH_KEY, "X-Kash-Api-Version": "2026-08-19"}
    result = {}
    cursor = None
    for page in range(100):
        params = {"status": "ACTIVE", "limit": 100}
        if cursor:
            params["cursor"] = cursor
        data = http_json(KASH_API, params=params, headers=headers)
        if isinstance(data, list):
            rows, pagination = data, {}
        elif isinstance(data, dict):
            rows = next((data[k] for k in ("markets", "items", "results", "data")
                         if isinstance(data.get(k), list)), None)
            if rows is None and isinstance(data.get("data"), dict):
                rows = data["data"].get("markets") or data["data"].get("items")
            pagination = data.get("pagination") or {}
        else:
            raise ValueError("Unrecognized Kash API response")
        if not isinstance(rows, list):
            raise ValueError("No market list in Kash response; verify KASH_MARKETS_API")
        for raw in rows:
            if not isinstance(raw, dict):
                continue
            m = normalize(raw)
            if m["id"] and m["title"] and m["tradeable"] and m["close"] is not None:
                result[m["id"]] = m
        new_cursor = pagination.get("cursor")
        if not pagination.get("hasMore"):
            break
        if not new_cursor or new_cursor == cursor:
            raise ValueError("Incomplete Kash pagination: next cursor missing or repeated")
        cursor = new_cursor
    else:
        raise ValueError("Market pagination exceeded 100 pages; refusing partial scan")
    enrich_with_market_state(result)
    return result

def enrich_with_market_state(markets):
    """Fetch live USDC volumes from the documented public embed API in batches.
    Kash REST /v1/markets contains lifecycle data but no total volume field.
    Public state volume is USDC atomic-6, not whole USDC.
    Failures must not prevent closing-time alerts.
    """
    ids = list(markets)
    for start in range(0, len(ids), 200):
        batch = ids[start:start + 200]
        try:
            result = http_json("https://app.kash.bot/api/markets/state",
                               params={"ids": ",".join(batch)})
            if not isinstance(result, dict) or not isinstance(result.get("markets"), list):
                raise ValueError("Invalid public market-state response")
            for raw in result["markets"]:
                if not isinstance(raw, dict):
                    continue
                mid = raw.get("id")
                if mid not in markets:
                    continue
                atomic_volume = numeric(raw.get("totalVolume"))
                if atomic_volume is not None and atomic_volume >= 0:
                    markets[mid]["volume"] = atomic_volume / 1_000_000
        except Exception as exc:
            logging.warning("Volume enrichment unavailable (closing alerts still work): %s", exc)

def send(chat, message, market=None, keyboard=None):
    data = {"chat_id": chat, "text": message, "parse_mode": "HTML",
            "disable_web_page_preview": True}
    if market and market.get("url"):
        data["reply_markup"] = {"inline_keyboard": [[
            {"text": "🔗 View Market on Kash", "url": market["url"]}]]}
    elif keyboard:
        data["reply_markup"] = {"inline_keyboard": keyboard}
    telegram("sendMessage", data)

def settings_keyboard(cfg):
    return [
        [{"text": ("✅" if n in cfg["thresholds"] else "⬜") + f" {n} min",
          "callback_data": f"toggle:{n}"} for n in (15, 30, 60)],
        [{"text": ("✅" if cfg["volume"] else "⬜") + " High Volume", "callback_data": "toggle:volume"}],
        [{"text": ("✅" if cfg["activity"] else "⬜") + " Unusual Activity", "callback_data": "toggle:activity"}],
        [{"text": "▶️ Resume" if cfg["paused"] else "⏸ Pause", "callback_data": "toggle:pause"}],
        [{"text": "⏰ Next Closings", "callback_data": "soon"}],
        [{"text": "📊 Top Markets", "callback_data": "top"}],
    ]

def show_settings(chat, state):
    cfg = user(state, chat)
    send(chat, "⚙️ <b>Verdigo Kash Alerts — Settings</b>\n\n"
         "Choose your closing alerts and market activity notifications.\n"
         f"Minimum reported volume: {cfg['min_volume']:,.0f}\n"
         "Change minimum with /minvolume 10000\n\n"
         "Alerts are informational, not trading advice.",
         keyboard=settings_keyboard(cfg))

def market_message(m, header, details):
    return f"{header}\n\n<b>{html.escape(m['title'])}</b>\n{details}"

def top_markets(chat, markets):
    ranked = sorted((m for m in markets.values() if m["url"] and m["volume"] is not None),
                    key=lambda m: m["volume"], reverse=True)[:5]
    if not ranked:
        send(chat, "No verified market links and volume data are available yet.")
        return
    for m in ranked:
        send(chat, market_message(m, "📊 <b>Top Volume Market</b>",
                                  f"Reported volume: {m['volume']:,.0f}"), m)

def next_closings(chat, markets, now=None):
    """Show the nearest real trade-freeze times, without false alerts."""
    now = time.time() if now is None else now
    upcoming = sorted(
        (m for m in markets.values() if m.get("close") is not None
         and m["close"] > now and m.get("url")),
        key=lambda m: m["close"],
    )
    if not upcoming:
        send(chat, "⏰ No upcoming trade freezes are currently available.")
        return
    within_two_hours = [m for m in upcoming if m["close"] - now <= 7200]
    if not within_two_hours:
        minutes = max(1, round((upcoming[0]["close"] - now) / 60))
        send(chat, f"⏰ No markets freeze within the next 2 hours.\n"
             f"Next market freezes in about {minutes} minutes.")
        return
    for m in within_two_hours[:5]:
        minutes = max(1, round((m["close"] - now) / 60))
        send(chat, market_message(m, "⏰ <b>Upcoming Trade Freeze</b>",
                                  f"Time until trading stops: about {minutes} min\n"
                                  "(Manual preview — not an automatic alert)"), m)


def command(chat, text, state, markets):
    name = text.strip().split()[0].split("@")[0].lower()
    cfg = user(state, chat)
    if name == "/start":
        send(chat, "👋 <b>Welcome to Verdigo Kash Alerts!</b>\n\n"
             "Free Kash market monitoring: closing alerts, high volume and activity spikes.\n"
             "No wallet or trading API key required.")
        show_settings(chat, state)
    elif name in ("/settings", "/help"):
        show_settings(chat, state)
    elif name in ("/15", "/30", "/60"):
        n = int(name[1:])
        cfg["thresholds"] = sorted(set(cfg["thresholds"]) ^ {n})
        show_settings(chat, state)
    elif name in ("/volume", "/activity"):
        key = "volume" if name == "/volume" else "activity"
        cfg[key] = not cfg[key]
        show_settings(chat, state)
    elif name in ("/pause", "/resume"):
        cfg["paused"] = name == "/pause"
        show_settings(chat, state)
    elif name == "/minvolume":
        try:
            value = int(text.split()[1])
            if not 0 <= value <= 1000000000:
                raise ValueError()
            cfg["min_volume"] = value
            show_settings(chat, state)
        except (IndexError, ValueError):
            send(chat, "Usage: /minvolume 10000")
    elif name == "/top":
        top_markets(chat, markets)
    elif name == "/soon":
        next_closings(chat, markets)
    elif name == "/status":
        send(chat, f"📡 <b>Monitoring Status</b>\n"
             f"Markets in latest scan: {len(markets)}\n"
             f"Scan interval: {POLL} seconds\n"
             f"Alerts: {'paused' if cfg['paused'] else 'active'}\n"
             "Closing alerts use the trade-freeze time from Kash.")

def toggle(chat, action, state, markets):
    cfg = user(state, chat)
    if action in ("15", "30", "60"):
        n = int(action)
        cfg["thresholds"] = sorted(set(cfg["thresholds"]) ^ {n})
    elif action in ("volume", "activity"):
        cfg[action] = not cfg[action]
    elif action == "pause":
        cfg["paused"] = not cfg["paused"]
    elif action == "top":
        top_markets(chat, markets)
        return
    elif action == "soon":
        next_closings(chat, markets)
        return
    show_settings(chat, state)

def scan(state, markets, now):
    for chat, cfg in list(state["users"].items()):
        if cfg.get("paused"):
            continue
        for m in markets.values():
            if not m["url"]:
                continue  # Never invent a direct market URL.
            prefix = chat + ":" + m["id"]
            if m["close"] is not None:
                remaining = (m["close"] - now) / 60
                # Catch up on missed scan windows without issuing multiple stale
                # threshold alerts: pick the closest configured threshold.
                eligible = sorted(t for t in set(cfg["thresholds"])
                                  if 0 < remaining <= t)
                if eligible:
                    threshold = eligible[0]
                    event = f"{prefix}:closing:{threshold}"
                    if event not in state["sent"]:
                        send(chat, market_message(m, "⏰ <b>Market Closing Soon!</b>",
                             f"Time remaining: {max(1, round(remaining))} min\n"
                             f"Alert: {threshold} minutes"), m)
                        # Larger alerts have already been missed: do not send
                        # them later after a restart or a brief API outage.
                        for t in eligible:
                            state["sent"][f"{prefix}:closing:{t}"] = now
            old = state["history"].get(m["id"])
            if (cfg["volume"] and old and m["volume"] is not None and
                    old["volume"] < cfg["min_volume"] <= m["volume"]):
                event = f"{prefix}:volume:{cfg['min_volume']}"
                if event not in state["sent"]:
                    send(chat, market_message(m, "💰 <b>High Volume Market</b>",
                         f"Reported volume: {m['volume']:,.0f}"), m)
                    state["sent"][event] = now
            if cfg["activity"] and old and m["volume"] is not None:
                age = now - old["at"]
                delta = m["volume"] - old["volume"]
                if 300 <= age <= 3600 and old["volume"] >= 100 and delta >= max(500, old["volume"] * 1.5):
                    event = f"{prefix}:spike:{int(now // 3600)}"
                    if event not in state["sent"]:
                        send(chat, market_message(m, "🔥 <b>Unusual Volume Increase</b>",
                             f"Volume increase since previous snapshot: +{delta:,.0f}"), m)
                        state["sent"][event] = now
    # Update history once per scan, not once per user.
    for m in markets.values():
        if m["volume"] is not None:
            old = state["history"].get(m["id"])
            if old is None or now - old["at"] >= 300:
                state["history"][m["id"]] = {"volume": m["volume"], "at": now}
    state["sent"] = {k: v for k, v in state["sent"].items() if now - v < 3 * 86400}
    state["history"] = {k: v for k, v in state["history"].items() if now - v["at"] < 2 * 86400}

def main():
    if not TOKEN:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN on your hosting platform. Never commit it.")
    state = load()
    markets = {}
    last_scan = 0
    logging.info("Verdigo Kash Alerts started")
    while True:
        now = time.time()
        if now - last_scan >= POLL:
            try:
                fresh = fetch_markets()
                markets = fresh
                scan(state, markets, now)
                logging.info("Fetched %d markets; %d subscribers", len(markets), len(state["users"]))
            except Exception as exc:
                logging.error("Market scan failed: %s", exc)
            last_scan = now
            save(state)
        try:
            result = telegram("getUpdates", {"offset": state["offset"], "timeout": 15,
                                             "allowed_updates": ["message", "callback_query"]})
            for update in result.get("result", []):
                state["offset"] = max(state["offset"], update["update_id"] + 1)
                message = update.get("message") or {}
                chat = (message.get("chat") or {}).get("id")
                if chat and str(message.get("text", "")).startswith("/"):
                    command(chat, message["text"], state, markets)
                callback = update.get("callback_query") or {}
                if callback:
                    telegram("answerCallbackQuery", {"callback_query_id": callback["id"]})
                    cb_chat = ((callback.get("message") or {}).get("chat") or {}).get("id")
                    if cb_chat and callback.get("data", "").startswith("toggle:"):
                        toggle(cb_chat, callback["data"].split(":", 1)[1], state, markets)
                    elif cb_chat and callback.get("data") == "top":
                        top_markets(cb_chat, markets)
            save(state)
        except Exception as exc:
            logging.error("Telegram polling error: %s", exc)
            time.sleep(5)

if __name__ == "__main__":
    main()
