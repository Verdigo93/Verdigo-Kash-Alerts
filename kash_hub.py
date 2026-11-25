"""Read-only Kash Hub pages and market analytics. No wallet or trading API."""
import datetime as dt
import html
import math
import time
import uuid

NEWS_BLOG="https://blog.kash.bot/"
FUNDING_URL="https://www.globenewswire.com/news-release/2026/02/24/3243981/0/en/kash-raises-2m-pre-seed-to-bring-prediction-markets-to-social-media.html"
TEAM_URL="https://www.kash.bot/team"
TEAM=[
    ("Lucas Martin Calderon","Founder & CEO","https://x.com/lmc_security"),
    ("Andrew Law","Founder's Office","https://x.com/andrew__lw"),
    ("Miguel Santafé","Head of Product","https://x.com/miguelsantafe"),
    ("Thomas Vandermarcq","Marketing & Community Lead","https://x.com/0xth320v"),
    ("Chris Orza","Chief Revenue Officer","https://x.com/BoredCoobs"),
    ("Benedict W. H. Dixon","Head of Ecosystem","https://x.com/bwhdx"),
    ("Javier Sanchez","Head of Legal",TEAM_URL),
]
INVESTORS=[
    "Big Brain Holdings","Spartan Group","Coinbase Ventures","Fabric VC",
    "Kosmos Ventures","Halo Capital","MoonRock Capital","Polaris Fund",
]
MAX_MARKETS=12
MAX_TRADERS=10
CACHE_INTERVAL=600
PRICE_HISTORY_STEP=300
PRICE_HISTORY_LIFETIME=25*3600


def esc(x,maxlen=125):
    return html.escape(str(x or "")[:maxlen],quote=True)


def button(label,action=None,url=None):
    obj={"text":label}
    if url:
        obj["url"]=url
    else:
        name="hub:"+action
        if len(name.encode("utf-8"))>64:
            raise ValueError("Telegram button callback too long")
        obj["callback_data"]=name
    return obj


def nav(parent="home"):
    return [button("◀️ Back",parent),button("🏠 Home","home")]


def home():
    return (
        "🟡 <b>VERDIGO KASH HUB</b>\n"
        "<i>Your Kash market companion</i>\n\n"
        "📊 Find active markets and price movements.\n"
        "🐋 Follow large public positions.\n"
        "📰 Read verified Kash blog updates.\n"
        "ℹ️ Learn about Kash, the team and investors.\n\n"
        "Choose a section below.\n\n"
        "<i>Independent community tool · Not official Kash support · No trading advice.</i>"
    ),[
        [button("📊 Market Analytics","analytics")],
        [button("🔔 Alerts & Filters","alerts")],
        [button("📰 Kash News","news")],
        [button("ℹ️ About Kash","about")],
        [button("⭐ My Watchlists","watch")],
        [button("⏰ Next Closings", "next"),button("📈 Top Markets","top")],
    ]


