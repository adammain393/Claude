"""
bars.py — fetch intraday candles (OHLCV) for a symbol.

A "candle" / "bar" is one time slice of price: open, high, low, close, volume.
Day-trading setups are built on these (e.g. 1-min or 5-min bars).

Source: Yahoo chart endpoint (stdlib only, no install). Free data is delayed
~15 min — fine for building; we upgrade the feed later.
"""

import json
import urllib.request

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) paper-trading/0.1"

# Yahoo-supported intraday intervals and how far back they allow.
_VALID = {"1m", "2m", "5m", "15m", "30m", "60m", "1h", "1d"}


def get_bars(symbol: str, interval: str = "5m", lookback: str = "5d"):
    """
    Return a list of candles, oldest first:
        [{"t": epoch_seconds, "o":, "h":, "l":, "c":, "v":}, ...]
    """
    symbol = symbol.strip().upper()
    if interval not in _VALID:
        raise ValueError(f"interval must be one of {sorted(_VALID)}")
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
           f"?interval={interval}&range={lookback}")
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())

    result = data["chart"]["result"][0]
    ts = result.get("timestamp") or []
    q = result["indicators"]["quote"][0]
    bars = []
    for i, t in enumerate(ts):
        o, h, l, c, v = q["open"][i], q["high"][i], q["low"][i], q["close"][i], q["volume"][i]
        if None in (o, h, l, c):        # skip gap bars
            continue
        bars.append({"t": t, "o": o, "h": h, "l": l, "c": c, "v": v or 0})
    if not bars:
        raise ValueError(f"No intraday bars returned for {symbol}")
    return bars


if __name__ == "__main__":
    import sys
    sym = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    b = get_bars(sym, "5m", "1d")
    print(f"{sym}: {len(b)} five-minute bars")
    last = b[-1]
    print(f"last bar close=${last['c']:.2f}  high=${last['h']:.2f}  vol={last['v']:,}")
