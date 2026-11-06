"""Process one time window: GDELT -> clusters -> events (with RSS confirmation), then the Wikipedia check.

Usage:
  uv run python -m newsalert.collector.run --start 2026-11-05 --end 2026-11-06 [--rss-dir DIR] [--no-wiki]
--rss-dir loads saved RSS XML (<feed>.xml) before matching, e.g. an earlier snapshot.
"""
import argparse
import json
import logging
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from newsalert.collector import events, gdelt, grouping, rss, wikipedia
from newsalert.collector.config import CollectorSettings
from newsalert.db.base import utc_now
from newsalert.db.collector import CollectorRun, Event, RssItem
from newsalert.db.session import make_engine

log = logging.getLogger("collector")


def process_window(start: datetime, end: datetime, cfg: CollectorSettings,
                   rss_dir: Path | None = None, wiki: bool = True, rolling: bool = False) -> dict:
    """rolling=True (the worker): reuse one DuckDB file and delete raw files older than the window."""
    engine = make_engine(cfg.database_url)
    params = {k: getattr(cfg, k) for k in ("auto_min_outlets", "auto_min_rss", "review_min_outlets",
                                            "keep_clusters", "rss_min_shared_terms", "rss_max_hours")}
    with Session(engine) as s:
        run = CollectorRun(window_start=events._iso(start), window_end=events._iso(end), params=json.dumps(params))
        s.add(run)
        s.commit()
        run_id = run.id
    try:
        db = gdelt.download(start, end, cfg.data_dir, db_name="rolling.duckdb" if rolling else None,
                            prune_before=start if rolling else None)
        stories = grouping.group(db)
        log.info("%d stories from GDELT", len(stories))
        with Session(engine) as s:
            if rss_dir:
                log.info("%d rss items loaded from %s", rss.load_dir(s, rss_dir), rss_dir)
            lo = (start - timedelta(hours=cfg.rss_max_hours)).isoformat()[:19]
            hi = (end + timedelta(hours=cfg.rss_max_hours)).isoformat()[:19]
            items = s.scalars(select(RssItem).where(RssItem.published_at >= lo, RssItem.published_at <= hi)).all()
            counts = events.build(s, run_id, stories, list(items), cfg)
            run = s.get(CollectorRun, run_id)
            run.n_clusters, run.n_events = min(len(stories), cfg.keep_clusters), sum(counts.values())
            s.commit()
        result = {"run_id": run_id, "stories": len(stories), "rss_items": len(items), "bands": counts}
        if wiki:
            # Two days back: stories that started earlier are listed on the day they began.
            days = [(start.date() + timedelta(days=d)) for d in range(-2, (end - start).days + 1)]
            with Session(engine) as s:
                for d in days:
                    wikipedia.store(s, wikipedia.fetch_day(d))
                ids = s.scalars(select(Event.id).where(Event.last_run_id == run_id, Event.band != "drop")).all()
                result["wiki"] = wikipedia.check(s, list(ids), [d.isoformat() for d in days])
                s.commit()
        with Session(engine) as s:
            run = s.get(CollectorRun, run_id)
            run.status, run.finished_at = "ok", utc_now()
            s.commit()
        return result
    except Exception as e:
        with Session(engine) as s:
            run = s.get(CollectorRun, run_id)
            run.status, run.finished_at, run.error = "failed", utc_now(), f"{type(e).__name__}: {e}"[:2000]
            s.commit()
        raise


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=date.fromisoformat, required=True)
    ap.add_argument("--end", type=date.fromisoformat, required=True)
    ap.add_argument("--rss-dir", type=Path)
    ap.add_argument("--no-wiki", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    start = datetime(a.start.year, a.start.month, a.start.day, tzinfo=UTC).replace(tzinfo=None)
    end = datetime(a.end.year, a.end.month, a.end.day, tzinfo=UTC).replace(tzinfo=None)
    print(json.dumps(process_window(start, end, CollectorSettings(), a.rss_dir, not a.no_wiki), indent=1))


if __name__ == "__main__":
    main()
