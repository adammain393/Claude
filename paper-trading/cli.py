#!/usr/bin/env python3
"""
cli.py — talk to your paper-trading account from the terminal.

Examples:
  python3 cli.py quote AAPL
  python3 cli.py buy AAPL 10
  python3 cli.py sell AAPL 5
  python3 cli.py account          # balances + P/L
  python3 cli.py positions        # what you hold, with live P/L
  python3 cli.py history          # every trade you've made
  python3 cli.py reset            # wipe the paper account back to $100k
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from broker.paper_broker import PaperBroker, OrderError  # noqa: E402
from broker.quotes import get_quote, QuoteError          # noqa: E402


def _money(x):
    return f"${x:,.2f}"


def cmd_quote(args):
    sym = args[0].upper()
    print(f"{sym}: {_money(get_quote(sym))}")


def cmd_buy(args):
    b = PaperBroker()
    fill = b.buy(args[0], int(args[1]))
    print(f"✅ BOUGHT {fill['qty']} {fill['symbol']} @ {_money(fill['price'])}")
    _print_account(b)


def cmd_sell(args):
    b = PaperBroker()
    fill = b.sell(args[0], int(args[1]))
    tag = f"  (realized { _money(fill['realized']) })"
    print(f"✅ SOLD {fill['qty']} {fill['symbol']} @ {_money(fill['price'])}{tag}")
    _print_account(b)


def _print_account(b):
    s = b.snapshot()
    print("\n── Account ─────────────────────────────")
    print(f"  Cash:            {_money(s['cash'])}")
    print(f"  Holdings value:  {_money(s['holdings_value'])}")
    print(f"  Total value:     {_money(s['total_value'])}")
    sign = "+" if s["total_pnl"] >= 0 else ""
    print(f"  Total P/L:       {sign}{_money(s['total_pnl'])}  ({sign}{s['total_pnl_pct']:.2f}%)")
    print(f"  Realized P/L:    {_money(s['realized_pnl'])}")


def cmd_account(args):
    _print_account(PaperBroker())


def cmd_positions(args):
    s = PaperBroker().snapshot()
    if not s["positions"]:
        print("No open positions.")
        return
    print(f"{'SYM':<6}{'QTY':>6}{'AVG':>12}{'LAST':>12}{'MKT VAL':>14}{'UNREAL P/L':>14}")
    print("-" * 64)
    for p in s["positions"]:
        sign = "+" if p["unrealized"] >= 0 else ""
        print(f"{p['symbol']:<6}{p['qty']:>6}{_money(p['avg_price']):>12}"
              f"{_money(p['last']):>12}{_money(p['market_value']):>14}"
              f"{sign+_money(p['unrealized']):>14}")


def cmd_history(args):
    h = PaperBroker().history
    if not h:
        print("No trades yet.")
        return
    for t in h:
        r = "" if t["realized"] is None else f"  realized={_money(t['realized'])}"
        print(f"{t['time']}  {t['side']:<4} {t['qty']:>4} {t['symbol']:<6} @ {_money(t['price'])}{r}")


def cmd_reset(args):
    path = PaperBroker().state_path
    if os.path.exists(path):
        os.remove(path)
    print("Paper account reset to a fresh $100,000.")


COMMANDS = {
    "quote": cmd_quote, "buy": cmd_buy, "sell": cmd_sell,
    "account": cmd_account, "positions": cmd_positions,
    "history": cmd_history, "reset": cmd_reset,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        return
    try:
        COMMANDS[sys.argv[1]](sys.argv[2:])
    except (OrderError, QuoteError) as e:
        print(f"⚠️  {e}")
    except (IndexError, ValueError):
        print("Bad arguments. See usage:")
        print(__doc__)


if __name__ == "__main__":
    main()
