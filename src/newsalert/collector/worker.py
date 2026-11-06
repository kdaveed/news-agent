"""Continuous collector: every cycle polls RSS and processes the last 24 hours of GDELT.

Usage: uv run python -m newsalert.collector.worker [--interval-minutes 15] [--once]
Each cycle reuses process_window(); events keep their ids across overlapping windows
(see events._same_story), so an already selected story is not sent again.
The Wikipedia check covers the window plus two earlier days on every cycle; entries for
yesterday keep filling in, so later cycles can still confirm yesterday's events.
"""
import argparse
import logging
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from newsalert.collector import rss
from newsalert.collector.config import CollectorSettings
from newsalert.collector.run import process_window
from newsalert.db.session import make_engine

log = logging.getLogger("collector.worker")


RSS_KEEP_DAYS = 3


def prune_rss_snapshots(data_dir, now: datetime) -> int:
    """Delete raw RSS poll folders (data/rss/<YYYYmmddTHHMMSSZ>) older than RSS_KEEP_DAYS; items stay in the DB."""
    cutoff = (now - timedelta(days=RSS_KEEP_DAYS)).strftime("%Y%m%dT%H%M%SZ")
    removed = 0
    for folder in (data_dir / "rss").glob("*T*Z"):
        if folder.is_dir() and folder.name < cutoff:
            for f in folder.iterdir():
                f.unlink()
            folder.rmdir()
            removed += 1
    return removed


def cycle(cfg: CollectorSettings, hours: int = 24) -> dict:
    engine = make_engine(cfg.database_url)
    with Session(engine) as s:
        new_items = rss.poll(s, cfg.data_dir)
        s.commit()
    end = datetime.now(UTC).replace(tzinfo=None, second=0, microsecond=0)
    end -= timedelta(minutes=end.minute % 15)  # last complete GDELT slot
    result = process_window(end - timedelta(hours=hours), end, cfg, rolling=True)
    result["new_rss_items"] = new_items
    result["pruned_rss_folders"] = prune_rss_snapshots(cfg.data_dir, datetime.now(UTC))
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval-minutes", type=int, default=15)
    ap.add_argument("--hours", type=int, default=24, help="length of the rolling GDELT window")
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    cfg = CollectorSettings()
    while True:
        started = time.monotonic()
        try:
            log.info("cycle done: %s", cycle(cfg, a.hours))
        except Exception:  # keep the worker alive; the failed run is recorded in collector_runs
            log.exception("cycle failed")
        if a.once:
            break
        time.sleep(max(60.0, a.interval_minutes * 60 - (time.monotonic() - started)))


if __name__ == "__main__":
    main()
