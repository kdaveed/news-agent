"""Approach B: structured keys.

Group GDELT events into stories using only their structured fields (actor codes, ActionGeo,
QuadClass, time), then score each story by how many *independent* outlets mention it, and how fast.

1. Event -> cell = (location, unordered actor pair, family).
   location precision follows ActionGeo_Type: city/landmark -> 0.25deg grid, state -> ADM1,
   country -> country; ungeocoded events are dropped. Actor = CAMEO actor code; role-only codes
   (GOV, COP, ...) are namespaced by the location's country. Family = coop (Quad 1-2) / conflict (3-4).
2. A cell is *generic* if it has no informative actor (one foreign to the location's country).
   Only *solid* cells (>= min_cell_sources independent voices) create links. Union-find rules:
     G_loc   generic cells at the same point location (non-capital)
     G_nat   generic cells at ADM1/country precision or at the country's busiest point (= capital):
             one "national domestic" story per country
     E_actor same non-capital point location + same informative actor (cells naming exactly one)
     E_dyad  international cells with the same set of involved countries
             (location country + informative actors' countries), anywhere
3. Co-burst pass: bursty components (>= 50% voices within 12h of onset) whose onsets are within
   2h and whose centroids are within 500 km are merged (one breaking event geocoded to several
   nearby places). Non-transitive: a component joins the largest compatible earlier anchor.
4. Score = independent voices x (1 - w + w x fast_share). Voices: outlets with at least one own
   text, plus one per syndicated text (identical DocLen+DocTone in >1 outlet) for outlets that only
   republished wire copy. iheart.com is excluded.
"""
import json, math, sys, time
from collections import defaultdict, Counter
from datetime import timedelta
from pathlib import Path
import duckdb

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shared"))
from text import story_keywords  # noqa: E402

PARAMS = {
    "min_event_day": 20261026,      # drop retrospective events (EventDay well before window)
    "grid_deg": 0.25,               # point-location grid for ActionGeo_Type 3/4
    "family_split": False,          # True: link rules never cross coop/conflict (ablation)
    "min_confidence": 0,            # mention Confidence floor (0 = keep all)
    "excluded_sources": ["iheart.com"],
    "collapse_syndication": True,  # identical (DocLen, DocTone) across outlets = one voice
    "min_cell_sources": 3,          # cells with fewer independent voices do not create links
    "domestic_subroles_uninformative": True,
    "link_rules": ["G_loc", "G_nat", "E_actor", "E_dyad"],
    "actor_link_skip_capital": True,  # E_actor not applied at the capital point (hub)
    "actor_link_single_only": True,   # E_actor only for cells with exactly one informative actor
    "coburst": True,
    "coburst_min_sources": 10,      # min voices of a component to take part
    "coburst_min_fast_share": 0.5,
    "coburst_same_country": False,
    "coburst_window_hours": 2,
    "coburst_km": 500,
    "onset_rank": 3,               # onset = time of the n-th distinct source
    "fast_hours": 12,
    "velocity_weight": 0.5,         # score = n_independent * (1 - w + w * fast_share)
    "min_story_sources": 3,
    "core_url_share": 0.5,          # label URLs: >= this share of the article's events in the story
    "core_url_min": 5,              # else fall back to all URLs
    "top_n": 150,
}
P = PARAMS


class DSU:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        a, b = self.find(a), self.find(b)
        if a != b:
            self.p[max(a, b)] = min(a, b)


