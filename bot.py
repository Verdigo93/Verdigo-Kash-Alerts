"""Verdigo Kash Alerts v0.8 — English-only, multi-user Telegram alerts.
Python 3.11+; standard library only. No trading endpoints or wallet access.
"""
import datetime as dt
import html
import json
import logging
import os
import pathlib
import re
import time
import urllib.error
import urllib.parse
import urllib.request

def load_private_credentials(path=None):
    """Optional private config for hosts that cannot add arbitrary env vars.

    Store data/secrets.json only on the private host, never in the Git repository.
    Normal environment variables take priority over this file.
    """
    path = pathlib.Path(path or os.environ.get("ALERTS_SECRETS_FILE",
                                             "data/secrets.json"))
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        raise SystemExit("Private credentials file is unreadable or invalid JSON.") from exc
    if not isinstance(cfg, dict):
        raise SystemExit("Private credentials file must contain a JSON object.")
    return cfg


_PRIVATE = load_private_credentials()
TOKEN = str(os.environ.get("TELEGRAM_BOT_TOKEN") or
            _PRIVATE.get("TELEGRAM_BOT_TOKEN") or "").strip()
KASH_API = os.environ.get("KASH_MARKETS_API", "https://api.kash.bot/v1/markets").strip()
KASH_KEY = str(os.environ.get("KASH_API_KEY") or
               _PRIVATE.get("KASH_API_KEY") or "").strip()
STATE = pathlib.Path(os.environ.get("STATE_FILE", "data/state.json"))
POLL = max(60, int(os.environ.get("POLL_SECONDS", "60")))
_LAST_CHAT_SEND = {}
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

def http_json(url, params=None, payload=None, headers=None):
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    h = {"Accept": "application/json", "User-Agent": "VerdigoKashAlerts/0.8"}
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
            "min_volume": 10000, "max_volume": None, "paused": False,
            "top_limit": 5}

def load():
    try:
        data = json.loads(STATE.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("users"), dict):
            return data
    except (OSError, ValueError):
        pass
    return {"users": {}, "sent": {}, "history": {}, "offset": 0,
            "seen_volume_markets": {}, "volume_baseline_ready": False}

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
    # Telegram may throttle several sendMessage requests to the same chat.
    # Pace notifications and matching-market lists to reduce HTTP 429 risk.
    chat_key = str(chat)
    next_allowed = _LAST_CHAT_SEND.get(chat_key, 0.0)
    remaining = next_allowed - time.monotonic()
    if remaining > 0:
        time.sleep(remaining)
    data = {"chat_id": chat, "text": message, "parse_mode": "HTML",
            "disable_web_page_preview": True}
    if market and market.get("url"):
        data["reply_markup"] = {"inline_keyboard": [
            [{"text": "🔗 View Market on Kash", "url": market["url"]}],
            [{"text": "🏠 Main Menu", "callback_data": "menu"}]]}
    elif keyboard:
        data["reply_markup"] = {"inline_keyboard": keyboard}
    telegram("sendMessage", data)
    _LAST_CHAT_SEND[chat_key] = time.monotonic() + 1.1


def volume_matches(volume, cfg):
    """Match reported *total market volume* in USDC, not individual bet size."""
    if volume is None:
        return False
    minimum = cfg.get("min_volume", 10000)
    maximum = cfg.get("max_volume")
    return volume >= minimum and (maximum is None or volume < maximum)


def volume_label(cfg):
    minimum = cfg.get("min_volume", 10000)
    maximum = cfg.get("max_volume")

    def fmt(value):
        return f"{value:,.2f}".rstrip("0").rstrip(".") if isinstance(value, float) else f"{value:,}"

    if maximum is None:
        return "All volumes" if minimum == 0 else f"From ${fmt(minimum)} USDC"
    if minimum == 0:
        return f"Under ${fmt(maximum)} USDC"
    return f"${fmt(minimum)}–${fmt(maximum)} USDC"


