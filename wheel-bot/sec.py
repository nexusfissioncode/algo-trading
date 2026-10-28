"""How many shares each company has, from the SEC's free XBRL "frames" - one file per quarter that
holds a number for every company that filed it. Market cap is then shares times price.

Two numbers, in order of preference:
  dei EntityCommonStockSharesOutstanding     the count on a filing's cover page
  us-gaap WeightedAverageNumberOfSharesOutstandingBasic
                                             the quarter's average; covers companies with two share
                                             classes (Alphabet, Meta), whose cover page counts each
                                             class apart
Foreign companies report their own shares, not the ADRs that trade here (one Toyota ADR is ten
shares), so `us_only` keeps companies based in the US.

The SEC asks every program to send a User-Agent naming who runs it, and limits requests to ten a
second. Files are cached for a day in .cache/."""
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

FRAMES = "https://data.sec.gov/api/xbrl/frames/{taxonomy}/{tag}/shares/{period}.json"
TICKERS = "https://www.sec.gov/include/ticker.txt"
COVER = ("dei", "EntityCommonStockSharesOutstanding", "I")
AVERAGE = ("us-gaap", "WeightedAverageNumberOfSharesOutstandingBasic", "")
CACHE = Path(__file__).parent / ".cache"


def recent_quarters(today, n=4):
    """The quarter today is in and the n-1 before it, newest first: ['CY2026Q4', 'CY2026Q3', ...]."""
    y, q = today.year, (today.month - 1) // 3 + 1
    out = []
    for _ in range(n):
        out.append(f"CY{y}Q{q}")
        y, q = (y, q - 1) if q > 1 else (y - 1, 4)
    return out


def parse_tickers(text):
    """ticker.txt ('aapl\\t320193' per line) -> {cik: ['AAPL', ...]}, in the file's order."""
    out = {}
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) == 2 and parts[1].strip().isdigit():
            out.setdefault(int(parts[1]), []).append(parts[0].strip().upper().replace("-", "."))
    return out


def join(cover_frames, average_frames, tickers, us_only=True):
    """Frames (newest first) and the ticker map -> {ticker: {"shares", "as_of", "source"}}.
    The newest cover-page count wins; a company with none falls back to the quarter's average."""
    best = {}
    for source, frames in (("cover", cover_frames), ("average", average_frames)):
        for frame in frames:                       # newest quarter first, so the first seen wins
            for row in frame.get("data", []):
                if row["cik"] in best:
                    continue
                if us_only and not str(row.get("loc", "")).startswith("US-"):
                    continue
                best[row["cik"]] = {"shares": row["val"], "as_of": row["end"], "source": source}
    out = {}
    for cik, found in best.items():
        for t in tickers.get(cik, []):
            out[t] = found
    return out


def _get(url, user_agent):
    req = urllib.request.Request(url, headers={"User-Agent": user_agent, "Accept-Encoding": "identity"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None       # a quarter nobody has filed for yet
        raise


def _cached(name, url, user_agent, today):
    """Today's copy of a file, fetched once a day. If the SEC refuses (it throttles busy callers for
    a while), the newest copy from the last week is used instead, and the run says so."""
    CACHE.mkdir(exist_ok=True)
    path = CACHE / f"{today.isoformat()}-{name}"
    if path.exists():
        return path.read_text()
    try:
        text = _get(url, user_agent)
        time.sleep(0.2)       # well under the SEC's ten requests a second
        if text is not None and text.lstrip().startswith("<"):
            raise urllib.error.HTTPError(url, 403, "refused", {}, None)
    except urllib.error.HTTPError as e:
        older = newest_copy(name, today)
        if older is None:
            raise RuntimeError(f"the SEC refused the request ({e.code}) - set sec_user_agent in wheel.toml to "
                               "your name and email, and try again in ten minutes") from None
        print(f"(the SEC refused just now; using its {older.name[:10]} copy of {name})", file=sys.stderr)
        return older.read_text()
    text = "{}" if text is None else text
    path.write_text(text)
    return text


def newest_copy(name, today, days=7):
    """The newest saved copy of a file from the last `days` days, or None."""
    for back in range(1, days + 1):
        older = CACHE / f"{(today - timedelta(days=back)).isoformat()}-{name}"
        if older.exists():
            return older
    return None


def share_counts(user_agent, today=None, us_only=True):
    today = today or date.today()
    if not user_agent or "your-email@example.com" in user_agent:
        raise RuntimeError("set sec_user_agent in wheel.toml (or SEC_USER_AGENT) - the SEC asks "
                           "every caller to say who it is")
    frames = {}
    for taxonomy, tag, instant in (COVER, AVERAGE):
        frames[tag] = [json.loads(_cached(f"{tag}-{p}{instant}.json",
                                          FRAMES.format(taxonomy=taxonomy, tag=tag, period=p + instant),
                                          user_agent, today))
                       for p in recent_quarters(today)]
    tickers = parse_tickers(_cached("ticker.txt", TICKERS, user_agent, today))
    return join(frames[COVER[1]], frames[AVERAGE[1]], tickers, us_only)
