"""Test read-only Whale Alerts diagnostics with no server terminal."""
import pathlib
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import bot
import whale_alerts

M = "e2d3e907-043b-4661-953c-ef05a6716d8d"


class WhaleStatusTests(unittest.TestCase):
    def test_empty_state_reports_uninitialized(self):
        state = {"users": {}, "sent": {}, "history": {}, "offset": 0}
        markets = {M: {"id": M, "title": "Market", "url": "https://app.kash.bot/markets/" + M,
                       "trade_count": 5}}
        with patch.object(bot, "send") as send:
            bot.command("123", "/whalestatus", state, markets)
        message = send.call_args.args[1]
        self.assertIn("Whale Monitoring Status", message)
        self.assertIn("Your alerts: ON", message)
        self.assertIn("Markets with trade counts: 1 / 1", message)
        self.assertIn("Markets with saved snapshots: 0", message)
        self.assertIn("Last successful leaderboard read: Not yet", message)
        self.assertNotIn(M, message)
        self.assertFalse("whale_tracker" in state, "Diagnostics must not create tracker data")

    def test_live_snapshot_reports_healthy_reads_and_positions(self):
        state = {"users": {"123": {"whale_enabled": True}}, "sent": {}, "history": {},
                 "whale_tracker": {"markets": {M: {"trade_count": 5,
                                                    "entries": {"abc": {"amount": 200000000}}}},
                                   "last_leaderboard_attempt_at": 990,
                                   "last_leaderboard_ok_at": 990,
                                   "last_leaderboard_error": None}}
        market = {"id": M, "title": "Market", "url": "https://app.kash.bot/markets/" + M,
                  "trade_count": 5}
        with patch.object(bot, "send") as send, patch.object(bot.time, "time", return_value=1050):
            bot.command("123", "/whalestatus", state, {M: market})
        message = send.call_args.args[1]
        self.assertIn("Public positions in snapshots: 1", message)
        self.assertIn("Markets with saved snapshots: 1", message)
        self.assertIn("Last successful leaderboard read: 1 min ago", message)
        self.assertIn("Last leaderboard error: None reported", message)

    def test_failed_leaderboard_does_not_reveal_private_data(self):
        state = {"users": {"123": {"whale_enabled": False}}, "sent": {}, "history": {},
                 "whale_tracker": {"markets": {}, "last_leaderboard_error": "HTTP 429",
                                   "pause_until": 1100}}
        with patch.object(bot, "send") as send, patch.object(bot.time, "time", return_value=1000):
            bot.command("123", "/whalestatus", state, {})
        message = send.call_args.args[1]
        self.assertIn("Your alerts: OFF", message)
        self.assertIn("HTTP 429", message)
        self.assertIn("Rate-limit cooldown: 1 min", message)


if __name__ == "__main__":
    unittest.main()
