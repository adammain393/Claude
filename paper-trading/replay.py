#!/usr/bin/env python3
"""
replay.py — time-machine test: step through recent bars one at a time and show
every alert the strategy WOULD have fired, exactly as the live scanner would
have seen it (no lookahead — the strategy only ever sees bars up to "now").

Usage:
  python3 replay.py --strategy ict_pb --symbol NQ=F
  python3 replay.py --strategy ict_pb --symbol NQ=F --lookback 5d --timeframe 5m
"""

import argparse
import importlib
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(__file__))
from broker.bars import get_bars  # noqa: E402
from broker.symbols import display, tv_link  # noqa: E402
import notify  # noqa: E402

ET = ZoneInfo("America/New_York")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", required=True)
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--timeframe", default=None)
    ap.add_argument("--lookback", default=None)
    ap.add_argument("--notify", action="store_true",
                    help="push each replay alert through the real Discord pipeline")
    args = ap.parse_args()

    strategy = importlib.import_module(f"strategies.{args.strategy}")
    tf = args.timeframe or getattr(strategy, "TIMEFRAME", "5m")
    lb = args.lookback or getattr(strategy, "LOOKBACK", "5d")
    sym = args.symbol.upper()

    bars = get_bars(sym, tf, lb)
    print(f"Replaying {len(bars)} {tf} bars of {sym} ({lb}) through "
          f"'{getattr(strategy, 'NAME', args.strategy)}'\n")

    seen = set()
    alerts = 0
    for t in range(40, len(bars) + 1):
        window = bars[:t]
        try:
            sig = strategy.check(sym, window)
        except Exception as e:  # noqa: BLE001 — a crash on one bar shouldn't kill the replay
            stamp = datetime.fromtimestamp(window[-1]["t"], tz=ET)
            print(f"  !! {stamp:%a %H:%M} strategy error: {e}")
            continue
        if not sig:
            continue
        key = (sig["reason"], sig["details"][0])   # same sweep+setup → one alert
        if key in seen:
            continue
        seen.add(key)
        alerts += 1
        stamp = datetime.fromtimestamp(window[-1]["t"], tz=ET)
        print(f"🔔 {stamp:%a %b %d %H:%M} ET — {sig['reason']}")
        for line in sig["details"]:
            print(f"     {line}")
        print()
        if args.notify:
            notify.log_alert(sym, sig, replay=True)
            notify.send(
                title=f"🎯 SETUP (REPLAY {stamp:%a %H:%M} ET): {display(sym)}",
                lines=[f"**{sig['reason']}**",
                       "_replayed historical setup — pipeline test, not live_", ""]
                + sig["details"],
                url_hint=tv_link(sym),
            )
    print(f"Done: {alerts} distinct alert(s) across the replay.")


if __name__ == "__main__":
    main()
