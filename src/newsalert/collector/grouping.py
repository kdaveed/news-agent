"""Group GDELT articles into stories (phase 1, approach C: article-text clustering).

1. Each distinct article URL is represented by its URL-slug words; identical slugs across
   domains collapse into one headline (wire syndication).
2. Binary TF-IDF + cosine, single pass in time order: a headline joins the most similar cluster
   updated in the last 24 h, otherwise it starts a new story.
3. Merge near-identical clusters, then fold each story into a higher-ranked one only if similar
   to that story's own centroid (no chaining).
4. Score = independent outlets (a syndicated headline counts as one voice) + the most new
   independent outlets in any 12-hour window.
Parameters are the phase 1 values; see phases/phase-1-event-source-discovery/research/approaches/c_article_text.
"""
import hashlib
import math
from collections import Counter, defaultdict
from datetime import timedelta
from pathlib import Path

import duckdb

from newsalert.collector.text import CLUSTER_STOP, norm_tok, slug_tokens, story_keywords

P = {
    "min_tokens": 2, "max_df_frac": 0.05, "retrieval_tokens": 4, "idf_power": 1.5, "thresh": 0.35,
    "active_hours": 24, "merge_thresh": 0.55, "merge_min_docs": 2, "merge_top_terms": 8,
    "fold_thresh": 0.30, "syndication_min_domains": 3, "syndication_min_tokens": 3,
    "early_hours": 12, "early_weight": 1.0, "min_sources": 3,
}


def _headlines(con):
    rows = con.execute("""
      SELECT MentionIdentifier, any_value(MentionSourceName), min(MentionTime)
      FROM mentions GROUP BY 1 ORDER BY 1""").fetchall()
    heads = {}
    for url, src, t in rows:
        toks = frozenset(norm_tok(x) for x in slug_tokens(url) if x not in CLUSTER_STOP)
        if not toks:
            continue
        key = toks if len(toks) >= 3 else (url,)  # short slugs are too generic to collapse
        h = heads.get(key)
        if h is None:
            h = heads[key] = {"urls": [], "sources": set(), "t": t, "toks": toks, "ntok_raw": len(toks)}
        h["urls"].append(url)
        h["sources"].add(src)
        h["t"] = min(h["t"], t)
    return heads


