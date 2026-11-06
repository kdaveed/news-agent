"""RSS: poll the feeds (raw XML saved per poll) and load items into rss_items.

Usage:
  uv run python -m newsalert.collector.rss poll          # fetch all feeds once, save XML, load items
  uv run python -m newsalert.collector.rss load <dir>    # load previously saved XML files (<feed>.xml)
RSS has no history, so polling has to run continuously from now on.
"""
import html
import logging
import re
import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

import httpx
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from newsalert.collector.config import FEEDS, CollectorSettings
from newsalert.db.collector import RssItem
from newsalert.db.session import make_engine

log = logging.getLogger(__name__)
UA = {"User-Agent": CollectorSettings().http_user_agent}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _field(el, name: str) -> str:
    for child in el:
        if name == "content" and child.tag.startswith("{http://search.yahoo.com/mrss/}"):
            continue  # Media RSS describes images/video, not article text
        if _local(child.tag) == name:
            return "".join(child.itertext()).strip()
    return ""


def _date(value: str) -> str | None:
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
    except (ValueError, TypeError):
        try:
            dt = datetime.fromisoformat(value)
        except ValueError:
            return None
    return dt.astimezone(UTC).isoformat() if dt.tzinfo else None


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text))).strip()


def parse(feed: str, raw: bytes, seen_at: str) -> list[dict]:
    items = []
    for el in ET.fromstring(raw).iter():
        if _local(el.tag) not in {"item", "entry"}:
            continue
        url = _field(el, "link") or next(
            (c.get("href", "") for c in el if _local(c.tag) == "link" and c.get("rel", "alternate") == "alternate"), "")
        title = _clean(_field(el, "title"))
        if not url or not title:
            continue
        items.append({
            "feed": feed, "guid": _field(el, "guid") or _field(el, "id") or url, "url": url, "title": title,
            "description": _clean(_field(el, "description") or _field(el, "summary"))[:2000] or None,
            "published_at": _date(_field(el, "pubDate") or _field(el, "published") or _field(el, "date")),
            "first_seen_at": seen_at,
        })
    return items


def store(session: Session, items: list[dict]) -> int:
    """Insert new items; existing (feed, guid) pairs are left untouched."""
    if not items:
        return 0
    res = session.execute(insert(RssItem).values(items).on_conflict_do_nothing(index_elements=["feed", "guid"]))
    return res.rowcount or 0


def load_dir(session: Session, folder: Path, seen_at: str | None = None) -> int:
    seen_at = seen_at or datetime.fromtimestamp(folder.stat().st_mtime, UTC).isoformat()
    n = 0
    for name in FEEDS:
        f = folder / f"{name}.xml"
        if f.exists():
            n += store(session, parse(name, f.read_bytes(), seen_at))
    return n


def poll(session: Session, data_dir: Path) -> int:
    stamp = datetime.now(UTC)
    folder = data_dir / "rss" / stamp.strftime("%Y%m%dT%H%M%SZ")
    folder.mkdir(parents=True, exist_ok=True)
    n = 0
    with httpx.Client(timeout=25, headers=UA, follow_redirects=True) as client:
        for name, url in FEEDS.items():
            try:
                r = client.get(url)
                r.raise_for_status()
            except httpx.HTTPError as e:
                log.warning("rss %s failed: %s", name, e)
                continue
            (folder / f"{name}.xml").write_bytes(r.content)
            n += store(session, parse(name, r.content, stamp.isoformat()))
    return n


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    cfg = CollectorSettings()
    engine = make_engine(cfg.database_url)
    with Session(engine) as s:
        if sys.argv[1:2] == ["load"]:
            n = load_dir(s, Path(sys.argv[2]))
        else:
            n = poll(s, cfg.data_dir)
        s.commit()
    print(f"{n} new rss items")