def volume_keyboard():
    return [
        [{"text": "⬇️ Under $10", "callback_data": "vol:under10"},
         {"text": "💵 $10–$100", "callback_data": "vol:10to100"}],
        [{"text": "📈 $100+", "callback_data": "vol:100plus"},
         {"text": "🚀 $1,000+", "callback_data": "vol:1000plus"}],
        [{"text": "💎 $10,000+", "callback_data": "vol:10000plus"},
         {"text": "🌐 All volumes", "callback_data": "vol:all"}],
        [{"text": "✏️ Enter custom amount", "callback_data": "vol:custom"}],
        [{"text": "🔎 Show matching markets", "callback_data": "vol:show"}],
        [{"text": "◀️ Back to Settings", "callback_data": "vol:back"}],
    ]


def show_volume_menu(chat, state):
    cfg = user(state, chat)
    send(chat,
         "💵 <b>Market Volume Filter</b>\n\n"
         f"Current: <b>{html.escape(volume_label(cfg))}</b>\n\n"
         "Choose a range or enter your own amount. "
         "This filters market-volume notifications and the "
         "🔎 Show matching markets list.\n"
         "⏰ Closing-time alerts are <b>not</b> filtered.\n\n"
         "Volume means the market's total reported trading volume in USDC, "
         "not the size of one trade.",
         keyboard=volume_keyboard())


def volume_markets(chat, state, markets):
    cfg = user(state, chat)
    selected = sorted(
        (m for m in markets.values() if m.get("url") and volume_matches(m.get("volume"), cfg)),
        key=lambda m: m["volume"], reverse=True,
    )
    if not selected:
        send(chat, f"🔎 No active markets currently match {html.escape(volume_label(cfg))}.")
        return
    send(chat, f"🔎 <b>Markets: {html.escape(volume_label(cfg))}</b>\n"
         f"Matches: {len(selected)} | Showing up to 5:")
    for m in selected[:5]:
        send(chat, market_message(m, "💵 <b>Matching Market</b>",
                                  f"Total volume: ${m['volume']:,.2f} USDC"), m)


def parse_volume_range(raw):
    """Accepted examples: 100, 100+, >100, <10, 10-100, all."""
    value = raw.strip().lower().replace("usdc", "").replace("$", "").replace(",", "").replace(" ", "")
    if value == "all":
        return 0, None
    if re.fullmatch(r"\d+(?:\.\d+)?-\d+(?:\.\d+)?", value):
        parts = value.split("-")
        minimum, maximum = float(parts[0]), float(parts[1])
        if not 0 <= minimum < maximum <= 1_000_000_000:
            raise ValueError("The range must have a larger maximum (up to 1B USDC).")
        return minimum, maximum
    if re.fullmatch(r"<\d+(?:\.\d+)?", value):
        maximum = float(value[1:])
        if not 0 < maximum <= 1_000_000_000:
            raise ValueError("The maximum must be above zero.")
        return 0, maximum
    if not re.fullmatch(r">?\d+(?:\.\d+)?\+?", value):
        raise ValueError("Use 100, 100+, <10, 10-100 or all.")
    minimum = float(value.strip(">+"))
    if not 0 <= minimum <= 1_000_000_000:
        raise ValueError("Amount must be between 0 and 1B USDC.")
    return minimum, None


def handle_volume_reply(chat, message, state):
    cfg = user(state, chat)
    if not cfg.get("awaiting_volume"):
        return False
    if message.strip().lower() in ("cancel", "/cancel"):
        cfg["awaiting_volume"] = False
        show_volume_menu(chat, state)
        return True
    try:
        minimum, maximum = parse_volume_range(message)
    except ValueError as exc:
        send(chat, f"❌ {html.escape(str(exc))}\n"
             "Try: 100, 100+, &lt;10 or 10-100. Send cancel to exit.")
        return True
    cfg["min_volume"] = minimum
    cfg["max_volume"] = maximum
    cfg["awaiting_volume"] = False
    send(chat, f"✅ Volume filter saved: {html.escape(volume_label(cfg))}")
    show_volume_menu(chat, state)
    return True


