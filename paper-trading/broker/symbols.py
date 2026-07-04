"""
symbols.py — one symbol, two worlds.

Our free data feed (Yahoo) and TradingView name the same futures contract
differently:

    market                          data feed    TradingView
    NASDAQ-100 E-mini (CME)         NQ=F         CME_MINI:NQ1!
    S&P 500 E-mini (CME)            ES=F         CME_MINI:ES1!

Internally (data, logs) we use the feed symbol; everything Adam SEES
(alert titles, chart links) uses the TradingView name.
"""

from urllib.parse import quote

TV_SYMBOLS = {
    "NQ=F": "CME_MINI:NQ1!",
    "ES=F": "CME_MINI:ES1!",
}

DISPLAY = {
    "NQ=F": "NQ1!",
    "ES=F": "ES1!",
}


def display(symbol):
    """Human/TradingView-facing name for a data-feed symbol."""
    return DISPLAY.get(symbol, symbol)


def tv_link(symbol):
    """A chart URL that actually opens in TradingView."""
    tv = TV_SYMBOLS.get(symbol, symbol)
    return f"https://www.tradingview.com/chart/?symbol={quote(tv, safe='')}"
