#!/usr/bin/env python3
"""
scanner.py — the "assistant that watches the charts for you".

It loops over your watchlist, runs your setup rules on fresh intraday bars,
and when your setup appears it pings you on Discord (or prints, in dry-run).
You look, confirm, and place the trade yourself.

Usage:
  python3 scanner.py --once                 # one pass, then exit (great for testing)
  python3 scanner.py                        # loop forever (default every 60s)
  python3 scanner.py --interval 30          # loop every 30 seconds
  python3 scanner.py --timeframe 1m         # use 1-minute bars
  python3 scanner.py --strategy example_ema_reclaim

Watchlist: edit watchlist.txt (one symbol per line). '#' comments allowed.
"""

import argparse
import importlib
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from broker.bars import get_bars  # noqa: E402
from broker.config import get as cfg_get  # noqa: E402
from broker.symbols import display, tv_link  # noqa: E402
import notify  # noqa: E402

WATCHLIST_FILE = os.path.join(os.path.dirname(__file__), "watchlist.txt")
COOLDOWN_MIN = 15  # don't re-alert the same symbol+setup within this many minutes


def load_watchlist():
    if not os.path.exists(WATCHLIST_FILE):
        return ["AAPL", "TSLA", "NVDA", "SPY"]
    out = []
    for line in open(WATCHLIST_FILE):
        line = line.split("#")[0].strip()
        if line:
            out.append(line.upper())
    return out


def load_strategy(name):
    mod = importlib.import_module(f"strategies.{name}")
    return mod




def scan_once(strategy, watchlist, timeframe, last_alert):
    stamp = datetime.now().strftime("%H:%M:%S")
    hits = 0
    lookback = getattr(strategy, "LOOKBACK", "1d")
    for sym in watchlist:
        try:
            bars = get_bars(sym, timeframe, lookback)
            sig = strategy.check(sym, bars)
        except Exception as e:  # noqa: BLE001 - one bad symbol shouldn't stop the scan
            print(f"[{stamp}] {sym}: skipped ({e})")
            continue
        if not sig:
            continue
        key = (sym, sig["setup"])
        now = time.time()
        if key in last_alert and now - last_alert[key] < COOLDOWN_MIN * 60:
            continue  # still cooling down; don't spam
        last_alert[key] = now
        hits += 1
        notify.log_alert(sym, sig)
        notify.send(
            title=f"🎯 SETUP: {display(sym)}",
            lines=[f"**{sig['reason']}**", ""] + sig["details"]
            + ["", "→ Come confirm, then place the trade yourself."],
            url_hint=tv_link(sym),
        )
    print(f"[{stamp}] scanned {len(watchlist)} symbols, {hits} setup(s) found.")
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="single pass then exit")
    ap.add_argument("--interval", type=int, default=60, help="seconds between passes")
    ap.add_argument("--timeframe", default=None, help="bar size: 1m,5m,15m...")
    ap.add_argument("--symbols", default=None, help="comma-separated, overrides watchlist")
    ap.add_argument("--strategy", default="example_ema_reclaim", help="strategy module name")
    args = ap.parse_args()

    strategy = load_strategy(args.strategy)
    # precedence: CLI flag > strategy's own defaults > watchlist.txt
    args.timeframe = args.timeframe or getattr(strategy, "TIMEFRAME", "5m")
    if args.symbols:
        watchlist = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    else:
        watchlist = getattr(strategy, "DEFAULT_SYMBOLS", None) or load_watchlist()
    print(f"Scanner armed. Setup: {strategy.NAME}")
    print(f"Watching {len(watchlist)} symbols on {args.timeframe} bars: {', '.join(watchlist)}")
    print(f"Alerts → {'Discord' if cfg_get('DISCORD_WEBHOOK_URL') else 'console (dry-run)'}")
    try:
        from broker import news
        evs = news.usd_events(day=datetime.now(news.ET).date())
        if evs:
            print("Today's USD news (red/orange folders) — alerts pause −5/+10 min around red:")
            for e in evs:
                print(f"  {e['time'].strftime('%H:%M ET')}  [{e['impact']:<6}]  {e['title']}")
        else:
            print("No USD red/orange news today.")
    except Exception as e:  # noqa: BLE001
        print(f"(Forex Factory feed unavailable: {e})")
    print()

    last_alert = {}
    if args.once:
        scan_once(strategy, watchlist, args.timeframe, last_alert)
        return
    try:
        while True:
            scan_once(strategy, watchlist, args.timeframe, last_alert)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nScanner stopped.")


if __name__ == "__main__":
    main()