def volume_action(chat, action, state, markets):
    cfg = user(state, chat)
    presets = {
        "under10": (0, 10),
        "10to100": (10, 100),
        "100plus": (100, None),
        "1000plus": (1000, None),
        "10000plus": (10000, None),
        "all": (0, None),
    }
    if action in presets:
        cfg["min_volume"], cfg["max_volume"] = presets[action]
        cfg["awaiting_volume"] = False
        send(chat, f"✅ Volume filter saved: {html.escape(volume_label(cfg))}")
        show_volume_menu(chat, state)
    elif action == "custom":
        cfg["awaiting_volume"] = True
        send(chat,
             "✏️ <b>Enter market volume (USDC)</b>\n\n"
             "Just send a normal message, for example:\n"
             "• <code>100</code> — from 100 USDC\n"
             "• <code>&lt;10</code> — under 10 USDC\n"
             "• <code>10-100</code> — 10 to under 100 USDC\n"
             "• <code>100+</code> — from 100 USDC\n\n"
             "Send <code>cancel</code> to return. No slash commands needed.")
    elif action == "show":
        volume_markets(chat, state, markets)
    elif action == "back":
        cfg["awaiting_volume"] = False
        show_settings(chat, state)
    elif action == "menu":
        show_volume_menu(chat, state)


def settings_keyboard(cfg):
    return [
        [{"text": ("✅" if n in cfg["thresholds"] else "⬜") + f" {n} min",
          "callback_data": f"toggle:{n}"} for n in (15, 30, 60)],
        [{"text": ("✅" if cfg["volume"] else "⬜") + " Volume Alerts", "callback_data": "toggle:volume"}],
        [{"text": "💵 Volume Filter", "callback_data": "vol:menu"}],
        [{"text": ("✅" if cfg["activity"] else "⬜") + " Unusual Activity", "callback_data": "toggle:activity"}],
        [{"text": "▶️ Resume" if cfg["paused"] else "⏸ Pause", "callback_data": "toggle:pause"}],
        [{"text": "⏰ Next Closings", "callback_data": "soon"}],
        [{"text": "📊 Top Markets", "callback_data": "top"}],
    ]

def show_settings(chat, state):
    cfg = user(state, chat)
    send(chat, "⚙️ <b>Verdigo Kash Alerts — Settings</b>\n\n"
         "Choose your closing alerts and market activity notifications.\n"
         f"Volume range: {html.escape(volume_label(cfg))}\n"
         "Change it using 💵 Volume Filter.\n\n"
         "Alerts are informational, not trading advice.",
         keyboard=settings_keyboard(cfg))

def market_message(m, header, details):
    """Emphasize the market question with safe HTML and readable spacing."""
    return f"{header}\n\n📌 <b>{html.escape(m['title'])}</b>\n\n{details}"

TOP_LIMITS = (5, 10, 15, 20)
TOP_PAGE_SIZE = 5


def top_size_keyboard(selected):
    return [
        [{"text": ("✅ " if n == selected else "") + f"Top {n}",
          "callback_data": f"top:set:{n}"} for n in (5, 10)],
        [{"text": ("✅ " if n == selected else "") + f"Top {n}",
          "callback_data": f"top:set:{n}"} for n in (15, 20)],
        [{"text": "🏠 Main Menu", "callback_data": "menu"}],
    ]


def edit_bot_message(chat, message_id, text, keyboard):
    """Replace an existing Telegram result in-place instead of spamming chats."""
    telegram("editMessageText", {
        "chat_id": chat,
        "message_id": message_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "reply_markup": {"inline_keyboard": keyboard},
    })


def top_menu(chat, state, message_id=None):
    cfg = user(state, chat)
    selected = cfg.get("top_limit", 5)
    if selected not in TOP_LIMITS:
        selected = 5
    text = ("📊 <b>Top Markets by Volume</b>\n\n"
            f"Choose how many markets to see (current: Top {selected}).\n"
            "Results are shown 5 at a time so your chat stays clean.\n"
            "Volume is total reported market volume in USDC.")
    keyboard = top_size_keyboard(selected)
    if message_id is not None:
        edit_bot_message(chat, message_id, text, keyboard)
    else:
        send(chat, text, keyboard=keyboard)


