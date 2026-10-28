"""Monitoring status reflects Kash fetch health, not just Telegram connectivity."""
import pathlib
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import bot


class MonitoringStatusTests(unittest.TestCase):
    def test_status_shows_fresh_kash_data(self):
        state = {"users": {}, "sent": {}, "history": {}, "offset": 0,
                 "last_market_success_at": 4000000000 - 120,
                 "last_market_error": None}
        with patch.object(bot.time, "time", return_value=4000000000), \
             patch.object(bot, "send") as send:
            bot.command(123, "/status", state, {})
        message = send.call_args.args[1]
        self.assertIn("Last Kash data update: 2 min ago", message)
        self.assertIn("Kash API: OK", message)

    def test_status_reports_kash_403_even_if_bot_responsive(self):
        state = {"users": {}, "sent": {}, "history": {}, "offset": 0,
                 "last_market_success_at": 4000000000 - 1200,
                 "last_market_error": "HTTP 403"}
        with patch.object(bot.time, "time", return_value=4000000000), \
             patch.object(bot, "send") as send:
            bot.command(123, "/status", state, {})
        message = send.call_args.args[1]
        self.assertIn("20 min ago", message)
        self.assertIn("Kash API: Latest fetch failed: HTTP 403", message)

    def test_status_handles_legacy_state_without_health_keys(self):
        state = {"users": {}, "sent": {}, "history": {}, "offset": 0}
        with patch.object(bot, "send") as send:
            bot.command(123, "/status", state, {})
        self.assertIn("No successful fetch recorded yet", send.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
