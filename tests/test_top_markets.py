"""Top Markets ranking / pagination tests (no real API or credentials required)."""
import pathlib
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import bot


def markets_of_size(n=30):
    result = {}
    for i in range(n):
        market_id = f"00000000-0000-4000-8000-{i:012x}"
        result[market_id] = {
            "id": market_id, "title": f"Sample market {i}",
            "url": f"https://app.kash.bot/markets/{market_id}",
            "volume": i * 100.0, "close": None, "status": "ACTIVE",
            "tradeable": True,
        }
    return result


class TopMarketsTests(unittest.TestCase):
    def test_preset_buttons(self):
        keyboard = bot.top_size_keyboard(10)
        labels = [button["text"] for row in keyboard for button in row]
        self.assertTrue(any("Top 5" in label for label in labels))
        self.assertTrue(any("Top 10" in label for label in labels))
        self.assertTrue(any("Top 15" in label for label in labels))
        self.assertTrue(any("Top 20" in label for label in labels))

    def test_paginated_ranking_has_five_items_and_links(self):
        data = markets_of_size()
        text, keyboard = bot.top_page_content(data, 20, 0)
        self.assertIn("Top 20 Markets", text)
        self.assertIn("Page 1/4", text)
        self.assertIn("Sample market 29", text)
        self.assertNotIn("Sample market 24", text)
        self.assertIn('https://app.kash.bot/markets/', text)
        self.assertEqual(keyboard[0][0]["callback_data"], "top:page:1")

        text, keyboard = bot.top_page_content(data, 20, 3)
        self.assertIn("Page 4/4", text)
        self.assertIn("Sample market 10", text)
        self.assertFalse(any(button["callback_data"] == "top:page:4"
                             for row in keyboard for button in row))

    def test_last_page_clamped_and_missing_volume_excluded(self):
        data = markets_of_size(7)
        data[next(iter(data))]["volume"] = None
        text, keyboard = bot.top_page_content(data, 20, 999)
        self.assertIn("Page 2/2", text)
        self.assertIn("Showing 6–6 of 6 available", text)
        self.assertIn("🏠 Main Menu", str(keyboard))

    def test_user_preferences_are_independent(self):
        data = markets_of_size()
        state = {"users": {}, "sent": {}, "history": {}, "offset": 0}
        with patch.object(bot, "telegram") as telegram:
            bot.top_action(1, "set:20", state, data, 444)
            telegram.assert_called_once()
            self.assertEqual(telegram.call_args.args[0], "editMessageText")
            self.assertIn("Top 20", telegram.call_args.args[1]["text"])
            self.assertEqual(state["users"]["1"]["top_limit"], 20)
            self.assertEqual(bot.user(state, 2)["top_limit"], 5)

    def test_legacy_user_defaults_to_top_five(self):
        data = markets_of_size()
        state = {"users": {"1": {"thresholds": [15, 30, 60],
                                 "min_volume": 100, "paused": False}},
                 "sent": {}, "history": {}, "offset": 0}
        with patch.object(bot, "send") as send:
            bot.top_menu(1, state)
            self.assertIn("current: Top 5", send.call_args.args[1])
            bot.command(1, "/top 10", state, data)
            self.assertEqual(state["users"]["1"]["top_limit"], 10)
            self.assertEqual(send.call_count, 2)
            self.assertIn("Top 10 Markets", send.call_args_list[1].args[1])


if __name__ == "__main__":
    unittest.main()
