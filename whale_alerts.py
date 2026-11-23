"""Opt-in read-only alerts for changes in Kash leaderboard investments.

Only observes top 50 public leaderboard entries per market. Does not identify
individual trades or prove a profile is human. Zero requests until enabled.
"""
import html
import json
import logging
import time
import urllib.error
import urllib.request
import uuid
from decimal import Decimal, InvalidOperation

BANDS = {
    "20-50": (20, 50),
    "50-100": (50, 100),
    "100-500": (100, 500),
    "500-1000": (500, 1000),
    "1000+": (1000, None),
}
DEFAULT_BANDS = ("50-100", "100-500", "500-1000", "1000+")
MAX_REQUESTS_PER_SCAN = 3
MAX_ALERTS_PER_SUBSCRIBER = 5
LEADERBOARD_LIMIT = 50


def matches_bands(amount_usdc, cfg):
    """Half-open ranges do not overlap at $50, $100, etc."""
    selected = cfg.get("whale_bands", DEFAULT_BANDS)
    if not isinstance(selected, (list, tuple)):
        return False
    for band in selected:
        if band not in BANDS:
            continue
        low, high = BANDS[band]
        if amount_usdc >= low and (high is None or amount_usdc < high):
            return True
    return False


def _amount_atomic(raw):
    """Kash exposes leaderboard investment in atomic-6 USDC units."""
    try:
        value = Decimal(str(raw))
        if not value.is_finite() or value < 0 or value != value.to_integral_value():
            return None
        if value > Decimal("1000000000000000000"):
            return None
        return int(value)
    except (InvalidOperation, TypeError, ValueError):
        return None


def normalize_entries(entries):
    if not isinstance(entries, list):
        raise ValueError("Invalid leaderboard data")
    result = {}
    for item in entries:
        if not isinstance(item, dict):
            continue
        uid = item.get("userId")
        amount = _amount_atomic(item.get("amount"))
        if not isinstance(uid, str) or not uid or len(uid) > 128 or amount is None:
            continue
        result[uid] = {
            "amount": amount,
            "username": str(item.get("username") or "")[:80],
            "handle": str(item.get("handle") or "")[:80],
            "outcome": str(item.get("outcomeLabel") or "")[:80],
        }
    return result


def fetch_leaderboard(market_id):
    market_uuid = str(uuid.UUID(market_id))
    if market_uuid != market_id.lower():
        raise ValueError("Invalid market UUID")
    url = ("https://app.kash.bot/api/markets/" + market_uuid
           + "/leaderboard?limit=" + str(LEADERBOARD_LIMIT))
    req = urllib.request.Request(
        url, headers={"Accept": "application/json",
                      "User-Agent": "VerdigoKashAlerts/whale-alerts"})
    with urllib.request.urlopen(req, timeout=6) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise ValueError("Invalid leaderboard response")
    return normalize_entries(payload.get("entries"))


def changes(previous, current):
    """Positive observed deposits only: never confuse price PnL with entry."""
    events = []
    for uid, entry in current.items():
        new_amount = entry["amount"]
        old = previous.get(uid)
        old_amount = old.get("amount", 0) if isinstance(old, dict) else 0
        if new_amount <= old_amount:
            continue
        events.append({
            "user_id": uid,
            "kind": "increase" if old is not None else "new",
            "previous": old_amount,
            "current": new_amount,
            "delta": new_amount - old_amount,
            "entry": entry,
        })
    return sorted(events, key=lambda event: event["delta"], reverse=True)


def format_alert(market, event):
    heading = ("🐋 <b>WHALE POSITION INCREASE</b>" if event["kind"] == "increase"
               else "🐋 <b>NEWLY OBSERVED POSITION</b>")
    entry = event["entry"]
    trader = entry.get("username") or entry.get("handle") or "Unnamed public trader"
    outcome = entry.get("outcome") or "Not provided"
    return (
        f"{heading}\n\n"
        f"📌 <b>{html.escape(market['title'])}</b>\n\n"
        f"💰 <b>Observed increase: +{event['delta'] / 1_000_000:,.2f} USDC</b>\n"
        f"Previous investment: {event['previous'] / 1_000_000:,.2f} USDC\n"
        f"Current investment: {event['current'] / 1_000_000:,.2f} USDC\n"
        f"🎯 Main outcome: {html.escape(outcome)}\n"
        f"👤 Public profile: {html.escape(trader)}\n\n"
        "<i>Change observed in public leaderboard, not a confirmed single trade. "
        "The profile may be an automated trader.</i>"
    )


