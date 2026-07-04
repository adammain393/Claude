"""
news.py — Forex Factory economic calendar (the "news folders").

PB's rules from the sessions episode:
  * Check Forex Factory every morning, filtered to USD.
  * Red folder = high impact, orange = medium. (On the site, yellow = LOW.)
  * No entries from ~5 min before a red release until ~5-10 min after.
  * The candle printed at a red release leaves DATA WICKS — its high and low
    become liquidity pools price often returns to raid.

Feed: Forex Factory's own weekly JSON (public, no key).
Impacts in the feed: "High" (red), "Medium" (orange), "Low" (yellow), "Holiday".
"""

import json
import os
import time
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
FEED = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) paper-trading/0.1"
_DISK = os.path.join(os.path.dirname(os.path.dirname(__file__)), "state", "news_cache.json")

_cache = {"t": 0.0, "events": None}


def _parse(raw):
    events = []
    for e in raw:
        try:
            when = datetime.fromisoformat(e["date"]).astimezone(ET)
        except (KeyError, ValueError):
            continue
        events.append({"time": when, "title": e.get("title", ""),
                       "country": e.get("country", ""), "impact": e.get("impact", "")})
    return events


def week_events(ttl=1800):
    """All events this week: [{'time': datetime ET, 'title', 'country', 'impact'}].
    Cached in memory AND on disk (the feed rate-limits repeat fetches)."""
    if _cache["events"] is not None and time.time() - _cache["t"] < ttl:
        return _cache["events"]
    if os.path.exists(_DISK) and time.time() - os.path.getmtime(_DISK) < ttl:
        with open(_DISK) as f:
            events = _parse(json.load(f))
        _cache.update(t=time.time(), events=events)
        return events
    try:
        req = urllib.request.Request(FEED, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = json.loads(r.read())
        os.makedirs(os.path.dirname(_DISK), exist_ok=True)
        with open(_DISK, "w") as f:
            json.dump(raw, f)
    except Exception:
        # feed down or rate-limited (it 429s easily): a stale calendar beats
        # none at all — news times don't move much within a week
        if os.path.exists(_DISK):
            with open(_DISK) as f:
                raw = json.load(f)
        else:
            raise
    events = _parse(raw)
    _cache.update(t=time.time(), events=events)
    return events


def usd_events(day=None, impacts=("High", "Medium")):
    """USD events, red+orange by default; optionally only one ET calendar day."""
    evs = [e for e in week_events()
           if e["country"] == "USD" and e["impact"] in impacts]
    if day is not None:
        evs = [e for e in evs if e["time"].date() == day]
    return sorted(evs, key=lambda e: e["time"])


def in_blackout(now_et, before_min=5, after_min=10):
    """The red-news no-entry window. Returns the blocking event, or None."""
    for e in usd_events(day=now_et.date(), impacts=("High",)):
        start = e["time"] - timedelta(minutes=before_min)
        end = e["time"] + timedelta(minutes=after_min)
        if start <= now_et <= end:
            return e
    return None


if __name__ == "__main__":
    today = datetime.now(ET).date()
    evs = usd_events(day=today)
    print(f"USD red/orange events today ({today}):")
    for e in evs or []:
        print(f"  {e['time'].strftime('%H:%M ET')}  [{e['impact']:<6}]  {e['title']}")
    if not evs:
        print("  (none)")
    b = in_blackout(datetime.now(ET))
    print("Currently in red-news blackout:", f"YES — {b['title']}" if b else "no")
