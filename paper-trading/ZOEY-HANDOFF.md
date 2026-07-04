# ZOEY HANDOFF — Adam's ICT Setup Scanner & Paper Trading System

*Everything that works, how the setup is found, and what the bot still needs.
Prepared 2026-07-03 for Zoey OS. Project lives in
`~/Desktop/Claude Code/Claude/paper-trading/`.*

---

## 1. What this is

A **setup scanner + paper-trading engine** for Adam's day trading. The division
of labor is fixed and non-negotiable:

> **The bot FINDS the setup and pings Discord. ADAM confirms the chart and
> takes the trade himself.** No auto-execution. This keeps prop-firm rules
> happy and keeps the human judgment where the courses say it belongs.

Roadmap: paper engine ✅ → setup encoded ✅ → real-time data via Adam's prop
firm (not chosen yet) → only then any talk of automation.

## 2. The setup (this is the important part)

Adam trades the **ICT model taught by PB Trading** (YouTube, "ICT for
dummies"), sharpened with one rule from Tiz Trades. It is encoded in
`strategies/ict_pb.py`. The bot hunts this exact sequence, longs and shorts
mirrored, on **NQ1! and ES1!** (CME NASDAQ-100 / S&P 500 E-mini futures — the
data feed calls them `NQ=F` / `ES=F`):

**Only during the NY AM killzone, 9:30–11:00 AM ET.** Nothing outside it.

1. **LIQUIDITY SWEEP** — price raids a *significant* sell-side pool (for a
   long): previous day's low, Asia session low (8pm–12am ET), London session
   low (2am–5am ET), a data wick low, or an obvious intraday swing low.
   Qualifies only if the wick goes THROUGH the level and the body closes back
   on the right side. A body close through with no reclaim = continuation,
   not a sweep.
2. **MARKET STRUCTURE SHIFT (MSS)** — after the sweep, a candle **body**
   closes above the most recent swing high. PB's hard rule: *"It has to be a
   body close. It cannot be a wick."* A wick = another sweep, not a shift.
3. **ENTRY ZONE** — preferred: an **inversion FVG** — a bearish fair value gap
   that a candle body closes **fully beyond** (Tiz's strict rule: close ON the
   gap edge doesn't count), then price retests it. Fallback: a fresh bullish
   FVG left by the displacement leg, still unviolated.
4. **CONFLUENCES** — reported in the alert for Adam to judge, not hard
   filters (unconfirmed — see §6): entry zone in **discount** (at/below the
   50% EQ of the impulse leg; "never long in premium, never short in
   discount"); **SMT divergence** (NQ swept the level but ES held it, or vice
   versa — the one that held is the stronger index); **displacement** on the
   shift candle.
5. **RISK FRAME suggested in the alert** — stop under the sweep wick;
   **TP1 = nearest internal liquidity** (PB: internal liquidity is always the
   first target, never previous-day/session levels); final draw = the bigger
   external pool.

**News rules (wired in, from Forex Factory):** no alerts from 5 min before to
10 min after a **red-folder USD** release; the high/low of the candle printed
at a red release ("data wicks") are tracked as liquidity pools. Red = High
impact, orange = Medium, yellow = LOW (yellow is mostly noise).

**Discipline rules from the courses** (for Zoey to reinforce, not enforced in
code): one win = done for the day; two losses = done (your draw on liquidity
is probably wrong); 0.5–1% risk per trade; trades typically last 20–30 min.

## 3. What's built and verified working

| Piece | File | Status |
|---|---|---|
| Setup detection (the model above) | `strategies/ict_pb.py` | ✅ replay-verified: found a textbook long Mon Jun 29 10:50 ET (London-low sweep + bullish SMT + discount), stayed silent on non-setup days |
| Live scanner loop | `scanner.py` | ✅ `python3 scanner.py --strategy ict_pb --interval 60` |
| Discord alerts (phone) | `notify.py` + webhook in `.env` | ✅ tested; embed with levels, confluences, one-tap TradingView chart link (`CME_MINI:NQ1!`) |
| Replay / backcheck (no lookahead) | `replay.py` | ✅ `python3 replay.py --strategy ict_pb --symbol NQ=F` (add `--notify` to push hits through the real Discord path) |
| Forex Factory calendar | `broker/news.py` | ✅ auto-fetch, disk-cached in `state/` (feed rate-limits; stale cache is served on failure by design) |
| ICT primitives (FVG/sweep/MSS/killzone/EQ) | `broker/ict.py` | ✅ unit-sanity-checked on live data |
| Paper broker ($100k virtual, avg-cost P/L) | `broker/paper_broker.py`, `cli.py` | ✅ full buy/sell/positions/history loop tested |
| Alert log for stats | `state/alerts.jsonl` | ✅ every alert recorded; replay alerts flagged `"replay": true` |

Environment: Mac (Apple Silicon), Python 3.14 — **stdlib only, zero pip
dependencies**. Secrets live in git-ignored `paper-trading/.env`
(`DISCORD_WEBHOOK_URL`). Repo pushes to GitHub, so nothing secret goes in
tracked files.

## 4. The stats plan (the real "probability")

Both YouTubers claim win rates (75%, 70%+) with **zero published evidence**.
The plan: trust only our own numbers. Every alert is logged to
`state/alerts.jsonl`; Adam reacts ✅ (would take) / ❌ (would pass) on each
Discord alert. After ~20–30 alerts, compute: setup frequency, Adam-agreement
rate, and paper win rate. That log is the ground truth — protect it.

## 5. Data feed — current limit

Free Yahoo data, **~15 min delayed**, 5-minute bars. Fine for replay, paper
stats, and validating logic. **Not good enough to trade the live killzone.**
The upgrade path: Adam picks a prop firm → his platform (usually Tradovate or
Rithmic) includes real-time CME data → wire the scanner to that feed. Do not
let him trade live off delayed data.

## 6. What the bot still needs (open items, in priority order)

1. **Adam's answers to 15 numbered questions** (sent 2026-07-03 in chat).
   Every one is a parameter currently running on an **unconfirmed default**:
   swing strictness (k=3 fractal), pool list, timeframes (all 5m), inversion
   strictness (Tiz-strict), entry point in zone (midpoint), IFVG-mandatory?,
   displacement required?, EQ hard filter or bonus (bonus), SMT hard or bonus
   (bonus), AM-only (yes), news colors (red only), ping timing, stop buffer,
   TP logic, skip-after-big-overnight-move (not implemented).
   **House rule (Adam's explicit instruction): never fill strategy gaps with
   assumptions — ask him numbered questions and label unconfirmed defaults.**
2. **PB lesson 6 notes** — the FVG-definition video has captions disabled;
   Adam is watching it. Wanted: his exact FVG definition, when a gap is dead,
   where in the gap to enter, inversion details.
3. **Prop firm choice** — Adam hasn't picked. Before he buys an eval, read
   that firm's rules for (a) alert-scanner legality (usually fine — he places
   trades manually) and (b) drawdown/consistency rules to encode in risk math.
4. **Real-time data** — follows automatically from #3.
5. **Auto-start** — killzone is 6:30–8:00 AM Adam's time (Pacific). He was
   offered a launchd auto-start ("option b") — not yet confirmed.

## 7. Quick-start commands

```bash
cd "~/Desktop/Claude Code/Claude/paper-trading"

python3 scanner.py --strategy ict_pb --interval 60   # live scan, killzone-gated
python3 replay.py --strategy ict_pb --symbol NQ=F    # backcheck past week
python3 cli.py account                               # paper account P/L
python3 broker/news.py                               # today's red/orange USD news
```

*Full architecture notes in `README.md`. Course-rule extraction sources: 20
lesson transcripts in `research/` (git-ignored).*
