"""Shared, deterministic labelling: turn article URLs into keywords.

Every approach MUST use `story_keywords` so that differences between approaches come
from grouping/scoring only, not from labelling.
"""
import re
from collections import Counter
from urllib.parse import urlparse

STOP = set("""a an the and or of to in on at for from by with as is are was were be been it its this that
these those after before over under into about amid says said say new news video watch live update updates
latest breaking report reports how why what who when where will would could can may not no yes vs than
more most up down out off his her their our your you we they he she them us has have had do does did
html htm php aspx shtml index article articles story stories amp www com page default en world local
national politics business sports sport opinion today week day year years one two three first last""".split())
_TOKEN = re.compile(r"[^\W\d_]{3,}", re.UNICODE)


def slug_tokens(url: str) -> list[str]:
    """Words from the URL path (not the domain), lowercased, stopwords/IDs removed."""
    try:
        path = urlparse(url).path
    except ValueError:
        return []
    out = []
    for seg in path.split("/"):
        if seg.count("-") + seg.count("_") < 2:  # skip section names / ids; keep slug-like segments
            continue
        out.extend(tok for tok in _TOKEN.findall(seg.lower()) if tok not in STOP)
    return out


def story_keywords(urls: list[str], k: int = 15) -> list[str]:
    """Top-k tokens by number of distinct URLs containing them."""
    c = Counter()
    for u in set(urls):
        c.update(set(slug_tokens(u)))
    # sort by (-count, token): Counter tie order depends on set iteration = per-process hash seed
    return [t for t, _ in sorted(c.items(), key=lambda x: (-x[1], x[0]))[:k]]
