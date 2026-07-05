"""
ict_pb.py — PB Trading's ICT day-trading setup, v2.

v1 was reconstructed from his TEACHING course. v2 corrects it against 20 of
his LIVE-TRADE recap videos — what he actually does with money on:

  * HARD GATE — the sweep must happen AT an unfilled higher-timeframe FVG
    (15m / 1H / 4H). "I don't take trades just off liquidity label like
    previously high, previously low, London high, London low, none of that."
    The session/PD pools still matter, but only when they sit at an HTF gap.
  * ENTRY — he never rests a limit inside the gap. Every recorded entry is a
    MARKET entry on the confirming body close ("I'm not trying to enter these
    halfass closes... I like that. Bang."). So the alert's entry ≈ the
    confirmation candle's close, and the resolver treats fills as immediate.
  * STOP — beyond the full manipulation wick; on an oversized wick, half-wick
    ("I hate these large wicks... I'm just going to go like half the wick").
    Never widened; he halves SIZE instead when the stop is wide.
  * TARGET — full close at ~1:1..1:2 or the first internal pool ("We're just
    going to go for that one to one" / "claim the low-hanging fruit").
    No partials, no runner, in 10 straight recap videos.
  * SMT — optional at entry ("Do I even need to look at ES in this case?
    Nah"), but a MANDATORY EXIT: "if there's an SMT at your target on ES,
    then you must close on NQ."
  * RE-SWEEP — second raid of the same level = his highest-conviction
    trigger ("once you got the re-sweep of the 5-minute that was an absolute
    lock"). Tagged in the alert when detected.
  * EQ premium/discount — never once drawn in 20 recaps; he takes premium
    entries knowingly. Kept as info only.
  * Overnight — he skips days after big one-way overnight moves ("we've sold
    off 337 points since 6:00 a.m.... let's just be reasonable"). Warned in
    the alert; threshold (1% of price) is OUR guess, not his — unconfirmed.

Still his: NY AM killzone only (all recorded trades 9:31-10:30), one trade a
day, sweep → body-close MSS → inversion-FVG trigger (plain FVG accepted).
The scanner detects on 5m; he confirms down to 30s-1m — so treat alerts as
"go look at the 1-minute now", not as the entry itself.
"""

import time
from datetime import timedelta

from broker.bars import get_bars
from broker import ict
from broker import news
from broker.symbols import display

NAME = "PB-ICT v2: sweep at HTF gap → MSS → confirmation close (NY AM)"
DEFAULT_SYMBOLS = ["NQ=F", "ES=F"]  # NQ1! and ES1!; each is the other's SMT pair
TIMEFRAME = "5m"
LOOKBACK = "5d"
COMPANION = {"NQ=F": "ES=F", "ES=F": "NQ=F", "QQQ": "SPY", "SPY": "QQQ"}
KILLZONE = ((9, 30), (11, 0))       # every recorded live entry: 9:31-10:30 ET
SWING_K = 3                         # fractal size for "obvious" swings (unconfirmed)
FRESH_BARS = 8                      # confirmation must be within 8 bars (40 min on 5m)
HTF_LEVELS = ((15, "15m"), (60, "1H"), (240, "4H"))
OVERNIGHT_WARN_PCT = 1.0            # warn above this overnight range (UNCONFIRMED guess)

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


def _htf_arrays(bars):
    """PB's 'key levels', the v2 hard gate: unfilled 15m/1H/4H FVGs plus
    HTF intermediate highs/lows ("I love the intermediate highs and lows").
    Both appear in every taken trade across the recaps."""
    arrays = {"bull": [], "bear": [], "lows": [], "highs": []}
    for minutes, label in HTF_LEVELS:
        rs = ict.resample(bars, minutes)
        for g in ict.unfilled_fvgs(rs, bullish=True):
            arrays["bull"].append({"tf": label, "lo": g["lo"], "hi": g["hi"]})
        for g in ict.unfilled_fvgs(rs, bullish=False):
            arrays["bear"].append({"tf": label, "lo": g["lo"], "hi": g["hi"]})
        sw_hi, sw_lo = ict.swings(rs, k=2)
        arrays["highs"] += [{"tf": label, "level": rs[q]["h"]} for q in sw_hi]
        arrays["lows"] += [{"tf": label, "level": rs[q]["l"]} for q in sw_lo]
    return arrays


