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

import io
import json
import os
import sys
from contextlib import redirect_stdout
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

    _eval_sim([(a, r) for a, r in graded if not a.get("replay")])


def _eval_sim(live, risk=500.0, target=3000.0, max_loss=2000.0, min_sample=20):
    """Simulate the Lucid 50K Flex eval over the LIVE graded alerts:
    would taking every alert at $500 risk have passed by now, and is the
    sample big enough to trust? This is the buy-the-eval gate."""
    days = {}
    for a, r in live:
        if "r" in r:
            days.setdefault(a["time"][:10], 0.0)
            days[a["time"][:10]] += r["r"] * risk
    print("\n════ LUCID 50K EVAL SIMULATION (live alerts @ $500 risk) ════")
    if not days:
        print("No graded live alerts yet — run the scanner on killzone mornings first.")
        return
    balance, worst, biggest = 0.0, 0.0, 0.0
    for day in sorted(days):
        balance += days[day]
        worst = min(worst, balance)
        biggest = max(biggest, days[day])
        print(f"  {day}: {days[day]:+8,.0f}  →  running {balance:+8,.0f}")
    n = len(live)
    decided = [r for _, r in live if r["outcome"] in ("WIN", "LOSS")]
    wins = sum(1 for r in decided if r["outcome"] == "WIN")
    consistency_ok = balance <= 0 or biggest <= 0.5 * max(balance, 1e-9)
    print(f"\n  P/L: ${balance:+,.0f} of ${target:,.0f} target"
          f" | worst drawdown ${worst:,.0f} (limit -${max_loss:,.0f})"
          f" | biggest day ${biggest:,.0f} ({'OK' if consistency_ok else 'VIOLATES 50% consistency'})")
    if n < min_sample:
        print(f"  VERDICT: sample too small ({n}/{min_sample} alerts) — keep paper trading. "
              "Do NOT buy the eval yet.")
    elif decided and wins / len(decided) >= 0.55 and balance > 0 and worst > -max_loss:
        print(f"  VERDICT: stats support buying the eval "
              f"({wins}/{len(decided)} = {wins/len(decided)*100:.0f}% wins, positive P/L, "
              "drawdown survivable). Final call is Adam's.")
    else:
        print("  VERDICT: stats do NOT yet support buying the eval "
              "(need ≥55% wins, positive P/L, drawdown inside -$2,000).")


if __name__ == "__main__":
    if "--post" in sys.argv:
        # capture the full report, print it locally, AND post it to Discord —
        # this is what the evening automation runs, so Adam (and Zoey, who
        # reads the channel) get the scoreboard without touching the Mac.
        buf = io.StringIO()
        with redirect_stdout(buf):
            main()
        report = buf.getvalue()
        print(report)
        import notify
        tail = "\n".join(report.strip().splitlines()[-20:])
        notify.send(title="📊 Nightly scoreboard",
                    lines=["```", tail[:3800], "```"])
    else:
        main()
