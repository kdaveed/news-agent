"""Download GDELT 2.0 events + mentions for a UTC window into a DuckDB file (raw layer).

Files are addressed directly by their 15-minute timestamp, so no 120 MB master list is needed.
Missing slots (GDELT occasionally skips one) are logged and skipped.
"""
import concurrent.futures as cf
import io
import logging
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

import duckdb
import httpx

log = logging.getLogger(__name__)
BASE = "https://data.gdeltproject.org/gdeltv2"

_actor = ["Code", "Name", "CountryCode", "KnownGroupCode", "EthnicCode", "Religion1Code",
          "Religion2Code", "Type1Code", "Type2Code", "Type3Code"]
_geo = ["Type", "Fullname", "CountryCode", "ADM1Code", "ADM2Code", "Lat", "Long", "FeatureID"]
EVENT_COLS = (["GlobalEventID", "Day", "MonthYear", "Year", "FractionDate"]
              + [f"Actor1{c}" for c in _actor] + [f"Actor2{c}" for c in _actor]
              + ["IsRootEvent", "EventCode", "EventBaseCode", "EventRootCode", "QuadClass",
                 "GoldsteinScale", "NumMentions", "NumSources", "NumArticles", "AvgTone"]
              + [f"Actor1Geo_{c}" for c in _geo] + [f"Actor2Geo_{c}" for c in _geo]
              + [f"ActionGeo_{c}" for c in _geo] + ["DATEADDED", "SOURCEURL"])
MENTION_COLS = ["GlobalEventID", "EventTimeDate", "MentionTimeDate", "MentionType",
                "MentionSourceName", "MentionIdentifier", "SentenceID", "Actor1CharOffset",
                "Actor2CharOffset", "ActionCharOffset", "InRawText", "Confidence",
                "MentionDocLen", "MentionDocTone", "MentionDocTranslationInfo", "Extras"]
assert len(EVENT_COLS) == 61 and len(MENTION_COLS) == 16


def slots(start: datetime, end: datetime):
    t = start.replace(minute=start.minute - start.minute % 15, second=0, microsecond=0)
    while t < end:
        yield t.strftime("%Y%m%d%H%M%S")
        t += timedelta(minutes=15)


def _fetch(client: httpx.Client, stamp: str, kind: str, raw: Path) -> str:
    dest = raw / kind / f"{stamp}.{kind}.CSV"
    if dest.exists():
        return "cached"
    r = client.get(f"{BASE}/{stamp}.{kind}.CSV.zip")
    if r.status_code == 404:
        return "missing"
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(z.read(z.namelist()[0]))
    return "ok"


def download(start: datetime, end: datetime, data_dir: Path, db_name: str | None = None,
             prune_before: datetime | None = None) -> Path:
    """Fetch the window's files and build data_dir/gdelt/<db_name or start_end>.duckdb. Returns its path.

    The rolling worker passes a fixed db_name (the file is replaced each cycle) and prune_before,
    so raw 15-minute files older than the window are deleted instead of piling up."""
    raw = data_dir / "gdelt" / "raw"
    jobs = [(s, k) for s in slots(start, end) for k in ("export", "mentions")]
    with httpx.Client(timeout=120, follow_redirects=True) as client, cf.ThreadPoolExecutor(8) as ex:
        results = list(ex.map(lambda j: (j, _fetch(client, j[0], j[1], raw)), jobs))
    counts = {}
    for _, status in results:
        counts[status] = counts.get(status, 0) + 1
    missing = [j for j, st in results if st == "missing"]
    log.info("gdelt files %s; missing %s", counts, [f"{s}.{k}" for s, k in missing][:10])

    if prune_before is not None:
        cutoff = prune_before.strftime("%Y%m%d%H%M%S")
        for f in raw.glob("*/*.CSV"):
            if f.name[:14] < cutoff:
                f.unlink()
    db = data_dir / "gdelt" / (db_name or f"{start:%Y%m%d%H%M}_{end:%Y%m%d%H%M}.duckdb")
    stamps = sorted({s for s, _ in jobs})
    con = duckdb.connect(str(db))
    for table, kind, cols in [("events", "export", EVENT_COLS), ("mentions", "mentions", MENTION_COLS)]:
        files = [str(raw / kind / f"{s}.{kind}.CSV") for s in stamps if (raw / kind / f"{s}.{kind}.CSV").exists()]
        colspec = "{" + ", ".join(f"'{c}': 'VARCHAR'" for c in cols) + "}"
        con.execute(f"""CREATE OR REPLACE TABLE {table}_raw AS SELECT * FROM read_csv(
            {files!r}, delim='\t', header=false, quote='', escape='',
            columns={colspec}, ignore_errors=true, strict_mode=false)""")
    con.execute("""CREATE OR REPLACE TABLE events AS SELECT
        CAST(GlobalEventID AS BIGINT) GlobalEventID, CAST("Day" AS INT) AS EventDay,
        EventRootCode, CAST(QuadClass AS INT) QuadClass,
        CAST(NumSources AS INT) NumSources, ActionGeo_CountryCode, ActionGeo_FeatureID,
        strptime(DATEADDED, '%Y%m%d%H%M%S') DateAdded, SOURCEURL
        FROM events_raw""")
    con.execute("""CREATE OR REPLACE TABLE mentions AS SELECT
        CAST(GlobalEventID AS BIGINT) GlobalEventID,
        strptime(MentionTimeDate, '%Y%m%d%H%M%S') MentionTime,
        MentionSourceName, MentionIdentifier, CAST(Confidence AS INT) Confidence
        FROM mentions_raw""")
    con.execute("DROP TABLE events_raw; DROP TABLE mentions_raw")
    n = con.execute("SELECT count(*) FROM mentions").fetchone()[0]
    con.close()
    log.info("gdelt window %s..%s: %d mentions in %s", start, end, n, db)
    return db
