"""Turn GDELT clusters into events: RSS confirmation, headline, banding, evidence.

Wikipedia is not read here. Scoring uses only GDELT outlets and RSS confirmations.
"""
import json
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from newsalert.collector.config import CollectorSettings
from newsalert.collector.text import canonical_url, norm_tok, text_terms, url_terms
from newsalert.db.base import utc_now
from newsalert.db.collector import Event, EventEvidence, GdeltCluster, RssItem


def _iso(dt) -> str:
    return dt.isoformat() + "+00:00" if dt.tzinfo is None else dt.isoformat()


def match_rss(stories: list[dict], items: list[RssItem], cfg: CollectorSettings) -> dict[int, list]:
    """Assign each RSS item to at most one story (best match). Returns story index -> [(item, method, conf)]."""
    url_index = {}
    terms = []
    for i, s in enumerate(stories):
        for u in s["urls"]:
            url_index.setdefault(canonical_url(u), i)
        t = {norm_tok(k) for k in s["keywords"]}
        for u in s["sample_urls"]:
            t |= url_terms(u)
        terms.append(t)
    window = timedelta(hours=cfg.rss_max_hours)
    out: dict[int, list] = {}
    for it in items:
        hit = url_index.get(canonical_url(it.url))
        if hit is not None:
            out.setdefault(hit, []).append((it, "url", 1.0))
            continue
        title = text_terms(it.title) | url_terms(it.url)
        if len(title) < cfg.rss_min_shared_terms or not it.published_at:
            continue
        best, best_n = None, cfg.rss_min_shared_terms - 1
        for i, s in enumerate(stories):
            pub = it.published_at[:19]
            if not (_iso(s["first_seen"] - window)[:19] <= pub <= _iso(s["last_seen"] + window)[:19]):
                continue
            n = len(title & terms[i])
            if n > best_n:
                best, best_n = i, n
        if best is not None:
            out.setdefault(best, []).append((it, "terms", round(best_n / len(title), 2)))
    return out


def band(outlets: int, feeds: int, cfg: CollectorSettings) -> str:
    if outlets >= cfg.auto_min_outlets and feeds >= cfg.auto_min_rss:
        return "auto"
    if outlets >= cfg.review_min_outlets:
        return "review"
    return "drop"


def _headline(story: dict, rss: list) -> tuple[str, str | None]:
    if rss:
        it = min((x[0] for x in rss), key=lambda i: (i.published_at or "9999", i.id))
        return it.title, it.description
    words = story["keywords"][:8]
    return (" ".join(words).capitalize() if words else story["sample_urls"][0]), None


def build(session: Session, run_id: int, stories: list[dict], rss_items: list[RssItem],
          cfg: CollectorSettings) -> dict:
    """Write clusters, events and evidence for one run. Returns counts per band."""
    kept = stories[: cfg.keep_clusters]
    matches = match_rss(kept, rss_items, cfg)
    counts = {"auto": 0, "review": 0, "drop": 0}
    now = utc_now()
    for i, s in enumerate(kept):
        cl = GdeltCluster(
            run_id=run_id, cluster_key=s["cluster_key"], keywords=json.dumps(s["keywords"]),
            sample_urls=json.dumps(s["sample_urls"]), independent_outlets=s["independent_outlets"],
            raw_outlets=s["raw_outlets"], peak_window_outlets=s["peak_window_outlets"],
            first_seen=_iso(s["first_seen"]), last_seen=_iso(s["last_seen"]), score=s["score"])
        session.add(cl)
        session.flush()
        rss = matches.get(i, [])
        feeds = len({x[0].feed for x in rss})
        b = band(s["independent_outlets"], feeds, cfg)
        counts[b] += 1
        headline, desc = _headline(s, rss)
        summary = desc or f"Covered by {s['independent_outlets']} independent outlets."
        eid = f"evt-{s['cluster_key']}"
        ev = session.get(Event, eid)
        if ev is None:
            ev = Event(id=eid, first_seen=_iso(s["first_seen"]), status="candidate")
            session.add(ev)
        ev.headline, ev.summary, ev.score = headline, summary, s["score"]
        ev.independent_outlets, ev.rss_confirmations, ev.last_run_id = s["independent_outlets"], feeds, run_id
        if ev.status != "selected":  # never move an event out of selected
            ev.band = b
            ev.status = {"auto": "selected", "review": "candidate", "drop": "dropped"}[b]
            if b == "auto":
                ev.selected_at = now
        session.flush()
        session.add(EventEvidence(event_id=eid, source="gdelt", item_id=cl.id,
                                  match_method="cluster", confidence=1.0))
        for it, method, conf in rss:
            exists = session.scalar(select(EventEvidence.id).where(
                EventEvidence.event_id == eid, EventEvidence.source == "rss", EventEvidence.item_id == it.id))
            if not exists:
                session.add(EventEvidence(event_id=eid, source="rss", item_id=it.id,
                                          match_method=method, confidence=conf))
    return counts
