"""Collector unit tests: no network, in-memory/temporary databases only."""
import datetime as dt
import json

import duckdb
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from newsalert.collector import events as ev
from newsalert.collector import grouping
from newsalert.collector.config import CollectorSettings
from newsalert.collector.text import canonical_url, slug_tokens
from newsalert.collector.wikipedia import check, parse_day
from newsalert.db import Base, CollectorRun, Event, EventEvidence, RssItem, WikiCheck, WikiEntry

T0 = dt.datetime(2026, 11, 5, 8, 0)


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def cfg(**kw):
    return CollectorSettings(database_url="sqlite://", **kw)


def story(key, urls, outlets=150, first=T0, keywords=("flood", "river", "city")):
    return {"cluster_key": key, "score": float(outlets), "independent_outlets": outlets,
            "peak_window_outlets": outlets // 2, "raw_outlets": outlets, "first_seen": first,
            "last_seen": first + dt.timedelta(hours=6), "keywords": list(keywords),
            "sample_urls": urls[:3], "urls": sorted(urls), "headline_hint": urls[0]}


def new_run(s):
    run = CollectorRun(window_start="2026-11-05T00:00:00+00:00", window_end="2026-11-06T00:00:00+00:00")
    s.add(run)
    s.flush()
    return run.id


# --- text --------------------------------------------------------------------------------

def test_canonical_url_keeps_identifying_query_and_drops_tracking():
    assert canonical_url("https://x.com/a?id=1") != canonical_url("https://x.com/a?id=2")
    assert canonical_url("https://www.bbc.co.uk/news/a-b-c?at_medium=RSS") == "bbc.co.uk/news/a-b-c"
    assert canonical_url("https://x.com/a?b=2&a=1") == canonical_url("https://x.com/a/?a=1&b=2")


def test_slug_tokens_skip_id_fragments():
    assert slug_tokens("https://w.com/article/spot-stolen-scam-valor-dcb3e-ecdd4f/12") == [
        "spot", "stolen", "scam", "valor"]


# --- grouping ----------------------------------------------------------------------------

def test_syndicated_copies_on_the_same_outlets_count_once(tmp_path):
    db = tmp_path / "m.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE TABLE mentions(GlobalEventID BIGINT, MentionTime TIMESTAMP, "
                "MentionSourceName VARCHAR, MentionIdentifier VARCHAR, Confidence INT)")
    rows = [(i, T0 + dt.timedelta(minutes=i), dom,
             f"https://{dom}/news/river-flood-city-evacuation-warning-{w}")
            for i, w in enumerate(["alpha", "bravo", "charlie", "delta", "echo"])
            for dom in ("a.com", "b.com", "c.com")]
    con.executemany("INSERT INTO mentions VALUES (?, ?, ?, ?, 100)", rows)
    con.close()
    stories = grouping.group(db)
    assert stories and max(s["independent_outlets"] for s in stories) <= 3


# --- events ------------------------------------------------------------------------------

def test_banding_and_selection(session):
    run = new_run(session)
    urls = [f"https://site{i}.com/news/flood-river-city-{i}" for i in range(5)]
    rss = [RssItem(feed=f, guid=f, url=f"https://{f}.com/x/flood-river-city", title="Flood hits river city",
                   published_at=(T0 + dt.timedelta(hours=1)).isoformat() + "+00:00") for f in ("bbc", "dw")]
    session.add_all(rss)
    session.flush()
    counts = ev.build(session, run, [story("k1", urls, outlets=150)], rss, cfg())
    e = session.get(Event, "evt-k1")
    assert counts["auto"] == 1 and e.status == "selected" and e.selected_at
    assert e.rss_confirmations == 2 and e.headline == "Flood hits river city"
    order = session.scalars(select(EventEvidence.source).where(EventEvidence.event_id == "evt-k1")
                            .order_by(EventEvidence.id)).all()
    assert order[0] == "rss"  # RSS evidence first, so readers get confirming links


def test_same_story_in_a_later_window_keeps_its_event_id(session):
    urls = [f"https://site{i}.com/news/flood-river-city-{i}" for i in range(10)]
    ev.build(session, new_run(session), [story("k1", urls)], [], cfg(auto_min_rss=0))
    # Next window: the earliest article dropped out, so the key changes, but most articles are shared.
    later = story("k2", urls[1:] + ["https://new.com/news/flood-river-city-new"],
                  first=T0 + dt.timedelta(hours=2))
    ev.build(session, new_run(session), [later], [], cfg(auto_min_rss=0))
    assert session.get(Event, "evt-k2") is None
    assert session.scalar(select(func.count()).select_from(Event)) == 1


