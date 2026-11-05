"""Approach C: article text clustering.

Documents = distinct article URLs (mentions.MentionIdentifier), represented by their URL-slug words.
1. Collapse exact-duplicate headlines (same slug token set) into one "headline" document. Identical
   slugs on many domains are wire/network syndication (PA -> ~150 Newsquest sites, AP -> US locals).
2. TF-IDF (binary tf, idf over headline documents) + cosine, single-pass time-ordered clustering
   (online / first-story-detection style): each headline joins the most similar *active* cluster
   centroid if cosine >= THRESH, else it starts a new story.
3. Merge pass: union clusters whose centroids are very similar (repairs order-dependent fragmentation).
4. Score = independent outlets (syndicated copies of one headline count as one voice) plus a bonus
   for velocity: the most new independent outlets within any EARLY_HOURS sliding window.
"""
import json, math, os, sys, time
from collections import Counter, defaultdict
from datetime import timedelta
from pathlib import Path
import duckdb

# shared.story_keywords breaks Counter ties in set-iteration (string-hash) order, so its keywords vary
# run to run. Pin the hash seed so stories.json is byte-reproducible (clustering itself is order-safe).
if os.environ.get("PYTHONHASHSEED") != "0":
    os.execve(sys.executable, [sys.executable] + sys.argv, {**os.environ, "PYTHONHASHSEED": "0"})

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shared"))
from text import slug_tokens, story_keywords

PARAMS = {
    "min_tokens": 2,          # headline needs >= this many informative tokens (df>=2) to be clustered
    "stem": "strip plural/possessive trailing s (len>4, not ss/us/is)",
    "max_df_frac": 0.05,      # tokens in > this fraction of headlines are kept but never used for retrieval
    "retrieval_tokens": 4,    # candidate clusters come from the doc's k highest-idf tokens
    "idf_power": 1.5,         # term weight = idf ** idf_power (binary tf)
    "thresh": 0.35,           # cosine(doc, cluster centroid) to join a cluster
    "active_hours": 24,       # a cluster only accepts new docs if it was updated within this many hours
    "merge_thresh": 0.55,     # centroid-centroid cosine for the merge pass
    "merge_min_docs": 2,      # only clusters with >= this many headline docs take part in merging
    "merge_top_terms": 8,     # centroid terms used to find merge / fold candidates
    "fold_thresh": 0.30,      # story centroid vs higher-ranked seed centroid cosine to fold it in
    "syndication_min_domains": 3,  # headline on >= this many domains = one syndicated voice
    "syndication_min_tokens": 3,   # ... and only if the slug is specific enough (same as collapse key)
    "onset_rank": 3,          # story onset = time the 3rd independent voice appeared
    "velocity": "peak",       # "peak": best sliding window; "onset": window starting at onset
    "early_hours": 12,        # velocity window length
    "early_weight": 1.0,      # score = indep + early_weight * indep_peak_window
    "top_n": 150,
}
PARAMS.update(json.loads(os.environ.get("C_PARAMS", "{}")))  # for parameter sweeps only
P = PARAMS


# Extra clustering-only stopwords (dates / page-type boilerplate). keywords still use shared story_keywords.
CLUSTER_STOP = set("""jan feb mar apr jun jul aug sep sept oct nov dec january february march april june july
august september october november december monday tuesday wednesday thursday friday saturday sunday tonight
morning photos photo gallery podcast newsletter editor column""".split())


def norm_tok(t):
    if len(t) > 4 and t.endswith("s") and not t.endswith(("ss", "us", "is")):
        return t[:-1]
    return t