def _overnight_note(bars, day):
    """Warn on big one-way overnight sessions — PB skips those mornings."""
    prev_day = day - timedelta(days=1)
    on = [b for b in bars
          if (ict.bar_et(b).date() == prev_day and ict.bar_et(b).hour >= 18)
          or (ict.bar_et(b).date() == day and (ict.bar_et(b).hour * 60 + ict.bar_et(b).minute) < 570)]
    if not on:
        return None
    rng = max(b["h"] for b in on) - min(b["l"] for b in on)
    pct = rng / on[-1]["c"] * 100
    if pct >= OVERNIGHT_WARN_PCT:
        return (f"⚠️ Big overnight range ({rng:,.0f} pts, {pct:.1f}%) — PB skips "
                f"mornings after one-way overnight moves (threshold unconfirmed)")
    return None


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
    htf = _htf_arrays(bars)
    note = _overnight_note(bars, now.date())
    sw_hi, sw_lo = ict.swings(sess, k=SWING_K)
    return (_scan(symbol, sess, pools, htf, note, sw_hi, sw_lo, "long")
            or _scan(symbol, sess, pools, htf, note, sw_hi, sw_lo, "short"))


def _scan(symbol, sess, pools, htf, overnight_note, sw_hi, sw_lo, side):
    last = sess[-1]
    long_side = side == "long"

    # -- 1. SWEEP: raids of significant opposing pools --
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

    aligned_htf = htf["bull"] if long_side else htf["bear"]

    for i, pool_name, pool_level in sorted(events, key=lambda e: -e[0]):
        sweep_bar = sess[i]

        # -- v2 HARD GATE: the raid must interact with an HTF key level:
        # an unfilled 15m/1H/4H FVG, or an HTF intermediate high/low.
        # "I don't take trades just off liquidity label... none of that."
        wick_lo = sweep_bar["l"] if long_side else pool_level
        wick_hi = pool_level if long_side else sweep_bar["h"]
        key_level = None
        gap = next((a for a in aligned_htf
                    if wick_lo <= a["hi"] and wick_hi >= a["lo"]), None)
        if gap:
            key_level = f"{gap['tf']} unfilled FVG {gap['lo']:,.2f} – {gap['hi']:,.2f}"
        else:
            swings_htf = htf["lows"] if long_side else htf["highs"]
            hit = next((s for s in swings_htf if wick_lo <= s["level"] <= wick_hi), None)
            if hit:
                key_level = (f"{hit['tf']} intermediate "
                             f"{'low' if long_side else 'high'} {hit['level']:,.2f}")
        if key_level is None:
            continue

        # re-sweep of the same level earlier today = highest conviction
        tol = pool_level * 0.0005
        resweep = any(abs(lvl - pool_level) <= tol and j < i
                      for j, _, lvl in events)

        # -- 2. MSS: body close through the most recent opposing swing --
        mss_j, mss_level = None, None
        for j in range(i + 1, len(sess)):
            lvl = (ict.structure_shift_up(sess, j, sw_hi) if long_side
                   else ict.structure_shift_down(sess, j, sw_lo))
            if lvl is not None:
                mss_j, mss_level = j, lvl
                break
        if mss_j is None:
            continue

        # -- 3. CONFIRMATION: inversion FVG preferred, fresh FVG fallback --
        zone, zone_kind, zone_t = None, None, None
        opposing = (ict.bearish_fvgs(sess, start=i) if long_side
                    else ict.bullish_fvgs(sess, start=i))
        for g in opposing:
            # inversion = body close fully beyond the far edge (his strict rule)
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

        # -- freshness: the confirmation must be recent (he enters ON the close)
        last_i = len(sess) - 1
        if (last_i - max(mss_j, zone_t)) > FRESH_BARS:
            continue

        # -- confluences (reported; only the HTF gate is hard) --
        leg_ext = (max(b["h"] for b in sess[i:]) if long_side
                   else min(b["l"] for b in sess[i:]))
        leg_origin = sweep_bar["l"] if long_side else sweep_bar["h"]
        eq = (leg_origin + leg_ext) / 2
        displaced = any(ict.displacement(sess, k)
                        for k in range(mss_j, min(mss_j + 3, len(sess))))
        smt = _smt(symbol, side, sweep_bar, last["t"], ict.bar_et(last).date())

        # -- v2 risk frame: MARKET entry on the confirming close --
        entry = last["c"]
        avg_range = sum(b["h"] - b["l"] for b in sess[-20:]) / min(20, len(sess))
        wick_depth = (pool_level - sweep_bar["l"]) if long_side else (sweep_bar["h"] - pool_level)
        half_wick = wick_depth > 1.2 * avg_range        # "large wick → half the wick"
        buffer = max(entry * 0.0002, 0.01)
        if long_side:
            stop = (pool_level - 0.5 * wick_depth) if half_wick else (sweep_bar["l"] - buffer)
        else:
            stop = (pool_level + 0.5 * wick_depth) if half_wick else (sweep_bar["h"] + buffer)
        risk = abs(entry - stop)
        if risk <= 0:
            continue
        tp_1r = entry + risk if long_side else entry - risk
        internal = ([sess[q]["h"] for q in sw_hi if sess[q]["h"] > entry] if long_side
                    else [sess[q]["l"] for q in sw_lo if sess[q]["l"] < entry])
        tp_internal = (min(internal) if long_side else max(internal)) if internal else None
        # he closes in full at the NEARER of ~1R / first internal pool
        candidates = [x for x in (tp_1r, tp_internal) if x is not None]
        tp1 = (min(candidates) if long_side else max(candidates)) if candidates else None
        opposite = pools["buy"] if long_side else pools["sell"]
        unswept = [lvl for _, lvl in opposite
                   if (lvl > entry if long_side else lvl < entry)
                   and not any((b["h"] >= lvl if long_side else b["l"] <= lvl) for b in sess)]
        tp2 = (min(unswept) if long_side else max(unswept)) if unswept else None

        t_sweep = ict.bar_et(sweep_bar).strftime("%H:%M")
        t_mss = ict.bar_et(sess[mss_j]).strftime("%H:%M")
        in_disc = entry <= eq if long_side else entry >= eq
        details = [
            f"1️⃣ Swept **{pool_name}** @ {pool_level:,.2f} ({t_sweep} ET)"
            + ("  🔁 RE-SWEEP — his highest-conviction trigger" if resweep else ""),
            f"🧲 At HTF key level: {key_level}",
            f"2️⃣ MSS {'▲' if long_side else '▼'} body close through {mss_level:,.2f} ({t_mss} ET)",
            f"3️⃣ Confirmation: {zone_kind} {zone['lo']:,.2f} – {zone['hi']:,.2f}"
            " — he enters at market on this close (check the 1-minute now)",
            f"{'✅' if displaced else '⚠️'} Displacement on the shift"
            + ("" if displaced else " — MISSING; he calls no-displacement entries a mistake"),
            f"{'✅' if in_disc else 'ℹ️'} {'Discount' if long_side else 'Premium'} vs EQ "
            f"{eq:,.2f} (info only — he takes premium entries knowingly)",
        ]
        if smt:
            details.append(("✅ " if "✅" in smt else "— ") + smt)
        if overnight_note:
            details.append(overnight_note)
        risk_line = (f"📐 Market entry ≈ {entry:,.2f} | stop {stop:,.2f}"
                     + (" (half-wick rule)" if half_wick else ""))
        if tp1:
            risk_line += f" | TP1 {tp1:,.2f} (full close — he takes no partials)"
        if tp2:
            risk_line += f" | external draw {tp2:,.2f}"
        details.append(risk_line)
        details.append("🚪 Exit rule: SMT at your target on the pair → close immediately. One trade a day.")
        return {
            "symbol": symbol,
            "setup": NAME,
            "price": last["c"],
            "side": "LONG" if long_side else "SHORT",
            "reason": f"{'LONG' if long_side else 'SHORT'} — swept {pool_name} at "
                      f"HTF key level → MSS → {zone_kind} (NY AM)",
            "details": details,
            # machine-readable levels — resolve.py walks these forward for stats
            "levels": {
                "entry": round(entry, 2), "stop": round(stop, 2),
                "tp1": round(tp1, 2) if tp1 else None,
                "tp1_internal": round(tp_internal, 2) if tp_internal else None,
                "tp_1r": round(tp_1r, 2),
                "tp2": round(tp2, 2) if tp2 else None,
                "zone_lo": round(zone["lo"], 2), "zone_hi": round(zone["hi"], 2),
                "bar_time": last["t"],
                "market": True,        # entry = confirming close, filled immediately
            },
        }
    return None