def top_page_content(markets, limit, page):
    """Create a bounded, clickable list of market rankings in one Telegram message."""
    if limit not in TOP_LIMITS:
        limit = 5
    ranked = sorted(
        (m for m in markets.values()
         if m.get("url") and m.get("volume") is not None),
        key=lambda m: m["volume"], reverse=True
    )[:limit]
    max_page = max(0, (len(ranked) - 1) // TOP_PAGE_SIZE)
    page = min(max(0, page), max_page)
    total_pages = max_page + 1
    if not ranked:
        text = ("📊 <b>Top Markets by Volume</b>\n\n"
                "No market volume data is available right now. Try again later.")
    else:
        start = page * TOP_PAGE_SIZE
        lines = []
        for pos, m in enumerate(ranked[start:start + TOP_PAGE_SIZE], start + 1):
            title = str(m.get("title") or "Untitled market")
            if len(title) > 135:
                title = title[:132] + "..."
            safe_title = html.escape(title)
            safe_url = html.escape(m["url"], quote=True)
            lines.append(f'{pos}. <a href="{safe_url}">{safe_title}</a>\n'
                         f"    💰 {m['volume']:,.2f} USDC")
        text = (f"📊 <b>Top {limit} Markets by Volume</b>\n"
                f"Showing {start + 1}–{start + len(lines)} of {len(ranked)} available "
                f"| Page {page + 1}/{total_pages}\n\n"
                + "\n\n".join(lines))
    nav = []
    if page > 0:
        nav.append({"text": "⬅️ Previous", "callback_data": f"top:page:{page - 1}"})
    if page < max_page:
        nav.append({"text": "Next ➡️", "callback_data": f"top:page:{page + 1}"})
    keyboard = []
    if nav:
        keyboard.append(nav)
    keyboard.append([{"text": "⚙️ Choose Top 5 / 10 / 15 / 20",
                      "callback_data": "top:choose"}])
    keyboard.append([{"text": "🏠 Main Menu", "callback_data": "menu"}])
    return text, keyboard


def top_page(chat, state, markets, page=0, message_id=None):
    cfg = user(state, chat)
    text, keyboard = top_page_content(markets, cfg.get("top_limit", 5), page)
    if message_id is not None:
        edit_bot_message(chat, message_id, text, keyboard)
    else:
        send(chat, text, keyboard=keyboard)


def top_action(chat, action, state, markets, message_id):
    cfg = user(state, chat)
    if action == "choose":
        top_menu(chat, state, message_id)
    elif action.startswith("set:"):
        count_text = action.split(":", 1)[1]
        if count_text in ("5", "10", "15", "20"):
            cfg["top_limit"] = int(count_text)
            top_page(chat, state, markets, 0, message_id)
    elif action.startswith("page:"):
        page_text = action.split(":", 1)[1]
        if page_text.isdigit() and len(page_text) <= 2:
            top_page(chat, state, markets, int(page_text), message_id)


def top_markets(chat, markets, state=None):
    """Compatibility for existing commands and old inline menus."""
    if state is None:
        state = {"users": {}}
    top_menu(chat, state)

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
                                  f"❗ <b>Time until trading stops: about {minutes} min</b> ❗\n\n"
                                  "<i>Manual preview — not an automatic alert</i>"), m)


