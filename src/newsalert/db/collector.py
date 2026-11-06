"""Collector tables. Owner: collector. See phases/phase-2-implementation-v1/planning/data-schema-collector.md.

Registered on the shared Base, in the same database as the user/delivery tables.
Delivery reads only `events` (status = 'selected'). Wikipedia results live in `wiki_checks`
and are never used for scoring.
"""
from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from newsalert.db.base import Base, utc_now


class CollectorRun(Base):
    __tablename__ = "collector_runs"
    __table_args__ = (
        CheckConstraint("status IN ('running', 'ok', 'failed')", name="ck_collector_run_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    window_start: Mapped[str] = mapped_column(Text)
    window_end: Mapped[str] = mapped_column(Text)
    started_at: Mapped[str] = mapped_column(Text, default=utc_now)
    finished_at: Mapped[str | None] = mapped_column(Text)
    n_clusters: Mapped[int] = mapped_column(Integer, default=0)
    n_events: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(10), default="running")
    params: Mapped[str | None] = mapped_column(Text)  # JSON of thresholds used
    error: Mapped[str | None] = mapped_column(Text)


class GdeltCluster(Base):
    """Output of story grouping for one run (not raw GDELT records)."""

    __tablename__ = "gdelt_clusters"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("collector_runs.id"), index=True)
    cluster_key: Mapped[str] = mapped_column(String(64))  # stable: hash of earliest URL
    keywords: Mapped[str] = mapped_column(Text)  # JSON list
    sample_urls: Mapped[str] = mapped_column(Text)  # JSON list
    independent_outlets: Mapped[int] = mapped_column(Integer)
    raw_outlets: Mapped[int] = mapped_column(Integer)
    peak_window_outlets: Mapped[int] = mapped_column(Integer)
    first_seen: Mapped[str] = mapped_column(Text)
    last_seen: Mapped[str] = mapped_column(Text)
    score: Mapped[float] = mapped_column(Float)


class RssItem(Base):
    __tablename__ = "rss_items"
    __table_args__ = (UniqueConstraint("feed", "guid", name="uq_rss_feed_guid"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    feed: Mapped[str] = mapped_column(String(64))
    guid: Mapped[str] = mapped_column(Text)  # guid, or URL when the feed has none
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[str | None] = mapped_column(Text, index=True)
    first_seen_at: Mapped[str] = mapped_column(Text, default=utc_now)


class WikiEntry(Base):
    __tablename__ = "wiki_entries"
    __table_args__ = (UniqueConstraint("date", "text", name="uq_wiki_date_text"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[str] = mapped_column(String(10), index=True)
    category: Mapped[str | None] = mapped_column(Text)
    topic: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    links: Mapped[str] = mapped_column(Text)  # JSON list
    fetched_at: Mapped[str] = mapped_column(Text, default=utc_now)


class Event(Base):
    """Shared with delivery. Delivery reads only status = 'selected'."""

    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint("band IN ('auto', 'review', 'drop')", name="ck_event_band"),
        CheckConstraint("status IN ('candidate', 'selected', 'dropped')", name="ck_event_status"),
        Index("ix_events_status_selected", "status", "selected_at"),
    )

    id: Mapped[str] = mapped_column(String(255), primary_key=True)  # "evt-" + stable hash, TEXT
    headline: Mapped[str] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    score: Mapped[float] = mapped_column(Float)
    independent_outlets: Mapped[int] = mapped_column(Integer)
    rss_confirmations: Mapped[int] = mapped_column(Integer, default=0)
    band: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(10), default="candidate")
    first_seen: Mapped[str] = mapped_column(Text)
    selected_at: Mapped[str | None] = mapped_column(Text)
    last_run_id: Mapped[int] = mapped_column(ForeignKey("collector_runs.id"))
    note: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[str] = mapped_column(Text, default=utc_now, onupdate=utc_now)


class EventEvidence(Base):
    __tablename__ = "event_evidence"
    __table_args__ = (
        CheckConstraint("source IN ('gdelt', 'rss')", name="ck_evidence_source"),
        UniqueConstraint("event_id", "source", "item_id", name="uq_evidence"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[str] = mapped_column(String(255), ForeignKey("events.id"), index=True)
    source: Mapped[str] = mapped_column(String(10))
    item_id: Mapped[int] = mapped_column(Integer)  # gdelt_clusters.id or rss_items.id
    match_method: Mapped[str] = mapped_column(String(32))
    confidence: Mapped[float] = mapped_column(Float)


class WikiCheck(Base):
    """Independent checker: never read by scoring."""

    __tablename__ = "wiki_checks"
    __table_args__ = (UniqueConstraint("event_id", "method", name="uq_wiki_check"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[str] = mapped_column(String(255), ForeignKey("events.id"), index=True)
    wiki_entry_id: Mapped[int | None] = mapped_column(ForeignKey("wiki_entries.id"))
    matched: Mapped[bool] = mapped_column(default=False)
    method: Mapped[str] = mapped_column(String(16))  # keyword | llm
    shared_terms: Mapped[str | None] = mapped_column(Text)  # JSON list, for review
    checked_at: Mapped[str] = mapped_column(Text, default=utc_now)
