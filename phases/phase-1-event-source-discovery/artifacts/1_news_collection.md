# 1. News Collection & Importance

## Problem
We need (a) sources of world events and (b) a way to decide whether an event is important enough to alert on, and to check that decision against real past data.

## Decision: RSS is not the starting point
RSS feeds only show the latest ~10–100 items. There's no history, so we can't study or test against the past.
- Checked on 2026-11-05: the Wayback Machine has ~70–80 daily snapshots of BBC/NYT world feeds since May 2026, but the one BBC snapshot we opened had 0 items. It's patchy and unreliable.
- RSS may still be used later for live ingestion. It's not used for analysis.

## Principle: importance ≈ how widely it is covered
An event reported by many independent outlets, across many countries, within a short time, matters more than a single story.
- Measure: the number of distinct outlets / countries / languages covering an event over a time window, and how fast that number grows.
- Source: **GDELT**. It has raw files updated every 15 minutes back to 2015, which give mention counts per event. Checked: the file list is live. The DOC search API worked for a 2-month-old window; a 6-month-old window was rate-limited, so its depth (~3 months per GDELT's docs) is unconfirmed.

Some domains already rate severity at the source, so for them importance is a threshold:
| Domain | Source | Severity field | 6-month history |
|---|---|---|---|
| Earthquakes | USGS FDSN | magnitude | ✅ 4,230 events M4.5+ |
| Multi-hazard disasters | GDACS | alert level (Green/Orange/Red) | ✅ |
| US weather | NWS | severity | ❌ recent only (May 2026 returned 0 alerts) |
| Markets | price data | % change over a time window | not checked yet |

## How we test it: Wikipedia "Current events" as the answer key
`Portal:Current_events/<YYYY_Month_D>` is an editor-curated daily list of notable world events, with full history (checked: 10 May 2026 fetched fine via the MediaWiki API).

Method:
1. Pull 6 months of candidate events (GDELT coverage spikes + USGS + GDACS).
2. Apply each candidate importance rule (e.g. "≥ N outlets in ≥ M countries within T hours").
3. Match the triggered events to the Wikipedia entries for the same day (±1 day) by entities and keywords.
4. Report **precision** (what share of our alerts appear on Wikipedia) and **recall** (what share of Wikipedia's entries we'd have caught), plus alert volume per day.
5. Choose thresholds based on the trade-off, and write the choice down as a decision.

Caveats: Wikipedia leans toward Anglophone/geopolitical news and under-covers markets, so it's not a perfect answer key; matching events to entries is fuzzy and needs manual spot-checks. Recall isn't "everything important", just what the Wikipedia editors chose to list.

## Prior art (web research, 2026-11-05; from search summaries, primary docs not yet read)
- **GDELT itself** describes coverage volume as an "imperfect but best available" proxy for importance. That matches our principle.
  - Pitfall: `NumMentions`/`NumSources` keep increasing with follow-up coverage. So we alert on **growth within a time window**, not on totals, and we weight **distinct sources** above raw mentions.
- **GDELT Cloud** (commercial) already offers this: "rapidly growing stories" filtered by `source_count`, with hourly/daily SQL alerts sent by email. This confirms the approach. Its own docs warn that GDELT leans toward English-language outlets.
- **Event Registry / NewsAPI.ai** defines an event as "something reported in several news articles", built by grouping articles that cover the same event, with social-share scores as a second signal. It's paid; the same idea could later be applied to a different data source.
- **Dataminr / Factal** are commercial products that combine many signals with AI (Dataminr) or automated detection checked by journalists (Factal). Takeaway: a human check is how commercial products get high precision, which is out of scope for us. It's an argument for showing the admin the evidence behind each alert.
- **Research:** "first story detection" (TDT, UMass novelty scoring), Priberam's multilingual streaming clustering (EMNLP 2018, code available, inactive), Osborne et al. using **Wikipedia page-view spikes** to confirm first stories. A 2023 thesis built a dataset from the Wikipedia Current Events Portal, so our test method has precedent.
- **Huginn** (open source, Ruby, MIT): a graph of source → filter/dedup → action agents (Email, Slack). A useful model for our pipeline and for adding channels later; it doesn't help decide what's important.

Changes after this research:
- Score candidates on growth in distinct sources, not on totals.
- Add Wikipedia page-view spikes as an optional second signal.

## Open items
- Confirm how far back GDELT DOC search goes (only probed once due to rate limiting; ~3 months per docs, unconfirmed).
- Get a Guardian API key (the demo key was rejected) if we add it as a cross-check.
- Pick a market data source and check that its history is usable.
