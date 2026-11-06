"""Shared database setup: WAL mode and table creation for every registered model.

Usage: uv run python -m newsalert.db.init [database_url]

Proposed by the collector side as the "shared DB setup" in src/README.md; confirm with the
user/delivery side. V1 uses create_all plus ADDED_COLUMNS for columns added later (no data is lost).
Replace with a migration tool once schemas change more often.
"""
import sys
from pathlib import Path

from sqlalchemy import text

import newsalert.db  # noqa: F401  registers all models on Base.metadata
from newsalert.db.base import Base
from newsalert.db.session import make_engine


def init_db(url: str) -> None:
    if url.startswith("sqlite:///") and ":memory:" not in url:
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    engine = make_engine(url)
    with engine.begin() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))
    Base.metadata.create_all(engine)
    _add_missing_columns(engine)
    engine.dispose()


# Columns added after the first release; create_all does not alter existing tables.
ADDED_COLUMNS = {("gdelt_clusters", "article_urls"): "TEXT NOT NULL DEFAULT '[]'"}


def _add_missing_columns(engine) -> None:
    with engine.begin() as conn:
        for (table, column), ddl in ADDED_COLUMNS.items():
            have = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
            if have and column not in have:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))


if __name__ == "__main__":
    # Same source as the app and workers: environment first, then .env (pydantic settings).
    from newsalert.collector.config import CollectorSettings

    url = sys.argv[1] if len(sys.argv) > 1 else CollectorSettings().database_url
    init_db(url)
    print(f"initialized {url}: {', '.join(sorted(Base.metadata.tables))}")
