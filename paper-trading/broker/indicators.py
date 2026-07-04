"""
indicators.py — the math behind common day-trading setups.

Pure Python (no numpy/pandas needed). Each function takes a list of numbers
(usually closing prices) or a list of candles and returns the indicator series
or its latest value. These are the building blocks your setup rules use.
"""


def sma(values, period):
    """Simple moving average — the plain average of the last `period` values."""
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def ema_series(values, period):
    """Exponential moving average (weights recent prices more). Returns a series."""
    if len(values) < period:
        return []
    k = 2 / (period + 1)
    out = [sum(values[:period]) / period]           # seed with an SMA
    for price in values[period:]:
        out.append(price * k + out[-1] * (1 - k))
    return out


def ema(values, period):
    s = ema_series(values, period)
    return s[-1] if s else None


def rsi(values, period=14):
    """Relative Strength Index (0-100). <30 = oversold, >70 = overbought."""
    if len(values) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(values)):
        change = values[i] - values[i - 1]
        gains.append(max(change, 0))
        losses.append(max(-change, 0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def vwap(bars):
    """
    Volume-Weighted Average Price — the average price weighted by volume.
    Huge in day trading: many traders buy above VWAP / sell below it.
    Computed over the bars you pass in (pass today's bars for session VWAP).
    """
    cum_pv = 0.0
    cum_v = 0.0
    for b in bars:
        typical = (b["h"] + b["l"] + b["c"]) / 3
        cum_pv += typical * b["v"]
        cum_v += b["v"]
    return cum_pv / cum_v if cum_v else None


def session_high_low(bars):
    """Highest high and lowest low across the given bars (e.g. today's range)."""
    return max(b["h"] for b in bars), min(b["l"] for b in bars)


def avg_volume(bars, period):
    """Average volume of the last `period` bars — to detect volume spikes."""
    vols = [b["v"] for b in bars]
    if len(vols) < period:
        return None
    return sum(vols[-period:]) / period
