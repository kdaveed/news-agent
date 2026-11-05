# Approach A: event–article graph (lead author: main agent)

**Contamination note:** the author had already seen the Wikipedia answer key while building the evaluator.
To limit this, J was chosen from internal checks only (below), and the evaluator was run once, together with B and C.

## Method
1. Notable events = ≥5 distinct mentioning sources in the window (23,211 of 347k). Drop retrospective events (EventDay < 2026-10-26).
2. Edge between two events if they share ≥3 articles **and** the Jaccard overlap of their article sets is ≥ J.
3. Stories = connected components (union-find).
4. Score = **peak distinct sources within one UTC day**, chosen over the 3-day total so long-running topics don't win by accumulation. Total sources is also reported.

## Choosing J (internal checks; runtime ~20 s)
| J | edges | comps | largest 5 comps (events) | observed in top 17 |
|---|---|---|---|---|
| 0.1 | 245k | 4,782 | 3160, 1844, 1603, 883, 162 | over-merging: Florida crash + Iran + Michigan in one comp |
| **0.2** | 221k | 5,638 | 855, 771, 611, 608, 389 | some chaining (Iran comp contains the Florida crash; #15 mixes court/flood/election) |
| 0.35 | 181k | 6,842 | 421, 369, 200, 178, 151 | fragmentation: Florida crash at #1 and #11, midterms split across many stories |

## Known weaknesses
- Connected components let a few bridging events chain stories together. Next step: community detection (Leiden/Louvain) or keep only mutual strongest edges.
- The US midterms are really one huge topic with many sub-stories. Whether these should be one alert or many is a product question, not an algorithm question.
- Only events with ≥5 sources take part, so small stories are invisible by design.
- Inherits GDELT's English-language bias.
