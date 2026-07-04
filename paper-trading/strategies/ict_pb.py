"""
ict_pb.py — the ICT day-trading setup as taught by PB Trading (with Tiz Trades'
stricter inversion-entry definition), reconstructed from 20 lesson transcripts.

THE MODEL (NY AM killzone, 9:30-11:00 ET, NQ futures primary):

  1. SWEEP     — price raids a significant sell-side pool (previous day low,
                 Asia low, London low, or an obvious intraday swing low):
                 wick THROUGH the level, body closes back above.  [PB Ep4/7]
  2. MSS       — after the sweep, a candle BODY closes above the most recent
                 swing high ("it has to be a body close, cannot be a wick").
                 The turn is confirmed.                            [PB Ep3]
  3. ENTRY ZONE— preferred: an INVERSION FVG — a bearish fair value gap that
                 price body-closes fully beyond, then retests (Tiz: "a clear
                 close below/above the gap", close ON the line doesn't count).
                 Fallback: a fresh bullish FVG left by the displacement leg.
  4. CONFLUENCE (reported, not required — you judge):
                 - discount: entry zone at/below the 50% (EQ) of the impulse
                   leg ("never long in premium, never short in discount")
                 - SMT: NQ swept the low but ES held it (or vice versa)
                 - displacement candle on the structure shift
  5. RISK      — stop under the sweep wick; first target = nearest INTERNAL
                 liquidity ("your first TP should be internal liquidity" —
                 never previous day/session levels first).         [PB Ep7/11]

Shorts are the exact mirror (sweep buy-side pool → MSS down → IFVG retest).

The scanner fires when steps 1-3 are freshly in place; YOU confirm on the
chart and decide. Judgment calls the courses leave to the trader (is the pool
"significant"? is the day clean or choppy?) stay with you — by design.
"""

import time
from datetime import timedelta

from broker.bars import get_bars
from broker import ict
from broker import news
from broker.symbols import display

NAME = "PB-ICT: sweep → MSS → FVG/IFVG retest (NY AM)"
DEFAULT_SYMBOLS = ["NQ=F", "ES=F"]  # NQ1! and ES1!; each is the other's SMT pair
TIMEFRAME = "5m"
LOOKBACK = "5d"
COMPANION = {"NQ=F": "ES=F", "ES=F": "NQ=F", "QQQ": "SPY", "SPY": "QQQ"}
KILLZONE = ((9, 30), (11, 0))       # NY AM, the only session both courses trade
SWING_K = 3                         # fractal size for "obvious" swing points
FRESH_BARS = 8                      # setup must have completed within 8 bars (40min on 5m)

_cache = {}


def _bars_cached(symbol, interval, lookback, ttl=90):
    key = (symbol, interval, lookback)
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    data = get_bars(symbol, interval, lookback)
    _cache[key] = (time.time(), data)
    return data


def _rth(bars, day):
    """Regular-hours bars (>=9:30 ET) of the given ET date."""
    out = []
    for b in bars:
        t = ict.bar_et(b)
        if t.date() == day and (t.hour * 60 + t.minute) >= 570:
            out.append(b)
    return out


def _liquidity_pools(symbol, bars, day):
    """The pre-market level map PB marks every morning (step 0 of his prep)."""
    pools = {"buy": [], "sell": []}
    try:
        daily = _bars_cached(symbol, "1d", "1mo", ttl=600)
        prev = [b for b in daily if ict.bar_et(b).date() < day]
        if prev:
            pools["buy"].append(("prev day high", prev[-1]["h"]))
            pools["sell"].append(("prev day low", prev[-1]["l"]))
    except Exception:
        pass

    def session(name, sel):
        sbars = [b for b in bars if sel(ict.bar_et(b))]
        if sbars:
            pools["buy"].append((f"{name} high", max(b["h"] for b in sbars)))
            pools["sell"].append((f"{name} low", min(b["l"] for b in sbars)))

    prev_day = day - timedelta(days=1)
    session("Asia", lambda t: t.date() == prev_day and t.hour >= 20)          # 8pm-12am ET
    session("London", lambda t: t.date() == day and 2 <= t.hour < 5)          # 2am-5am ET

    # data wicks: the H/L of the candle printed at each red USD release [PB Ep7]
    try:
        seen = set()
        for e in news.usd_events(day=day, impacts=("High",)):
            ts = e["time"].timestamp()
            bar = next((b for b in bars if b["t"] <= ts < b["t"] + 300), None)
            if bar and bar["t"] not in seen:
                seen.add(bar["t"])
                pools["buy"].append((f"data wick high ({e['title']})", bar["h"]))
                pools["sell"].append((f"data wick low ({e['title']})", bar["l"]))
    except Exception:
        pass          # news feed down → scanner keeps working without data wicks
    return pools


