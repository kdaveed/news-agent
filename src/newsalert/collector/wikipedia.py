"""Wikipedia Current Events: fetch and parse day pages into wiki_entries, and the independent check.

The check only writes wiki_checks. Nothing in scoring or banding reads Wikipedia.
Matching (phase 1, strict rule): an event matches an entry if they share at least 2 terms,
one of them a capitalised name in the Wikipedia sentence and one rare (in at most 2 entries),
with summed IDF >= 4. Best match per event. Fuzzy by design; see phase 1 for its known errors.
"""
import json
import math
import re
from collections import Counter
from datetime import date

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from newsalert.collector.config import CollectorSettings
from newsalert.collector.text import _TOKEN, norm_tok, text_terms
from newsalert.db.collector import Event, EventEvidence, GdeltCluster, WikiCheck, WikiEntry

UA = {"User-Agent": CollectorSettings().http_user_agent}
API = "https://en.wikipedia.org/w/api.php"
GENERIC_CAPS = {"united", "state", "the"}
MIN_SCORE = 4.0  # phase 1 threshold T on summed IDF of shared terms


def _plain(s: str) -> str:
    s = re.sub(r"<ref[^>]*>.*?</ref>|<ref[^>]*/>", "", s)
    s = re.sub(r"\{\{[^{}]*\}\}", "", s)
    s = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"\[https?://\S+\s*([^\]]*)\]", r"\1", s)
    return re.sub(r"'{2,}", "", s).strip()


def parse_day(day: date, wikitext: str) -> list[dict]:
    entries, category, stack = [], None, []
    lines = wikitext.splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"^'''(.+?)'''\s*$", line.strip())
        if m:
            category, stack = _plain(m.group(1)), []
            continue
        m = re.match(r"^(\*+)\s*(.*)$", line)
        if not m:
            continue
        depth, body = len(m.group(1)), m.group(2)
        stack = stack[: depth - 1] + [_plain(body)]
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        if not re.match(rf"^\*{{{depth + 1},}}", nxt) and len(_plain(body)) > 30:
            entries.append({"date": day.isoformat(), "category": category, "topic": stack[0],
                            "text": _plain(body), "links": json.dumps(re.findall(r"\[\[([^|\]]+)", body))})
    return entries


def fetch_day(day: date) -> list[dict]:
    page = f"Portal:Current_events/{day.year}_{day.strftime('%B')}_{day.day}"
    r = httpx.get(API, headers=UA, timeout=60,
                  params={"action": "parse", "page": page, "prop": "wikitext", "format": "json"})
    r.raise_for_status()
    data = r.json()
    return parse_day(day, data["parse"]["wikitext"]["*"]) if "parse" in data else []


def store(session: Session, entries: list[dict]) -> int:
    if not entries:
        return 0
    res = session.execute(insert(WikiEntry).values(entries).on_conflict_do_nothing(index_elements=["date", "text"]))
    return res.rowcount or 0


def _names(text: str) -> set[str]:
    body = re.sub(r"(\s*\([^)]*\))+\s*$", "", text)  # drop trailing "(Source)" citations
    words = _TOKEN.findall(body)
    return {norm_tok(w.lower()) for w in words[1:] if w[0].isupper()} - GENERIC_CAPS


def check(session: Session, event_ids: list[str], days: list[str]) -> dict:
    """Match events against Wikipedia entries of the given days (pass the window's days, two days back and one ahead)."""
    entries = session.scalars(select(WikiEntry).where(WikiEntry.date.in_(days))).all()
    if not entries:
        return {"entries": 0, "checked": 0, "matched": 0}
    terms = {e.id: text_terms(" ".join([e.text, e.topic or ""] + json.loads(e.links))) for e in entries}
    names = {e.id: _names(e.text) for e in entries}
    df = Counter(t for ts in terms.values() for t in ts)
    idf = {t: math.log(len(entries) / c) for t, c in df.items()}
    rare = math.log(len(entries) / 2)  # phase 1: at least one shared term in <= 2 entries
    matched = 0
    for eid in event_ids:
        kw = session.scalars(
            select(GdeltCluster.keywords).join(EventEvidence, EventEvidence.item_id == GdeltCluster.id)
            .where(EventEvidence.event_id == eid, EventEvidence.source == "gdelt")).all()
        headline = session.get(Event, eid).headline
        ev_terms = text_terms(headline) | {norm_tok(k) for ks in kw for k in json.loads(ks)}
        best = None
        for e in entries:
            shared = ev_terms & terms[e.id]
            s = sum(idf[t] for t in shared)
            if (len(shared) >= 2 and shared & names[e.id] and s >= MIN_SCORE
                    and any(idf[t] >= rare for t in shared) and (best is None or s > best[0])):
                    best = (s, e.id, sorted(shared))
        row = {"event_id": eid, "method": "keyword", "matched": best is not None,
               "wiki_entry_id": best[1] if best else None,
               "shared_terms": json.dumps(best[2]) if best else None}
        session.execute(insert(WikiCheck).values(row).on_conflict_do_update(
            index_elements=["event_id", "method"],
            set_={k: row[k] for k in ("matched", "wiki_entry_id", "shared_terms")}))
        matched += best is not None
    return {"entries": len(entries), "checked": len(event_ids), "matched": matched}