def build(con):
    g = P["grid_deg"]
    # FIPS (ActionGeo) -> ISO3 (actor) country mapping, learned from the data: each ISO actor's
    # "home" is the FIPS country where its events are most often located; each FIPS country then
    # takes the most frequent ISO actor whose home it is. (Plain argmax per FIPS would map many
    # countries to USA, because the US is the most common actor everywhere.)
    con.execute("""
      CREATE TEMP TABLE fips2iso AS
      WITH n AS (
        SELECT ActionGeo_CountryCode fips, c iso, count(*) n FROM (
          SELECT ActionGeo_CountryCode, Actor1CountryCode c FROM events
          UNION ALL SELECT ActionGeo_CountryCode, Actor2CountryCode FROM events)
        WHERE c IS NOT NULL AND ActionGeo_CountryCode IS NOT NULL GROUP BY 1, 2),
      home AS (SELECT iso, arg_max(fips, n) fips, max(n) n FROM n GROUP BY 1)
      SELECT fips, arg_max(iso, n) iso FROM home GROUP BY 1""")
    con.execute(f"""
      CREATE TEMP TABLE ev AS
      WITH base AS (
        SELECT GlobalEventID id, QuadClass, ActionGeo_Type gt, ActionGeo_CountryCode gc,
          coalesce(f.iso, ActionGeo_CountryCode, 'XX') ciso,
          CASE WHEN ActionGeo_Type IN ('3','4') THEN 'P:' || round(ActionGeo_Lat/{g})*{g} || ',' || round(ActionGeo_Long/{g})*{g}
               WHEN ActionGeo_Type IN ('2','5') THEN 'A:' || ActionGeo_ADM1Code
               WHEN ActionGeo_Type = '1' THEN 'C:' || ActionGeo_CountryCode
               ELSE NULL END loc,
          ActionGeo_Fullname locname, ActionGeo_Lat lat, ActionGeo_Long lon,
          CASE WHEN Actor1Code IS NULL THEN NULL WHEN Actor1CountryCode IS NULL THEN coalesce(f.iso, 'XX') || '/' || Actor1Code ELSE Actor1Code END a1,
          CASE WHEN Actor2Code IS NULL THEN NULL WHEN Actor2CountryCode IS NULL THEN coalesce(f.iso, 'XX') || '/' || Actor2Code ELSE Actor2Code END a2
        FROM events e LEFT JOIN fips2iso f ON f.fips = e.ActionGeo_CountryCode
        WHERE EventDay >= {P['min_event_day']})
      SELECT id, gt, ciso, loc, locname, lat, lon,
        CASE WHEN QuadClass <= 2 THEN 'coop' ELSE 'conf' END fam,
        least(coalesce(a1, a2), coalesce(a2, a1)) x, greatest(coalesce(a1, a2), coalesce(a2, a1)) y
      FROM base WHERE loc IS NOT NULL""")
    excl = ",".join(f"'{s}'" for s in P["excluded_sources"])
    con.execute(f"""
      CREATE TEMP TABLE men AS
      WITH m AS (
        SELECT m.GlobalEventID id, m.MentionSourceName src, m.MentionIdentifier url, m.MentionTime t,
               m.MentionDocLen || ':' || round(m.MentionDocTone, 3) doc
        FROM mentions m JOIN ev ON ev.id = m.GlobalEventID
        WHERE m.MentionSourceName NOT IN ({excl}) AND m.Confidence >= {P['min_confidence']}),
      -- syndication: the same text (identical length + tone) published by several outlets
      d AS (SELECT doc, count(DISTINCT src) k FROM m GROUP BY 1)
      SELECT m.*, CASE WHEN {P['collapse_syndication']} AND d.k > 1 THEN 'syn:' || m.doc ELSE m.src END voice
      FROM m JOIN d USING (doc)""")
    con.execute("""
      CREATE TEMP TABLE cell AS
      SELECT row_number() OVER (ORDER BY loc, x, y, fam) - 1 cid, loc, x, y, fam, any_value(ciso) ciso,
             mode(locname) locname, count(*) n_events, avg(lat) lat, avg(lon) lon
      FROM ev GROUP BY loc, x, y, fam""")
    con.execute("CREATE TEMP TABLE evc AS SELECT ev.id, c.cid FROM ev JOIN cell c USING (loc, x, y, fam)")
    cells = con.execute("""
      SELECT c.cid, c.loc, c.x, c.y, c.fam, c.ciso, c.locname, c.n_events, count(DISTINCT m.voice) ns
      FROM cell c LEFT JOIN evc USING (cid) LEFT JOIN men m ON m.id = evc.id
      GROUP BY ALL ORDER BY cid""").fetchall()
    latlon = {r[0]: (r[1], r[2]) for r in con.execute("SELECT cid, lat, lon FROM cell").fetchall()}
    return cells, latlon