def group(duckdb_path: Path) -> list[dict]:
    """Return stories sorted by score, each with urls, sources, keywords and outlet counts."""
    con = duckdb.connect(str(duckdb_path), read_only=True)
    heads = _headlines(con)
    con.close()

    df = Counter()
    for h in heads.values():
        df.update(h["toks"])
    docs = []
    for h in heads.values():
        toks = sorted(x for x in h["toks"] if df[x] >= 2)
        if len(toks) >= P["min_tokens"]:
            h["toks"] = toks
            docs.append(h)
    n = max(len(heads), 1)
    idf = {w: math.log(n / c) ** P["idf_power"] for w, c in df.items()}
    max_df = P["max_df_frac"] * n
    docs.sort(key=lambda h: (h["t"], min(h["urls"])))
    for h in docs:
        nrm = math.sqrt(sum(idf[w] ** 2 for w in h["toks"])) or 1.0
        h["vec"] = {w: idf[w] / nrm for w in h["toks"]}
        h["syn"] = (len(h["sources"]) >= P["syndication_min_domains"]
                    and h["ntok_raw"] >= P["syndication_min_tokens"])

    # single-pass clustering
    cent, cnorm2, last, members = [], [], [], []
    index = defaultdict(list)
    active = timedelta(hours=P["active_hours"])
    for h in docs:
        v = h["vec"]
        keys = sorted((w for w in v if df[w] <= max_df), key=lambda w: (-idf[w], w))[:P["retrieval_tokens"]]
        best, bsim = -1, 0.0
        for c in sorted({c for w in keys for c in index[w]}):
            if h["t"] - last[c] > active:
                continue
            s = sum(x * cent[c].get(w, 0.0) for w, x in v.items()) / math.sqrt(cnorm2[c])
            if s > bsim:
                best, bsim = c, s
        if bsim >= P["thresh"]:
            c = best
        else:
            c = len(cent)
            cent.append({}); cnorm2.append(0.0); last.append(h["t"]); members.append([])
        for w, x in v.items():
            if w not in cent[c]:
                index[w].append(c)
            cent[c][w] = cent[c].get(w, 0.0) + x
        cnorm2[c] = sum(x * x for x in cent[c].values())
        last[c] = max(last[c], h["t"])
        members[c].append(h)

    # merge pass
    parent = list(range(len(cent)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    big = [c for c in range(len(cent)) if len(members[c]) >= P["merge_min_docs"]]
    unit = {c: {w: x / math.sqrt(cnorm2[c]) for w, x in cent[c].items()} for c in big}
    tidx, tops = defaultdict(list), {}
    for c in big:
        tops[c] = [w for w, _ in sorted(unit[c].items(), key=lambda kv: (-kv[1], kv[0]))
                   if df[w] <= max_df][:P["merge_top_terms"]]
        for w in tops[c]:
            tidx[w].append(c)
    for c in big:
        for d in sorted({d for w in tops[c] for d in tidx[w] if d > c}):
            a, b = unit[c], unit[d]
            if len(a) > len(b):
                a, b = b, a
            if sum(x * b.get(w, 0.0) for w, x in a.items()) >= P["merge_thresh"]:
                ra, rb = find(c), find(d)
                if ra != rb:
                    parent[max(ra, rb)] = min(ra, rb)
    merged = defaultdict(list)
    for c in range(len(cent)):
        merged[find(c)].extend(members[c])

    def score(hs):
        own = {}
        for h in hs:
            if not h["syn"]:
                for s in h["sources"]:
                    own[s] = min(own.get(s, h["t"]), h["t"])
        voices = list(own.values()) + [h["t"] for h in hs if h["syn"] and not h["sources"] <= own.keys()]
        voices.sort()
        w, j, early = timedelta(hours=P["early_hours"]), 0, 0
        for i, t in enumerate(voices):
            while voices[j] < t - w:
                j += 1
            early = max(early, i - j + 1)
        return len(voices) + P["early_weight"] * early, len(voices), early

    def unit_centroid(hs):
        c = defaultdict(float)
        for h in hs:
            for w, x in h["vec"].items():
                c[w] += x
        nn = math.sqrt(sum(x * x for x in c.values())) or 1.0
        return {w: x / nn for w, x in c.items()}

    groups = [hs for hs in merged.values()
              if len(set().union(*(h["sources"] for h in hs))) >= P["min_sources"]]
    groups.sort(key=lambda hs: (-score(hs)[0], min(min(h["urls"]) for h in hs)))

    # fold near-duplicates into higher-ranked seeds
    seeds, seed_cent, sidx = [], [], defaultdict(list)
    for hs in groups:
        u = unit_centroid(hs)
        top = [w for w, _ in sorted(u.items(), key=lambda kv: (-kv[1], kv[0])) if df[w] <= max_df][:P["merge_top_terms"]]
        best, bsim = -1, 0.0
        for k in sorted({k for w in top for k in sidx[w]}):
            sim = sum(x * seed_cent[k].get(w, 0.0) for w, x in u.items())
            if sim > bsim:
                best, bsim = k, sim
        if bsim >= P["fold_thresh"]:
            seeds[best].extend(hs)
        else:
            for w in top:
                sidx[w].append(len(seeds))
            seeds.append(list(hs))
            seed_cent.append(u)

    stories = []
    for hs in seeds:
        sc, indep, early = score(hs)
        urls = sorted({u for h in hs for u in h["urls"]})
        sample = [min(h["urls"]) for h in
                  sorted(hs, key=lambda h: (-len(h["sources"]), h["t"], min(h["urls"])))][:10]
        stories.append({
            "cluster_key": hashlib.sha1(urls[0].encode()).hexdigest()[:16],
            "score": round(sc, 2), "independent_outlets": indep, "peak_window_outlets": early,
            "raw_outlets": len(set().union(*(h["sources"] for h in hs))),
            "first_seen": min(h["t"] for h in hs), "last_seen": max(h["t"] for h in hs),
            "keywords": story_keywords(urls), "sample_urls": sample, "urls": urls,
        })
    stories.sort(key=lambda s: (-s["score"], s["cluster_key"]))
    return stories
