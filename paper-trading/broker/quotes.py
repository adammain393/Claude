"""
quotes.py — fetch a live-ish price for a stock symbol.

Design notes (this is the "market data" layer):
- Uses ONLY the Python standard library, so there is nothing to install.
- Primary source: Yahoo Finance's public chart endpoint (near real-time,
  ~15 min delayed for some symbols). Fallback: Stooq CSV (very reliable).
- Later, in Phase 2, we'll add a Questrade quotes source with the SAME
  get_quote() shape, so the rest of the code won't have to change.
"""

import json
import urllib.request
import urllib.error

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) paper-trading/0.1"


class QuoteError(Exception):
    pass


def _http_get(url: str, timeout: float = 8.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _from_yahoo(symbol: str) -> float:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=1d"
    data = json.loads(_http_get(url))
    result = data["chart"]["result"][0]
    price = result["meta"].get("regularMarketPrice")
    if price is None:
        raise QuoteError("Yahoo returned no regularMarketPrice")
    return float(price)


def _from_stooq(symbol: str) -> float:
    # Stooq wants US tickers as e.g. "aapl.us"
    sym = symbol.lower()
    if "." not in sym:
        sym = sym + ".us"
    url = f"https://stooq.com/q/l/?s={sym}&f=sd2t2ohlcv&h&e=csv"
    text = _http_get(url).decode("utf-8", "replace").strip().splitlines()
    if len(text) < 2:
        raise QuoteError("Stooq returned no data")
    # header: Symbol,Date,Time,Open,High,Low,Close,Volume
    row = text[1].split(",")
    close = row[6]
    if close in ("", "N/D"):
        raise QuoteError("Stooq close is N/D (market closed / bad symbol)")
    return float(close)


def get_quote(symbol: str) -> float:
    """Return the latest price for `symbol`, trying Yahoo then Stooq."""
    symbol = symbol.strip().upper()
    errors = []
    for source in (_from_yahoo, _from_stooq):
        try:
            return source(symbol)
        except (urllib.error.URLError, KeyError, IndexError, ValueError,
                QuoteError, TimeoutError) as e:
            errors.append(f"{source.__name__}: {e}")
    raise QuoteError(f"Could not get a quote for {symbol}. Tried: {' | '.join(errors)}")


if __name__ == "__main__":
    import sys
    sym = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    print(f"{sym}: ${get_quote(sym):,.2f}")
