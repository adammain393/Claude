"""
example_ema_reclaim.py — a TEMPLATE setup, so you can see how yours will plug in.

This example fires a LONG signal when, on the latest bar:
  1. the 9-EMA crosses above the 20-EMA   (momentum turning up), AND
  2. price is above VWAP                    (buyers in control on the day)

When you teach me YOUR setup, I'll write a file just like this with your rules.
A strategy only needs a NAME and a check(symbol, bars) function that returns
either None (no setup) or a signal dict.
"""

from broker import indicators as ta

NAME = "EMA9/20 reclaim above VWAP (example)"


def check(symbol, bars):
    closes = [b["c"] for b in bars]
    if len(closes) < 25:
        return None

    ema9 = ta.ema_series(closes, 9)
    ema20 = ta.ema_series(closes, 20)
    if len(ema9) < 2 or len(ema20) < 2:
        return None

    crossed_up = ema9[-2] <= ema20[-2] and ema9[-1] > ema20[-1]
    vwap = ta.vwap(bars)
    price = closes[-1]
    above_vwap = vwap is not None and price > vwap

    if crossed_up and above_vwap:
        return {
            "symbol": symbol,
            "setup": NAME,
            "price": price,
            "reason": "9-EMA crossed above 20-EMA while price is above VWAP",
            "details": [
                f"Price: ${price:.2f}",
                f"EMA9: ${ema9[-1]:.2f}  |  EMA20: ${ema20[-1]:.2f}",
                f"VWAP: ${vwap:.2f}",
                f"RSI(14): {ta.rsi(closes):.0f}",
            ],
        }
    return None
