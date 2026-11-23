"""No-network tests for read-only opt-in whale position alerts."""
import json
import pathlib
import sys
import unittest
import urllib.error
from unittest.mock import Mock, patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import bot
import whale_alerts as whales

M1 = "e2d3e907-043b-4661-953c-ef05a6716d8d"
M2 = "aeb460d8-a404-4b0f-9385-0abcee8f3727"


def market(mid=M1, count=3):
    return {"id": mid, "title": 'Bitcoin & <Kash>?', "url": "https://app.kash.bot/markets/" + mid,
            "trade_count": count}


def entry(uid, amount_usdc, outcome="Yes", name="Example <Trader>"):
    return {"userId": uid, "amount": int(amount_usdc * 1000000),
            "outcomeLabel": outcome, "username": name, "currentValue": 999999999}


def cfg(bands=None):
    return {"whale_enabled": True, "whale_new": True, "whale_increase": True,
            "whale_bands": bands or list(whales.BANDS), "paused": False}


def state(users=None):
    return {"users": users or {"123": cfg()}, "sent": {}, "history": {},
            "offset": 0}


class WhaleTests(unittest.TestCase):
    def test_atomic_sums_and_market_value_not_used(self):
        rows = whales.normalize_entries([entry("a", 100), entry("b", 250)])
        self.assertEqual(rows["a"]["amount"], 100_000_000)
        self.assertEqual(rows["b"]["amount"], 250_000_000)
        self.assertNotIn("currentValue", rows["a"])
        self.assertEqual(whales.normalize_entries([{"userId": "x", "amount": "-10"}]), {})
        with self.assertRaises(ValueError):
            whales.normalize_entries({"entries": []})

    def test_half_open_bands(self):
        self.assertTrue(whales.matches_bands(20, {"whale_bands": ["20-50"]}))
        self.assertTrue(whales.matches_bands(49.99, {"whale_bands": ["20-50"]}))
        self.assertFalse(whales.matches_bands(50, {"whale_bands": ["20-50"]}))
        self.assertTrue(whales.matches_bands(50, {"whale_bands": ["50-100"]}))
        self.assertTrue(whales.matches_bands(1000, {"whale_bands": ["1000+"]}))
        self.assertFalse(whales.matches_bands(1000, {"whale_bands": []}))

    def test_increase_and_new_but_no_decrease(self):
        a = whales.normalize_entries([entry("a", 100), entry("b", 400)])
        b = whales.normalize_entries([entry("a", 250), entry("b", 100), entry("c", 50)])
        events = whales.changes(a, b)
        self.assertEqual([(e["user_id"], e["kind"], e["delta"]) for e in events],
                         [("a", "increase", 150_000_000), ("c", "new", 50_000_000)])

    def test_opted_out_subscriber_makes_no_requests(self):
        s = state({"123": {"thresholds": [60], "whale_enabled": False}})
        f = Mock()
        whales.poll(s, {M1: market()}, Mock(), now=1000, fetch=f)
        f.assert_not_called()
        self.assertNotIn("whale_tracker", s)

    def test_legacy_and_new_subscribers_enabled_by_default(self):
        self.assertTrue(bot.defaults()["whale_enabled"])
        self.assertIn("20-50", bot.defaults()["whale_bands"])
        s = state({"old": {"thresholds": [60]}})
        fetch = Mock(return_value=whales.normalize_entries([entry("a", 100)]))
        send = Mock()
        whales.poll(s, {M1: market()}, send, now=1000, fetch=fetch)
        fetch.assert_called_once()
        send.assert_not_called()  # Older subscribers never receive historical alerts.

    def test_initial_baseline_silent_then_position_increase_once(self):
        s = state()
        fetch = Mock(side_effect=[
            whales.normalize_entries([entry("a", 100)]),
            whales.normalize_entries([entry("a", 250)]),
        ])
        send = Mock()
        whales.poll(s, {M1: market(count=3)}, send, now=1000, fetch=fetch)
        send.assert_not_called()
        whales.poll(s, {M1: market(count=4)}, send, now=1060, fetch=fetch)
        send.assert_called_once()
        msg = send.call_args.args[1]
        self.assertIn("150.00 USDC", msg)
        self.assertIn("250.00 USDC", msg)
        self.assertIn("POSITION INCREASE", msg)
        self.assertIn("&lt;Kash&gt;", msg)
        self.assertIn("&lt;Trader&gt;", msg)
        whales.poll(s, {M1: market(count=4)}, send, now=1120, fetch=fetch)
        send.assert_called_once()
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(s["whale_tracker"]["markets"][M1]["entries"]["a"]["amount"], 250_000_000)

    def test_cached_leaderboard_rechecked_once_after_trade_count_change(self):
        s, send = state(), Mock()
        old = whales.normalize_entries([entry("a", 100)])
        new = whales.normalize_entries([entry("a", 250)])
        fetch = Mock(side_effect=[old, old, new])
        whales.poll(s, {M1: market(count=3)}, send, now=1000, fetch=fetch)
        whales.poll(s, {M1: market(count=4)}, send, now=1060, fetch=fetch)
        send.assert_not_called()
        self.assertEqual(s["whale_tracker"]["markets"][M1]["trade_count"], 3)
        whales.poll(s, {M1: market(count=4)}, send, now=1120, fetch=fetch)
        send.assert_called_once()
        self.assertIn("150.00 USDC", send.call_args.args[1])

    def test_zero_trade_baseline_alerts_on_first_trade(self):
        s, send = state(), Mock()
        fetch = Mock(return_value=whales.normalize_entries([entry("a", 50)]))
        whales.poll(s, {M1: market(count=0)}, send, now=1000, fetch=fetch)
        fetch.assert_not_called()
        whales.poll(s, {M1: market(count=1)}, send, now=1060, fetch=fetch)
        send.assert_called_once()
        self.assertIn("NEWLY OBSERVED POSITION", send.call_args.args[1])

    def test_preferences_independent_per_subscriber(self):
        s = state({"low": cfg(["20-50"]), "high": cfg(["100-500"])})
        fetch = Mock(side_effect=[
            whales.normalize_entries([entry("a", 100)]),
            whales.normalize_entries([entry("a", 250)]),
        ])
        send = Mock()
        whales.poll(s, {M1: market(count=3)}, send, now=1000, fetch=fetch)
        whales.poll(s, {M1: market(count=4)}, send, now=1060, fetch=fetch)
        self.assertEqual(send.call_count, 1)
        self.assertEqual(send.call_args.args[0], "high")

    def test_disabled_type_and_spam_cap(self):
        user = cfg()
        user["whale_new"] = False
        s = state({"123": user})
        send = Mock()
        whales.poll(s, {M1: market(count=0)}, send, now=1000, fetch=Mock())
        lots = whales.normalize_entries([entry(str(i), 100 + i) for i in range(20)])
        whales.poll(s, {M1: market(count=20)}, send, now=1060,
                    fetch=Mock(return_value=lots))
        send.assert_not_called()
        user["whale_new"] = True
        more = whales.normalize_entries([entry(str(i), 100 + i) for i in range(20, 40)])
        # Simulate a fresh HTTP response, not a mutation of the stored snapshot.
        latest = {**lots, **more}
        whales.poll(s, {M1: market(count=40)}, send, now=1120,
                    fetch=Mock(return_value=latest))
        self.assertEqual(send.call_count, whales.MAX_ALERTS_PER_SUBSCRIBER)

    def test_rate_limit_backoff_and_original_bot_survives(self):
        s = state()
        error = urllib.error.HTTPError("https://app.kash.bot", 429, "Too many", {"Retry-After": "120"}, None)
        fetch = Mock(side_effect=error)
        whales.poll(s, {M1: market(count=2)}, Mock(), now=1000, fetch=fetch)
        self.assertEqual(s["whale_tracker"]["pause_until"], 1120)
        whales.poll(s, {M1: market(count=2)}, Mock(), now=1060, fetch=fetch)
        self.assertEqual(fetch.call_count, 1)

    def test_persisted_snapshots_survive_restart(self):
        s = state()
        send = Mock()
        whales.poll(s, {M1: market(count=3)}, send, now=1000,
                    fetch=Mock(return_value=whales.normalize_entries([entry("a", 100)])))
        restored = json.loads(json.dumps(s))
        whales.poll(restored, {M1: market(count=4)}, send, now=1060,
                    fetch=Mock(return_value=whales.normalize_entries([entry("a", 250)])))
        self.assertEqual(send.call_count, 1)

    def test_request_budget(self):
        s = state()
        markets = {str(i): market(M1, count=i+1) for i in range(20)}
        # Valid IDs aren't necessary when the API fetcher is injected.
        fetch = Mock(return_value={})
        whales.poll(s, markets, Mock(), now=1000, fetch=fetch)
        self.assertEqual(fetch.call_count, whales.MAX_REQUESTS_PER_SCAN)

    def test_trade_counts_passed_from_public_market_state(self):
        markets = {M1: bot.normalize({"id": M1, "title": "Market?", "tradeable": True,
                                     "status": "ACTIVE", "freezeAt": "2099-01-01T00:00:00Z"})}
        with patch.object(bot, "http_json", return_value={"markets": [
                {"id": M1, "tradeCount": 4, "totalVolume": 20_000_000}]}):
            bot.enrich_with_market_state(markets)
        self.assertEqual(markets[M1]["trade_count"], 4)

    def test_bot_settings_toggle_and_bands(self):
        s = state({"123": bot.defaults()})
        with patch.object(bot, "send") as send:
            bot.whale_action("123", "toggle", s)
            self.assertFalse(s["users"]["123"]["whale_enabled"])
            bot.whale_action("123", "toggle", s)
            self.assertTrue(s["users"]["123"]["whale_enabled"])
            bot.whale_action("123", "band:20-50", s)
            self.assertNotIn("20-50", s["users"]["123"]["whale_bands"])
            bot.whale_action("123", "new", s)
            self.assertFalse(s["users"]["123"]["whale_new"])
            bot.command("123", "/whales", s, {})
        self.assertGreaterEqual(send.call_count, 4)
        self.assertIn("whale:menu", str(bot.settings_keyboard(s["users"]["123"])))

    def test_no_backlog_when_whales_disabled_then_reenabled(self):
        s = state()
        fetch = Mock(return_value=whales.normalize_entries([entry("a", 100)]))
        whales.poll(s, {M1: market(count=3)}, Mock(), now=1000, fetch=fetch)
        s["users"]["123"]["whale_enabled"] = False
        whales.poll(s, {M1: market(count=4)}, Mock(), now=1060, fetch=fetch)
        self.assertNotIn("whale_tracker", s)
        s["users"]["123"]["whale_enabled"] = True
        notify = Mock()
        whales.poll(s, {M1: market(count=5)}, notify, now=1120, fetch=fetch)
        notify.assert_not_called()


if __name__ == "__main__":
    unittest.main()
