# Paper Trading (Phase 0)

A **simulated** trading account that runs on your Mac. No real money, no real
orders, no brokerage connection yet. Prices are real (pulled live from Yahoo,
falling back to Stooq); the fills and the account are fake and safe.

## Why this exists

We're building toward automated trading in safe stages:

| Phase | What | Money at risk |
|-------|------|---------------|
| **0 — you are here** | Paper account + live quotes on your Mac | none |
| 1 | Encode *your* trading method as a strategy, forward-test it on paper | none |
| 2 | Swap the simulator for **Questrade's official practice account** (real broker API, fake money) | none |
| 3 | Go live via Questrade API — with position caps + a kill switch | REAL |

> Wealthsimple has **no official trading API**, so it can't be automated
> safely/legally. Questrade does, which is why live automation goes through it.

## Usage

```bash
cd paper-trading

python3 cli.py quote AAPL      # look up a live price
python3 cli.py buy AAPL 10     # simulate buying 10 shares at market
python3 cli.py sell AAPL 5     # simulate selling 5
python3 cli.py positions       # what you hold + live unrealized P/L
python3 cli.py account         # cash, total value, total P/L
python3 cli.py history         # every simulated trade
python3 cli.py reset           # wipe back to a fresh $100,000
```

## Phase 1: the ICT setup scanner

The setup from PB Trading's ICT course (with Tiz Trades' stricter inversion
rule) lives in `strategies/ict_pb.py`: NY-AM killzone (9:30–11:00 ET) sweep of
a liquidity pool → body-close market-structure shift → FVG/inversion-FVG
retest, with EQ-discount, NQ/ES SMT, and displacement reported as confluences.

```bash
python3 scanner.py --strategy ict_pb              # watch NQ=F live, alert Discord
python3 replay.py --strategy ict_pb --symbol NQ=F # replay the past week, no lookahead
```

The scanner finds the mechanical conditions; the human confirms the chart and
places the trade. Free Yahoo data is ~15 min delayed — fine for testing, must
be upgraded (prop-firm feed / real-time API) before trading live killzones.

## Files

- `broker/quotes.py` — live price fetcher (stdlib only; Yahoo → Stooq fallback).
- `broker/paper_broker.py` — the simulated account: cash, positions, fills, P/L.
- `cli.py` — the terminal interface shown above.
- `strategies/` — where *your method* will live (Phase 1).
- `state/portfolio.json` — your account state (git-ignored, local only).

## Safety

- No secrets live in this folder. When we reach Questrade, tokens go in a
  git-ignored `.env` and **never** get committed.
- Paper mode has no margin and no short-selling on purpose — it can't do
  anything a beginner account couldn't undo.
- Nothing here is investment advice.
