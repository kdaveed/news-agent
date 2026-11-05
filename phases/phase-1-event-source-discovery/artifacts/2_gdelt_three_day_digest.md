# GDELT: selecting important news from the past three days

Research date: 2026-11-05. Recommendation: cluster reporting into distinct stories, rank those stories by breadth of coverage, then select a small, diverse digest. Coverage is a measurable proxy for importance, not a measure of truth or human impact.

## Project context and evidence

The product brief calls for important-event alerts through email and Slack, extensible delivery channels, and an admin view. `docs/1_news_collection.md` already proposes coverage breadth and growth as importance signals. `research/CONTRACT.md` defines a deterministic comparison on a shared DuckDB snapshot.

Read-only SQL checks during this research confirmed:

| Observation | Result | Implication |
|---|---:|---|
| Event records | 347,809 | A record is too fine-grained to assume it is a digest item |
| Mention records | 953,494 | Deduplicate before counting coverage |
| Distinct article identifiers in mentions | 150,119 | Practical initial input size; not all GDELT-monitored articles |
| Mention batches | 288 | All expected batch timestamps are present; this does not establish completeness within each batch |
| Mentions without matching event metadata | 45,591 (4.8%) | Preserve them with a left join; enrich historical event metadata separately |
| Maximum distinct event IDs in one article | 215 | Shared articles alone are unsafe evidence for merging events |
| Mentions attributed to iheart.com | 39,112 (4.1%) | Investigate syndication; a domain is not necessarily an independent reporting source |

The existing `research/results/comparison.md` reports P@10=1.00, but 16 repeated matched threads in the top 20 and only three distinct matched threads. These are existing fuzzy-matcher results, not newly validated precision estimates. They show why duplicate removal matters more than optimizing that headline metric.

## Which GDELT interfaces to use

| Interface | Useful for | Recommendation |
|---|---|---|
| Events 2.0 | Structured actor/action/location evidence | Keep as enrichment and a baseline |
| Mentions 2.0 | Linking event IDs to reporting and measuring coverage over time | Reuse the downloaded snapshot |
| GKG 2.1 | Article-level entities, locations, themes, and other extracted metadata | Preferred next input for broader story discovery |
| DOC 2.0 API | Targeted searches, representative links, coverage timelines | Use for inspection/enrichment rather than exhaustive discovery |

