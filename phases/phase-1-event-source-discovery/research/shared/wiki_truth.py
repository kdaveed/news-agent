"""Fetch Wikipedia Portal:Current_events day pages and parse them into entries.

Output: data/wiki_truth.json  [{date, category, topic, path, text, links}]
  topic = top-level bullet (story thread, e.g. "2026 Iran war"); text = leaf entry plain text.
"""
import datetime as dt
import json
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "wiki_truth.json"
UA = {"User-Agent": "news-agent-research/0.1 (evaluation script)"}


def plain(s: str) -> str:
    s = re.sub(r"<ref[^>]*>.*?</ref>|<ref[^>]*/>", "", s)
    s = re.sub(r"\{\{[^{}]*\}\}", "", s)
    s = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"\[https?://\S+\s*([^\]]*)\]", r"\1", s)  # [url (Source)] -> (Source)
    return re.sub(r"'{2,}", "", s).strip()


def parse_day(date: dt.date, wikitext: str) -> list[dict]:
    entries, category, stack = [], None, []
    lines = wikitext.splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"^'''(.+?)'''\s*$", line.strip())
        if m:
            category, stack = plain(m.group(1)), []
            continue
        m = re.match(r"^(\*+)\s*(.*)$", line)
        if not m:
            continue
        depth, body = len(m.group(1)), m.group(2)
        stack = stack[: depth - 1] + [plain(body)]
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        is_leaf = not re.match(r"^\*{%d,}" % (depth + 1), nxt)
        if is_leaf and len(plain(body)) > 30:  # leaf sentence, not a bare topic link
            entries.append({
                "date": date.isoformat(), "category": category, "topic": stack[0],
                "path": stack[:-1], "text": plain(body),
                "links": re.findall(r"\[\[([^|\]]+)", body),
            })
    return entries


def fetch(date: dt.date) -> str:
    page = f"Portal:Current_events/{date.year}_{date.strftime('%B')}_{date.day}"
    r = requests.get("https://en.wikipedia.org/w/api.php", headers=UA, timeout=60, params={
        "action": "parse", "page": page, "prop": "wikitext", "format": "json"}).json()
    return r["parse"]["wikitext"]["*"]


if __name__ == "__main__":
    start = dt.date.fromisoformat(sys.argv[1] if len(sys.argv) > 1 else "2026-11-01")
    end = dt.date.fromisoformat(sys.argv[2] if len(sys.argv) > 2 else "2026-11-05")  # inclusive, ±1 day slack
    out, d = [], start
    while d <= end:
        try:
            day = parse_day(d, fetch(d))
        except KeyError:
            day = []
        print(d, len(day), "entries")
        out += day
        d += dt.timedelta(days=1)
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False))
