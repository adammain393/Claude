#!/usr/bin/env python3
"""
resolve.py — closes the stats loop. For every logged alert, walk forward
through the bars and grade what actually happened:

  WIN     TP1 traded before the stop
  LOSS    stop traded before TP1 (if one bar hits BOTH, we count LOSS —
          we can't know the order inside a bar, so we take the worst case)
  NO-FILL price never came back to the entry before the session ended
  OPEN    filled, but neither stop nor TP1 hit by the 16:00 ET close
          (graded by P/L at the close)

Assumes entry is a resting order at the alert's suggested entry price.
Only alerts that carry machine-readable levels can be graded; older ones are
skipped. Replay-flagged alerts are graded too but reported separately, so
live stats stay clean.

Usage:  python3 resolve.py            # grade everything, print the scoreboard
"""

import json
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(__file__))
from broker.bars import get_bars          # noqa: E402
from broker.ict import ET, bar_et         # noqa: E402

LOG = os.path.join(os.path.dirname(__file__), "state", "alerts.jsonl")
SESSION_END = (16, 0)                     # grade until the 16:00 ET close


def grade(alert, bars):
    lv = alert["levels"]
    side = alert.get("side", "LONG")
    long_side = side == "LONG"
    entry, stop, tp1 = lv["entry"], lv["stop"], lv.get("tp1")
    if tp1 is None:
        return {"outcome": "UNGRADABLE", "note": "no TP1 recorded"}

    t0 = lv.get("bar_time")
    day_end = None
    # v2 alerts are market entries on the confirming close — filled immediately.
    # Older alerts assumed a resting limit at the entry price.
    filled_at = t0 if lv.get("market") else None
    for b in bars:
        if b["t"] <= t0:
            continue
        et = bar_et(b)
        if day_end is None:
            close_dt = et.replace(hour=SESSION_END[0], minute=SESSION_END[1])
            day_end = close_dt.timestamp()
        if b["t"] >= day_end:
            break
        if filled_at is None:
            touched = b["l"] <= entry if long_side else b["h"] >= entry
            if touched:
                filled_at = b["t"]
            else:
                continue
        hit_stop = b["l"] <= stop if long_side else b["h"] >= stop
        hit_tp = b["h"] >= tp1 if long_side else b["l"] <= tp1
        if hit_stop:                       # worst case wins ties on the same bar
            return {"outcome": "LOSS", "r": -1.0, "at": b["t"]}
        if hit_tp:
            r = abs(tp1 - entry) / abs(entry - stop) if entry != stop else 0.0
            return {"outcome": "WIN", "r": round(r, 2), "at": b["t"]}
    if filled_at is None:
        return {"outcome": "NO-FILL"}
    last = next((b for b in reversed(bars) if b["t"] < (day_end or 1e18)), None)
    if last is None:
        return {"outcome": "OPEN", "note": "no bars after fill"}
    move = (last["c"] - entry) if long_side else (entry - last["c"])
    r = move / abs(entry - stop) if entry != stop else 0.0
    return {"outcome": "OPEN", "r": round(r, 2), "note": "graded at session close"}


def main():
    if not os.path.exists(LOG):
        print("No alerts logged yet (state/alerts.jsonl missing).")
        return
    alerts = [json.loads(line) for line in open(LOG) if line.strip()]
    graded, skipped = [], 0
    bars_cache = {}
    for a in alerts:
        if not a.get("levels"):
            skipped += 1
            continue
        sym = a["symbol"]
        if sym not in bars_cache:
            bars_cache[sym] = get_bars(sym, "5m", "1mo")
        result = grade(a, bars_cache[sym])
        graded.append((a, result))
        when = a["time"][:16].replace("T", " ")
        tag = " [replay]" if a.get("replay") else ""
        r = f"  ({result['r']:+.2f}R)" if "r" in result else ""
        print(f"{when}{tag}  {a.get('side','?'):<5} {sym:<6} {result['outcome']}{r}"
              f"  — {a.get('reason','')[:60]}")

    for label, keep in (("LIVE", lambda a: not a.get("replay")),
                        ("REPLAY", lambda a: a.get("replay"))):
        rows = [r for a, r in graded if keep(a)]
        decided = [r for r in rows if r["outcome"] in ("WIN", "LOSS")]
        if not rows:
            continue
        wins = sum(1 for r in decided if r["outcome"] == "WIN")
        total_r = sum(r.get("r", 0.0) for r in rows if "r" in r)
        wr = f"{wins}/{len(decided)} = {wins/len(decided)*100:.0f}%" if decided else "n/a (none decided)"
        print(f"\n[{label}] alerts: {len(rows)} | win rate: {wr} | "
              f"net: {total_r:+.2f}R | "
              f"no-fill: {sum(1 for r in rows if r['outcome']=='NO-FILL')}, "
              f"open: {sum(1 for r in rows if r['outcome']=='OPEN')}")
    if skipped:
        print(f"\n({skipped} old alert(s) skipped — logged before levels were recorded)")


if __name__ == "__main__":
    main()
