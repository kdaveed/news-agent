"""One SQLite-backed dispatcher process. Does not create or migrate tables.

Run: python -m newsalert.delivery.dispatcher [--once]
"""

import argparse
import fcntl
import json
import logging
import signal
import threading
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import case, exists, literal, or_, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from newsalert.db import Delivery, Destination, Event, EventEvidence, GdeltCluster, RssItem
from newsalert.db.session import make_engine
from newsalert.delivery.channels import ChannelSender
from newsalert.delivery.config import DeliverySettings
from newsalert.delivery.messages import Notification, SendError, Target

logger = logging.getLogger(__name__)


def clock() -> datetime:
    return datetime.now(UTC)


def timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds")


def enqueue(engine, now: datetime, batch_size: int = 100) -> int:
    """Record fan-out once, including skipped rows for destinations already paused."""
    candidates = (
        select(
            Event.id,
            Destination.id,
            case((Destination.enabled.is_(True), "pending"), else_="skipped"),
            literal(0),
            literal(timestamp(now)),
        )
        .select_from(Event)
        .join(Destination, Destination.created_at <= Event.selected_at)
        .where(
            Event.status == "selected",
            Event.selected_at.is_not(None),
            ~exists().where(
                Delivery.event_id == Event.id, Delivery.destination_id == Destination.id
            ),
        )
        .order_by(Event.selected_at, Event.id, Destination.id)
        .limit(batch_size)
    )
    statement = (
        insert(Delivery)
        .from_select(
            ["event_id", "destination_id", "status", "attempts", "created_at"],
            candidates,
            include_defaults=False,
        )
        .on_conflict_do_nothing(index_elements=["event_id", "destination_id"])
    )
    with engine.begin() as connection:
        return connection.execute(statement).rowcount


def notification_for(session: Session, event: Event) -> Notification:
    links = []
    evidence = session.scalars(
        # RSS articles first (editor-chosen, confirming sources), then the newest GDELT cluster's samples.
        select(EventEvidence)
        .where(EventEvidence.event_id == event.id)
        .order_by(case((EventEvidence.source == "rss", 0), else_=1), EventEvidence.id.desc())
    )
    for item in evidence:
        if item.source == "rss":
            article = session.get(RssItem, item.item_id)
            if article:
                links.append(article.url)
        elif item.source == "gdelt":
            cluster = session.get(GdeltCluster, item.item_id)
            if cluster:
                try:
                    urls = json.loads(cluster.sample_urls)
                    if isinstance(urls, list):
                        links.extend(url for url in urls if isinstance(url, str))
                except (ValueError, TypeError):
                    continue
    return Notification(event.id, event.headline, event.summary or "", tuple(links))


def dispatch_once(engine, sender, settings: DeliverySettings, *, now_fn=clock) -> dict:
    stats = {
        "enqueued": enqueue(engine, now_fn(), settings.dispatcher_batch_size),
        "sent": 0,
        "retry": 0,
        "failed": 0,
        "skipped": 0,
    }
    with Session(engine) as session:
        ids = list(
            session.scalars(
                select(Delivery.id)
                .where(
                    Delivery.status == "pending",
                    or_(
                        Delivery.next_attempt_at.is_(None),
                        Delivery.next_attempt_at <= timestamp(now_fn()),
                    ),
                )
                .order_by(Delivery.id)
                .limit(settings.dispatcher_batch_size)
            )
        )

    for delivery_id in ids:
        with Session(engine) as session:
            job = session.get(Delivery, delivery_id)
            if job is None or job.status != "pending":
                continue
            destination = session.get(Destination, job.destination_id)
            event = session.get(Event, job.event_id)
            if (
                not destination
                or not destination.enabled
                or not event
                or event.status != "selected"
            ):
                job.status = "skipped"
                job.next_attempt_at = None
                session.commit()
                stats["skipped"] += 1
                continue
            if job.attempts >= settings.delivery_max_attempts:
                job.status = "failed"
                job.last_error = "Previous submission was interrupted; attempt limit reached"
                job.next_attempt_at = None
                session.commit()
                stats["failed"] += 1
                continue
            notification = notification_for(session, event)
            target = Target(
                destination.type, destination.email_address or destination.webhook_url or ""
            )
            job.attempts += 1
            # Persist the attempt before network I/O. A crash leaves a delayed, recoverable
            # pending row; delivery after a timeout remains at-least-once, not exactly-once.
            job.next_attempt_at = timestamp(now_fn() + timedelta(seconds=120))
            session.commit()

        error = None
        try:
            sender.send(notification, target)
        except SendError as failure:
            error = failure
        except Exception as failure:  # noqa: BLE001 - redact untrusted adapter exceptions
            # Never persist raw exception strings, which may contain webhook credentials.
            logger.error("Delivery %s: adapter raised %s", delivery_id, type(failure).__name__)
            error = SendError("Unexpected notification adapter failure", retryable=True)

        with Session(engine) as session:
            job = session.get(Delivery, delivery_id)
            if error is None:
                job.status = "sent"
                job.sent_at = timestamp(now_fn())
                job.last_error = None
                job.next_attempt_at = None
                stats["sent"] += 1
            else:
                job.last_error = str(error)
                if error.retryable and job.attempts < settings.delivery_max_attempts:
                    delay = max(
                        settings.delivery_retry_seconds * 2 ** (job.attempts - 1),
                        error.retry_after,
                    )
                    job.next_attempt_at = timestamp(now_fn() + timedelta(seconds=delay))
                    stats["retry"] += 1
                else:
                    job.status = "failed"
                    job.next_attempt_at = None
                    stats["failed"] += 1
            session.commit()
    return stats


@contextmanager
def single_dispatcher(engine):
    database = engine.url.database
    if not database or database == ":memory:":
        raise RuntimeError("Dispatcher CLI requires a file-backed SQLite database")
    path = Path(database).resolve().with_suffix(".dispatcher.lock")
    with path.open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("A dispatcher is already running for this database") from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Process one bounded batch and exit")
    args = parser.parse_args()
    settings = DeliverySettings()
    engine = make_engine(settings.database_url)
    sender = ChannelSender(settings)
    stopped = threading.Event()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_args: stopped.set())
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        with single_dispatcher(engine):
            while not stopped.is_set():
                try:
                    logger.info("Dispatch cycle: %s", dispatch_once(engine, sender, settings))
                except SQLAlchemyError as error:
                    logger.error(
                        "Dispatcher cycle failed (%s); check shared database setup",
                        type(error).__name__,
                    )
                    if args.once:
                        raise SystemExit(1) from None
                if args.once:
                    break
                stopped.wait(settings.dispatcher_poll_seconds)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
