"""Fetch a small RSS shortlist once and retain evidence for a collection benchmark.

Run from any directory: python3 research/rss/probe.py
Raw XML is kept under research/data (gitignored); reports contain metadata only.
No article pages are fetched. Network errors are recorded per feed.
"""

import concurrent.futures
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
from pathlib import Path
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET


FEEDS = {
    "bbc_world": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "guardian_world": "https://www.theguardian.com/world/rss",
    "dw_world": "https://rss.dw.com/rdf/rss-en-world",
    "france24_en": "https://www.france24.com/en/rss",
    "aljazeera_en": "https://www.aljazeera.com/xml/rss/all.xml",
    "nyt_world": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    "sky_world": "https://feeds.skynews.com/feeds/rss/world.xml",
}
ROOT = Path(__file__).resolve().parents[1]


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def local_name(tag):
    return tag.rsplit("}", 1)[-1]


def text_field(element, name):
    for child in element:
        # Media RSS content describes an image/video, not the article body.
        if name == "content" and child.tag.startswith("{http://search.yahoo.com/mrss/}"):
            continue
        if local_name(child.tag) == name:
            return "".join(child.itertext()).strip()
    return ""


def parse_date(value):
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
    except (ValueError, TypeError):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    # Do not invent a timezone when a publisher omits it.
    return dt.astimezone(timezone.utc).isoformat() if dt.tzinfo else None


def probe(name, url, raw_dir):
    started = time.monotonic()
    result = {"name": name, "url": url, "requested_at": utc_now()}
    try:
        request = urllib.request.Request(
            url, headers={"User-Agent": "news-agent-research/0.1 (RSS evaluation)"}
        )
        with urllib.request.urlopen(request, timeout=25) as response:
            raw = response.read(5_000_001)
            if len(raw) > 5_000_000:
                raise ValueError("feed exceeds probe size limit")
            result.update({
                "status": response.status,
                "final_url": response.url,
                "content_type": response.headers.get("Content-Type"),
                "etag": response.headers.get("ETag"),
                "last_modified": response.headers.get("Last-Modified"),
                "cache_control": response.headers.get("Cache-Control"),
                "http_date": response.headers.get("Date"),
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            })
        result["received_at"] = utc_now()
        raw_path = raw_dir / f"{name}.xml"
        raw_path.write_bytes(raw)
        result["raw_path"] = str(raw_path.relative_to(ROOT))
        root = ET.fromstring(raw)
        items = []
        for element in root.iter():
            if local_name(element.tag) not in {"item", "entry"}:
                continue
            link = text_field(element, "link")
            if not link:
                link = next((child.get("href", "") for child in element
                             if local_name(child.tag) == "link"
                             and child.get("rel", "alternate") == "alternate"), "")
            published = (text_field(element, "pubDate")
                         or text_field(element, "published")
                         or text_field(element, "date"))
            description = text_field(element, "description") or text_field(element, "summary")
            content = text_field(element, "encoded") or text_field(element, "content")
            items.append({
                "title": text_field(element, "title"),
                "url": link,
                "guid": text_field(element, "guid") or text_field(element, "id"),
                "published_raw": published,
                "published_utc": parse_date(published),
                "updated_raw": text_field(element, "updated"),
                "description_characters": len(description),
                "content_characters": len(content),
            })
        dates = sorted(item["published_utc"] for item in items if item["published_utc"])
        result.update({
            "root_tag": root.tag,
            "items": items,
            "item_count": len(items),
            "unique_urls": len({item["url"] for item in items if item["url"]}),
            "fields_present": {key: sum(bool(item[key]) for item in items) for key in
                               ["title", "url", "guid", "published_utc",
                                "description_characters", "content_characters"]},
            "oldest_published_utc": dates[0] if dates else None,
            "newest_published_utc": dates[-1] if dates else None,
        })
        if dates:
            result["publication_span_hours"] = round(
                (datetime.fromisoformat(dates[-1]) - datetime.fromisoformat(dates[0])).total_seconds() / 3600, 2
            )
    except Exception as error:
        result["error"] = f"{type(error).__name__}: {error}"
        if isinstance(error, urllib.error.HTTPError):
            result["status"] = error.code
    result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    return result


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    raw_dir = ROOT / "data" / "rss" / stamp
    raw_dir.mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(probe, name, url, raw_dir) for name, url in FEEDS.items()]
        results = [future.result() for future in futures]
    report_dir = ROOT / "results" / "rss_probe"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{stamp}.json"
    report_path.write_text(json.dumps({"feeds": results}, indent=2) + "\n")
    print(f"Report: {report_path}")
    for result in results:
        print(json.dumps({key: value for key, value in result.items()
                          if key not in {"items", "fields_present"}}))


if __name__ == "__main__":
    main()
