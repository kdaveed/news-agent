# Research contract: "Most important news of the past 3 days" from GDELT

Several approaches run side by side. Everything here keeps them comparable.

## Shared inputs (read-only)
- `data/gdelt.duckdb`, built by `shared/fetch_gdelt.py`. Window: **2026-11-02 00:00 → 2026-11-05 00:00 UTC** (288 × 15-min slots).
  - `events` (347,809 rows): GlobalEventID, EventDay, Actor1/2 Code/Name/CountryCode/Type1Code, IsRootEvent, EventCode/BaseCode/RootCode, QuadClass, GoldsteinScale, NumMentions, NumSources, NumArticles, AvgTone, ActionGeo_* (Type, Fullname, CountryCode, ADM1Code, Lat, Long), DateAdded, SOURCEURL.
  - `mentions` (953,494 rows): GlobalEventID, EventTime, MentionTime, MentionType, MentionSourceName, MentionIdentifier (article URL), Confidence, MentionDocLen, MentionDocTone, Translated.
  - **Always open with `duckdb.connect(path, read_only=True)`.** Several processes share this file.
- Known data quirks (measured):
  - `iheart.com` makes up ~4% of all mentions because it republishes other outlets' articles.
  - Single articles mention 200+ events.
  - ~3.3k events have EventDay < 20261025 (retrospective coverage).
- `shared/text.py`: `story_keywords(urls)`. **Required** for the `keywords` field, so every approach labels stories the same way.

## Off limits for approach authors
- `data/wiki_truth.json`, `shared/wiki_truth.py`, `shared/evaluate.py`, `results/comparison.md`, and the Wikipedia Current Events portal. That's the answer key. Tuning against it would invalidate the comparison.
- No LLM or manual labelling of stories. The pipeline must be deterministic code.

## Output: `results/<approach>/stories.json`
```json
{
  "approach": "b_structured_keys",
  "summary": "one paragraph: grouping + scoring idea",
  "params": {"...": "every tunable value used"},
  "runtime_seconds": 12.3,
  "stories": [
    {
      "rank": 1,
      "story_id": "any stable id",
      "score": 123.4,
      "n_sources": 87,
      "n_articles": 140,
      "n_events": 312,
      "first_seen": "2026-11-02T07:15:00",
      "keywords": ["...from story_keywords(article_urls)..."],
      "sample_urls": ["up to 10 article URLs"]
    }
  ]
}
```
At least the top 100 stories, ranked by importance (rank 1 = most important).

## Code location
`approaches/<approach>/` with a single entry point `run.py` (`uv run python approaches/<approach>/run.py`), plus a `NOTES.md` covering design, what was tried and rejected, sanity checks run, and known weaknesses.
