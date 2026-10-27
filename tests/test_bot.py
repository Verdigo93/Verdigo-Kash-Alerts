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

if __name__ == "__main__":
    unittest.main()
