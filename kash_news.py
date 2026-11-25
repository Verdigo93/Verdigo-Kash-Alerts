"""Official Kash RSS headlines and public resolved-market previews.

Read-only, stdlib-only, opt-in notifications, bounded network calls.
Official X and Discord are linked, not scraped.
"""
import email.utils
import html
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

RSS_URL="https://blog.kash.bot/feed.xml"
BLOG="https://blog.kash.bot/"
RESOLVED_URL="https://app.kash.bot/api/markets"
CACHE=1800
MAX_FEED_BYTES=300000


def clean(text,limit=120):
    return html.escape(str(text or "")[:limit],quote=True)


def item_link(url):
    parsed=urllib.parse.urlsplit(str(url or ""))
    if parsed.scheme!="https" or parsed.hostname!="blog.kash.bot":
        return None
    return str(url)[:500]


def fetch():
    """Fetch an RSS 2.0 feed from the official blog, never arbitrary URLs."""
    req=urllib.request.Request(RSS_URL,headers={
        "Accept":"application/rss+xml, application/xml",
        "User-Agent":"VerdigoKashAlerts/1.0"})
    with urllib.request.urlopen(req,timeout=8) as r:
        raw=r.read(MAX_FEED_BYTES+1)
    if len(raw)>MAX_FEED_BYTES:
        raise ValueError("RSS feed too large")
    root=ET.fromstring(raw)
    result=[]
    for item in root.findall("./channel/item")[:25]:
        title=item.findtext("title")
        link=item_link(item.findtext("link"))
        if not title or not link:
            continue
        date=item.findtext("pubDate") or ""
        try:
            pub=email.utils.parsedate_to_datetime(date).strftime("%d %b %Y")
        except (TypeError,ValueError,OverflowError):
            pub=""
        result.append({"title":str(title)[:180],"link":link,"date":pub})
        if len(result)>=8:
            break
    if not result:
        raise ValueError("No usable RSS items")
    return result


def refresh(state,now,fetcher=None):
    cache=state.setdefault("hub_news",{})
    if not isinstance(cache,dict):
        state["hub_news"]=cache={}
    if "checked_at" in cache and now-cache.get("checked_at",0)<CACHE:
        return cache.get("items",[])
    cache["checked_at"]=now
    try:
        items=(fetcher or fetch)()
        if not isinstance(items,list):
            raise ValueError("Bad RSS result")
    except Exception as exc:
        cache["error"]=type(exc).__name__
    else:
        cache["items"]=[i for i in items[:8] if isinstance(i,dict) and item_link(i.get("link"))]
        cache["error"]=None
    return cache.get("items",[])


def news_page(state,now):
    from kash_hub import button
    items=refresh(state,now)
    text=("📰 <b>OFFICIAL KASH NEWS</b>\n\n"
          "Latest articles from the Kash blog. Official X and Discord below.\n\n")
    text+="\n\n".join(
        "• <a href=\""+clean(item["link"],500)+"\">"+clean(item.get("title"),125)+"</a>"+
        ("\n📅 "+clean(item.get("date"),30) if item.get("date") else "")
        for item in items[:5]
    ) if items else ("News feed temporarily unavailable. "
                     "Visit the official blog directly.")
    text+="\n\n<i>Independent community bot. These are external articles.</i>"
    return text,[
        [button("📰 Official Blog",url=BLOG),
         button("𝕏 Official Kash",url="https://x.com/kash_bot")],
        [button("💬 Discord",url="https://discord.gg/ZnrTzKumWh")],
        [button("🔔 Manage Blog Notifications","alerts")],
        [button("🏠 Home","home")],
    ]


def poll(state,send,now,fetcher=None):
    users=[(c,x) for c,x in state.get("users",{}).items()
           if x.get("hub_news_enabled",False)
           and not x.get("paused") and not x.get("delivery_disabled")]
    if not users:
        return
    articles=refresh(state,now,fetcher=fetcher)
    if not articles:
        return
    newest=articles[0]
    from kash_hub import button
    for chat,cfg in users:
        if not cfg.get("hub_news_initialized",False):
            cfg["hub_news_initialized"]=True
            cfg["hub_news_last_link"]=newest["link"]
            continue
        if cfg.get("hub_news_last_link")==newest["link"]:
            continue
        msg="📰 <b>NEW FROM KASH</b>\n\n"+clean(newest.get("title"),180)
        if newest.get("date"):
            msg+="\n📅 "+clean(newest["date"],30)
        try:
            send(chat,msg,keyboard=[
                [button("📖 Read Article",url=newest["link"])],
                [button("📰 More Kash News","news")]
            ])
        except Exception:
            continue
        cfg["hub_news_last_link"]=newest["link"]


def resolved_page(state,http_json,now):
    """Requested by a user only: no expensive continuous resolved-market polling."""
    from kash_hub import button,is_uuid
    cache=state.setdefault("hub_resolved",{})
    if "checked_at" not in cache or now-cache.get("checked_at",0)>=CACHE:
        cache["checked_at"]=now
        try:
            payload=http_json(RESOLVED_URL,params={
                "status":"resolved","sortBy":"end_time",
                "sortOrder":"desc","limit":10
            })
            if not isinstance(payload,dict) or not isinstance(payload.get("markets"),list):
                raise ValueError("Invalid resolved markets API")
            rows=[]
            for raw in payload["markets"][:10]:
                if not isinstance(raw,dict) or not is_uuid(raw.get("id")):
                    continue
                winning=raw.get("winningOutcomeIndex")
                if not isinstance(winning,int) or winning<0:
                    label="Not reported"
                else:
                    label="Not reported"
                    for outcome in raw.get("outcomes",[]):
                        if isinstance(outcome,dict) and outcome.get("outcomeIndex")==winning:
                            label=outcome.get("label") or label
                rows.append({
                    "link":"https://app.kash.bot/markets/"+raw["id"],
                    "title":str(raw.get("title") or "Market")[:125],
                    "winning":str(label)[:45]})
            cache["rows"]=rows
            cache["error"]=None
        except Exception as exc:
            cache["error"]=type(exc).__name__
    rows=cache.get("rows",[])
    text="🏁 <b>RECENTLY ENDED & RESOLVED MARKETS</b>\n\n"
    text+="\n\n".join(str(i)+". <a href=\""+clean(r["link"],200)+"\">"+
                     clean(r["title"],100)+"</a>\n🏆 Winner: "+clean(r["winning"],45)
                     for i,r in enumerate(rows[:5],1)) if rows else (
                         "Resolved market data temporarily unavailable.")
    return text,[[button("◀️ Analytics","analytics"),button("🏠 Home","home")]]
