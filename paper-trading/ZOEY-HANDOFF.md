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
(Every one of his recorded live entries lands 9:31–10:30.)

This is **v2** — corrected against 20 of PB's LIVE-TRADE recap videos (what
he does with money on, not just what he teaches):

1. **LIQUIDITY SWEEP at an HTF KEY LEVEL — hard gate.** The raid (prev-day
   low, Asia/London low, data wick, swing low… for a long) only counts if it
   happens AT an unfilled 15m/1H/4H fair value gap or an HTF intermediate
   high/low. His words: *"I don't take trades just off liquidity label like
   previously high, previously low, London high, London low, none of that."*
   A **re-sweep** (second raid of the same level) is his highest-conviction
   trigger and is tagged in the alert.
2. **MARKET STRUCTURE SHIFT (MSS)** — a candle **body** closes through the
   most recent opposing swing. *"It has to be a body close. It cannot be a
   wick."*
3. **CONFIRMATION → MARKET ENTRY.** Preferred trigger: inversion FVG (body
   close fully beyond the gap). But he does NOT rest limit orders inside the
   gap — every recorded entry is **market, on the confirming body close**
   (down to 30-second/1-minute charts): *"I'm not trying to enter these
   halfass closes… I like that. Bang."* The alert's entry = the confirming
   close; treat the alert as "go check the 1-minute now."
4. **CONFLUENCES (reported, not gates):** displacement on the shift
   (near-mandatory — its absence is flagged as a warning), NQ/ES SMT
   (optional at entry: *"Do I even need to look at ES? Nah"*), EQ
   premium/discount (info only — he knowingly takes premium entries).
5. **RISK FRAME:** stop beyond the full manipulation wick; on an oversized
   wick, **half-wick** (*"I'm just going to go like half the wick"*) — never
   widened; he halves SIZE instead. **Full close at TP1** = nearer of ~1:1 or
   the first internal pool (*"We're just going to go for that one to one"*,
   *"claim the low-hanging fruit"*) — no partials, no runners, in 10 straight
   recap videos. **Mandatory exit:** *"if there's an SMT at your target on
   ES, then you must close on NQ."* **One trade a day**, and a failed trade
   invalidates the daily bias — no re-entry.
6. **Skip conditions he applies live:** big one-way overnight move (alert
   warns above a 1% overnight range — OUR threshold, unconfirmed), choppy
   no-key-level days, and reduced size in historically bad months (his
   backtest: March).

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
| Outcome resolver (win/loss/no-fill/open per alert, R-multiples, win-rate scoreboard) | `resolve.py` | ✅ walks each logged alert forward through the bars; conservative tie-break (stop+TP same bar = LOSS); replay alerts scored separately from live |
| Forex Factory calendar | `broker/news.py` | ✅ auto-fetch, disk-cached in `state/` (feed rate-limits; stale cache is served on failure by design) |
| ICT primitives (FVG/sweep/MSS/killzone/EQ) | `broker/ict.py` | ✅ unit-sanity-checked on live data |
| Paper broker ($100k virtual) | `broker/paper_broker.py`, `cli.py` | ✅ stocks long-only; **futures long AND short** with correct point-value P/L (NQ $20/pt, MNQ $2/pt, ES $50/pt, MES $5/pt) and simplified initial-margin enforcement |
| Alert log for stats | `state/alerts.jsonl` | ✅ every alert recorded; replay alerts flagged `"replay": true` |

Environment: Mac (Apple Silicon), Python 3.14 — **stdlib only, zero pip
dependencies**. Secrets live in git-ignored `paper-trading/.env`
(`DISCORD_WEBHOOK_URL`). Repo pushes to GitHub, so nothing secret goes in
tracked files.

## 4. The stats plan (the real "probability")

Both YouTubers claim win rates (75%, 70%+) with **zero published evidence**.
The plan: trust only our own numbers. Every alert is logged to
`state/alerts.jsonl` with machine-readable levels (entry/stop/TP1/TP2);
`resolve.py` grades each one by walking forward through the bars
(WIN/LOSS/NO-FILL/OPEN + R-multiples) and prints the scoreboard. Adam still
reacts ✅ (would take) / ❌ (would pass) on each Discord alert — that measures
his agreement with the bot, while resolve.py measures the setup itself. The
log is the ground truth — protect it.

Case study (replay of Mon Jun 29): under v1's assumed limit-at-zone-midpoint
entry, the setup graded NO-FILL — right direction, missed trade. Under v2's
evidence-based market-on-confirmation entry (how PB actually enters), the
same setup grades **WIN +0.83R**. Entry mechanics decide which trades exist
at all — this is why the strategy is corrected against his live trades, not
just his lessons.

## 5. Data feed — current limit

Free Yahoo data, **~15 min delayed**, 5-minute bars. Fine for replay, paper
stats, and validating logic. **Not good enough to trade the live killzone.**
The upgrade path: Adam picks a prop firm → his platform (usually Tradovate or
Rithmic) includes real-time CME data → wire the scanner to that feed. Do not
let him trade live off delayed data.

## 6. What the bot still needs (open items, in priority order)

1. **Adam's remaining open questions.** Most of the original 15 were
   RESOLVED by live-video evidence (entry = market on confirming close; stop
   = full wick or half-wick when oversized; TP = full close at ~1R/first
   internal pool, no partials; SMT optional at entry + mandatory exit; EQ not
   enforced; AM session only; one trade a day; skip big-overnight/choppy
   days). Still genuinely open for Adam:
   - swing tightness (scanner uses a 3-bar fractal — unconfirmed),
   - the overnight-move warn threshold (1% is our guess),
   - confirm the HTF hard gate feels right once he sees live alerts,
   - PB lesson 6 notes (FVG definitions video, captions disabled),
   - prop firm choice, scanner auto-start (option b), and confirming
     pings-only through the funded stage.
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
python3 resolve.py                                   # grade logged alerts, win-rate scoreboard
python3 cli.py account                               # paper account P/L (futures shorts OK)
python3 broker/news.py                               # today's red/orange USD news
```

*Full architecture notes in `README.md`. Course-rule extraction sources: 20
lesson transcripts in `research/` (git-ignored).*
