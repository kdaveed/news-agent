# Approach C: article text clustering

Run: `uv run python approaches/c_article_text/run.py` from `research/` (about 45 s, pure Python, no new deps).
Output: `results/c_article_text/stories.json` (top 150). The output also has a `stats` block, plus the extra
per-story fields `n_indep_sources`, `n_indep_peak12h`, `n_headlines` and `onset`.

## Design
GDELT's event decomposition is not used for grouping. The units are articles: the 150,119 distinct
`MentionIdentifier` URLs. Each one is represented by its URL slug (`shared.text.slug_tokens`).

1. **Headline documents.** Tokens get a light normalisation for clustering only: a trailing plural or
   possessive `s` is stripped, and month/weekday/page-type boilerplate (`nov`, `tuesday`, `photos`,
   `editor`...) is dropped. URLs whose token sets are identical (3 or more tokens) are collapsed into one
   *headline doc*. That gives 83,336 headline docs. IDF is computed over headline docs, not URLs, so heavily
   syndicated stories do not get their own words down-weighted.
2. **Online clustering.** Headline docs are processed in order of first mention time. Each doc is a binary
   TF-IDF vector with weight `idf^1.5`, L2-normalised. Candidate clusters are looked up through an inverted
   index on the doc's 4 highest-idf tokens; tokens that appear in more than 5% of docs (`election`,
   `trump`...) are never used for lookup, though they still count in the cosine. The doc joins the
   *active* cluster (one updated in the last 24 h) whose centroid it is most similar to, provided the
   cosine is at least 0.35. Otherwise it starts a new story. This is the classic single-pass /
   first-story-detection scheme.
3. **Merge pass.** Clusters with 2 or more docs whose centroids have cosine ≥ 0.55 are union-found.
   The threshold is strict because union-find chains.
4. **Fold pass, with no chaining.** Clusters are ranked by score. Going down the list, each one is folded
   into the most similar higher-ranked *seed* if their cosine is ≥ 0.30. The comparison is always
   against the seed's original centroid, so A~B and B~C does not drag C into A.
5. **Score.** `score = indep + peak12h`.
   - `indep` is the number of independent voices. A source counts once if it has at least one headline
     in the story that is not syndicated. A *syndicated* headline (identical slug on ≥3 domains) counts
     as one voice in total.
   - `peak12h` is the largest number of new independent voices inside any 12 h sliding window, which
     measures velocity.
   - `n_sources` in the output is the raw count of distinct `MentionSourceName` values. `n_events` is
     the number of distinct GlobalEventIDs mentioned by the story's articles.

## Data quirks measured and how they are handled
- **Syndication is the biggest quirk for this question.** 52.6k of 150k URLs (35%) share an exact slug
  with an article on another domain. The PA feed alone appears on about 150 Newsquest UK local sites:
  the largest exact-slug groups have 152 domains each, and the stories are UK items such as the Isle of
  Lewis fishermen and Karl Bushby. AP copy behaves the same way across US local papers. Counted naively,
  any PA story gets 150 "sources". Treating each syndicated headline as one voice brings top-150 stories
  to a median of 0.52 independent voices per raw source. The ranking changes noticeably: only 32 of the
  top-50 by raw sources are in the final top 50. AP copy that local papers re-slug slightly is **not**
  caught, so syndication is only partly removed.
- **iheart.com** (9.9k URLs) is a single `MentionSourceName`, so it adds at most 1 per story. Its sister
  radio-station domains get the syndication treatment when their slugs are identical.
- **URLs with no informative slug.** 8,673 URLs (5.8%) give no tokens (numeric IDs, e.g.
  `kyivpost.com/post/88952`), and 990 more (0.7%) have fewer than 2 tokens with df ≥ 2. All of these are
  dropped, 6.4% in total. The top sources losing URLs this way are allafrica.com (635),
  webindia123.com (522), prokerala.com (417), english.news.cn (351), jpost.com (305),
  chinadaily.com.cn (231), bbc.co.uk (225), interfax.com.ua (155) and koreaherald.com (123).
  **The bias is against African, Chinese, Indian, Israeli and Ukrainian outlets and against the BBC**,
  so non-US stories lose part of their coverage count.
- **Non-English.** `Translated` is false for every mention, so this DB comes from the English GDELT feed
  only and the translation question does not come up. The set is still strongly US-weighted.
