"""
ict.py — ICT / smart-money concept primitives.

These are the chart-geometry building blocks used by ICT-style setups
(as taught by PB Trading, Tiz Trades, and ICT himself):

  * swing highs/lows        — local turning points; where "liquidity" rests
  * liquidity sweep         — price wicks THROUGH a prior high/low, then closes
                              back inside (stop-hunt / "raid")
  * fair value gap (FVG)    — 3-candle imbalance: a gap between candle 1's high
                              and candle 3's low (bullish) that price often
                              returns to before continuing
  * displacement            — an unusually large, decisive candle body showing
                              real buying/selling, not drift
  * market structure shift  — after a sweep, price CLOSES beyond the most
                              recent opposing swing → the turn is confirmed
  * killzones               — the time windows (in ET) when these plays are taken

All functions take bars: [{"t","o","h","l","c","v"}, ...] oldest-first.
Pure stdlib; timezone handling via zoneinfo.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


# ---------- time ----------

def bar_et(bar):
    """The bar's timestamp as an Eastern-Time datetime (ICT time is always ET)."""
    return datetime.fromtimestamp(bar["t"], tz=ET)


def in_window(bar, start_hm, end_hm):
    """Is this bar inside [start,end) ET? start_hm/end_hm like (9,30)."""
    t = bar_et(bar)
    mins = t.hour * 60 + t.minute
    return start_hm[0] * 60 + start_hm[1] <= mins < end_hm[0] * 60 + end_hm[1]


# ---------- structure ----------

def swings(bars, k=2):
    """
    Find swing highs/lows: bar i is a swing high if its high is the highest of
    the k bars on each side (classic fractal). Returns two lists of indices.
    """
    sw_hi, sw_lo = [], []
    for i in range(k, len(bars) - k):
        window = bars[i - k:i + k + 1]
        if bars[i]["h"] == max(b["h"] for b in window):
            sw_hi.append(i)
        if bars[i]["l"] == min(b["l"] for b in window):
            sw_lo.append(i)
    return sw_hi, sw_lo


def swept_low(bars, i, swing_lows):
    """
    Did bar i SWEEP a prior swing low? True when its low pokes below the most
    recent swing low before i, but it CLOSES back above it (wick raid).
    Returns the swept level or None.
    """
    prior = [j for j in swing_lows if j < i]
    if not prior:
        return None
    level = bars[prior[-1]]["l"]
    b = bars[i]
    if b["l"] < level and b["c"] > level:
        return level
    return None


def swept_high(bars, i, swing_highs):
    """Mirror of swept_low: wick above a prior swing high, close back below."""
    prior = [j for j in swing_highs if j < i]
    if not prior:
        return None
    level = bars[prior[-1]]["h"]
    b = bars[i]
    if b["h"] > level and b["c"] < level:
        return level
    return None


def structure_shift_up(bars, i, swing_highs):
    """
    Bullish market-structure shift (MSS): bar i CLOSES above the most recent
    swing high before i. Returns the broken level or None.
    """
    prior = [j for j in swing_highs if j < i]
    if not prior:
        return None
    level = bars[prior[-1]]["h"]
    return level if bars[i]["c"] > level else None


def structure_shift_down(bars, i, swing_lows):
    """Bearish MSS: bar i closes below the most recent swing low."""
    prior = [j for j in swing_lows if j < i]
    if not prior:
        return None
    level = bars[prior[-1]]["l"]
    return level if bars[i]["c"] < level else None


# ---------- imbalance ----------

def bullish_fvgs(bars, start=0):
    """
    Bullish fair value gaps in bars[start:]:
    candle1 high < candle3 low leaves a gap [c1.h, c3.l] the market skipped.
    Returns [{"i": index_of_candle3, "lo": gap_bottom, "hi": gap_top}].
    """
    out = []
    for i in range(max(start, 2), len(bars)):
        c1, c3 = bars[i - 2], bars[i]
        if c1["h"] < c3["l"]:
            out.append({"i": i, "lo": c1["h"], "hi": c3["l"]})
    return out


def bearish_fvgs(bars, start=0):
    """Bearish FVG: candle1 low > candle3 high; gap [c3.h, c1.l]."""
    out = []
    for i in range(max(start, 2), len(bars)):
        c1, c3 = bars[i - 2], bars[i]
        if c1["l"] > c3["h"]:
            out.append({"i": i, "lo": c3["h"], "hi": c1["l"]})
    return out


def displacement(bars, i, mult=1.5, lookback=20):
    """
    Is bar i a displacement candle? Its BODY is `mult`x the average body of the
    prior `lookback` bars. Displacement = conviction; drift = noise.
    """
    if i < lookback:
        return False
    avg_body = sum(abs(b["c"] - b["o"]) for b in bars[i - lookback:i]) / lookback
    return abs(bars[i]["c"] - bars[i]["o"]) >= mult * avg_body if avg_body else False


def resample(bars, minutes):
    """Aggregate bars into a larger timeframe (e.g. 5m bars -> 60m bars)."""
    size = minutes * 60
    out = []
    bucket = None
    for b in bars:
        key = b["t"] - (b["t"] % size)
        if bucket is None or bucket["t"] != key:
            if bucket:
                out.append(bucket)
            bucket = dict(t=key, o=b["o"], h=b["h"], l=b["l"], c=b["c"], v=b["v"])
        else:
            bucket["h"] = max(bucket["h"], b["h"])
            bucket["l"] = min(bucket["l"], b["l"])
            bucket["c"] = b["c"]
            bucket["v"] += b["v"]
    if bucket:
        out.append(bucket)
    return out


def unfilled_fvgs(bars, bullish=True):
    """FVGs that price has NOT fully traded through since they formed.
    These are the 'unfilled gaps' PB uses as his key levels / draws."""
    out = []
    for g in (bullish_fvgs(bars) if bullish else bearish_fvgs(bars)):
        later = bars[g["i"] + 1:]
        filled = (any(b["l"] <= g["lo"] for b in later) if bullish
                  else any(b["h"] >= g["hi"] for b in later))
        if not filled:
            out.append(g)
    return out


# ---------- reference levels ----------

def session_levels(bars, start_hm, end_hm):
    """High/low made inside an ET window (e.g. Asia range, London, premarket)."""
    sess = [b for b in bars if in_window(b, start_hm, end_hm)]
    if not sess:
        return None, None
    return max(b["h"] for b in sess), min(b["l"] for b in sess)


def prev_day_levels(daily_bars):
    """Previous COMPLETED day's high/low from daily bars."""
    if len(daily_bars) < 2:
        return None, None
    d = daily_bars[-2]
    return d["h"], d["l"]