def informative(actor, ciso):
    """An actor carries story identity if it is foreign to the location: not role-only ('XXX/GOV')
    and not the location's own country, including its sub-roles (at a US location 'USAGOV',
    'USALEG' are as uninformative as 'USA')."""
    if actor is None or "/" in actor:
        return False
    if P["domestic_subroles_uninformative"]:
        return actor[:3] != ciso
    return actor != ciso


def link(cells):
    """Union-find over solid cells. Returns dsu and number of effective unions per rule."""
    dsu = DSU(len(cells))
    solid = [c for c in cells if c[8] >= P["min_cell_sources"]]
    # the busiest point-grid cell of each country = where national news gets geocoded (capital)
    point_load = Counter()
    for cid, loc, x, y, fam, ciso, _, n_ev, ns in solid:
        if loc.startswith("P:"):
            point_load[(ciso, loc)] += ns
    capital = {}
    for (ciso, loc), v in sorted(point_load.items(), key=lambda kv: -kv[1]):
        capital.setdefault(ciso, loc)

    groups = {r: defaultdict(list) for r in ("G_loc", "G_nat", "E_actor", "E_dyad")}
    for cid, loc, x, y, fam, ciso, _, _, ns in solid:
        f = (fam,) if P["family_split"] else ()
        inf = sorted({a for a in (x, y) if informative(a, ciso)})
        if not inf:  # generic domestic cell: no actor that identifies a story
            if loc.startswith("P:") and capital.get(ciso) != loc:
                groups["G_loc"][(loc, *f)].append(cid)
            else:
                groups["G_nat"][(ciso, *f)].append(cid)
            continue
        # international cell: the set of countries involved (location + foreign actors' countries)
        groups["E_dyad"][(tuple(sorted({ciso} | {a[:3] for a in inf})), *f)].append(cid)
        if P["actor_link_skip_capital"] and capital.get(ciso) == loc:
            continue
        if P["actor_link_single_only"] and len(inf) > 1:
            continue  # a cell naming two foreign actors would bridge two otherwise separate stories
        for a in inf:
            groups["E_actor"][(loc, a, *f)].append(cid)
    counts = Counter()
    for rule in P["link_rules"]:
        for ids in groups[rule].values():
            for o in ids[1:]:
                if dsu.find(o) != dsu.find(ids[0]):
                    counts[rule] += 1
                    dsu.union(ids[0], o)
    return dsu, counts


def source_times(con, cells, dsu):
    """Assign cells to current components (temp table c2s); return {sid: sorted first-mention time per source}."""
    root = [dsu.find(c[0]) for c in cells]
    con.execute("CREATE OR REPLACE TEMP TABLE c2s (cid INTEGER, sid INTEGER)")
    con.execute("INSERT INTO c2s SELECT * FROM (SELECT unnest(?::INTEGER[]) cid, unnest(?::INTEGER[]) sid)",
                [list(range(len(root))), root])
    # Independent voices of a story: every outlet with at least one own (non-syndicated) text, plus,
    # for outlets that only republished wire copy, one voice per distinct syndicated text (capped at
    # the number of such outlets).
    rows = con.execute("""
      WITH x AS (SELECT s.sid, m.src, m.voice, min(m.t) t
                 FROM men m JOIN evc USING (id) JOIN c2s s USING (cid) GROUP BY 1, 2, 3),
      own AS (SELECT sid, src, min(t) t FROM x WHERE voice = src GROUP BY 1, 2),
      synonly AS (SELECT x.* FROM x ANTI JOIN own USING (sid, src)),
      synv AS (SELECT sid, voice, min(t) t, row_number() OVER (PARTITION BY sid ORDER BY min(t), voice) r
               FROM synonly GROUP BY 1, 2),
      nso AS (SELECT sid, count(DISTINCT src) n FROM synonly GROUP BY 1)
      SELECT sid, src, t FROM own
      UNION ALL SELECT sid, voice, t FROM synv JOIN nso USING (sid) WHERE r <= n""").fetchall()
    per = defaultdict(list)
    for sid, src, t in rows:
        per[sid].append(t)
    for v in per.values():
        v.sort()
    return per