def main():
    t0 = time.time()
    con = duckdb.connect(str(ROOT / "data/gdelt.duckdb"), read_only=True)
    rows = con.execute("""
      SELECT MentionIdentifier, any_value(MentionSourceName), min(MentionTime), list(DISTINCT GlobalEventID)
      FROM mentions GROUP BY 1 ORDER BY 1""").fetchall()
    n_urls = len(rows)

    # ---- 1. headline documents --------------------------------------------------------------
    heads = {}  # key -> dict(urls, sources, t, events, toks, raw)
    n_empty = n_short = 0
    for url, src, t, evs in rows:
        raw = slug_tokens(url)
        toks = frozenset(norm_tok(x) for x in raw if x not in CLUSTER_STOP)
        if not toks:
            n_empty += 1
            continue
        key = toks if len(toks) >= 3 else (url,)  # short slugs too generic to collapse across URLs
        h = heads.get(key)
        if h is None:
            h = heads[key] = {"urls": [], "sources": set(), "t": t, "events": set(), "toks": toks,
                              "ntok_raw": len(toks)}
        h["urls"].append(url); h["sources"].add(src); h["events"].update(evs)
        h["t"] = min(h["t"], t)
    df = Counter()
    for h in heads.values():
        df.update(h["toks"])
    docs = []
    for h in heads.values():
        toks = sorted(x for x in h["toks"] if df[x] >= 2)  # sorted: no hash-order dependence
        if len(toks) < P["min_tokens"]:
            n_short += len(h["urls"])
            continue
        h["toks"] = toks
        docs.append(h)
    N = len(heads)
    idf = {w: math.log(N / c) ** P["idf_power"] for w, c in df.items()}
    max_df = P["max_df_frac"] * N
    docs.sort(key=lambda h: (h["t"], min(h["urls"])))
    for h in docs:
        nrm = math.sqrt(sum(idf[w] ** 2 for w in h["toks"]))
        h["vec"] = {w: idf[w] / nrm for w in h["toks"]}
        h["syn"] = len(h["sources"]) >= P["syndication_min_domains"] and h["ntok_raw"] >= P["syndication_min_tokens"]
    stats = {"urls": n_urls, "urls_empty_slug": n_empty, "urls_too_short": n_short,
             "headline_docs": N, "clustered_docs": len(docs),
             "urls_in_clustered_docs": sum(len(h["urls"]) for h in docs),
             "syndicated_headlines": sum(h["syn"] for h in docs),
             "urls_in_syndicated_headlines": sum(len(h["urls"]) for h in docs if h["syn"])}

    # ---- 2. single-pass time-ordered clustering ---------------------------------------------
    cent, cnorm2, last, members = [], [], [], []
    index = defaultdict(list)  # token -> cluster ids whose centroid contains it
    active = timedelta(hours=P["active_hours"])
    for h in docs:
        v = h["vec"]
        keys = sorted((w for w in v if df[w] <= max_df), key=lambda w: (-idf[w], w))[:P["retrieval_tokens"]]
        cands = set()
        for w in keys:
            cands.update(index[w])
        best, bsim = -1, 0.0
        for c in cands:
            if h["t"] - last[c] > active:
                continue
            cv = cent[c]
            dot = sum(x * cv.get(w, 0.0) for w, x in v.items())
            s = dot / math.sqrt(cnorm2[c])
            if s > bsim or (s == bsim and c < best):
                best, bsim = c, s
        if bsim >= P["thresh"]:
            c = best
        else:
            c = len(cent); cent.append({}); cnorm2.append(0.0); last.append(h["t"]); members.append([])
        cv = cent[c]
        for w, x in v.items():
            if w not in cv:
                index[w].append(c)
            cv[w] = cv.get(w, 0.0) + x
        cnorm2[c] = sum(x * x for x in cv.values())
        last[c] = max(last[c], h["t"])
        members[c].append(h)
    n_online = len(cent)

    # ---- 3. merge pass on centroids ---------------------------------------------------------
    parent = list(range(len(cent)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]; a = parent[a]
        return a
    big = [c for c in range(len(cent)) if len(members[c]) >= P["merge_min_docs"]]
    unit = {c: {w: x / math.sqrt(cnorm2[c]) for w, x in cent[c].items()} for c in big}
    tidx = defaultdict(list)
    tops = {}
    for c in big:
        tops[c] = [w for w, _ in sorted(unit[c].items(), key=lambda kv: (-kv[1], kv[0]))
                   if df[w] <= max_df][:P["merge_top_terms"]]
        for w in tops[c]:
            tidx[w].append(c)
    n_merges = 0
    for c in big:
        seen = set()
        for w in tops[c]:
            for d in tidx[w]:
                if d <= c or d in seen:
                    continue
                seen.add(d)
                a, b = unit[c], unit[d]
                if len(a) > len(b):
                    a, b = b, a
                if sum(x * b.get(w2, 0.0) for w2, x in a.items()) >= P["merge_thresh"]:
                    ra, rb = find(c), find(d)
                    if ra != rb:
                        parent[max(ra, rb)] = min(ra, rb); n_merges += 1
    groups = defaultdict(list)
    for c in range(len(cent)):
        groups[find(c)].extend(members[c])
    stats.update(online_clusters=n_online, merges=n_merges, final_clusters=len(groups))
    srcs = sorted((len(set().union(*(h["sources"] for h in hs))) for hs in groups.values()), reverse=True)
    stats["clusters_by_sources"] = {f">={k}": sum(1 for x in srcs if x >= k) for k in (1, 3, 10, 30, 100, 300)}
    stats["top_cluster_sources"] = srcs[:5]

    # ---- 4. scoring -------------------------------------------------------------------------
    def score_group(hs):
        # independent voices: a source counts on its own if it has >=1 non-syndicated headline in the
        # story; each syndicated headline counts once (only if it brings an otherwise-uncounted source).
        own = {}  # source -> earliest own (non-syndicated) article time
        for h in hs:
            if not h["syn"]:
                for s in h["sources"]:
                    own[s] = min(own.get(s, h["t"]), h["t"])
        voices = list(own.values())
        for h in hs:
            if h["syn"] and not h["sources"] <= own.keys():
                voices.append(h["t"])
        voices.sort()
        indep = len(voices)
        onset = voices[min(P["onset_rank"], indep) - 1]
        if P["velocity"] == "onset":
            early = sum(1 for t in voices if t <= onset + timedelta(hours=P["early_hours"]))
        else:  # "peak": most new independent voices in any EARLY_HOURS sliding window
            w, j, early = timedelta(hours=P["early_hours"]), 0, 0
            for i, t in enumerate(voices):
                while voices[j] < t - w:
                    j += 1
                early = max(early, i - j + 1)
        return indep + P["early_weight"] * early, indep, early, onset

    def unit_centroid(hs):
        c = defaultdict(float)
        for h in hs:
            for w, x in h["vec"].items():
                c[w] += x
        n = math.sqrt(sum(x * x for x in c.values()))
        return {w: x / n for w, x in c.items()}

    groups = [hs for hs in groups.values() if len(set().union(*(h["sources"] for h in hs))) >= 3]
    groups.sort(key=lambda hs: (-score_group(hs)[0], min(min(h["urls"]) for h in hs)))

    # ---- 5. fold near-duplicate stories into a higher-ranked seed (no chaining) ---------------
    # Each story is compared with the *original* centroids of higher-scored seed stories only, so
    # A~B and B~C never pulls C into A unless C~A itself.
    seeds, seed_cent, sidx = [], [], defaultdict(list)
    n_folded = 0
    for hs in groups:
        u = unit_centroid(hs)
        top = [w for w, _ in sorted(u.items(), key=lambda kv: (-kv[1], kv[0])) if df[w] <= max_df][:P["merge_top_terms"]]
        best, bsim = -1, 0.0
        for k in sorted({k for w in top for k in sidx[w]}):
            sc = seed_cent[k]
            sim = sum(x * sc.get(w, 0.0) for w, x in u.items())
            if sim > bsim:
                best, bsim = k, sim
        if bsim >= P["fold_thresh"]:
            seeds[best].extend(hs); n_folded += 1
        else:
            for w in top:
                sidx[w].append(len(seeds))
            seeds.append(list(hs)); seed_cent.append(u)
    stats["folded"] = n_folded

    stories = []
    for hs in seeds:
        sources = set().union(*(h["sources"] for h in hs))
        score, indep, early, onset = score_group(hs)
        urls = sorted({u for h in hs for u in h["urls"]})
        # sample: representative headlines (most cross-source first), one URL each
        samp = [sorted(h["urls"])[0] for h in sorted(hs, key=lambda h: (-len(h["sources"]), h["t"], min(h["urls"])))][:10]
        stories.append({
            "story_id": "c" + min(min(h["urls"]) for h in hs)[-60:], "score": round(score, 2),
            "n_sources": len(sources), "n_indep_sources": indep, "n_indep_peak12h": early,
            "n_articles": len(urls), "n_headlines": len(hs),
            "n_events": len(set().union(*(h["events"] for h in hs))),
            "first_seen": min(h["t"] for h in hs).isoformat(), "onset": onset.isoformat(),
            "keywords": story_keywords(urls), "sample_urls": samp, "_urls": urls})
    stories.sort(key=lambda s: (-s["score"], -s["n_sources"], s["story_id"]))
    if os.environ.get("C_DEBUG"):  # dump member URLs of top stories for manual coherence inspection
        Path(os.environ["C_DEBUG"]).write_text(json.dumps({s["story_id"]: s["_urls"] for s in stories[:80]}))
    for s in stories:
        del s["_urls"]
    stories = stories[:P["top_n"]]
    for i, s in enumerate(stories):
        s["rank"] = i + 1
    stories = [{"rank": s.pop("rank"), **s} for s in stories]

    out = ROOT / "results/c_article_text"; out.mkdir(parents=True, exist_ok=True)
    rt = round(time.time() - t0, 1)
    (out / "stories.json").write_text(json.dumps({
        "approach": "c_article_text",
        "summary": ("Articles (distinct mention URLs) represented by URL-slug words; exact-duplicate "
                    "headlines collapsed; binary TF-IDF + cosine single-pass time-ordered clustering "
                    "against active cluster centroids, then a centroid merge pass. Score = independent "
                    "outlets (a syndicated headline on many domains counts as one voice) + outlets "
                    "in its busiest 12h window (velocity). URLs without informative slugs (~7%) are dropped."),
        "params": P, "stats": stats, "runtime_seconds": rt, "stories": stories},
        indent=1, ensure_ascii=False))
    # internal sanity metric: near-duplicate stories in the top 100 by top-8 keyword Jaccard
    kws = [set(x["keywords"][:8]) for x in stories[:100]]
    dup = sum(1 for i in range(len(kws)) if any(len(kws[i] & kws[j]) / len(kws[i] | kws[j]) >= 0.3 for j in range(i)))
    print("top100_kw_dups", dup, "runtime", rt, "s")
    print(json.dumps(stats))
    for s in stories[:40]:
        print(s["rank"], s["score"], s["n_sources"], s["n_indep_sources"], s["n_headlines"], s["onset"][5:16],
              " ".join(s["keywords"][:9]))


if __name__ == "__main__":
    main()