- Single articles mentioning 200+ events and retrospective events do not affect grouping, because events
  are only used for `n_events`.

## Sanity checks (final parameters)
- Clusters: 31,612 final clusters. Of these, 7,732 have ≥3 sources, 1,969 have ≥10, 527 have ≥30,
  94 have ≥100 and 5 have ≥300. The online pass made 31,900 clusters, the merge pass did 288 merges and
  the fold pass did 1,746 folds.
- Coherence: for each top-50 story, I measured the share of its URLs that contain at least one of its
  top-3 keywords. The median is 0.97 and the minimum 0.64.
- Manual reading of random member headlines in the top clusters: they are coherent. Examples are the
  Florida Learjet crash, the Michigan Senate race with the Stevens endorsement, and Iran/Qeshm strikes.
  Some stray short headlines get absorbed into large clusters (e.g. "florida palm beach county flooding"
  into the jet crash).
- Duplicates: 7 of the top-100 stories have a top-8 keyword Jaccard ≥ 0.3 with a higher-ranked story.
  The Florida jet crash appears twice (#2 and #134, the "fireball nosedives" phrasing).
- Template clusters, where unrelated articles share a headline pattern, appear 5 times in the top 150
  (ranks 39, 52, 60, 101, 141): "X pleads guilty", child abuse cases, open enrollment, sentencing,
  weather.
- Determinism: two runs under different `PYTHONHASHSEED` give identical output once keywords are
  ignored. Keywords differ only because of shared `story_keywords` tie-breaking (see Weaknesses).
  run.py now re-execs itself with `PYTHONHASHSEED=0`, which makes the whole file byte-identical.

## Parameter effects (from sweeps; all checks are internal)
| change | effect |
|---|---|
| merge_thresh 0.45 / 0.35 (single-link) | chaining: a single midterm megacluster with 1,664 / 3,403 sources swallowed most US politics. Rejected; replaced by the non-chaining fold |
| thresh 0.5 (idf^1) | Florida crash split in two, more fragments |
| thresh 0.3 (idf^1) | more election chaining |
| idf^1 | 10 template clusters in the top 150 (e.g. "pleads guilty", "wins reelection district"), jet crash in 2 pieces |
| idf^2 | 2–3 template clusters, but jet crash split into 4–5 pieces |
| **idf^1.5, thresh 0.35, fold 0.30** | 5 template clusters, jet crash in 2 pieces, fewest keyword duplicates (4–7). **Chosen** |
| velocity = window from onset (3rd voice) | penalised stories that had a preview phase before the event (e.g. midterm previews, then results). Replaced by the peak sliding window |

## Tried and rejected
- Single-link merging at lower thresholds, because of chaining (above).
- Requiring a shared low-df "anchor" token to join a cluster. Big real stories push their own
  signature words to high df (`learjet` 344, `sayed` 431 headline docs), higher than template words
  (`pleads` 108, `guilty` 184), so a df cap cannot separate them.
- A 4-token minimum for the syndication rule. 3-token slugs such as `6-things-to-watch-for-on-election-night`
  across NPR member stations then went uncollapsed and inflated an NPR explainer to rank 6.

## Known weaknesses
- **US midterms fragmentation.** The midterm elections fall inside this window, and about half of the
  top 100 are election-related: national control, results, individual races, voting logistics. Some of
  these are distinct sub-stories, but several are near-duplicates of "the midterms". Folding more
  aggressively turns them into one megacluster instead. Text clustering on slugs cannot tell
  "same event" apart from "same topic".
- Slugs are short: about 6–8 tokens, and a few of them are generic. Short or generic headlines get
  absorbed into big clusters. Templated headlines form junk clusters, and the related mix-ups stay too:
  the Ryanair bomb threats merged with US polling-place threats.
- Syndication handling only catches exact slugs. It undercounts sources for wire stories that every
  outlet runs: an independent outlet that only runs the identical wire slug is collapsed along with the
  others. It overcounts re-slugged wire copy.
- Dropped no-slug URLs bias the results against some non-US outlets (above).
- The order dependence of single-pass clustering is mitigated by the merge and fold passes, but not
  removed.
- The shared `story_keywords` breaks ties in hash order, so its labels are not reproducible across
  processes unless `PYTHONHASHSEED` is fixed. run.py pins it.