def burst_stats(times):
    ns = len(times)
    onset = times[min(P["onset_rank"], ns) - 1]
    fast = sum(1 for t in times if t <= onset + timedelta(hours=P["fast_hours"])) / ns
    return onset, fast


def km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 12742 * math.asin(math.sqrt(min(1.0, h)))


def coburst(con, cells, latlon, dsu):
    """Second pass: merge *bursty* components whose onsets coincide and that have the same primary
    country or source-weighted centroids within COBURST_KM. Catches one breaking event geocoded to
    several nearby places / coded with different actors (e.g. a crash coded at the airport, the
    county and the airline's country). Non-transitive: each component joins the biggest compatible
    anchor processed before it."""
    per = source_times(con, cells, dsu)
    cty_w = defaultdict(Counter)
    geo = defaultdict(lambda: [0.0, 0.0, 0.0])
    for cid, loc, x, y, fam, ciso, _, _, ns in cells:
        if ns >= P["min_cell_sources"]:
            r = dsu.find(cid)
            cty_w[r][ciso] += ns
            lat, lon = latlon[cid]
            if lat is not None:
                g = geo[r]
                g[0] += ns * lat; g[1] += ns * lon; g[2] += ns
    feats = {}
    for r in cty_w:
        g = geo[r]
        feats[r] = (cty_w[r].most_common(1)[0][0], (g[0] / g[2], g[1] / g[2]) if g[2] else None)
    comps = []
    for sid, times in per.items():
        if len(times) < P["coburst_min_sources"]:
            continue
        onset, fast = burst_stats(times)
        if fast >= P["coburst_min_fast_share"]:
            comps.append((len(times), sid, onset))
    comps.sort(key=lambda c: (-c[0], c[1]))
    anchors, merges = [], []
    win = timedelta(hours=P["coburst_window_hours"])
    for ns, sid, onset in comps:
        if sid not in feats:
            continue
        cty, cen = feats[sid]
        for a_sid, a_onset in anchors:
            a_cty, a_cen = feats[a_sid]
            near = cen is not None and a_cen is not None and km(cen, a_cen) <= P["coburst_km"]
            same = P["coburst_same_country"] and cty == a_cty
            if abs(onset - a_onset) <= win and (same or near):
                dsu.union(a_sid, sid)
                merges.append((a_sid, sid))
                break
        else:
            anchors.append((sid, onset))
    return merges


def stories_from(con, cells, dsu):
    per = source_times(con, cells, dsu)
    meta = {r[0]: r[1:] for r in con.execute("""
      SELECT s.sid, count(DISTINCT m.url), count(DISTINCT m.id), min(m.t), count(DISTINCT m.src)
      FROM men m JOIN evc USING (id) JOIN c2s s USING (cid) GROUP BY 1""").fetchall()}
    out = []
    w = P["velocity_weight"]
    for sid, times in per.items():
        nv = len(times)  # independent voices: own-reporting outlets + one per syndicated text
        if nv < P["min_story_sources"]:
            continue
        onset, fast = burst_stats(times)
        score = nv * (1 - w + w * fast)
        na, ne, first, ns = meta[sid]
        out.append({"sid": sid, "score": round(score, 2), "n_sources": ns, "n_independent": nv, "n_articles": na,
                    "n_events": ne, "first_seen": first.isoformat(), "fast_share": round(fast, 3)})
    out.sort(key=lambda s: (-s["score"], -s["n_sources"], s["sid"]))
    return out


