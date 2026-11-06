"""Turn GDELT clusters into events: RSS confirmation, headline, banding, evidence.

Wikipedia is not read here. Scoring uses only GDELT outlets and RSS confirmations.
"""
import json
import re
from collections import Counter
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

from sqlalchemy import func, select, update
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


def _slug_headline(url: str) -> str | None:
    """Readable words of the article's own slug, in order: 'florida-jet-crash-kills-nine' -> 'Florida jet crash kills nine'."""
    segs = [s for s in urlparse(url).path.split("/") if s.count("-") + s.count("_") >= 2]
    if not segs:
        return None
    seg = re.sub(r"\.(html?|php|aspx?|shtml)$", "", max(segs, key=len))
    words = [w for w in re.split(r"[-_.]+", seg) if w and not any(c.isdigit() for c in w)]
    return " ".join(words).capitalize() if len(words) >= 3 else None


def _headline(story: dict, rss: list) -> tuple[str, str | None]:
    if rss:
        it = min((x[0] for x in rss), key=lambda i: (i.published_at or "9999", i.id))
        return it.title, it.description
    hint = _slug_headline(story.get("headline_hint") or story["sample_urls"][0])
    if hint:
        return hint, None
    words = story["keywords"][:8]
    return (" ".join(words).capitalize() if words else story["sample_urls"][0]), None


MAX_ARTICLE_URLS = 500  # stored per cluster for matching the same story across runs


def _latest_clusters():
    """Newest GDELT cluster id per event."""
    return (select(EventEvidence.event_id, func.max(EventEvidence.item_id).label("cluster_id"))
            .where(EventEvidence.source == "gdelt").group_by(EventEvidence.event_id).subquery())


def _known_urls(session: Session, since: str) -> tuple[dict[str, str], dict[str, int]]:
    """canonical article URL -> event id, and event id -> number of stored URLs,
    from each recent event's newest cluster only (older clusters are cleared, see _prune)."""
    latest = _latest_clusters()
    rows = session.execute(
        select(GdeltCluster.article_urls, latest.c.event_id)
        .join(latest, GdeltCluster.id == latest.c.cluster_id)
        .where(GdeltCluster.last_seen >= since)).all()
    known: dict[str, str] = {}
    sizes: dict[str, int] = {}
    for urls, eid in rows:
        stored = json.loads(urls or "[]")
        sizes[eid] = len(stored)
        for u in stored:
            known[canonical_url(u)] = eid
    return known, sizes


MIN_SHARED_ARTICLES = 5


def _same_story(urls: list[str], known: dict[str, str], sizes: dict[str, int],
                taken: set[str]) -> str | None:
    """Existing event that shares enough articles with this cluster: at least 5, and 20% of the
    smaller of the two (so a story that grows a lot still matches its earlier event)."""
    hits = Counter(known[c] for c in (canonical_url(u) for u in urls) if c in known)
    for eid, n in hits.most_common():
        if eid not in taken and n >= max(MIN_SHARED_ARTICLES, 0.2 * min(len(urls), sizes.get(eid, 0))):
            return eid
    return None


def _prune(session: Session, run_id: int) -> None:
    """Keep article URLs only on each event's newest cluster; older copies are not needed for matching."""
    latest = select(_latest_clusters().c.cluster_id)
    session.execute(update(GdeltCluster)
                    .where(GdeltCluster.run_id < run_id, GdeltCluster.article_urls != "[]",
                           GdeltCluster.id.not_in(latest))
                    .values(article_urls="[]"))


def build(session: Session, run_id: int, stories: list[dict], rss_items: list[RssItem],
          cfg: CollectorSettings) -> dict:
    """Write clusters, events and evidence for one run. Returns counts per band."""
    kept = stories[: cfg.keep_clusters]
    matches = match_rss(kept, rss_items, cfg)
    counts = {"auto": 0, "review": 0, "drop": 0}
    now = utc_now()
    since = _iso(min((s["first_seen"] for s in kept), default=datetime.now(UTC).replace(tzinfo=None))
                 - timedelta(days=3))
    (known, sizes), taken = _known_urls(session, since), set()
    for i, s in enumerate(kept):
        urls = s["urls"]  # match on all articles; store at most MAX_ARTICLE_URLS
        cl = GdeltCluster(
            run_id=run_id, cluster_key=s["cluster_key"], keywords=json.dumps(s["keywords"]),
            sample_urls=json.dumps(s["sample_urls"]), article_urls=json.dumps(urls[:MAX_ARTICLE_URLS]),
            independent_outlets=s["independent_outlets"],
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
        # Same story as an event from an earlier run? Keep that event's id, so delivery dedup holds.
        eid = _same_story(urls, known, sizes, taken) or f"evt-{s['cluster_key']}"
        if eid in taken:  # two clusters of this run mapped to one id: keep them apart
            eid = f"evt-{s['cluster_key']}-{i}"
        taken.add(eid)
        ev = session.get(Event, eid)
        if ev is None:
            ev = Event(id=eid, first_seen=_iso(s["first_seen"]), status="candidate")
            session.add(ev)
        ev.headline, ev.summary, ev.score = headline, summary, s["score"]
        ev.independent_outlets, ev.rss_confirmations, ev.last_run_id = s["independent_outlets"], feeds, run_id
        admin_decided = bool(ev.note and "by admin" in ev.note)
        # A review candidate stays reviewable while its coverage fades in the rolling window.
        waiting_review = ev.band == "review" and ev.status == "candidate" and b == "drop"
        if ev.status != "selected" and not admin_decided and not waiting_review:
            ev.band = b
            ev.status = {"auto": "selected", "review": "candidate", "drop": "dropped"}[b]
            if b == "auto":
                ev.selected_at = now
        session.flush()
        for it, method, conf in rss:  # RSS evidence first: these are the links readers should see
            exists = session.scalar(select(EventEvidence.id).where(
                EventEvidence.event_id == eid, EventEvidence.source == "rss", EventEvidence.item_id == it.id))
            if not exists:
                session.add(EventEvidence(event_id=eid, source="rss", item_id=it.id,
                                          match_method=method, confidence=conf))
        session.add(EventEvidence(event_id=eid, source="gdelt", item_id=cl.id,
                                  match_method="cluster", confidence=1.0))
    session.flush()
    _prune(session, run_id)
    return counts
