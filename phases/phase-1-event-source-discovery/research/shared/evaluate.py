"""Compare approaches against the Wikipedia Current Events answer key.

Reads results/<approach>/stories.json (see CONTRACT.md), data/wiki_truth.json.
Writes results/comparison.md and results/matches.json (for manual audit).

Matching is fuzzy on purpose-limited signals: story keywords (from URL slugs, shared labeller)
vs. Wikipedia entry words. A story matches an entry if they share >= 2 tokens whose summed IDF
>= T. We report several T values because no single threshold is "right".
"""
import json
import math
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WINDOW_DAYS = {"2026-11-02", "2026-11-03", "2026-11-04"}
SLACK_DAYS = WINDOW_DAYS | {"2026-11-01", "2026-11-05"}
T = 4.0
MODES = ["strict", "lenient"]  # strict = also requires a shared capitalised name (default)
GENERIC_CAPS = {"united", "state", "the"}

import sys
sys.path.insert(0, str(ROOT / "shared"))
from text import STOP, _TOKEN  # noqa: E402


def norm(tokens):
    out = set()
    for t in tokens:
        t = t.lower()
        if t in STOP or len(t) < 3:
            continue
        out.add(t[:-1] if t.endswith("s") and len(t) > 4 else t)  # crude plural folding
    return out


def wiki_entries():
    entries = [e for e in json.loads((ROOT / "data/wiki_truth.json").read_text()) if e["date"] in SLACK_DAYS]
    for i, e in enumerate(entries):
        e["id"] = i
        e["thread"] = e["path"][-1] if e["path"] else e["text"][:60]
        e["tok"] = norm(_TOKEN.findall(" ".join([e["text"]] + e["path"] + e["links"]).lower()))
        # names = capitalised words in the entry sentence, excluding the first word and the
        # trailing "(Source)" citations; generic capitalised words removed
        body = re.sub(r"(\s*\([^)]*\))+\s*$", "", e["text"])
        words = _TOKEN.findall(body)
        e["names"] = norm(w for w in words[1:] if w[0].isupper()) - GENERIC_CAPS
    return entries


def evaluate(stories, entries, idf, T, mode):
    RARE = math.log(len(entries) / 2)
    matched = {}  # story rank -> [(entry id, score, shared)]
    for s in stories:
        st = norm(s["keywords"])
        hits = []
        for e in entries:
            shared = st & e["tok"]
            score = sum(idf.get(t, 0) for t in shared)
            # >=2 shared tokens, enough total IDF, and at least one rare token (df <= 2)
            ok = len(shared) >= 2 and score >= T and any(idf.get(t, 0) >= RARE for t in shared)
            if mode == "strict":  # additionally require a shared proper name
                ok = ok and bool(shared & e["names"])
            if ok:
                hits.append((e["id"], round(score, 2), sorted(shared)))
        if hits:  # a story counts only toward its best-matching entry
            matched[s["rank"]] = sorted(hits, key=lambda h: -h[1])[:1]
    res = {}
    for k in (10, 20, 50):
        top = [s for s in stories if s["rank"] <= k]
        res[f"P@{k}"] = sum(s["rank"] in matched for s in top) / max(len(top), 1)
    window = [e for e in entries if e["date"] in WINDOW_DAYS]
    hit50 = {h[0] for r, hs in matched.items() if r <= 50 for h in hs}
    res["R@50"] = sum(e["id"] in hit50 for e in window) / len(window)
    # fragmentation: in the top 20, how many matched stories point at an already-seen thread?
    seen, dup = set(), 0
    for r in sorted(r for r in matched if r <= 20):
        th = {entries[h[0]]["thread"] for h in matched[r][:1]}
        dup += bool(th & seen)
        seen |= th
    res["dup@20"] = dup
    res["threads@20"] = len(seen)
    return res, matched


def main():
    entries = wiki_entries()
    df = Counter(t for e in entries for t in e["tok"])
    idf = {t: math.log(len(entries) / c) for t, c in df.items()}
    approaches = sorted(p.parent.name for p in (ROOT / "results").glob("*/stories.json"))
    lines = ["# Approach comparison vs Wikipedia Current Events", "",
             f"Answer key: {sum(e['date'] in WINDOW_DAYS for e in entries)} entries in window "
             f"({', '.join(sorted(WINDOW_DAYS))}); matching allows ±1 day ({len(entries)} entries).", "",
             "P@k = share of top-k stories matching any entry. R@50 = share of window entries matched by "
             "a top-50 story. dup@20 = matched top-20 stories that repeat an already-matched thread "
             "(fragmentation). threads@20 = distinct threads hit in top 20.", ""]
    audit = {}
    for mode in MODES:
        lines += [f"## matching = {mode}" + (" (default)" if mode == "strict" else ""), "",
                  "| approach | stories | P@10 | P@20 | P@50 | R@50 | dup@20 | threads@20 |",
                  "|---|---|---|---|---|---|---|---|"]
        for a in approaches:
            doc = json.loads((ROOT / "results" / a / "stories.json").read_text())
            stories = sorted(doc["stories"], key=lambda s: s["rank"])[:50]
            r, matched = evaluate(stories, entries, idf, T, mode)
            lines.append(f"| {a} | {len(doc['stories'])} | {r['P@10']:.2f} | {r['P@20']:.2f} | "
                         f"{r['P@50']:.2f} | {r['R@50']:.2f} | {r['dup@20']} | {r['threads@20']} |")
            if mode == "strict":
                audit[a] = {"stories": stories, "matched": matched}
        lines.append("")
    lines += ["## Top 20 per approach (default T) — ✅ = matched entry thread", ""]
    for a, d in audit.items():
        lines += [f"### {a}", "", "| # | sources | keywords | match |", "|---|---|---|---|"]
        for s in d["stories"][:20]:
            m = d["matched"].get(s["rank"])
            mt = f"✅ {entries[m[0][0]]['thread'][:50]} ({', '.join(m[0][2][:4])})" if m else ""
            lines.append(f"| {s['rank']} | {s['n_sources']} | {' '.join(s['keywords'][:8])} | {mt} |")
        lines.append("")
    lines += ["## Window entries never matched by any approach (top 50, default T)", ""]
    hit = {h[0] for d in audit.values() for r, hs in d["matched"].items() for h in hs}
    lines += [f"- {e['date']} {e['text'][:120]}" for e in entries if e["date"] in WINDOW_DAYS and e["id"] not in hit]
    (ROOT / "results/comparison.md").write_text("\n".join(lines) + "\n")
    (ROOT / "results/matches.json").write_text(json.dumps(
        {a: {str(r): [(entries[h[0]]["text"][:100], h[1], h[2]) for h in hs] for r, hs in d["matched"].items()}
         for a, d in audit.items()}, indent=1, ensure_ascii=False))
    print("\n".join(lines[:40]))


if __name__ == "__main__":
    main()