def _smt(symbol, side, sweep_bar, now_ts, day):
    """Did the companion index FAIL to sweep alongside us? (bullish/bearish SMT)"""
    comp = COMPANION.get(symbol)
    if not comp:
        return None
    try:
        cbars = [b for b in _bars_cached(comp, TIMEFRAME, LOOKBACK) if b["t"] <= now_ts]
        csess = _rth(cbars, day)
        if len(csess) < SWING_K * 2 + 3:
            return None
        c_hi, c_lo = ict.swings(csess, k=SWING_K)
        window = [b for b in csess if abs(b["t"] - sweep_bar["t"]) <= 15 * 60]
        if not window:
            return None
        if side == "long":
            prior = [j for j in c_lo if csess[j]["t"] < sweep_bar["t"]]
            if not prior:
                return None
            ref = csess[prior[-1]]["l"]
            failed = all(b["l"] >= ref for b in window)
            return (f"bullish SMT ✅ — {display(comp)} held its low while {display(symbol)} swept"
                    if failed else f"no SMT — {display(comp)} swept its low too")
        prior = [j for j in c_hi if csess[j]["t"] < sweep_bar["t"]]
        if not prior:
            return None
        ref = csess[prior[-1]]["h"]
        failed = all(b["h"] <= ref for b in window)
        return (f"bearish SMT ✅ — {display(comp)} held its high while {display(symbol)} swept"
                if failed else f"no SMT — {display(comp)} swept its high too")
    except Exception:
        return None


def check(symbol, bars):
    if len(bars) < 40 or not ict.in_window(bars[-1], *KILLZONE):
        return None
    now = ict.bar_et(bars[-1])
    try:
        if news.in_blackout(now):     # PB: no entries −5/+10 min around red USD news
            return None
    except Exception:
        pass
    sess = _rth(bars, now.date())
    if len(sess) < SWING_K * 2 + 4:
        return None
    pools = _liquidity_pools(symbol, bars, now.date())
    sw_hi, sw_lo = ict.swings(sess, k=SWING_K)
    return (_scan(symbol, sess, pools, sw_hi, sw_lo, "long")
            or _scan(symbol, sess, pools, sw_hi, sw_lo, "short"))


