# Five RSS feeds ready for a small collection experiment

Research date: 2026-11-05. This follows the user's request for concrete, free-to-fetch feeds that can be compared with GDELT. Assumption: “Jida” in the request refers to GDELT.

## What was actually checked

Direct HTTP GETs at **2026-11-05 20:38 UTC / 21:38 Budapest** returned HTTP 200 and parseable XML for every shortlisted feed. No signup, API key, payment or article-page scraping was needed. Initial sandbox requests failed DNS resolution; the successful direct checks used approved network access. The web research reader rejected most XML content types, so those errors were not treated as feed failures.

The five feeds below supplied **126 items**, including **103 with publication timestamps in the preceding 24 hours**. Every item had a title, URL and parseable publication date. All but one had a description. These are observed snapshot properties, not fixed feed capacities or completeness guarantees.

| Publisher and exact feed | Items | Published within preceding 24h | Oldest → newest publication in snapshot (UTC) | Why include it / main weakness |
| --- | ---: | ---: | --- | --- |
| [BBC World](https://feeds.bbci.co.uk/news/world/rss.xml) | 21 | 17 | Nov 2 17:34 → Nov 5 20:28 | Compact international news baseline; descriptions only 63–147 characters, so limited text for clustering |
| [Guardian World](https://www.theguardian.com/world/rss) | 45 | 29 | Oct 25 02:00 → Nov 5 20:33 | Richer descriptions, 559–1,746 characters including HTML; older editorial selections make feed position and oldest date poor indicators of freshness or archive depth |
| [DW World](https://rss.dw.com/rdf/rss-en-world) | 11 | 8 | Nov 4 16:17 → Nov 5 19:12 | Adds a German international publisher and exercises RSS 1.0/RDF parsing; small sample and no ordinary GUID fields in the parsed items |
| [France 24 English](https://www.france24.com/en/rss) | 24 | 24 | Nov 5 11:32 → Nov 5 19:59 | Adds a French international publisher; one description missing and only about 8.5 hours between oldest/newest items |
| [Al Jazeera English](https://www.aljazeera.com/xml/rss/all.xml) | 25 | 25 | Nov 5 14:19 → Nov 5 20:11 | Adds a Qatar-based international publisher; mixes articles, videos and other formats, with only about six hours between oldest/newest items |

Publisher geography is a reason for source diversity, not proof of independent reporting or regional completeness. All five selected feeds are English-language; this cannot validate multilingual coverage.

BBC, Guardian, France 24 and Al Jazeera provided GUIDs for all observed items. DW's RSS 1.0 records use RDF structure and Dublin Core dates; use canonical URLs or RDF identifiers for deduplication rather than rejecting items without a conventional GUID. Remove known tracking parameters such as BBC `at_*`, DW `maca` and Al Jazeera `traffic_source`; retain meaningful query parameters.

No selected feed supplied a separate article body through the probe's `content:encoded`/article-content fields. Guardian descriptions contain useful excerpts and HTML, but should not be called full articles. During inspection, the probe initially mistook Media RSS image metadata for article content; that was corrected and the report was reparsed from the same raw XML before recording these findings.

## Does this remove the historical-data problem?

**It enables an immediate small experiment, not a historical replacement for GDELT.** The publication span of a rolling feed does not establish that all intervening articles are present. Guardian's oldest selected item is nearly twelve days old; that does not mean the feed contains twelve days of complete news. Repeating the current snapshot cannot recover discarded items.

The existing GDELT data covers **November 2 00:00 to November 5 00:00 UTC**, while these feeds were fetched later on November 5. A read-only comparison against the existing web Mentions found:

| Feed | Current RSS items published inside existing GDELT window | Canonical URL matches in existing Mentions |
| --- | ---: | ---: |
| BBC | 4 | 1 |
| Guardian | 10 | 7 |
| DW | 3 | 3 |
| France 24 | 0 | 0 |
| Al Jazeera | 0 | 0 |
| Total | 17 | 11 |

This is a smoke check, **not a GDELT recall score**. RSS eligibility uses publisher publication dates; the stored GDELT dataset uses processing batches. URL variants, article selection in the Events/Mentions pipeline, delayed discovery and timestamp differences can explain unmatched URLs. It does not check whether the same story appeared under another URL. Zero eligible items for France 24 and Al Jazeera says nothing about whether GDELT covers those publishers.

## Smallest useful benchmark

**Immediately:** use the saved 126 items to compare parser behavior, URL normalization, duplicate handling, metadata availability and story clustering. Use titles and descriptions as observed; avoid adding full-page extraction to this initial experiment. The 17 overlapping items offer a limited sanity check against existing GDELT data.

**Over the next 24–72 hours:** poll these five feeds approximately every five minutes, subject to publisher guidance and error backoff. This is a proposed interval, not a verified polling allowance. Keep each raw response and observation timestamp; use conditional requests where supported. Guardian and Al Jazeera exposed ETags in this check. A five-minute schedule is 1,440 feed requests/day across five feeds, before retries.

Collect GDELT for the same future interval. Define two comparisons explicitly:

1. **Collection comparison:** restrict GDELT to the same publishers and match canonical article URLs; report overlaps and items seen on only one side. First-observed timestamps can compare collector discovery, with resolution limited by polling/batch cadence. A current RSS `pubDate` alone cannot reconstruct historical RSS discovery latency.
2. **Product comparison:** allow GDELT its broader publisher coverage and compare the usefulness of resulting story groups. Report that the source universes differ. Do not interpret five publishers' agreement as independent confirmation without considering syndication.

For a collection comparison, GKG article-level discovery or targeted DOC searches are better inputs than treating Events/Mentions as an exhaustive article index. DOC searches still require pagination/time-window checks and a final grace period for delayed indexing. Persist the actual responses so current archive revisions do not silently change the comparison later.

RSS should stay in consideration. Its concrete advantage is easy collection from known publishers; its concrete disadvantage remains historical completeness. None of these feeds provides evidence for a ready-made six-month RSS benchmark.

## Evidence and rerun

- Probe: [`research/rss/probe.py`](../research/rss/probe.py), standard-library Python, no new dependencies.
- Run from the repository root: `python3 research/rss/probe.py`.
- Measured metadata: [`20261105T203836Z.json`](../research/results/rss_probe/20261105T203836Z.json).
- Existing-window comparison: [`existing_window_overlap.json`](../research/results/rss_probe/existing_window_overlap.json).
- Raw XML: `research/data/rss/20261105T203836Z/`, retained locally under the already gitignored data directory.

The probe also checked two reserves: NYT World returned 52 items (52.6-hour publication span), and Sky World returned six (56.5-hour span). Both worked, but the selected five already provide a bounded first experiment. NYT is a useful substitute if a larger initial sample matters more than testing DW's RDF format. Sky's six-item snapshot is small for benchmarking.

Free-to-fetch is distinct from permission to redistribute content. The Guardian's publisher guidance describes personal, non-commercial feed use; a deployed email/Slack product needs a separate usage assessment. No production redistribution rights were established by this technical probe. See [Guardian RSS guidance](https://www.theguardian.com/help/feeds), [BBC feed catalogue](https://support.bbc.co.uk/platform/feeds/NewsFeeds.htm), and [Sky's publisher feed index](https://news.sky.com/info/rss). The live XML responses are the primary evidence for current functionality and counts.

## Prompt and scope record

The user clarified that this is an approach experiment, that paid services are less useful at this stage, and requested four or five concrete RSS providers for a quick comparison without prematurely excluding RSS. Work consisted of public-source research, direct feed probes and a read-only URL intersection with the existing GDELT dataset. No subscription, scheduled/background collector, outbound notification or new GDELT ingestion was started. No agents were delegated.