def command(chat, text, state, markets):
    parts = text.strip().split()
    if not parts:
        return
    name = parts[0].split("@")[0].lower()
    cfg = user(state, chat)
    if name == "/start":
        send(chat, "👋 <b>Welcome to Verdigo Kash Alerts!</b>\n\n"
             "Free Kash market monitoring: closing alerts, high volume and activity spikes.\n"
             "No wallet or trading API key required.")
        show_settings(chat, state)
    elif name in ("/settings", "/help", "/menu", "/home"):
        cfg["awaiting_volume"] = False
        show_settings(chat, state)
    elif name == "/ping":
        send(chat, "🏓 Pong! Verdigo Kash Alerts is responding.",
             keyboard=[[{"text": "🏠 Main Menu", "callback_data": "menu"}]])
    elif name in ("/filter", "/volumerange"):
        show_volume_menu(chat, state)
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
            cfg["max_volume"] = None
            cfg["awaiting_volume"] = False
            show_settings(chat, state)
        except (IndexError, ValueError):
            send(chat, "Usage: /minvolume 10000")
    elif name == "/top":
        if len(parts) > 1 and parts[1] in ("5", "10", "15", "20"):
            cfg["top_limit"] = int(parts[1])
            top_page(chat, state, markets)
        else:
            top_menu(chat, state)
    elif name == "/markets":
        volume_markets(chat, state, markets)
    elif name == "/soon":
        next_closings(chat, markets)
    elif name == "/status":
        last_ok = numeric(state.get("last_market_success_at"))
        if last_ok is None:
            last_update = "No successful fetch recorded yet"
        else:
            elapsed = max(0, int((time.time() - last_ok) / 60))
            last_update = f"{elapsed} min ago"
        recent_error = state.get("last_market_error")
        api_health = ("OK" if not recent_error
                      else "Latest fetch failed: " + html.escape(str(recent_error)))
        send(chat, f"📡 <b>Monitoring Status</b>\n"
             f"Markets in latest successful scan: {len(markets)}\n"
             f"Last Kash data update: {last_update}\n"
             f"Kash API: {api_health}\n"
             f"Scan interval: {POLL} seconds\n"
             f"Alerts: {'paused' if cfg.get('paused') else 'active'}\n"
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
        top_menu(chat, state)
        return
    elif action == "soon":
        next_closings(chat, markets)
        return
    elif action in ("menu", "home"):
        cfg["awaiting_volume"] = False
    show_settings(chat, state)

def scan_subscriber(chat, cfg, state, markets, now, seen_volumes,
                    volume_baseline_ready):
    """Process alerts per subscriber so one blocked chat cannot affect others."""
    volume_alerts_this_scan = 0
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
                         f"❗ <b>Time remaining: {max(1, round(remaining))} min</b> ❗\n\n"
                         f"🔔 Alert: {threshold} minutes"), m)
                    # Larger alerts have already been missed: do not send
                    # them later after a restart or a brief API outage.
                    for t in eligible:
                        state["sent"][f"{prefix}:closing:{t}"] = now
        old = state["history"].get(m["id"])
        in_range = volume_matches(m["volume"], cfg)
        crossed_into_range = (old is not None and
                              not volume_matches(old["volume"], cfg) and in_range)
        newly_seen_matching = (volume_baseline_ready and
                               m["id"] not in seen_volumes and in_range)
        if (cfg.get("volume", True) and
                (crossed_into_range or newly_seen_matching) and
                volume_alerts_this_scan < 5):
            band = f"{cfg.get('min_volume',10000)}:{cfg.get('max_volume')}"
            event = f"{prefix}:volume:{band}"
            if event not in state["sent"]:
                send(chat, market_message(m, "💰 <b>Market Matches Your Volume Filter</b>",
                     f"Total volume: ${m['volume']:,.2f} USDC\n"
                     f"Your range: {html.escape(volume_label(cfg))}"), m)
                state["sent"][event] = now
                volume_alerts_this_scan += 1
        if cfg["activity"] and old and m["volume"] is not None:
            age = now - old["at"]
            delta = m["volume"] - old["volume"]
            if 300 <= age <= 3600 and old["volume"] >= 100 and delta >= max(500, old["volume"] * 1.5):
                event = f"{prefix}:spike:{int(now // 3600)}"
                if event not in state["sent"]:
                    send(chat, market_message(m, "🔥 <b>Unusual Volume Increase</b>",
                         f"Volume increase since previous snapshot: +{delta:,.0f}"), m)
                    state["sent"][event] = now

