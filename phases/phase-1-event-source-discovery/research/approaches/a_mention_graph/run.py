"""Approach A: event–article graph.

Events that are mentioned by the same articles describe the same story. Link notable events
(>= MIN_EVENT_SOURCES distinct sources) when they share >= MIN_SHARED articles AND their article
sets overlap with Jaccard >= MIN_JACCARD (guards against long articles gluing unrelated events);
stories = connected components. Score = peak distinct sources within one UTC day (intensity, so
long-running topics don't win by accumulation).
"""
import json
import sys
import time
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shared"))
from text import story_keywords  # noqa: E402

P = {"MIN_EVENT_SOURCES": 5, "MIN_SHARED": 3, "MIN_JACCARD": float(sys.argv[1]) if len(sys.argv) > 1 else 0.2,
     "RETRO_BEFORE_EVENTDAY": 20261026, "TOP_N": 150}


def find(parent, x):
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


def main():
    t0 = time.time()
    con = duckdb.connect(str(ROOT / "data/gdelt.duckdb"), read_only=True)
    con.execute(f"""CREATE TEMP TABLE ea AS
        WITH ok AS (SELECT GlobalEventID FROM mentions
                    WHERE GlobalEventID NOT IN (SELECT GlobalEventID FROM events
                                                WHERE EventDay < {P['RETRO_BEFORE_EVENTDAY']})
                    GROUP BY 1 HAVING count(DISTINCT MentionSourceName) >= {P['MIN_EVENT_SOURCES']})
        SELECT DISTINCT GlobalEventID e, MentionIdentifier a FROM mentions JOIN ok USING (GlobalEventID)""")
    con.execute("CREATE TEMP TABLE deg AS SELECT e, count(*) n FROM ea GROUP BY e")
    edges = con.execute(f"""
        WITH pairs AS (SELECT x.e e1, y.e e2, count(*) shared
                       FROM ea x JOIN ea y ON x.a = y.a AND x.e < y.e GROUP BY 1, 2
                       HAVING count(*) >= {P['MIN_SHARED']})
        SELECT e1, e2 FROM pairs JOIN deg d1 ON d1.e = e1 JOIN deg d2 ON d2.e = e2
        WHERE shared / (d1.n + d2.n - shared) >= {P['MIN_JACCARD']}""").fetchall()
    nodes = [r[0] for r in con.execute("SELECT e FROM deg").fetchall()]
    parent = {n: n for n in nodes}
    for a, b in edges:
        ra, rb = find(parent, a), find(parent, b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)
    con.execute("CREATE TEMP TABLE comp (e BIGINT, c BIGINT)")
    con.executemany("INSERT INTO comp VALUES (?, ?)", [(n, find(parent, n)) for n in nodes])
    rows = con.execute(f"""
        WITH m AS (SELECT c, m.MentionSourceName s, m.MentionIdentifier a, m.MentionTime t
                   FROM mentions m JOIN comp ON comp.e = m.GlobalEventID),
        daily AS (SELECT c, date_trunc('day', t) d, count(DISTINCT s) ns FROM m GROUP BY 1, 2),
        peak AS (SELECT c, max(ns) peak FROM daily GROUP BY 1)
        SELECT c, peak, count(DISTINCT s), count(DISTINCT a), min(t),
               (SELECT count(*) FROM comp x WHERE x.c = m.c), list(DISTINCT a)
        FROM m JOIN peak USING (c) GROUP BY c, peak ORDER BY peak DESC, 3 DESC LIMIT {P['TOP_N']}""").fetchall()
    sizes = con.execute("SELECT count(*) FROM comp GROUP BY c ORDER BY 1 DESC LIMIT 5").fetchall()
    stories = [{"rank": i + 1, "story_id": f"A{r[0]}", "score": r[1], "n_sources": r[2], "n_articles": r[3],
                "n_events": r[5], "first_seen": r[4].isoformat(), "keywords": story_keywords(r[6]),
                "sample_urls": sorted(r[6])[:10]} for i, r in enumerate(rows)]
    out = ROOT / "results/a_mention_graph"
    out.mkdir(parents=True, exist_ok=True)
    (out / "stories.json").write_text(json.dumps({
        "approach": "a_mention_graph", "summary": __doc__.strip(), "params": P,
        "runtime_seconds": round(time.time() - t0, 1), "stories": stories}, indent=1, ensure_ascii=False))
    print(f"{len(nodes)} events, {len(edges)} edges, {len(set(parent[n] for n in nodes))} comps; "
          f"largest comps {[s[0] for s in sizes]}; {time.time() - t0:.1f}s")
    for s in stories[:25]:
        print(s["rank"], s["score"], s["n_sources"], s["n_events"], " ".join(s["keywords"][:9]))


if __name__ == "__main__":
    main()
