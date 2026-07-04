"""
paper_broker.py — a simulated brokerage account (NO real money, NO real orders).

Supports:
  * stocks/ETFs — long only, cash-settled (price × shares)
  * FUTURES (NQ/ES minis & micros) — LONGS **AND SHORTS**, correct futures math

Futures differ from stocks in two ways that matter for honest paper numbers:
  1. P/L = points moved × POINT VALUE × contracts — not price × quantity.
     NQ = $20/pt, MNQ = $2/pt, ES = $50/pt, MES = $5/pt.
  2. Opening a position posts MARGIN, it doesn't spend the notional. We
     enforce a simplified initial margin per contract, and settle realized
     P/L into cash whenever a position is reduced, closed, or flipped.

Positions carry SIGNED quantity: +3 = long 3 contracts, -3 = short 3.
Everything persists to state/portfolio.json between runs.
"""

import json
import os
from datetime import datetime, timezone

from .quotes import get_quote

DEFAULT_STATE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "state", "portfolio.json")

# Approximate CME initial margins — they drift over time; close enough for paper.
FUTURES = {
    "NQ=F":  {"pv": 20.0, "margin": 25000.0, "label": "NQ E-mini, $20/pt"},
    "MNQ=F": {"pv": 2.0,  "margin": 2500.0,  "label": "MNQ micro, $2/pt"},
    "ES=F":  {"pv": 50.0, "margin": 16000.0, "label": "ES E-mini, $50/pt"},
    "MES=F": {"pv": 5.0,  "margin": 1600.0,  "label": "MES micro, $5/pt"},
}


class OrderError(Exception):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")


class PaperBroker:
    def __init__(self, starting_cash: float = 100_000.0, state_path: str = DEFAULT_STATE,
                 commission: float = 0.0):
        self.state_path = state_path
        self.commission = commission
        self.starting_cash = starting_cash
        self.cash = starting_cash
        self.positions = {}   # symbol -> {"qty": signed int, "avg_price": float}
        self.realized_pnl = 0.0
        self.history = []
        self._load()

    # ---------- persistence ----------
    def _load(self):
        if os.path.exists(self.state_path):
            with open(self.state_path) as f:
                s = json.load(f)
            self.cash = s.get("cash", self.starting_cash)
            self.starting_cash = s.get("starting_cash", self.starting_cash)
            self.positions = s.get("positions", {})
            self.realized_pnl = s.get("realized_pnl", 0.0)
            self.history = s.get("history", [])

    def _save(self):
        os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
        with open(self.state_path, "w") as f:
            json.dump({
                "starting_cash": self.starting_cash,
                "cash": self.cash,
                "positions": self.positions,
                "realized_pnl": self.realized_pnl,
                "history": self.history,
            }, f, indent=2)

    # ---------- orders ----------
    def buy(self, symbol: str, qty: int):
        return self._trade(symbol.strip().upper(), +int(qty))

    def sell(self, symbol: str, qty: int):
        return self._trade(symbol.strip().upper(), -int(qty))

    def _trade(self, symbol: str, delta: int):
        if delta == 0:
            raise OrderError("Quantity must be positive.")
        spec = FUTURES.get(symbol)
        price = get_quote(symbol)
        pos = self.positions.get(symbol, {"qty": 0, "avg_price": 0.0})
        q0, q1 = pos["qty"], pos["qty"] + delta
        pv = spec["pv"] if spec else 1.0

        if spec is None and q1 < 0:
            raise OrderError("Shorting stocks isn't supported in paper mode. "
                             f"Shorts work on futures: {', '.join(FUTURES)}")

        # figure out the realized P/L of any closing portion first (no mutation yet)
        realized = 0.0
        if q0 != 0 and (delta > 0) != (q0 > 0):
            closed = min(abs(delta), abs(q0))
            side = 1 if q0 > 0 else -1           # +1 closing longs, -1 closing shorts
            realized = (price - pos["avg_price"]) * closed * side * pv

        # ---- validate before committing ----
        if spec is None:
            if delta > 0:
                cost = price * delta + self.commission
                if cost > self.cash + 1e-9:
                    raise OrderError(f"Not enough cash: need ${cost:,.2f}, have ${self.cash:,.2f}.")
        else:
            others = sum(FUTURES[s]["margin"] * abs(p["qty"])
                         for s, p in self.positions.items()
                         if s in FUTURES and s != symbol)
            margin_needed = others + FUTURES[symbol]["margin"] * abs(q1)
            if margin_needed > self.cash + realized + 1e-9:
                raise OrderError(
                    f"Not enough margin: {abs(q1)} {symbol} needs "
                    f"${FUTURES[symbol]['margin'] * abs(q1):,.0f} "
                    f"(cash ${self.cash:,.2f}). Fewer contracts, or use micros "
                    f"(MNQ=F/MES=F).")

        # ---- commit ----
        if q0 != 0 and (delta > 0) != (q0 > 0):          # reducing / closing / flipping
            self.realized_pnl += realized
            self.cash += realized
            if q1 == 0:
                self.positions.pop(symbol, None)
            elif (q1 > 0) == (q0 > 0):                    # partial close, same side remains
                pos["qty"] = q1
                self.positions[symbol] = pos
            else:                                         # flipped through zero
                self.positions[symbol] = {"qty": q1, "avg_price": price}
        else:                                             # opening / adding
            pos["avg_price"] = (pos["avg_price"] * abs(q0) + price * abs(delta)) / abs(q1)
            pos["qty"] = q1
            self.positions[symbol] = pos

        if spec is None:                                  # stocks are cash-settled
            self.cash -= price * delta                    # delta<0 (sell) adds cash
        self.cash -= self.commission

        self._record("BUY" if delta > 0 else "SELL", symbol, abs(delta), price,
                     realized=realized if realized else None)
        self._save()
        return {"symbol": symbol, "side": "BUY" if delta > 0 else "SELL",
                "qty": abs(delta), "price": price, "realized": realized,
                "position": q1}

    def _record(self, side, symbol, qty, price, realized=None):
        self.history.append({
            "time": _now(), "side": side, "symbol": symbol,
            "qty": qty, "price": round(price, 4),
            "realized": None if realized is None else round(realized, 2),
        })

    # ---------- reporting ----------
    def snapshot(self):
        rows = []
        stock_value = 0.0
        futures_unreal = 0.0
        margin_used = 0.0
        for sym, pos in sorted(self.positions.items()):
            last = get_quote(sym)
            spec = FUTURES.get(sym)
            pv = spec["pv"] if spec else 1.0
            unreal = (last - pos["avg_price"]) * pos["qty"] * pv   # signed qty → shorts correct
            if spec:
                futures_unreal += unreal
                margin_used += spec["margin"] * abs(pos["qty"])
                mkt = unreal
            else:
                mkt = last * pos["qty"]
                stock_value += mkt
            rows.append({
                "symbol": sym, "qty": pos["qty"], "avg_price": pos["avg_price"],
                "last": last, "market_value": mkt, "unrealized": unreal,
                "kind": spec["label"] if spec else "stock",
            })
        total = self.cash + stock_value + futures_unreal
        return {
            "cash": self.cash,
            "holdings_value": stock_value + futures_unreal,
            "margin_used": margin_used,
            "total_value": total,
            "starting_cash": self.starting_cash,
            "total_pnl": total - self.starting_cash,
            "total_pnl_pct": (total - self.starting_cash) / self.starting_cash * 100,
            "realized_pnl": self.realized_pnl,
            "positions": rows,
        }
