# Data schema: collector (Claude)

Storage: SQLite for everything below. Raw GDELT data stays in DuckDB and files (too large for the app database).
Owner: the collector writes all tables in this file. Delivery (Codex) only reads events.


# Layers

1 Raw (files, not in SQLite, can be reprocessed): GDELT downloads and DuckDB, RSS XML per poll, Wikipedia page text per day.
2 Source items: one table per source, one row per item, never edited.
3 Events: the cleaned aggregate, one row per real-world event. This is what gets sent.
4 Checker: Wikipedia results, kept apart and never used for scoring.


# Tables

Implemented in src/newsalert/db/collector.py, on the shared Base, in the same database as users, destinations and deliveries. Timestamps are ISO 8601 UTC text, like the user tables.

gdelt_clusters - one row per story cluster from one collector run
  id, run_id, cluster_key (hash of the earliest article URL), keywords, sample_urls, article_urls (up to 500, for matching across runs),
  independent_outlets, raw_outlets, peak_window_outlets (most new outlets in any 12 h), first_seen, last_seen, score

rss_items - one row per RSS article
  id, feed, guid, url, title, description, published_at, first_seen_at
  unique: feed + guid (URL when the feed has no guid)

wiki_entries - one row per Wikipedia Current Events entry
  id, date, category, topic, text, links, fetched_at
  unique: date + text

events - one row per real-world event (shared with delivery)
  id TEXT (stable across runs), headline, summary, score, independent_outlets, rss_confirmations,
  band: auto | review | drop
  status: candidate | selected | dropped
  first_seen, selected_at, last_run_id, note, updated_at

event_evidence - links an event to its source items
  event_id, source (gdelt | rss), item_id, match_method, confidence
  unique: event_id + source + item_id

wiki_checks - whether an event was later found on Wikipedia
  event_id, wiki_entry_id (empty if no match), matched, method (keyword | llm), shared_terms, checked_at
  unique: event_id + method

collector_runs - one row per run, for the admin panel
  id, window_start, window_end, started_at, finished_at, n_clusters, n_events, status (running | ok | failed), params, error

Setup: uv run python -m newsalert.db.init creates every registered table (users and collector) with WAL mode. Proposed shared setup; create_all only adds missing tables, so recreate the dev database if a column changes.


# Algorithm: one "process a time window" run

1 Ingest: download GDELT events and mentions for the window into DuckDB; save new RSS items; store Wikipedia entries as raw data only.
2 Group: cluster GDELT articles into stories by headline words (phase 1, approach C), collapse syndicated copies, count independent outlets. Write gdelt_clusters.
3 Confirm: match RSS items to clusters by URL, or by headline words within 12 hours. Count confirming feeds. Use the RSS headline when there is one.
4 Build events: if a cluster is the same story as an existing event (shared articles or keywords), update that event and keep its ID. Otherwise create a new one. Write event_evidence.
5 Band:
  auto - independent outlets at or above the high threshold and at least k RSS confirmations. Status becomes selected.
  review - middle range. Shown in the admin panel.
  drop - below the low threshold.
6 Hand-off: delivery reads newly selected events and creates deliveries.
7 Check (daily, one day later): match yesterday's events against Wikipedia and write wiki_checks. The admin panel shows the agreement rate, used to tune the thresholds.

Thresholds (high, low, k) are configuration, tuned in the admin panel on past days using wiki_checks.


# Contract with delivery

events.id is stable. Delivery can rely on it for de-duplication (one delivery per event and destination).
status = selected means ready to send. The collector never moves an event out of selected once it is set.
The collector never writes users, destinations or deliveries.

Phase 3 changes (see phases/phase-3-final/): article_urls added; a cluster that shares at least 3 articles (and 20%) with an event from the last 3 days keeps that event's id; syndicated copies on already counted outlets no longer add voices; evidence is written RSS first.