def scan(state, markets, now):
    seen_volumes = state.setdefault("seen_volume_markets", {})
    volume_baseline_ready = state.get("volume_baseline_ready", False)
    for chat, cfg in list(state["users"].items()):
        if cfg.get("paused") or cfg.get("delivery_disabled"):
            continue
        try:
            scan_subscriber(chat, cfg, state, markets, now, seen_volumes,
                            volume_baseline_ready)
        except urllib.error.HTTPError as exc:
            # Only Telegram sendMessage calls occur in scan_subscriber.
            if exc.code == 403:
                cfg["delivery_disabled"] = True
                logging.warning(
                    "Telegram refused delivery to one subscriber (HTTP 403). "
                    "Their alerts are paused until they interact with the bot again.")
            else:
                logging.warning("Telegram notification delivery failed: HTTP %d", exc.code)
        except Exception as exc:
            logging.error("Notification processing failed for one subscriber: %s",
                          type(exc).__name__)
    # Update history and first-seen data once per scan, not per user.
    for m in markets.values():
        if m["volume"] is not None:
            seen_volumes[m["id"]] = now
            old = state["history"].get(m["id"])
            if old is None or now - old["at"] >= 300:
                state["history"][m["id"]] = {"volume": m["volume"], "at": now}
    state["sent"] = {k: v for k, v in state["sent"].items() if now - v < 3 * 86400}
    state["history"] = {k: v for k, v in state["history"].items() if now - v["at"] < 2 * 86400}
    state["seen_volume_markets"] = {k: v for k, v in seen_volumes.items() if now - v < 7 * 86400}
    if not volume_baseline_ready:
        # Do not mark baseline ready until the volume API has returned data.
        state["volume_baseline_ready"] = any(m.get("volume") is not None for m in markets.values())

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
            except urllib.error.HTTPError as exc:
                # Authenticated Kash request failed, not Telegram delivery.
                state["last_market_error"] = f"HTTP {exc.code}"
                logging.error("Kash markets API refused access: HTTP %d", exc.code)
            except Exception as exc:
                state["last_market_error"] = type(exc).__name__
                logging.error("Kash market retrieval failed: %s",
                              type(exc).__name__)
            else:
                markets = fresh
                state["last_market_success_at"] = now
                state["last_market_error"] = None
                scan(state, markets, now)
                logging.info("Fetched %d markets; %d subscribers",
                             len(markets), len(state["users"]))
            last_scan = now
            save(state)
        try:
            result = telegram("getUpdates", {"offset": state["offset"], "timeout": 15,
                                             "allowed_updates": ["message", "callback_query"]})
            for update in result.get("result", []):
                state["offset"] = max(state["offset"], update["update_id"] + 1)
                message = update.get("message") or {}
                chat = (message.get("chat") or {}).get("id")
                if chat and isinstance(message.get("text"), str):
                    incoming = message["text"].strip()
                    cfg = user(state, chat)
                    cfg.pop("delivery_disabled", None)
                    name = incoming.casefold()
                    if name in ("settings", "menu", "home"):
                        cfg["awaiting_volume"] = False
                        show_settings(chat, state)
                    elif name == "start":
                        cfg["awaiting_volume"] = False
                        command(chat, "/start", state, markets)
                    elif name == "/cancel" and cfg.get("awaiting_volume"):
                        handle_volume_reply(chat, "cancel", state)
                    elif incoming.startswith("/"):
                        command(chat, incoming, state, markets)
                    elif not handle_volume_reply(chat, incoming, state):
                        send(chat, "Use /settings to open the main menu.",
                             keyboard=[[{"text": "🏠 Main Menu", "callback_data": "menu"}]])
                callback = update.get("callback_query") or {}
                if callback:
                    try:
                        telegram("answerCallbackQuery", {"callback_query_id": callback["id"]})
                    except Exception as exc:
                        logging.warning("Callback acknowledgement failed: %s", exc)
                    cb_chat = ((callback.get("message") or {}).get("chat") or {}).get("id")
                    if cb_chat:
                        user(state, cb_chat).pop("delivery_disabled", None)
                    if cb_chat and callback.get("data", "").startswith("toggle:"):
                        toggle(cb_chat, callback["data"].split(":", 1)[1], state, markets)
                    elif cb_chat and callback.get("data", "").startswith("vol:"):
                        volume_action(cb_chat, callback["data"].split(":", 1)[1], state, markets)
                    elif cb_chat and callback.get("data") == "top":
                        top_menu(cb_chat, state)
                    elif cb_chat and callback.get("data", "").startswith("top:"):
                        msg_id = (callback.get("message") or {}).get("message_id")
                        if isinstance(msg_id, int):
                            top_action(cb_chat, callback["data"].split(":", 1)[1],
                                       state, markets, msg_id)
                    elif cb_chat and callback.get("data") == "soon":
                        next_closings(cb_chat, markets)
                    elif cb_chat and callback.get("data") == "menu":
                        cfg = user(state, cb_chat)
                        cfg["awaiting_volume"] = False
                        show_settings(cb_chat, state)
            save(state)
        except urllib.error.HTTPError as exc:
            # HTTPError contains a URL with the BotFather token. Log only the
            # code, never the full exception or traceback.
            logging.error("Telegram update processing failed: HTTP %d", exc.code)
            time.sleep(5)
        except Exception as exc:
            logging.error("Telegram update processing failed: %s",
                          type(exc).__name__)
            time.sleep(5)

if __name__ == "__main__":
    main()
