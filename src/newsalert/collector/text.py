"""Text helpers shared by grouping, RSS matching and the Wikipedia check (ported from phase 1)."""
import re
from collections import Counter
from urllib.parse import urlparse

STOP = set("""a an the and or of to in on at for from by with as is are was were be been it its this that
these those after before over under into about amid says said say new news video watch live update updates
latest breaking report reports how why what who when where will would could can may not no yes vs than
more most up down out off his her their our your you we they he she them us has have had do does did
html htm php aspx shtml index article articles story stories amp www com page default en world local
national politics business sports sport opinion today week day year years one two three first last""".split())  # noqa: SIM905

# Dates and page-type boilerplate: ignored for clustering and matching.
CLUSTER_STOP = set("""jan feb mar apr jun jul aug sep sept oct nov dec january february march april june july
august september october november december monday tuesday wednesday thursday friday saturday sunday tonight
morning photos photo gallery podcast newsletter editor column""".split())  # noqa: SIM905

_TOKEN = re.compile(r"[^\W\d_]{3,}", re.UNICODE)


def norm_tok(t: str) -> str:
    """Crude plural folding: 'strikes' -> 'strike'."""
    if len(t) > 4 and t.endswith("s") and not t.endswith(("ss", "us", "is")):
        return t[:-1]
    return t


def slug_tokens(url: str) -> list[str]:
    """Words from the URL path (not the domain), lowercased, stopwords removed."""
    try:
        path = urlparse(url).path
    except ValueError:
        return []
    out = []
    for seg in path.split("/"):
        if seg.count("-") + seg.count("_") < 2:  # skip section names and ids; keep slug-like segments
            continue
        out.extend(tok for tok in _TOKEN.findall(seg.lower()) if tok not in STOP)
    return out


def text_terms(text: str) -> set[str]:
    """Normalized informative terms of free text (titles, Wikipedia sentences)."""
    return {norm_tok(t) for t in _TOKEN.findall(text.lower()) if t not in STOP and t not in CLUSTER_STOP}


def url_terms(url: str) -> set[str]:
    return {norm_tok(t) for t in slug_tokens(url) if t not in CLUSTER_STOP}


def story_keywords(urls: list[str], k: int = 15) -> list[str]:
    """Top-k tokens by number of distinct URLs containing them. Ties broken alphabetically."""
    c = Counter()
    for u in set(urls):
        c.update(set(slug_tokens(u)))
    return [t for t, _ in sorted(c.items(), key=lambda x: (-x[1], x[0]))[:k]]


def canonical_url(url: str) -> str:
    """Scheme/host/path without query, fragment or trailing slash, for cross-source URL matching."""
    try:
        p = urlparse(url.strip())
    except ValueError:
        return url
    host = p.netloc.lower().removeprefix("www.")
    return f"{host}{p.path.rstrip('/')}"
