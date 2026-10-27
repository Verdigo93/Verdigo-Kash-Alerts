import datetime as dt
import pathlib
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import bot

ID1 = "e2d3e907-043b-4661-953c-ef05a6716d8d"
ID2 = "aeb460d8-a404-4b0f-9385-0abcee8f3727"

def sample_market(mid, tradeable=True):
    return {"id": mid, "title": "A real Kash market?", "status": "ACTIVE",
            "tradeable": tradeable, "freezeAt": "2099-05-01T16:30:00Z"}

class BotTests(unittest.TestCase):
    def test_market_link_freeze_and_tradeable(self):
        m = bot.normalize(sample_market(ID1))
        self.assertEqual(m["url"], "https://app.kash.bot/markets/" + ID1)
        self.assertTrue(m["tradeable"])
        self.assertEqual(m["close"], dt.datetime(2099, 5, 1, 16, 30,
                                            tzinfo=dt.timezone.utc).timestamp())

    def test_cursor_pages_and_exclude_untradeable(self):
        first = {"data": [sample_market(ID1)],
                 "pagination": {"cursor": "next-page", "hasMore": True, "limit": 100}}
        second = {"data": [sample_market(ID2, False)],
                  "pagination": {"cursor": None, "hasMore": False, "limit": 100}}
        with patch.object(bot, "KASH_KEY", "kash_live_test"), \
             patch.object(bot, "http_json", side_effect=[first, second]) as req, \
             patch.object(bot, "enrich_with_market_state"):
            found = bot.fetch_markets()
        self.assertEqual(list(found), [ID1])
        self.assertEqual(req.call_args_list[1].kwargs["params"]["cursor"], "next-page")
        self.assertEqual(req.call_args_list[0].kwargs["headers"]["X-API-Key"], "kash_live_test")

    def test_atomic_volume_converted_to_usdc(self):
        markets = {ID1: bot.normalize(sample_market(ID1))}
        response = {"markets": [{"id": ID1, "totalVolume": 35_000_000}]}
        with patch.object(bot, "http_json", return_value=response) as http:
            bot.enrich_with_market_state(markets)
        self.assertEqual(markets[ID1]["volume"], 35.0)
        self.assertIn("/api/markets/state", http.call_args.args[0])

    def test_freeze_alert_sends_once(self):
        now = dt.datetime(2099, 5, 1, 16, 0, tzinfo=dt.timezone.utc).timestamp()
        markets = {ID1: bot.normalize(sample_market(ID1))}
        state = {"users": {"123": {"thresholds": [30], "volume": False,
                                  "activity": False, "min_volume": 10000,
                                  "paused": False}},
                 "sent": {}, "history": {}, "offset": 0}
        with patch.object(bot, "send") as send:
            bot.scan(state, markets, now)
            bot.scan(state, markets, now)
        send.assert_called_once()
        self.assertIn("30 minutes", send.call_args.args[1])

    def test_late_discovery_sends_one_nearest_threshold_then_15(self):
        freeze = dt.datetime(2099, 5, 1, 16, 30, tzinfo=dt.timezone.utc).timestamp()
        markets = {ID1: bot.normalize(sample_market(ID1))}
        cfg = {"thresholds": [15, 30, 60], "volume": False,
               "activity": False, "min_volume": 10000, "paused": False}
        state = {"users": {"123": cfg}, "sent": {}, "history": {}, "offset": 0}
        with patch.object(bot, "send") as send:
            bot.scan(state, markets, freeze - 25 * 60)
            bot.scan(state, markets, freeze - 24 * 60)
            self.assertEqual(send.call_count, 1)
            self.assertIn("Alert: 30 minutes", send.call_args.args[1])
            bot.scan(state, markets, freeze - 14 * 60)
            bot.scan(state, markets, freeze - 13 * 60)
            self.assertEqual(send.call_count, 2)
            self.assertIn("Alert: 15 minutes", send.call_args.args[1])

    def test_soon_preview_no_markets_within_two_hours(self):
        freeze = dt.datetime(2099, 5, 1, 16, 30, tzinfo=dt.timezone.utc).timestamp()
        markets = {ID1: bot.normalize(sample_market(ID1))}
        with patch.object(bot, "send") as send:
            bot.next_closings("123", markets, now=freeze - 3 * 3600)
        send.assert_called_once()
        self.assertIn("No markets freeze within the next 2 hours",
                      send.call_args.args[1])

    def test_soon_preview_lists_nearby_markets(self):
        freeze = dt.datetime(2099, 5, 1, 16, 30, tzinfo=dt.timezone.utc).timestamp()
        markets = {ID1: bot.normalize(sample_market(ID1))}
        with patch.object(bot, "send") as send:
            bot.next_closings("123", markets, now=freeze - 40 * 60)
        send.assert_called_once()
        self.assertIn("40 min", send.call_args.args[1])
        self.assertEqual(send.call_args.args[2]["url"],
                         "https://app.kash.bot/markets/" + ID1)


    def test_volume_range_parsing(self):
        self.assertEqual(bot.parse_volume_range("100"), (100, None))
        self.assertEqual(bot.parse_volume_range("<10"), (0, 10))
        self.assertEqual(bot.parse_volume_range("10-100"), (10, 100))
        self.assertEqual(bot.parse_volume_range("100+"), (100, None))
        self.assertEqual(bot.parse_volume_range("all"), (0, None))
        self.assertEqual(bot.parse_volume_range("$1,000"), (1000, None))
        for invalid in ("-10", "100-10", "<0", "2+--5", "1+5", "hello", ""):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    bot.parse_volume_range(invalid)

    def test_volume_range_edges_and_legacy_preferences(self):
        legacy = {"min_volume": 100}
        self.assertFalse(bot.volume_matches(99.99, legacy))
        self.assertTrue(bot.volume_matches(100, legacy))
        band = {"min_volume": 10, "max_volume": 100}
        self.assertFalse(bot.volume_matches(9.9, band))
        self.assertTrue(bot.volume_matches(10, band))
        self.assertTrue(bot.volume_matches(99.9, band))
        self.assertFalse(bot.volume_matches(100, band))

    def test_volume_buttons_and_custom_user_reply(self):
        state = {"users": {}, "sent": {}, "history": {}, "offset": 0}
        with patch.object(bot, "send"):
            bot.volume_action("123", "under10", state, {})
            self.assertEqual(state["users"]["123"]["min_volume"], 0)
            self.assertEqual(state["users"]["123"]["max_volume"], 10)
            bot.volume_action("123", "custom", state, {})
            self.assertTrue(state["users"]["123"]["awaiting_volume"])
            self.assertTrue(bot.handle_volume_reply("123", "50-500", state))
            self.assertEqual(state["users"]["123"]["min_volume"], 50)
            self.assertEqual(state["users"]["123"]["max_volume"], 500)
            self.assertFalse(state["users"]["123"]["awaiting_volume"])
        # Each user's settings remain independent.
        self.assertEqual(bot.user(state, "456")["min_volume"], 10000)

    def test_volume_first_scan_baseline_then_new_market_alert(self):
        now = dt.datetime(2099, 5, 1, 16, 0, tzinfo=dt.timezone.utc).timestamp()
        markets = {ID1: bot.normalize(sample_market(ID1))}
        markets[ID1]["volume"] = 5
        cfg = {"thresholds": [], "volume": True, "activity": False,
               "min_volume": 0, "max_volume": 10, "paused": False}
        state = {"users": {"123": cfg}, "sent": {}, "history": {}, "offset": 0}
        with patch.object(bot, "send") as send:
            bot.scan(state, markets, now)
            self.assertEqual(send.call_count, 0, "Do not spam all existing low-volume markets")
            markets[ID2] = bot.normalize(sample_market(ID2))
            markets[ID2]["volume"] = 7
            bot.scan(state, markets, now + 60)
            self.assertEqual(send.call_count, 1, "Alert for a newly listed matching market")
            self.assertIn("Market Matches Your Volume Filter", send.call_args.args[1])
            bot.scan(state, markets, now + 120)
            self.assertEqual(send.call_count, 1, "Do not repeat market volume alerts")

    def test_matching_markets_preview_independent_of_alerts(self):
        m1 = bot.normalize(sample_market(ID1))
        m1["volume"] = 7
        m2 = bot.normalize(sample_market(ID2))
        m2["volume"] = 700
        state = {"users": {"123": {"min_volume": 0, "max_volume": 10}},
                 "sent": {}, "history": {}, "offset": 0}
        with patch.object(bot, "send") as send:
            bot.volume_markets("123", state, {ID1: m1, ID2: m2})
        self.assertEqual(send.call_count, 2)
        self.assertIn("Matching Market", send.call_args_list[1].args[1])
        self.assertEqual(send.call_args_list[1].args[2]["id"], ID1)

    def test_alert_readability_and_safe_title(self):
        m = bot.normalize(sample_market(ID1))
        m["title"] = "Who wins: Essen & Leipzig <Final>?"
        formatted = bot.market_message(
            m, "⏰ <b>Market Closing Soon!</b>",
            "❗ <b>Time remaining: 60 min</b> ❗\n\n🔔 Alert: 60 minutes",
        )
        self.assertIn("📌 <b>Who wins: Essen &amp; Leipzig &lt;Final&gt;?</b>", formatted)
        self.assertIn("</b>\n\n❗ <b>Time remaining", formatted)
        self.assertIn("min</b> ❗\n\n🔔 Alert", formatted)

    def test_live_closing_alert_has_time_spacing(self):
        freeze = dt.datetime(2099, 5, 1, 16, 30, tzinfo=dt.timezone.utc).timestamp()
        m = bot.normalize(sample_market(ID1))
        state = {"users": {"123": {"thresholds": [60], "volume": False,
                 "activity": False, "min_volume": 10000, "paused": False}},
                 "sent": {}, "history": {}, "offset": 0}
        with patch.object(bot, "send") as send:
            bot.scan(state, {ID1: m}, freeze - 3600)
        payload = send.call_args.args[1]
        self.assertIn("📌 <b>A real Kash market?</b>", payload)
        self.assertIn("❗ <b>Time remaining: 60 min</b> ❗\n\n🔔 Alert: 60 minutes", payload)

if __name__ == "__main__":
    unittest.main()
