"""Download GDELT 2.0 events + mentions for a fixed UTC window and load them into DuckDB.

Usage: uv run python shared/fetch_gdelt.py [START] [END]   (YYYYMMDDHHMMSS, END exclusive)
Output: data/gdelt.duckdb with tables `events` and `mentions`.
"""
import concurrent.futures as cf
import hashlib
import io
import re
import sys
import zipfile
from pathlib import Path

import duckdb
import requests

START = sys.argv[1] if len(sys.argv) > 1 else "20261102000000"
END = sys.argv[2] if len(sys.argv) > 2 else "20261105000000"
ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
DB = ROOT / "data" / "gdelt.duckdb"
MASTER = "https://data.gdeltproject.org/gdeltv2/masterfilelist.txt"

# GDELT 2.0 Event codebook: 61 columns.
_actor = ["Code", "Name", "CountryCode", "KnownGroupCode", "EthnicCode", "Religion1Code",
          "Religion2Code", "Type1Code", "Type2Code", "Type3Code"]
_geo = ["Type", "Fullname", "CountryCode", "ADM1Code", "ADM2Code", "Lat", "Long", "FeatureID"]
EVENT_COLS = (["GlobalEventID", "Day", "MonthYear", "Year", "FractionDate"]
              + [f"Actor1{c}" for c in _actor] + [f"Actor2{c}" for c in _actor]
              + ["IsRootEvent", "EventCode", "EventBaseCode", "EventRootCode", "QuadClass",
                 "GoldsteinScale", "NumMentions", "NumSources", "NumArticles", "AvgTone"]
              + [f"Actor1Geo_{c}" for c in _geo] + [f"Actor2Geo_{c}" for c in _geo]
              + [f"ActionGeo_{c}" for c in _geo] + ["DATEADDED", "SOURCEURL"])
# GDELT 2.0 Mentions codebook: 16 columns.
MENTION_COLS = ["GlobalEventID", "EventTimeDate", "MentionTimeDate", "MentionType",
                "MentionSourceName", "MentionIdentifier", "SentenceID", "Actor1CharOffset",
                "Actor2CharOffset", "ActionCharOffset", "InRawText", "Confidence",
                "MentionDocLen", "MentionDocTone", "MentionDocTranslationInfo", "Extras"]
assert len(EVENT_COLS) == 61 and len(MENTION_COLS) == 16


def file_list():
    out = []
    for line in requests.get(MASTER, timeout=120).text.splitlines():
        parts = line.split()
        if len(parts) != 3:
            continue
        m = re.search(r"/(\d{14})\.(export|mentions)\.CSV\.zip$", parts[2])
        if m and START <= m.group(1) < END:
            out.append((int(parts[0]), parts[1], parts[2], m.group(2)))
    return out


def fetch(item):
    size, md5, url, kind = item
    dest = RAW / kind / (url.rsplit("/", 1)[1].removesuffix(".zip"))
    if dest.exists():
        return "cached"
    data = requests.get(url.replace("http://", "https://"), timeout=120).content
    if hashlib.md5(data).hexdigest() != md5:
        raise ValueError(f"md5 mismatch: {url}")
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(z.read(z.namelist()[0]))
    return "ok"


def load():
    con = duckdb.connect(str(DB))
    for table, kind, cols in [("events", "export", EVENT_COLS), ("mentions", "mentions", MENTION_COLS)]:
        colspec = "{" + ", ".join(f"'{c}': 'VARCHAR'" for c in cols) + "}"
        con.execute(f"""CREATE OR REPLACE TABLE {table}_raw AS SELECT * FROM read_csv(
            '{RAW / kind}/*.CSV', delim='\t', header=false, quote='', escape='',
            columns={colspec}, ignore_errors=true, strict_mode=false)""")
    con.execute("""CREATE OR REPLACE TABLE events AS SELECT
        CAST(GlobalEventID AS BIGINT) GlobalEventID, CAST("Day" AS INT) AS EventDay,
        Actor1Code, Actor1Name, Actor1CountryCode, Actor1Type1Code,
        Actor2Code, Actor2Name, Actor2CountryCode, Actor2Type1Code,
        CAST(IsRootEvent AS INT) IsRootEvent, EventCode, EventBaseCode, EventRootCode,
        CAST(QuadClass AS INT) QuadClass, TRY_CAST(GoldsteinScale AS DOUBLE) GoldsteinScale,
        CAST(NumMentions AS INT) NumMentions, CAST(NumSources AS INT) NumSources,
        CAST(NumArticles AS INT) NumArticles, TRY_CAST(AvgTone AS DOUBLE) AvgTone,
        ActionGeo_Type, ActionGeo_Fullname, ActionGeo_CountryCode, ActionGeo_ADM1Code,
        TRY_CAST(ActionGeo_Lat AS DOUBLE) ActionGeo_Lat, TRY_CAST(ActionGeo_Long AS DOUBLE) ActionGeo_Long,
        strptime(DATEADDED, '%Y%m%d%H%M%S') DateAdded, SOURCEURL
        FROM events_raw""")
    con.execute("""CREATE OR REPLACE TABLE mentions AS SELECT
        CAST(GlobalEventID AS BIGINT) GlobalEventID,
        strptime(EventTimeDate, '%Y%m%d%H%M%S') EventTime,
        strptime(MentionTimeDate, '%Y%m%d%H%M%S') MentionTime,
        CAST(MentionType AS INT) MentionType, MentionSourceName, MentionIdentifier,
        CAST(Confidence AS INT) Confidence, CAST(MentionDocLen AS INT) MentionDocLen,
        TRY_CAST(MentionDocTone AS DOUBLE) MentionDocTone,
        MentionDocTranslationInfo IS NOT NULL AND MentionDocTranslationInfo <> '' AS Translated
        FROM mentions_raw""")
    con.execute("DROP TABLE events_raw; DROP TABLE mentions_raw")
    for t in ["events", "mentions"]:
        print(t, con.execute(f"SELECT count(*) FROM {t}").fetchone()[0], "rows")
    con.close()


if __name__ == "__main__":
    items = file_list()
    print(f"{len(items)} files for {START}..{END}")
    with cf.ThreadPoolExecutor(8) as ex:
        results = list(ex.map(fetch, items))
    print({r: results.count(r) for r in set(results)})
    load()