Events and GKG update every 15 minutes; GDELT 2.0 describes translation across 65 languages. That is the scope of this pipeline, not a claim that GDELT covers every outlet or language. [GDELT 2.0 introduction](https://blog.gdeltproject.org/gdelt-2-0-our-global-world-in-realtime/)

Important corrections to the earlier notes: event-level `NumMentions`, `NumSources`, and `NumArticles` describe the initial 15-minute batch, rather than accumulating follow-up coverage. Recompute windowed coverage from Mentions. `MentionTimeDate` is the processing-batch timestamp; `EventTimeDate` is when GDELT first recorded the event, not its real-world occurrence time. Goldstein is an action-type score, not incident-specific severity. [Events codebook](https://data.gdeltproject.org/documentation/GDELT-Event_Codebook-V2.0.pdf)

GKG 2.1 has a separate record per document and does not provide ready-made story clusters. It can include articles without extracted geographic locations. That makes it a better starting point for broad news coverage than requiring every article to contain a coded actor/action event. [GKG 2.1 codebook](https://data.gdeltproject.org/documentation/GDELT-Global_Knowledge_Graph_Codebook-V2.1.pdf)

DOC article lists are capped at 250 results, and relevance sorting ranks matches to a query rather than worldwide news importance. Use explicit time boundaries and treat results as samples. Historical documentation changed: a 2018 update extended searching back to January 2017, with a three-month restriction within the requested window for non-timeline modes. Do not repeat the earlier claim that all DOC access has a hard three-month history limit. Current operational availability and rate limits remain untested in this research. [DOC documentation](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/), [history update](https://blog.gdeltproject.org/doc-2-0-updates-1-5-year-searching-and-updated-mobile-interface/)

## Proposed pipeline

### 1. Fix the time semantics and ingest reproducibly

Use `[cutoff - 72 hours, cutoff)` in UTC for the live digest. The existing experiment instead covers three completed UTC days: November 2–4, 2026. Retain that fixed window for comparable experiments; label it accurately.

Select reporting observed in the window, including fresh developments in older stories. Store observation time, publication time where available, and inferred occurrence time separately. Do not exclude all ongoing stories using event date. Add prior context later to identify stale retrospectives and calculate growth.

Reuse Python and DuckDB. Download raw files from the master index, verify checksums, record a batch manifest and ingestion failures, and retain provenance. Before reusing `fetch_gdelt.py` across windows, fix its unfiltered cached-file glob and make skipped parse rows visible. Its current table load can include files cached for other windows.

### 2. Normalize reporting units

Start with web mentions and canonical article URLs: remove known tracking parameters, reconcile AMP/mobile versions, and preserve meaningful query parameters. Count a canonical article once per story, regardless of its number of mentions or event IDs.

Normalize publishers to registered domains, with an explicit mapping for known publisher families. Track raw domain breadth separately from estimated independent reporting breadth. Near-identical wire copies can demonstrate distribution but should not count as many independent confirmations. Keep those two signals separate.

### 3. Group articles into stories

First compare deterministic approaches using the existing data:

1. Keep the current individual-event ranking as the control.
2. Group event records using specific actor names, action family, location, and temporal proximity. Expect fragmentation and over-merging; broad country/action keys are insufficient.
3. Build conservative groups from distinctive URL-slug terms plus available structured evidence. Require agreement on specific entities/action/location; skip articles without useful slugs rather than inventing text.

For the stronger next iteration, ingest GKG, use article titles plus entities/themes, and cluster by text similarity constrained by time and specific entities. GKG `Extras` can contain `PAGE_TITLE`; check field availability instead of assuming every record has one. GDELT demonstrates extracting titles this way in its own [GKG example](https://blog.gdeltproject.org/experiments-in-summarizing-global-media-tenor-views-towards-china-part-2/).

Use candidate blocking and a cluster representative to avoid all-pairs comparisons and chains of weak matches. Shared articles are supporting evidence, not an unconditional merge rule: roundups and live blogs can bridge unrelated stories. Preserve specific developments beneath broad topics such as an election or war.

The current contract prohibits LLM/manual story labelling and requires the shared URL-keyword labeller. Keep that comparison compliant. A richer headline-based experiment should be a separately declared evaluation track.

### 4. Rank with interpretable evidence

Start with a deliberately simple baseline: distinct normalized publishers per story over 72 hours. Test syndication-adjusted breadth against raw domain breadth before adding weights.

Then compare additional signals independently:

- Breadth across publisher countries and original languages, when reliably available. Publisher country and event location are different attributes. The current loader's boolean `Translated` cannot identify individual languages.
- Coverage growth: new publishers in a recent six-hour bucket versus preceding comparable buckets. Normalize against overall monitored coverage, require minimum support, and separate newly emerging from established stories.
- Recency: retain an earlier major story in a three-day digest while preferring stories with meaningful recent reporting.
- User interests: apply geography/topic preferences explicitly rather than silently defining globally important as English-language political coverage.

Use a log transform on source counts if combining signals so one huge story does not dominate every component. Any weights and thresholds are hypotheses to validate, not GDELT-provided importance scores. Avoid using negative tone or Goldstein as the principal ranking rule.

### 5. Select and prepare the digest

Select an initial target of 5–10 distinct developments, with a redundancy penalty and a soft limit on repeated broad topics. Do not fill the quota with weak candidates. For each item retain a stable story ID, descriptive headline, evidence links from 2–3 publishers where available, first/latest observation, coverage counts, and a plain explanation of selection.

Fetch representative article text before producing factual summaries; URL keywords cannot support a reliable synopsis. If the text is unavailable, use an attributed headline and link. Keep summarization separate from deterministic ranking and outside the existing comparison contract.

Persist sent story IDs per subscription. Repeated runs should suppress already-sent items unless a material new development warrants an update. Render the same digest payload for email and Slack; expose grouping evidence, score components, ingestion gaps, and delivery state in the admin view. No messages need to be sent during research.

## Experiment and acceptance

Prioritize grouping first, ranking second, presentation third. Keep top-100 candidate outputs compatible with the existing contract. Compare distinct useful stories in the top 10, duplicate developments, false merges, missed major developments, source concentration, and runtime.

Use Wikipedia Current Events as an incomplete reference, not ground truth about importance. The existing matcher compares URL tokens to entry text and groups repeats by a broad Wikipedia thread; it can both accept loose matches and penalize legitimate separate developments. Reserve evaluation inputs for evaluation, freeze parameters before scoring, and assess actual clustering errors separately from keyword-match scores. Any human audit belongs in a separately authorized evaluation procedure, respecting the current no-manual-labelling contract.

After the fixed-window comparison, freeze the selected method and evaluate on additional disjoint windows, including quieter days and non-English/regional news. For an eventual live alert system, replay batches chronologically: using a full 72-hour total at an earlier alert time would leak future information.

This research inspected local artifacts, ran read-only SQL, and reviewed official GDELT documentation. It did not execute new clustering approaches, validate current DOC endpoint behavior, or send notifications.