def test_selected_and_admin_decisions_are_never_undone(session):
    urls = [f"https://s{i}.com/news/storm-coast-town-{i}" for i in range(6)]
    ev.build(session, new_run(session), [story("k1", urls, outlets=150)], [], cfg(auto_min_rss=0))
    assert session.get(Event, "evt-k1").status == "selected"
    ev.build(session, new_run(session), [story("k1", urls, outlets=5)], [], cfg(auto_min_rss=0))
    assert session.get(Event, "evt-k1").status == "selected"  # drop band later does not unselect

    other = [f"https://o{i}.com/news/quake-hill-village-{i}" for i in range(6)]
    ev.build(session, new_run(session), [story("k9", other, outlets=50)], [], cfg())
    e = session.get(Event, "evt-k9")
    e.status, e.note = "dropped", "dropped by admin a@example.com"
    session.flush()
    ev.build(session, new_run(session), [story("k9", other, outlets=500)], [], cfg(auto_min_rss=0))
    assert session.get(Event, "evt-k9").status == "dropped"


# --- wikipedia ---------------------------------------------------------------------------

def test_parse_day_keeps_leaf_entries():
    text = ("'''Disasters'''\n*[[2026 Learjet crash]]\n**Nine people are killed after a Learjet "
            "crashes in Greenacres, Florida. (AP)\n*Short.")
    entries = parse_day(dt.date(2026, 11, 1), text)
    assert len(entries) == 1 and entries[0]["topic"] == "2026 Learjet crash"


def test_wikipedia_check_needs_a_shared_name(session):
    run = new_run(session)
    urls = [f"https://s{i}.com/news/learjet-crash-florida-nine-killed-{i}" for i in range(4)]
    ev.build(session, run, [story("k1", urls, outlets=60, keywords=("learjet", "crash", "florida"))],
             [], cfg())
    session.add_all([
        WikiEntry(date="2026-11-05", topic="Learjet crash", links=json.dumps(["Greenacres"]),
                  text="Nine people are killed after a Learjet business jet crashes in Florida. (AP)"),
        WikiEntry(date="2026-11-05", topic="Elections", links="[]",
                  text="Voters in several states choose a new governor in close races. (Reuters)"),
        WikiEntry(date="2026-11-05", topic="Weather", links="[]",
                  text="Heavy rain causes flooding across the northern provinces of the country. (AP)"),
    ])
    session.flush()
    result = check(session, ["evt-k1"], ["2026-11-05"])
    wc = session.scalar(select(WikiCheck).where(WikiCheck.event_id == "evt-k1"))
    assert result["matched"] == 1 and wc.matched and "learjet" in json.loads(wc.shared_terms)


def test_story_that_grows_a_lot_keeps_its_event_id(session):
    first = [f"https://s{i}.com/news/storm-coast-town-{i}" for i in range(80)]
    ev.build(session, new_run(session), [story("k1", first)], [], cfg(auto_min_rss=0))
    grown = first + [f"https://n{i}.com/news/storm-coast-town-more-{i}" for i in range(500)]
    ev.build(session, new_run(session), [story("k2", grown, first=T0 - dt.timedelta(hours=1))], [],
             cfg(auto_min_rss=0))
    assert session.get(Event, "evt-k2") is None


def test_small_overlap_does_not_take_over_an_event(session):
    a = [f"https://a{i}.com/news/quake-hill-village-{i}" for i in range(15)]
    ev.build(session, new_run(session), [story("k1", a)], [], cfg(auto_min_rss=0))
    b = a[:3] + [f"https://b{i}.com/news/budget-vote-parliament-{i}" for i in range(12)]
    ev.build(session, new_run(session), [story("k2", b)], [], cfg(auto_min_rss=0))
    assert session.get(Event, "evt-k2") is not None  # 3 shared articles are not enough


def test_review_candidate_stays_reviewable_as_coverage_fades(session):
    urls = [f"https://s{i}.com/news/strike-port-workers-{i}" for i in range(8)]
    ev.build(session, new_run(session), [story("k1", urls, outlets=50)], [], cfg())
    assert session.get(Event, "evt-k1").band == "review"
    ev.build(session, new_run(session), [story("k1", urls, outlets=5)], [], cfg())
    e = session.get(Event, "evt-k1")
    assert (e.band, e.status) == ("review", "candidate")


def test_only_the_newest_cluster_keeps_article_urls(session):
    from newsalert.db import GdeltCluster
    urls = [f"https://s{i}.com/news/flood-river-city-{i}" for i in range(10)]
    for _ in range(3):
        ev.build(session, new_run(session), [story("k1", urls)], [], cfg(auto_min_rss=0))
    stored = [json.loads(c.article_urls) for c in session.scalars(select(GdeltCluster).order_by(GdeltCluster.id))]
    assert [len(x) for x in stored] == [0, 0, 10]
