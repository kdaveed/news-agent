# Five best news collection options for this brief

Research date: 2026-11-05. Read alongside `task-04-feature-design-and-build.md` and the existing GDELT research. This is a source and architecture comparison, not a measured provider benchmark.

## Scope and decision criteria

The brief asks for important-event alerts, including breaking news, market movements and disasters. Collection must supply evidence for detection, rather than simply return articles matching a query. The shortlist therefore considers freshness, source coverage, event grouping, historical replay, operating effort, cost and usage restrictions. Email and Slack belong downstream of collection.

No budget, geography, languages or latency target is specified. This recommendation assumes a 24-hour implementation, modest initial traffic, and alerts measured in minutes rather than financial trading latency. Rankings express usefulness to this project; the specialist feeds in fifth place are essential for their domains, despite having narrower news coverage.

| Rank | Option | Strongest reason to choose it | Main tradeoff |
| --- | --- | --- | --- |
| 1 | GDELT open metadata and bulk archives | Historical replay and broad coverage without an API subscription | Significant processing and story grouping work |
| 2 | Curated publisher RSS/Atom feeds | Simple, transparent live ingestion with explicit source control | Limited default history and inconsistent metadata |
| 3 | Event Registry / NewsAPI.ai | Buy article clustering and event enrichment | Token costs, opaque clustering and provider dependence |
| 4 | Commercial article APIs, starting with GNews | Quickly obtain searchable headlines and article text | Quotas and paid freshness; story detection still required |
| 5 | Authoritative domain feeds and market data | Detect measurable disasters and price changes directly | Several domain-specific integrations rather than general news |

## 1. GDELT: best open foundation for this project's research

**Collection:** ingest the 15-minute GKG batches for article-level discovery, with Events/Mentions as additional structured evidence. Use DOC searches to inspect topics and obtain representative links. GDELT's 2.0 documentation describes 65-language translation and 15-minute updates; those are processing characteristics, not a guaranteed maximum delay from a real-world event. [GDELT 2.0 introduction](https://blog.gdeltproject.org/gdelt-2-0-our-global-world-in-realtime/)

**Strengths**

