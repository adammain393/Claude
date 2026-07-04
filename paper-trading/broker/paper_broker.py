"""
paper_broker.py — a simulated brokerage account (NO real money, NO real orders).

This is the heart of Phase 0. It mimics what a real broker does:
  - holds a cash balance
  - fills your buy/sell orders at the current market price
  - tracks your positions and average cost
  - computes realized + unrealized profit/loss

Everything is saved to state/portfolio.json so it survives between runs.

KEY CONCEPTS (so the live version later is not a mystery):
  * Market order  = "fill me right now at whatever the price is." That's what
                    we simulate here.
  * Average cost  = if you buy 10 @ $100 then 10 @ $120, your avg cost is $110.
                    P/L is measured against this.
  * Realized P/L  = profit/loss you locked in by SELLING.
  * Unrealized P/L= paper profit/loss on shares you still HOLD.
  * Commission    = fee per trade. Wealthsimple = $0. Questrade charges on
                    stocks. We keep a knob for it; default $0.
"""

import json
import os
from datetime import datetime, timezone

from .quotes import get_quote

DEFAULT_STATE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "state", "portfolio.json")


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
        self.positions = {}   # symbol -> {"qty": int, "avg_price": float}
        self.realized_pnl = 0.0
        self.history = []     # list of trade dicts
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
        symbol = symbol.upper()
        if qty <= 0:
            raise OrderError("Quantity must be positive.")
        price = get_quote(symbol)
        cost = price * qty + self.commission
        if cost > self.cash + 1e-9:
            raise OrderError(
                f"Not enough cash: need ${cost:,.2f}, have ${self.cash:,.2f}. "
                f"(No margin in paper mode — that's on purpose.)")
        pos = self.positions.get(symbol, {"qty": 0, "avg_price": 0.0})
        new_qty = pos["qty"] + qty
        pos["avg_price"] = (pos["avg_price"] * pos["qty"] + price * qty) / new_qty
        pos["qty"] = new_qty
        self.positions[symbol] = pos
        self.cash -= cost
        self._record("BUY", symbol, qty, price)
        self._save()
        return {"symbol": symbol, "side": "BUY", "qty": qty, "price": price}

    def sell(self, symbol: str, qty: int):
        symbol = symbol.upper()
        if qty <= 0:
            raise OrderError("Quantity must be positive.")
        pos = self.positions.get(symbol)
        if not pos or pos["qty"] < qty:
            held = pos["qty"] if pos else 0
            raise OrderError(f"Can't sell {qty} {symbol}: you hold {held}. "
                             f"(No short-selling in paper mode yet.)")
        price = get_quote(symbol)
        proceeds = price * qty - self.commission
        realized = (price - pos["avg_price"]) * qty
        self.realized_pnl += realized
        pos["qty"] -= qty
        if pos["qty"] == 0:
            del self.positions[symbol]
        else:
            self.positions[symbol] = pos
        self.cash += proceeds
        self._record("SELL", symbol, qty, price, realized=realized)
        self._save()
        return {"symbol": symbol, "side": "SELL", "qty": qty, "price": price,
                "realized": realized}

    def _record(self, side, symbol, qty, price, realized=None):
        self.history.append({
            "time": _now(), "side": side, "symbol": symbol,
            "qty": qty, "price": round(price, 4),
            "realized": None if realized is None else round(realized, 2),
        })

    # ---------- reporting ----------
    def snapshot(self):
        """Return a full account snapshot with live prices."""
        rows = []
        holdings_value = 0.0
        for sym, pos in sorted(self.positions.items()):
            last = get_quote(sym)
            mkt = last * pos["qty"]
            unreal = (last - pos["avg_price"]) * pos["qty"]
            holdings_value += mkt
            rows.append({
                "symbol": sym, "qty": pos["qty"], "avg_price": pos["avg_price"],
                "last": last, "market_value": mkt, "unrealized": unreal,
            })
        total = self.cash + holdings_value
        return {
            "cash": self.cash,
            "holdings_value": holdings_value,
            "total_value": total,
            "starting_cash": self.starting_cash,
            "total_pnl": total - self.starting_cash,
            "total_pnl_pct": (total - self.starting_cash) / self.starting_cash * 100,
            "realized_pnl": self.realized_pnl,
            "positions": rows,
        }
