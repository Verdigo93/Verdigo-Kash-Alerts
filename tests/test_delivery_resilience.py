"""Ensure one Telegram recipient's failure cannot interrupt all Kash alerts."""
import pathlib
import sys
import urllib.error
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import bot


def fake_market(now):
    return {"id": "e2d3e907-043b-4661-953c-ef05a6716d8d",
            "title": "Test market close", "close": now + 30 * 60,
            "url": "https://app.kash.bot/markets/e2d3e907-043b-4661-953c-ef05a6716d8d",
            "volume": None, "tradeable": True, "status": "ACTIVE"}


def prefs():
    return {"thresholds": [30], "volume": False, "activity": False,
            "min_volume": 10000, "paused": False}


class DeliveryResilienceTests(unittest.TestCase):
    def test_blocked_subscriber_does_not_interrupt_other_users(self):
        now = 4000000000
        market = fake_market(now)
        state = {"users": {"111": prefs(), "222": prefs()},
                 "sent": {}, "history": {}, "offset": 0}
        attempts = []

        def delivery(chat, message, market=None, keyboard=None):
            attempts.append(str(chat))
            if str(chat) == "111":
                raise urllib.error.HTTPError(
                    "https://api.telegram.org/botREDACTED/sendMessage",
                    403, "Forbidden", None, None)

        with patch.object(bot, "send", side_effect=delivery):
            bot.scan(state, {market["id"]: market}, now)
            self.assertEqual(attempts, ["111", "222"])
            self.assertTrue(state["users"]["111"]["delivery_disabled"])
            self.assertFalse(state["users"]["222"].get("delivery_disabled", False))
            self.assertIn("222:" + market["id"] + ":closing:30", state["sent"])
            bot.scan(state, {market["id"]: market}, now + 60)
            self.assertEqual(attempts, ["111", "222"])

    def test_non403_telegram_failure_does_not_disable_subscriber(self):
        now = 4000000000
        market = fake_market(now)
        state = {"users": {"111": prefs(), "222": prefs()},
                 "sent": {}, "history": {}, "offset": 0}
        attempts = []

        def delivery(chat, message, market=None, keyboard=None):
            attempts.append(str(chat))
            if str(chat) == "111":
                raise urllib.error.HTTPError(
                    "https://api.telegram.org/botREDACTED/sendMessage",
                    429, "Too Many Requests", None, None)

        with patch.object(bot, "send", side_effect=delivery):
            bot.scan(state, {market["id"]: market}, now)
        self.assertEqual(attempts, ["111", "222"])
        self.assertFalse(state["users"]["111"].get("delivery_disabled", False))

    def test_kash_errors_remain_separate_from_telegram_delivery(self):
        market = fake_market(4000000000)
        state = {"users": {"111": prefs()}, "sent": {}, "history": {}, "offset": 0}
        with patch.object(bot, "send") as send:
            bot.scan(state, {market["id"]: market}, 4000000000)
        send.assert_called_once()
        self.assertFalse(state["users"]["111"].get("delivery_disabled", False))


if __name__ == "__main__":
    unittest.main()