- Open metadata supports experimentation without per-query subscription charges. Compute, storage and optional BigQuery scans still cost resources.
- Bulk history makes reproducible replay possible: thresholds can be tested against what the collector could have known at each point in time.
- Entities, themes and geography help discover related reporting. Mentions supply evidence about coverage over time. [GKG codebook](https://data.gdeltproject.org/documentation/GDELT-Global_Knowledge_Graph_Codebook-V2.1.pdf), [Events codebook](https://data.gdeltproject.org/documentation/GDELT-Event_Codebook-V2.0.pdf)
- Existing Python/DuckDB work in this repository reduces initial integration effort, although its results have not been revalidated here.

**Weaknesses**

- A coded actor/action event is not automatically a user-facing story. One article can contain several events; one story can produce many records. Deduplication and grouping are substantial work.
- GKG is metadata, not a dependable full-article archive. Summaries may require a separate permitted text source.
- Syndication can inflate apparent independent coverage; translation and extraction introduce errors. Coverage breadth indicates media attention, not truth or impact.
- Public endpoints require defensive retries, monitoring and backfill. This research established no operational latency or availability guarantee.
- DOC article lists are capped at 250 results, so one query is not exhaustive discovery. Historical documentation changed over time; a three-month restriction on a requested article-list window must not be confused with the age of the bulk archive. [DOC documentation](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/), [historical-search update](https://blog.gdeltproject.org/doc-2-0-updates-1-5-year-searching-and-updated-mobile-interface/)

**Fit:** retain GDELT for research and historical evaluation. Use GKG for broad news discovery rather than assuming the Events table contains a complete catalogue of headline stories. Choose a bounded input for the initial implementation so collection does not consume the entire 24-hour task.

## 2. Publisher RSS/Atom: best simple live collector

**Collection:** maintain an explicit list of publisher feeds, poll at intervals consistent with publisher guidance, parse their items and persist observations immediately. RSS supports article links and descriptions, with optional identifiers, timestamps and caching hints. [RSS specification](https://www.rssboard.org/rss-specification)

**Strengths**

- Small implementation surface: HTTP, an XML parser, a scheduler and persistent deduplication.
- Explicit editorial control over publishers, languages, regions and topics; source failures are easy to expose in the admin view.
- Direct ingestion avoids an additional aggregator's discovery stage, although actual speed depends on when the publisher updates its feed.
- A continuously stored feed becomes a usable archive of what this system actually observed.

**Weaknesses**

- Ordinary rolling feeds provide no guaranteed historical backfill. An outage can cause missed items once the feed rolls over.
- Fields, full-text availability, update patterns and identifiers vary. Treat feed timestamps as publisher assertions and record local observation time separately.
- Feed availability and completeness depend on each publisher. A small curated list creates selection and language bias.
- Cross-publisher story clustering, syndication handling and importance scoring remain our responsibility.
- Accessible does not mean licensed for product reuse: Le Monde explicitly limits ordinary RSS use to personal, non-professional use without further authorization. [Publisher RSS terms](https://www.lemonde.fr/en/about-us/article/2026/03/27/le-monde-rss-feeds_6751860_115.html)

**Fit:** strong for a narrow working live demo and later as a controlled complement to GDELT. The earlier repository decision to avoid RSS for historical analysis is reasonable; it does not rule out RSS for live collection. A Guardian publisher API is another direct-source route: article text and archives are available, but the free developer access is non-commercial and capped at 500 calls/day. Commercial access is separately priced. [Guardian access](https://open-platform.theguardian.com/access/)

## 3. Event Registry / NewsAPI.ai: best way to buy story grouping

**Collection:** retrieve articles and provider-generated event clusters, then apply our own alert rules and retain supporting article links. NewsAPI.ai is operated by Event Registry; it is separate from NewsAPI.org.

**Strengths**

- Advertises duplicate detection, article clustering, entity enrichment and full article bodies, addressing several difficult processing steps.
- Advertises historical data from 2014, useful for evaluating event rules.
- Could free implementation time for subscriptions, email/Slack delivery and admin inspection.

**Weaknesses**

- Provider clusters need validation: they can split one development or merge several, and their internal behavior is outside our control.
- Provider event labels do not determine what matters to a particular subscriber.
- The public entry plan is $90/month for the 5K plan. Recent event search costs five tokens versus one for recent article search; pagination and archive searches add costs. The 2,000-search free allowance is finite. [Plans and token accounting](https://newsapi.ai/plans)
- Free access is evaluation-only. Full-text access does not grant publisher republication rights; the terms restrict raw-data redistribution and full-text republication. [Terms](https://newsapi.ai/terms)

**Fit:** strongest commercial candidate when engineering time matters more than minimizing subscriptions. Validate cluster quality and actual token use before adopting it. Provider marketing about real-time availability is not a measured end-to-end latency result.

## 4. Commercial article APIs: best straightforward paid integration

**Collection:** use a normalized search/headlines API with overlapping time windows and persistent deduplication. These services package article discovery; clustering capabilities vary by product and plan.

**Strengths**

- One API replaces maintaining many publisher integrations.
- Structured article metadata and available text make filtering and evidence presentation easier.
- Historical search can support replay, subject to archive access and pagination limits.

**Weaknesses**

- Quotas scale with queries, pages, languages and polling frequency. Searching separately for every subscriber becomes expensive.
- Free-plan latency can invalidate a breaking-news use case.
- Search results are limited by query design and pagination; an API's advertised source count does not prove relevant local coverage.
- Full-text availability differs, and basic search APIs do not remove the need for story grouping and importance detection.

| Candidate | Documented monthly offer | Important qualification |
| --- | --- | --- |
| GNews | Essential €49.99; 1,000 requests/day; up to 25 articles/request; history since 2020; full content | Paid real-time availability; free plan has 12-hour delay and non-commercial restrictions |
| NewsData.io | Basic $199.99; 20,000 credits/month; six-month history; paid real-time availability | Free plan has 12-hour delay; check needed fields and pagination costs |
| NewsAPI.org | Business $449; 250,000 requests/month; up to five-year search history | Free plan has 24-hour delay and is development-only, including no staging; search results do not provide full article text |
| NewsCatcher | News API pricing is custom | Its displayed $50 Starter web-search offer is a different product, not a general News API production price |

Sources: [GNews pricing](https://gnews.io/pricing), [NewsData.io pricing](https://newsdata.io/pricing), [NewsAPI.org pricing](https://newsapi.org/pricing), [NewsCatcher product distinction and pricing](https://www.newscatcherapi.com/).

**Fit:** trial GNews first when buying article collection on a modest budget; compare it with Event Registry if grouping is the main bottleneck. No subscription was purchased during this research.

## 5. Authoritative domain feeds: best for disasters and market thresholds

**Collection:** convert structured observations into the same internal alert-candidate format used for news stories.

- **USGS:** earthquake GeoJSON contains IDs, location, magnitude, observation/update times and significance fields. Summary feeds refresh every minute; that does not mean an earthquake is detected and published within one minute. [USGS format and refresh schedule](https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php)
- **NWS:** forecasts, observations and alerts through an open, free API with rate limits and a required application User-Agent. Its weather remit is US-focused. [NWS API](https://www.weather.gov/documentation/services-web-api)
- **GDACS:** a UN/European Commission disaster-awareness framework; useful as a complementary global disaster source. Hazard coverage, severity semantics and delivery behavior need endpoint-specific evaluation. [GDACS overview](https://www.gdacs.org/About/overview.aspx)
- **Market data, e.g. Alpaca:** stock trades, quotes and bars over WebSockets. Distinguish IEX, consolidated SIP and 15-minute-delayed SIP; feed access depends on subscription. A news API alone cannot reliably implement a price-change threshold. [Stock stream documentation](https://docs.alpaca.markets/us/docs/real-time-stock-pricing-data)

**Strengths:** measurable conditions, explicit identifiers, geography and update fields; stronger evidence for threshold alerts than interpreting article language. Many public hazard sources have no subscription fee.

**Weaknesses:** no general political/business news coverage; one adapter per source; preliminary records can change; geography and hazard coverage vary. Magnitude alone is not human impact. Market coverage, exchange entitlement and external display terms need separate selection rather than assuming all streams are interchangeable.

**Fit:** indispensable complements to whichever general-news option wins. Begin with USGS; scope market instruments, reference prices and time windows before choosing a production market feed.

## Alternatives considered and not selected

- **Broad web scraping:** maximum source customization, but discovery, extraction, site changes, blocked requests and per-publisher usage conditions create a poor 24-hour starting point. It remains useful for selected, permitted enrichment. Even a mature crawler needs concurrency and adaptive throttling. [Scrapy AutoThrottle](https://docs.scrapy.org/en/latest/topics/autothrottle.html)
- **Search engines / unofficial Google News RSS:** useful for exploratory discovery, but query rankings and result caps are an uncertain basis for exhaustive monitoring. Do not confuse the independent GNews API with an official Google News API.
- **Wikipedia Current Events:** useful as a delayed, incomplete editorial evaluation reference, consistent with the repository's existing approach. It should not be both the candidate generator and the independent evaluation target.
- **Social streams:** potentially early signals, but rumor verification and access dependencies add scope. Reconsider only if first eyewitness reporting is a requirement.
- **Enterprise wire services:** potentially valuable with an existing contract, but no suitable price or access was established here. Do not invent an affordable self-service option.

## Recommendation and validation before commitment

For this repository, retain GDELT as the research backbone, use a small set of permitted publisher feeds for controlled live ingestion, and add USGS for a concrete structured-event demonstration. If budget is available, compare GNews for article collection against Event Registry for outsourced grouping before adding both.

Normalize inputs into source ID, provider record ID, canonical URL, title or structured observation, publication time, observation time, event time when known, location, language and provenance. Group and score separately, then send channel-neutral notifications. The admin view should expose evidence, source freshness, failed batches, deduplication decisions and delivery state.

Budget sanity check: polling one query every five minutes for 30 days is 8,640 calls before pagination and retries. If each is an Event Registry recent-event search at five tokens, that is 43,200 tokens. A cheap entry plan is not automatically enough. Share collection across subscribers and match locally where permitted; do not run a separate global-news crawl for each user.

Suggested comparison, not executed here:

1. Run a 48–72-hour overlap between shortlisted collectors and store first-observed time plus failures.
2. Use a separately frozen set of multilingual/regional stories and structured events to assess coverage; report provider misses as well as successes.
3. Measure duplicate-alert rate, false story merges, missed developments, API spend and operator effort. Compare freshness on shared articles; publication-to-observation latency is only meaningful when timestamps are trustworthy.
4. Replay historical data chronologically, excluding future reporting from earlier alert decisions. Treat current archive results as potentially revised rather than perfect historical snapshots.
5. Inspect whether the actual response contains usable title/text, source metadata and stable identifiers, and confirm retention and email/Slack display terms for the chosen plan.

Evidence limits: official documentation and pricing pages were reviewed. No authenticated provider integration, live latency benchmark, new GDELT batch audit or provider quality comparison was performed. Source counts and real-time claims are vendor statements. The ranking is an engineering judgment, not measured superiority.

## Prompt record

User request: “Please check the task description - task-04-feature-design-and-build.md - and I want you to make a deep research on what options do we have for collecting news from the internet. For each option list the strength and weaknesses. Give me the best 5.”

Research used direct document inspection and web queries; no delegated agents were used. Existing documents and experiments were preserved. This file records the research outcome and limitations; the chat/tool history contains the individual search queries and source inspections.