def poll(state, markets, send, now=None, fetch=None):
    """Limited polling on the original scan schedule; persisted in state.json.

    An initial baseline is silent, including markets already containing whales.
    Requests and messages are capped to protect the original bot.
    """
    enabled = [
        (chat, cfg) for chat, cfg in state.get("users", {}).items()
        if cfg.get("whale_enabled", False)
        and not cfg.get("paused", False)
        and not cfg.get("delivery_disabled", False)
    ]
    if not enabled:
        state.pop("whale_tracker", None)
        return
    now = time.time() if now is None else now
    fetch = fetch_leaderboard if fetch is None else fetch
    tracker = state.setdefault("whale_tracker", {})
    if not isinstance(tracker, dict):
        state["whale_tracker"] = tracker = {}
    snapshots = tracker.setdefault("markets", {})
    if not isinstance(snapshots, dict):
        tracker["markets"] = snapshots = {}
    if now < tracker.get("pause_until", 0):
        return
    ids = [mid for mid, market in markets.items()
           if isinstance(market.get("trade_count"), int)
           and not isinstance(market["trade_count"], bool)
           and market["trade_count"] >= 0 and market.get("url")]
    if not ids:
        return
    for mid in list(snapshots):
        if mid not in markets:
            del snapshots[mid]
    cursor = tracker.get("cursor", 0)
    start = (cursor if isinstance(cursor, int) else 0) % len(ids)
    inspected = 0
    requests = 0
    sends_per_chat = {chat: 0 for chat, _ in enabled}
    while inspected < len(ids):
        mid = ids[(start + inspected) % len(ids)]
        inspected += 1
        market = markets[mid]
        trade_count = market["trade_count"]
        old = snapshots.get(mid)
        if old is None and trade_count == 0:
            snapshots[mid] = {"trade_count": 0, "entries": {}}
            continue
        if isinstance(old, dict) and old.get("trade_count") == trade_count:
            continue
        if requests >= MAX_REQUESTS_PER_SCAN:
            inspected -= 1
            break
        requests += 1
        try:
            entries = fetch(mid)
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 503):
                raw_retry = exc.headers.get("Retry-After", "60") if exc.headers else "60"
                try:
                    retry = max(60, min(3600, int(raw_retry)))
                except (ValueError, TypeError):
                    retry = 60
                tracker["pause_until"] = now + retry
            logging.warning("Whale leaderboard unavailable: HTTP %s", exc.code)
            break
        except Exception as exc:
            logging.warning("Whale leaderboard unavailable: %s", type(exc).__name__)
            continue
        if not isinstance(entries, dict):
            logging.warning("Whale leaderboard returned invalid entries")
            continue
        if isinstance(old, dict) and trade_count >= old.get("trade_count", 0):
            for event in changes(old.get("entries", {}), entries):
                for chat, cfg in enabled:
                    if sends_per_chat[chat] >= MAX_ALERTS_PER_SUBSCRIBER:
                        continue
                    if event["kind"] == "new" and not cfg.get("whale_new", True):
                        continue
                    if event["kind"] == "increase" and not cfg.get("whale_increase", True):
                        continue
                    if not matches_bands(event["delta"] / 1_000_000, cfg):
                        continue
                    key = f"whale:{mid}:{event['user_id']}:{event['current']}:{chat}"
                    if key in state.setdefault("sent", {}):
                        continue
                    try:
                        send(chat, format_alert(market, event), market)
                    except urllib.error.HTTPError as exc:
                        if exc.code == 403:
                            cfg["delivery_disabled"] = True
                        logging.warning("Whale alert delivery failed: HTTP %s", exc.code)
                    except Exception as exc:
                        logging.warning("Whale alert delivery failed: %s", type(exc).__name__)
                    else:
                        sends_per_chat[chat] += 1
                        state["sent"][key] = now
        snapshots[mid] = {"trade_count": trade_count, "entries": entries}
    tracker["cursor"] = (start + inspected) % len(ids)