def _scan(symbol, sess, pools, sw_hi, sw_lo, side):
    last = sess[-1]
    long_side = side == "long"

    # -- 1. SWEEP: latest raid of a significant opposing pool --
    events = []
    levels = pools["sell"] if long_side else pools["buy"]
    for i, b in enumerate(sess):
        for name, level in levels:
            if long_side and b["l"] < level and b["c"] > level:
                events.append((i, name, level))
            elif not long_side and b["h"] > level and b["c"] < level:
                events.append((i, name, level))
        lvl = (ict.swept_low(sess, i, sw_lo) if long_side
               else ict.swept_high(sess, i, sw_hi))
        if lvl is not None:
            events.append((i, "intraday swing " + ("low" if long_side else "high"), lvl))

    # -- 2. MSS: body close through the most recent opposing swing --
    for i, pool_name, pool_level in sorted(events, key=lambda e: -e[0]):
        mss_j, mss_level = None, None
        for j in range(i + 1, len(sess)):
            lvl = (ict.structure_shift_up(sess, j, sw_hi) if long_side
                   else ict.structure_shift_down(sess, j, sw_lo))
            if lvl is not None:
                mss_j, mss_level = j, lvl
                break
        if mss_j is None:
            continue

        # -- 3. ENTRY ZONE: inversion FVG preferred, fresh FVG fallback --
        zone, zone_kind, zone_t = None, None, None
        opposing = (ict.bearish_fvgs(sess, start=i) if long_side
                    else ict.bullish_fvgs(sess, start=i))
        for g in opposing:
            # inversion = body close fully beyond the far edge (Tiz's strict rule)
            inv = next((k for k in range(g["i"] + 1, len(sess))
                        if (long_side and sess[k]["c"] > g["hi"])
                        or (not long_side and sess[k]["c"] < g["lo"])), None)
            if inv is not None:
                zone, zone_kind, zone_t = g, "inversion FVG (IFVG)", inv
        if zone is None:
            aligned = (ict.bullish_fvgs(sess, start=i) if long_side
                       else ict.bearish_fvgs(sess, start=i))
            for g in aligned:
                violated = any((sess[k]["c"] < g["lo"]) if long_side
                               else (sess[k]["c"] > g["hi"])
                               for k in range(g["i"] + 1, len(sess)))
                if not violated:
                    zone, zone_kind, zone_t = g, "fresh FVG", g["i"]
        if zone is None:
            continue

        # -- freshness: alert while it's actionable, not hours later --
        last_i = len(sess) - 1
        touching = zone["lo"] <= (last["l"] if long_side else last["h"]) <= zone["hi"] \
            or (long_side and last["l"] <= zone["hi"] and last["c"] >= zone["lo"]) \
            or (not long_side and last["h"] >= zone["lo"] and last["c"] <= zone["hi"])
        if (last_i - max(mss_j, zone_t)) > FRESH_BARS and not touching:
            continue

        # -- 4. confluences (reported for YOUR judgment) --
        sweep_bar = sess[i]
        leg_ext = (max(b["h"] for b in sess[i:]) if long_side
                   else min(b["l"] for b in sess[i:]))
        leg_origin = sweep_bar["l"] if long_side else sweep_bar["h"]
        eq = (leg_origin + leg_ext) / 2
        entry = (zone["lo"] + zone["hi"]) / 2
        in_disc = entry <= eq if long_side else entry >= eq
        displaced = any(ict.displacement(sess, k)
                        for k in range(mss_j, min(mss_j + 3, len(sess))))
        smt = _smt(symbol, side, sweep_bar, last["t"], ict.bar_et(last).date())

        # -- 5. suggested risk frame (paper numbers — you decide) --
        buffer = max(entry * 0.0002, 0.01)
        stop = (sweep_bar["l"] - buffer) if long_side else (sweep_bar["h"] + buffer)
        internal = ([sess[q]["h"] for q in sw_hi if sess[q]["h"] > entry] if long_side
                    else [sess[q]["l"] for q in sw_lo if sess[q]["l"] < entry])
        tp1 = (min(internal) if long_side else max(internal)) if internal else None
        risk = abs(entry - stop)
        rr = (abs(tp1 - entry) / risk) if (tp1 and risk) else None
        if rr is not None and rr > 15:
            rr = None   # zone sits on the stop — a ratio that inflated is noise, not signal

        t_sweep = ict.bar_et(sweep_bar).strftime("%H:%M")
        t_mss = ict.bar_et(sess[mss_j]).strftime("%H:%M")
        details = [
            f"1️⃣ Swept **{pool_name}** @ {pool_level:,.2f} ({t_sweep} ET)",
            f"2️⃣ MSS {'▲' if long_side else '▼'} body close through {mss_level:,.2f} ({t_mss} ET)",
            f"3️⃣ Entry zone: {zone_kind} {zone['lo']:,.2f} – {zone['hi']:,.2f}"
            + ("  ← price touching now" if touching else ""),
            f"{'✅' if in_disc else '⚠️'} {'Discount' if long_side else 'Premium'}: "
            f"zone {'at/past' if in_disc else 'NOT at'} EQ ({eq:,.2f})",
            f"{'✅' if displaced else '—'} Displacement on the shift",
        ]
        if smt:
            details.append(("✅ " if "✅" in smt else "— ") + smt)
        details.append(f"📐 Suggested: stop {stop:,.2f}"
                       + (f" | TP1 (internal) {tp1:,.2f} | ≈{rr:.1f}R" if rr else ""))
        return {
            "symbol": symbol,
            "setup": NAME,
            "price": last["c"],
            "side": "LONG" if long_side else "SHORT",
            "reason": f"{'LONG' if long_side else 'SHORT'} setup — "
                      f"swept {pool_name} → MSS → {zone_kind} (NY AM killzone)",
            "details": details,
        }
    return None
