"""Control: rank individual GDELT events by distinct mentioning sources in the window. No grouping."""
import json, sys, time
from pathlib import Path
import duckdb
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shared"))
from text import story_keywords

t0 = time.time()
con = duckdb.connect(str(ROOT / "data/gdelt.duckdb"), read_only=True)
rows = con.execute("""
  SELECT GlobalEventID, count(DISTINCT MentionSourceName) ns, count(DISTINCT MentionIdentifier) na,
         min(MentionTime) fs, list(DISTINCT MentionIdentifier) urls
  FROM mentions GROUP BY 1 ORDER BY ns DESC LIMIT 100""").fetchall()
stories = [{"rank": i + 1, "story_id": str(r[0]), "score": r[1], "n_sources": r[1], "n_articles": r[2],
            "n_events": 1, "first_seen": r[3].isoformat(), "keywords": story_keywords(r[4]),
            "sample_urls": r[4][:10]} for i, r in enumerate(rows)]
out = ROOT / "results/baseline_raw_events"; out.mkdir(parents=True, exist_ok=True)
(out / "stories.json").write_text(json.dumps({"approach": "baseline_raw_events",
  "summary": "Control. Each GDELT event is a story; score = distinct sources in mentions.", "params": {},
  "runtime_seconds": round(time.time() - t0, 1), "stories": stories}, indent=1, ensure_ascii=False))
print("done", round(time.time() - t0, 1), "s")
