"""Shared database setup: WAL mode and table creation for every registered model.

Usage: uv run python -m newsalert.db.init [database_url]

Proposed by the collector side as the "shared DB setup" in src/README.md; confirm with the
user/delivery side. V1 uses create_all: it creates missing tables and never alters existing
ones. Replace with a migration tool once schemas start changing.
"""
import os
import sys
from pathlib import Path

from sqlalchemy import text

import newsalert.db  # noqa: F401  registers all models on Base.metadata
from newsalert.db.base import Base
from newsalert.db.session import make_engine

DEFAULT_URL = "sqlite:///./data/newsalert.db"


def init_db(url: str) -> None:
    if url.startswith("sqlite:///") and ":memory:" not in url:
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    engine = make_engine(url)
    with engine.begin() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))
    Base.metadata.create_all(engine)
    engine.dispose()


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("NEWSALERT_DATABASE_URL", DEFAULT_URL)
    init_db(url)
    print(f"initialized {url}: {', '.join(sorted(Base.metadata.tables))}")
