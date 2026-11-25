"""Offline regression tests for Kash Hub, RSS and Telegram navigation."""
import datetime as dt
import io
import pathlib
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import bot
import kash_hub as hub
import kash_news

MID="e2d3e907-043b-4661-953c-ef05a6716d8d"
TRADER="3f2b0c1e-6a7d-4e59-9b8a-1c2d3e4f5a6b"


def market(vol=400,prob=0.4):
    return {"id":MID,"title":"BTC price < $100K?",
            "url":"https://app.kash.bot/markets/"+MID,
            "volume":vol,"tradeable":True,"implied_yes":prob,
            "trade_count":10,"participant_count":4}


class HubTests(unittest.TestCase):
    def test_menu_layout_and_about_project_are_real_and_safe(self):
        state={"users":{"1":bot.defaults()}}
        text,keyboard=hub.render("home",state,"1",{MID:market()},1000)
        self.assertIn("Market Analytics",str(keyboard))
        self.assertIn("About Kash",str(keyboard))
        self.assertIn("Independent community tool",text)
        for page in ("about","what","team","funding","links","how"):
            title,keys=hub.render(page,state,"1",{},1000)
            self.assertIn("KASH",title.upper())
            self.assertIn("hub:home",str(keys))
        title,_=hub.render("funding",state,"1",{},1000)
        self.assertIn("$2,000,000",title)
        self.assertIn("not the investment",title)
        keys=hub.render("links",state,"1",{},1000)[1]
        self.assertIn("discord.gg/ZnrTzKumWh",str(keys))
        self.assertIn("x.com/kash_bot",str(keys))

    def test_callback_size_telegram_limit(self):
        _,keyboard=hub.home()
        for row in keyboard:
            for key in row:
                self.assertLessEqual(len(key.get("callback_data","").encode("utf-8")),64)
        with self.assertRaises(ValueError):
            hub.button("bad","x"*70)

    def test_market_details_are_atomic6_and_cached(self):
        s={"users":{}}
        m={MID:market()}
        fn=Mock(return_value={"markets":[{"id":MID,"volume24h":70000000,
            "category":"crypto","categoryLabel":"Crypto"}]})
        hub.enhance_market_details(s,m,fn,now=1000)
        self.assertEqual(m[MID]["volume_24h"],70)
        self.assertEqual(m[MID]["categoryLabel"],"Crypto")
        hub.enhance_market_details(s,{MID:market()},fn,now=1100)
        self.assertEqual(fn.call_count,1)

    def test_market_details_failure_cannot_break_existing_market(self):
        s={"users":{}}
        m={MID:market()}
        hub.enhance_market_details(s,m,Mock(side_effect=TimeoutError()),now=1000)
        self.assertEqual(m[MID]["volume"],400)
        self.assertEqual(s["hub_market_cache"]["last_error"],"TimeoutError")

    def test_24h_volume_and_participant_ranking(self):
        s={"users":{"1":{}}}
        m={MID:{**market(),"volume_24h":45,"participant_count":8,
                "categoryLabel":"Crypto"}}
        title,_=hub.render("top24",s,"1",m,1000)
        self.assertIn("$45.00",title)
        self.assertIn("&lt; $100K",title)
        x,_=hub.render("traders",s,"1",m,1000)
        self.assertIn("8 accounts",x)
        c,_=hub.render("categories",s,"1",m,1000)
        self.assertIn("Crypto",c)

    def test_price_movers_need_history_and_are_bounded(self):
        s={"users":{"1":{}}}
        m={MID:market(prob=0.25)}
        hub.record_prices(s,m,now=1000)
        m[MID]["implied_yes"]=0.55
        hub.record_prices(s,m,now=1900)
        changes=hub.movers(m,s,1900,15)
        self.assertEqual(len(changes),1)
        self.assertAlmostEqual(changes[0][1],30.0,places=2)
        self.assertFalse(hub.movers(m,s,1900,1440))
        text,_=hub.render("move15",s,"1",m,1900)
        self.assertIn("+30.0 pp",text)

    def test_watchlists_and_digest_are_optin(self):
        s={"users":{"1":bot.defaults()}}
        cfg=s["users"]["1"]
        self.assertFalse(cfg["hub_digest_enabled"])
        hub.action("1","save:"+MID,s,{MID:market()},1000)
        hub.action("1","save:"+MID,s,{MID:market()},1000)
        self.assertEqual(cfg["hub_watch_markets"],[MID])
        hub.action("1","follow:"+TRADER,s,{},1000)
        self.assertEqual(cfg["hub_watch_traders"],[TRADER])
        message,_=hub.render("watchtraders",s,"1",{},1000)
        self.assertIn(TRADER,message)
        hub.action("1","unfollow:"+TRADER,s,{},1000)
        self.assertEqual(cfg["hub_watch_traders"],[])
        hub.action("1","remove:"+MID,s,{},1000)
        self.assertEqual(cfg["hub_watch_markets"],[])
        ts=dt.datetime(2026,11,26,9,5,tzinfo=dt.timezone.utc).timestamp()
        send=Mock()
        hub.poll_digest(s,{MID:market()},send,ts)
        send.assert_not_called()
        hub.action("1","digest",s,{},ts)
        hub.poll_digest(s,{MID:market()},send,ts)
        send.assert_not_called()
        hub.poll_digest(s,{MID:{**market(),"volume_24h":40}},send,ts+86400)
        send.assert_called_once()
        hub.poll_digest(s,{MID:market()},send,ts+86460)
        send.assert_called_once()

    def test_menu_callbacks_edit_in_place(self):
        s={"users":{"123":bot.defaults()}}
        with patch.object(bot,"telegram",return_value={"ok":True}) as tg:
            bot.hub_action("123","about",s,{MID:market()},message_id=987)
        self.assertEqual(tg.call_count,1)
        method,data=tg.call_args.args
        self.assertEqual(method,"editMessageText")
        self.assertEqual(data["message_id"],987)
        self.assertIn("ABOUT KASH",data["text"])
        bot.hub_action if False else None