def describe(con, sid):
    """Representative cells (labels) and URLs for one story."""
    top_cells = con.execute("""
      SELECT c.locname, c.x, c.y, c.fam, count(DISTINCT m.src) ns
      FROM c2s s JOIN cell c USING (cid) JOIN evc USING (cid) JOIN men m USING (id)
      WHERE s.sid = ? GROUP BY ALL ORDER BY ns DESC LIMIT 3""", [sid]).fetchall()
    # Rank article URLs by how central the story is to them: share of the article's (kept) events
    # that belong to this story. Round-up articles that touch many stories rank last, and only
    # "core" URLs (share >= core_url_share) feed the keywords when there are enough of them.
    rows = con.execute("""
      WITH u AS (SELECT url, count(DISTINCT id) n_all FROM men WHERE url IN (
                   SELECT m.url FROM c2s s JOIN evc USING (cid) JOIN men m USING (id) WHERE s.sid = ?)
                 GROUP BY 1)
      SELECT m.url, count(DISTINCT m.id) / any_value(u.n_all) share, count(DISTINCT m.id) k, min(m.t) t
      FROM c2s s JOIN evc USING (cid) JOIN men m USING (id) JOIN u USING (url)
      WHERE s.sid = ? GROUP BY 1 ORDER BY share DESC, k DESC, t, 1""", [sid, sid]).fetchall()
    urls = [r[0] for r in rows]
    core = [r[0] for r in rows if r[1] >= P["core_url_share"]]
    return top_cells, urls, (core if len(core) >= P["core_url_min"] else urls)


def run_pipeline(con):
    cells, latlon = build(con)
    dsu, edge_counts = link(cells)
    if P["coburst"]:
        edge_counts["coburst"] = len(coburst(con, cells, latlon, dsu))
    ranked = stories_from(con, cells, dsu)
    stories = []
    for i, s in enumerate(ranked[:P["top_n"]]):
        top_cells, urls, core = describe(con, s["sid"])
        label = "; ".join(f"{c[0] or '?'} [{c[1]}-{c[2]} {c[3]}]" for c in top_cells)
        stories.append({"rank": i + 1, "story_id": f"b{s['sid']}", "score": s["score"],
                        "n_sources": s["n_sources"], "n_independent": s["n_independent"],
                        "n_articles": s["n_articles"], "n_events": s["n_events"],
                        "first_seen": s["first_seen"], "keywords": story_keywords(core),
                        "sample_urls": core[:10], "structured_label": label, "fast_share": s["fast_share"]})
    stats = {"cells": len(cells), "solid_cells": sum(c[8] >= P["min_cell_sources"] for c in cells),
             "unions": dict(edge_counts), "n_stories": len(ranked)}
    return ranked, stories, stats


SUMMARY = ("Structured-key grouping: events become cells keyed by location (0.25deg grid / ADM1 / country per "
           "ActionGeo_Type), unordered CAMEO actor pair and coop/conflict family. Solid cells are union-found: "
           "generic (no foreign actor) cells per point location or per country ('national domestic' story), "
           "international cells by the set of countries involved, and cells sharing a foreign actor at the same "
           "non-capital point. A co-burst pass merges bursty components with near-identical onset within 500 km. "
           "Score = independent voices (outlets with own text + one per syndicated text; iheart excluded) x "
           "(0.5 + 0.5 x share of voices arriving within 12h of onset).")


def main():
    """`run.py key=json_value ...` overrides PARAMS for experiments and skips writing stories.json."""
    t0 = time.time()
    overrides = dict(a.split("=", 1) for a in sys.argv[1:])
    for k, v in overrides.items():
        assert k in P, k
        P[k] = json.loads(v)
    con = duckdb.connect(str(ROOT / "data/gdelt.duckdb"), read_only=True)
    ranked, stories, stats = run_pipeline(con)
    if not overrides:
        out = ROOT / "results/b_structured_keys"
        out.mkdir(parents=True, exist_ok=True)
        (out / "stories.json").write_text(json.dumps({
            "approach": "b_structured_keys", "summary": SUMMARY, "params": P,
            "runtime_seconds": round(time.time() - t0, 1), "stories": stories}, indent=1, ensure_ascii=False))
    print(stats, "runtime", round(time.time() - t0, 1), "s")
    for s in stories[:40]:
        print(s["rank"], s["n_sources"], s["n_independent"], s["n_events"], s["fast_share"],
              s["structured_label"][:110], "|", " ".join(s["keywords"][:8]))


if __name__ == "__main__":
    main()