def about(page):
    if page=="about":
        return ("ℹ️ <b>ABOUT KASH</b>\n\n"
                "Kash brings social prediction markets to conversations and news.\n\n"
                "Explore the team, verified financing information, official links and guides."), [[button("❓ What is Kash?","what")],
             [button("👥 Team & Founders","team")],
             [button("💰 Funding & Investors","funding")],
             [button("🌐 Official Links","links")],
             [button("📖 How Kash Works","how")],
             [button("🏠 Main Menu","home")]]
    if page=="what":
        return ("❓ <b>WHAT IS KASH?</b>\n\n"
                "Kash is a social-native prediction market platform. "
                "People can create or trade markets about real events including sports, crypto and culture.\n\n"
                "The platform integrates markets into social feeds with on-chain execution. "
                "Market prices express implied probabilities, not guaranteed outcomes.\n\n"
                "Learn more on the official site."), [[button("🌐 Official Website",url="https://www.kash.bot/")],nav("about")]
    if page=="how":
        return ("📖 <b>HOW KASH WORKS</b>\n\n"
                "1️⃣ Discover or create a prediction market.\n"
                "2️⃣ Read the rules and trading deadline.\n"
                "3️⃣ Select an outcome and review the price.\n"
                "4️⃣ Follow the market to settlement.\n\n"
                "Trading involves risk. Always check the market's settlement rules."), [[button("📚 Official FAQ",url="https://www.kash.bot/faq"),
              button("🚀 Trading App",url="https://app.kash.bot/")],nav("about")]
    if page=="team":
        text="👥 <b>KASH TEAM</b>\n\n"
        text+="\n".join("• <b>"+esc(n)+"</b> — "+esc(role) for n,role,_ in TEAM)
        text+="\n\n<i>Roles from the official team page; they may change.</i>"
        keys=[[button(n[:26]+" ↗",url=url)] for n,_,url in TEAM]
        keys+=[[button("📄 Official Team Page",url=TEAM_URL)],nav("about")]
        return text,keys
    if page=="funding":
        text=("💰 <b>KASH FUNDING & INVESTORS</b>\n\n"
              "Announced: <b>$2,000,000 pre-seed</b>\n"
              "Date: <b>24 February 2026</b>\n\n"
              "Publicly named backers:\n")
        text+="\n".join("• "+esc(name) for name in INVESTORS)
        text+=("\n\n<i>$2M is the announced total round, not the investment "
               "by each individual firm. Per-investor amounts were not disclosed.</i>")
        return text,[[button("🔎 Funding Announcement",url=FUNDING_URL),
                      button("📊 CryptoRank",url="https://cryptorank.io/ico/kash")],nav("about")]
    if page=="links":
        return ("🌐 <b>OFFICIAL KASH LINKS</b>\n\n"
                "Quick access to the project and public communities.\n"
                "<i>Discord invite provided by the community; access may expire.</i>"), [[button("🌍 Website",url="https://www.kash.bot/"),
              button("🚀 Trading App",url="https://app.kash.bot/")],
             [button("𝕏 Official X",url="https://x.com/kash_bot"),
              button("💬 Discord",url="https://discord.gg/ZnrTzKumWh")],
             [button("📰 Blog",url="https://blog.kash.bot/"),
              button("📚 Docs",url="https://docs.kash.bot/")],
             [button("👥 Team",url=TEAM_URL)],nav("about")]
    return home()


def finite(x):
    return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x)


def money(x):
    return "$"+format(x,",.2f")


def market_link(m):
    return '<a href="'+esc(m["url"],512)+'">'+esc(m.get("title") or "Untitled market",100)+"</a>"


def top(markets,key,n=5):
    return sorted((m for m in markets.values()
                   if m.get("url") and m.get("tradeable",True)
                   and finite(m.get(key)) and m[key]>=0),
                  key=lambda x:x[key],reverse=True)[:n]


def enhance_market_details(state, markets, http_json, now):
    """One public API request per 100 markets every ten minutes; never affect alerts."""
    cache=state.setdefault("hub_market_cache",{})
    if not isinstance(cache,dict):
        state["hub_market_cache"]=cache={}
    previous=cache.get("data",{})
    if not isinstance(previous,dict):
        previous={}
    if ("checked_at" not in cache or now-cache.get("checked_at",0)>=CACHE_INTERVAL) and markets:
        cache["checked_at"]=now
        result={}
        ids=[mid for mid in markets if is_uuid(mid)][:300]
        try:
            for i in range(0,len(ids),100):
                response=http_json("https://app.kash.bot/api/markets",
                                   params={"ids":",".join(ids[i:i+100]),"limit":100})
                if not isinstance(response,dict) or not isinstance(response.get("markets"),list):
                    raise ValueError("Invalid Kash markets API response")
                for m in response["markets"]:
                    if not isinstance(m,dict) or m.get("id") not in markets:
                        continue
                    entry={}
                    vol=m.get("volume24h")
                    if finite(vol) and vol>=0:
                        entry["volume_24h"]=vol/1_000_000
                    for field in ("category","categoryLabel","subCategory"):
                        if isinstance(m.get(field),str):
                            entry[field]=m[field][:80]
                    if entry:
                        result[m["id"]]=entry
        except Exception as exc:
            cache["last_error"]=type(exc).__name__
        else:
            cache["data"]=previous=result
            cache["last_error"]=None
    for mid,add in previous.items():
        if mid in markets and isinstance(add,dict):
            markets[mid].update(add)