class NewsTests(unittest.TestCase):
    def test_rss_safe_domain_and_dates(self):
        xml=b'''<?xml version="1.0" encoding="utf-8"?>
        <rss version="2.0"><channel>
        <item><title>New &amp; exciting Kash</title><link>https://blog.kash.bot/new-kash</link>
        <pubDate>Tue, 24 Nov 2026 09:00:00 +0000</pubDate></item>
        <item><title>Fake</title><link>https://attacker.example/phish</link></item>
        </channel></rss>'''
        with patch.object(kash_news.urllib.request,"urlopen",return_value=io.BytesIO(xml)):
            values=kash_news.fetch()
        self.assertEqual(len(values),1)
        self.assertEqual(values[0]["title"],"New & exciting Kash")
        self.assertEqual(values[0]["date"],"24 Nov 2026")
        self.assertIsNone(kash_news.item_link("https://blog.kash.bot.evil.com/phish"))

    def test_news_optin_and_silent_initial_baseline(self):
        s={"users":{"1":{"hub_news_enabled":True}}}
        send=Mock()
        first=[{"title":"First","link":"https://blog.kash.bot/first","date":"25 Nov"}]
        second=[{"title":"Second","link":"https://blog.kash.bot/second","date":"26 Nov"}]
        kash_news.poll(s,send,now=1000,fetcher=lambda:first)
        send.assert_not_called()
        self.assertTrue(s["users"]["1"]["hub_news_initialized"])
        kash_news.poll(s,send,now=3000,fetcher=lambda:second)
        send.assert_called_once()
        self.assertIn("Second",send.call_args.args[1])
        kash_news.poll(s,send,now=6000,fetcher=lambda:second)
        send.assert_called_once()

    def test_resolved_markets_read_on_demand(self):
        s={}
        res={"markets":[{"id":MID,"title":"Will Kash win?",
              "winningOutcomeIndex":0,
              "outcomes":[{"outcomeIndex":0,"label":"YES"}]}]}
        fetch=Mock(return_value=res)
        title,keys=kash_news.resolved_page(s,fetch,now=2000)
        self.assertIn("YES",title)
        self.assertIn("Will Kash win?",title)
        self.assertIn("hub:analytics",str(keys))
        kash_news.resolved_page(s,fetch,now=2200)
        fetch.assert_called_once()



class AdditionalIntegrationTests(unittest.TestCase):
    def test_optin_new_market_alerts_use_silent_baseline(self):
        extra="aeb460d8-a404-4b0f-9385-0abcee8f3727"
        newest="0b7d5a4e-2c1f-4e8a-9d3b-6f1e2a7c9d40"
        base={MID:market()}
        state={"users":{"1":bot.defaults()}}
        send=Mock()
        hub.poll_new_markets(state,base,send,1000)
        self.assertTrue(state["hub_market_baseline_ready"])
        send.assert_not_called()
        mid2={**base,extra:{**market(),"id":extra,"url":"https://app.kash.bot/markets/"+extra}}
        hub.poll_new_markets(state,mid2,send,1100)
        send.assert_not_called()
        self.assertEqual(hub.action("1","newmarkets",state,mid2,1150),"alerts")
        self.assertTrue(state["users"]["1"]["hub_new_markets_enabled"])
        three={**mid2,newest:{**market(),"id":newest,"url":"https://app.kash.bot/markets/"+newest}}
        hub.poll_new_markets(state,three,send,1200)
        send.assert_called_once()
        self.assertIn("NEWLY DISCOVERED",send.call_args.args[1])

    def test_start_sends_one_clean_menu(self):
        s={"users":{}}
        with patch.object(bot,"send") as mock_send:
            bot.command("123","/start",s,{MID:market()})
        mock_send.assert_called_once()
        self.assertIn("VERDIGO KASH HUB",mock_send.call_args.args[1])

    def test_followed_trader_shows_name_from_existing_snapshot(self):
        s={"users":{"123":bot.defaults()},
           "whale_tracker":{"markets":{MID:{"trade_count":10,"entries":{
               TRADER:{"username":"Friendly Kash Trader","amount":50000000}}}}}}
        hub.action("123","follow:"+TRADER,s,{},1000)
        label,_=hub.render("watchtraders",s,"123",{},1010)
        self.assertIn("Friendly Kash Trader",label)


class HubStatusTests(unittest.TestCase):
    def test_hubstatus_reports_safe_counts_without_ids(self):
        state={"users":{},"hub_market_cache":{"checked_at":1000,
               "data":{MID:{"volume_24h":20}}},"hub_news":{"checked_at":1000,
               "items":[{"title":"Blog","link":"https://blog.kash.bot/post"}]}}
        with patch.object(bot,"send") as send, patch.object(bot.time,"time",return_value=1060):
            bot.command("123","/hubstatus",state,{MID:market()})
        message=send.call_args.args[1]
        self.assertIn("KASH HUB STATUS",message)
        self.assertIn("Markets with public 24h data: 1",message)
        self.assertIn("Official blog headlines cached: 1",message)
        self.assertNotIn(MID,message)

if __name__=="__main__":
    unittest.main()