def record_prices(state,markets,now):
    """Keep bounded 5-minute snapshots for 15m/1h/24h probability changes."""
    history=state.setdefault("hub_prices",{})
    if not isinstance(history,dict):
        state["hub_prices"]=history={}
    bucket=int(now//PRICE_HISTORY_STEP)*PRICE_HISTORY_STEP
    active=set(list(markets)[:250])
    for mid in list(history):
        if mid not in active:
            del history[mid]
    for mid in active:
        value=markets[mid].get("implied_yes")
        if not finite(value) or not 0<=value<=1:
            continue
        series=history.setdefault(mid,[])
        if not isinstance(series,list):
            history[mid]=series=[]
        if not series or series[-1][0]<bucket:
            series.append([bucket,round(value,6)])
        history[mid]=[r for r in series[-305:] if isinstance(r,list)
                      and len(r)==2 and finite(r[0])
                      and r[0]>=now-PRICE_HISTORY_LIFETIME]


def movers(markets,state,now,minutes):
    old=state.get("hub_prices",{})
    result=[]
    cutoff=now-minutes*60
    for mid,m in markets.items():
        if not m.get("url") or not finite(m.get("implied_yes")):
            continue
        snaps=old.get(mid,[]) if isinstance(old,dict) else []
        eligible=[r for r in snaps if len(r)==2 and finite(r[0]) and
                  abs(r[0]-cutoff)<=360]
        if not eligible:
            continue
        previous=min(eligible,key=lambda r:abs(r[0]-cutoff))[1]
        delta=(m["implied_yes"]-previous)*100
        result.append((abs(delta),delta,m))
    return sorted(result,key=lambda r:r[0],reverse=True)[:5]


def is_uuid(x):
    try:
        return str(uuid.UUID(str(x)))==str(x).lower()
    except (TypeError,ValueError,AttributeError):
        return False


def save_keys(rows,back_page):
    keys=[[button("⭐ Save market #"+str(i),"save:"+m["id"])]
          for i,m in enumerate(rows,1) if is_uuid(m.get("id"))]
    keys.append(nav(back_page))
    return keys


def analytics(page,state,markets,now):
    if page=="analytics":
        return ("📊 <b>MARKET ANALYTICS</b>\n\n"
                "Explore Kash trading activity, volume and probability changes.\n"
                "<i>Data may be cached; analytics are not trading signals.</i>"), [[button("🔥 Top Volume · 24h","top24")],
             [button("📈 Price Movers","movers")],
             [button("🏆 Market Categories","categories")],
             [button("👥 Trader Activity","traders")],
             [button("🏁 Resolved Markets","resolved")],
             [button("🏠 Main Menu","home")]]
    if page=="top24":
        rows=top(markets,"volume_24h")
        text="🔥 <b>TOP MARKETS · LAST 24 HOURS</b>\n\n"
        text+="\n\n".join(str(i)+". "+market_link(m)+"\n💰 "+money(m["volume_24h"])+" USDC"
                        for i,m in enumerate(rows,1)) if rows else "24h volume data unavailable."
        return text,save_keys(rows,"analytics")
    if page=="movers":
        return ("📈 <b>PRICE MOVERS</b>\n\n"
                "Biggest changes in implied YES probability.\n"
                "History is collected gradually after deployment."), [[button("⏱ 15 min","move15"),button("🕐 1 hour","move60")],
             [button("🗓 24 hours","move1440")],nav("analytics")]
    if page in ("move15","move60","move1440"):
        mins=int(page[4:])
        changes=movers(markets,state,now,mins)
        text="📈 <b>PRICE MOVERS · "+str(mins)+" MIN</b>\n\n"
        text+="\n\n".join(str(i)+". "+market_link(m)+"\n"
                         +("🟢 " if delta>0 else "🔴 ")+format(delta,"+.1f")+" pp"
                         for i,(_,delta,m) in enumerate(changes,1)) if changes else (
                             "Not enough price history for this period yet.")
        text+="\n\n<i>pp = percentage points, not investment returns.</i>"
        return text,save_keys([m for _,_,m in changes],"movers")
    if page=="categories":
        groups={}
        for m in markets.values():
            name=str(m.get("categoryLabel") or m.get("category") or "Other")[:55]
            group=groups.setdefault(name,[0,0.])
            group[0]+=1
            if finite(m.get("volume_24h")):
                group[1]+=m["volume_24h"]
        ranked=sorted(groups.items(),key=lambda x:x[1][1],reverse=True)[:8]
        text="🏆 <b>MARKET CATEGORIES</b>\n\n"
        text+="\n".join("• <b>"+esc(name)+"</b> — "+str(v[0])+
                        " markets · "+money(v[1])+" / 24h" for name,v in ranked) if ranked else "No data."
        return text,[nav("analytics")]
    if page=="traders":
        rows=top(markets,"participant_count")
        text="👥 <b>TOP MARKETS BY PARTICIPANTS</b>\n\n"
        text+="\n\n".join(str(i)+". "+market_link(m)+"\n👥 "+str(m["participant_count"])+
                         " accounts · 🔄 "+str(m.get("trade_count","?"))+" trades"
                         for i,m in enumerate(rows,1)) if rows else "No participant data."
        text+="\n\n<i>Distinct accounts do not necessarily represent distinct humans.</i>"
        return text,save_keys(rows,"analytics")
    return home()


def watches(page,cfg,markets,state):
    if page=="watch":
        n=len(cfg.get("hub_watch_markets",[]))
        t=len(cfg.get("hub_watch_traders",[]))
        return ("⭐ <b>MY WATCHLISTS</b>\n\nSaved markets: "+str(n)+"/12\n"
                "Followed public traders: "+str(t)+"/10\n\n"
                "Add markets from Analytics or traders from Whale Alerts.\n"
                "<i>Public top-50 leaderboard coverage is not complete trade history.</i>"), [[button("⭐ Saved Markets","watchmarkets")],
             [button("👀 Followed Traders","watchtraders")],
             [button("📊 Browse Markets","top24")],[button("🏠 Main Menu","home")]]
    if page=="watchmarkets":
        ids=cfg.get("hub_watch_markets",[])
        if not isinstance(ids,list):
            ids=[]
        text="⭐ <b>SAVED MARKETS</b>\n\n"
        text+="\n\n".join("• "+market_link(markets[mid]) if mid in markets and markets[mid].get("url")
                         else "• Unavailable/closed: "+esc(mid,42) for mid in ids[:MAX_MARKETS]) if ids else "No markets saved yet."
        keys=[[button("❌ Remove #"+str(i),"remove:"+mid)]
              for i,mid in enumerate(ids[:MAX_MARKETS],1) if is_uuid(mid)]
        keys.append(nav("watch"))
        return text,keys
    if page=="watchtraders":
        ids=cfg.get("hub_watch_traders",[])
        if not isinstance(ids,list):
            ids=[]
        text="👀 <b>FOLLOWED PUBLIC TRADERS</b>\n\n"
        labels={}
        snapshots=state.get("whale_tracker",{}).get("markets",{})
        if isinstance(snapshots,dict):
            for snap in snapshots.values():
                entries=snap.get("entries",{}) if isinstance(snap,dict) else {}
                if isinstance(entries,dict):
                    for uid,profile in entries.items():
                        if uid in ids and isinstance(profile,dict):
                            labels[uid]=profile.get("username") or profile.get("handle") or uid
        text+="\n".join("• "+esc(labels.get(x) or x,60) for x in ids[:MAX_TRADERS]) if ids else (
            "No traders followed yet. Tap 👀 Follow Trader on a Whale Alert.")
        keys=[[button("❌ Unfollow #"+str(i),"unfollow:"+uid)]
              for i,uid in enumerate(ids[:MAX_TRADERS],1) if is_uuid(uid)]
        keys.append(nav("watch"))
        return text,keys
    return home()


def alerts(cfg):
    return ("🔔 <b>ALERTS & FILTERS</b>\n\n"
            "Your existing closing, volume, activity and Whale Alerts stay intact.\n\n"
            "☀️ Daily Kash Digest (09:00 UTC): "+("✅ ON" if cfg.get("hub_digest_enabled") else "⬜ OFF")+
            "\n📰 New Kash blog posts: "+("✅ ON" if cfg.get("hub_news_enabled") else "⬜ OFF")+
            "\n🆕 New market alerts: "+("✅ ON" if cfg.get("hub_new_markets_enabled") else "⬜ OFF")+
            "\n🔕 All alerts: "+("PAUSED" if cfg.get("paused") else "ACTIVE")), [[button("⏰ Closing / Volume / Activity","oldsettings")],
         [button("🐋 Whale Alerts","oldwhales")],
         [button("☀️ Toggle Daily Digest","digest")],
         [button("📰 Toggle Blog Notifications","newsalert")],
         [button("🆕 Toggle New Market Alerts","newmarkets")],
         [button("⏸ Pause / Resume","pause")],
         [button("🏠 Main Menu","home")]]


def render(page,state,chat,markets,now):
    if page=="home":
        return home()
    if page in ("about","what","team","funding","links","how"):
        return about(page)
    cfg=state["users"].setdefault(str(chat),{})
    if page=="alerts":
        return alerts(cfg)
    if page in ("analytics","top24","movers","move15","move60","move1440","categories","traders"):
        return analytics(page,state,markets,now)
    if page in ("watch","watchmarkets","watchtraders"):
        return watches(page,cfg,markets,state)
    return home()


def action(chat,data,state,markets,now):
    """Store only explicit opt-ins/preferences; return which page to show."""
    cfg=state["users"].setdefault(str(chat),{})
    if data in ("oldsettings","oldwhales"):
        return data
    if data=="digest":
        cfg["hub_digest_enabled"]=not cfg.get("hub_digest_enabled",False)
        if cfg["hub_digest_enabled"]:
            cfg["hub_digest_last_day"]=dt.datetime.fromtimestamp(now,dt.timezone.utc).strftime("%Y-%m-%d")
        return "alerts"
    if data=="newsalert":
        cfg["hub_news_enabled"]=not cfg.get("hub_news_enabled",False)
        cfg["hub_news_initialized"]=False
        return "alerts"
    if data=="newmarkets":
        cfg["hub_new_markets_enabled"]=not cfg.get("hub_new_markets_enabled",False)
        return "alerts"
    if data=="pause":
        cfg["paused"]=not cfg.get("paused",False)
        return "alerts"
    for prefix,field,maximum,after in (
        ("save:","hub_watch_markets",MAX_MARKETS,"watchmarkets"),
        ("remove:","hub_watch_markets",MAX_MARKETS,"watchmarkets"),
        ("follow:","hub_watch_traders",MAX_TRADERS,"watchtraders"),
        ("unfollow:","hub_watch_traders",MAX_TRADERS,"watchtraders"),
    ):
        if data.startswith(prefix):
            uid=data[len(prefix):]
            if not is_uuid(uid):
                return after
            values=cfg.setdefault(field,[])
            if not isinstance(values,list):
                cfg[field]=values=[]
            if prefix in ("save:","follow:") and uid not in values and len(values)<maximum:
                if field=="hub_watch_traders" or uid in markets:
                    values.append(uid)
            if prefix in ("remove:","unfollow:") and uid in values:
                values.remove(uid)
            return after
    return data


def poll_digest(state,markets,send,now):
    """Send one optional UTC-morning market overview, never historical spam."""
    utc=dt.datetime.fromtimestamp(now,dt.timezone.utc)
    if utc.hour<9:
        return
    day=utc.strftime("%Y-%m-%d")
    rows=top(markets,"volume_24h",3)
    for chat,cfg in state.get("users",{}).items():
        if not cfg.get("hub_digest_enabled") or cfg.get("paused") or cfg.get("delivery_disabled"):
            continue
        if cfg.get("hub_digest_last_day")==day:
            continue
        body="☀️ <b>DAILY KASH DIGEST</b>\n\n🔥 24-hour leaders:\n"
        body+="\n".join(str(i)+". "+esc(m.get("title"),80)+" — "+money(m["volume_24h"])
                        for i,m in enumerate(rows,1)) if rows else "Volume data unavailable."
        body+="\n\n<i>For information only; not trading advice.</i>"
        try:
            send(chat,body,keyboard=[[button("📊 Analytics","analytics")]])
        except Exception:
            continue
        cfg["hub_digest_last_day"]=day


def poll_new_markets(state,markets,send,now):
    """Opt-in, silent initial baseline, bounded alerts for newly discovered markets."""
    current={mid for mid,m in markets.items()
             if is_uuid(mid) and m.get("url") and m.get("tradeable",True)}
    if not state.get("hub_market_baseline_ready",False):
        state["hub_known_market_ids"]=sorted(current)
        state["hub_market_baseline_ready"]=True
        return
    known=state.get("hub_known_market_ids",[])
    if not isinstance(known,list):
        known=[]
    unseen=sorted(current-set(known))
    state["hub_known_market_ids"]=sorted((set(known)|current))[-1000:]
    if not unseen:
        return
    chosen=unseen[:3]
    body="🆕 <b>NEWLY DISCOVERED KASH MARKETS</b>\n\n"
    body+="\n\n".join("• "+market_link(markets[mid]) for mid in chosen)
    if len(unseen)>len(chosen):
        body+="\n\n+"+str(len(unseen)-len(chosen))+" additional new markets."
    body+="\n\n<i>New to monitoring; not necessarily created right now.</i>"
    for chat,cfg in state.get("users",{}).items():
        if not cfg.get("hub_new_markets_enabled") or cfg.get("paused") or cfg.get("delivery_disabled"):
            continue
        try:
            send(chat,body,keyboard=[[button("📊 Analytics","analytics")]])
        except Exception:
            continue
