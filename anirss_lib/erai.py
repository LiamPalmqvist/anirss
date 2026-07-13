"""Erai-raws specifics: resolving a show's anime-list feed for subscriptions.

The search endpoint (WordPress `s=` on the tokenized feed) is plain `rss`
kind; nothing here touches searching. What Erai adds beyond a generic feed is
a per-show feed at /anime-list/<slug>/feed/ that carries only that show's
current offerings. Subscribing to it (instead of the search feed) keeps the
qBittorrent feed small and immune to search-term drift. The show slug is
derived from the release post URL each feed item links to, then validated
with a single fetch: a wrong slug returns HTTP 200 with an empty feed, so an
empty probe means "fall back to the search feed", never a hard failure.
"""

import re
import urllib.parse

from anirss_lib import nyaa
from anirss_lib.endpoints import Endpoint
from anirss_lib.logging import log
from anirss_lib.types import Item


_HOST = "erai-raws.info"

# Release post URL inside a feed item, e.g.
#   https://www.erai-raws.info/episodes/<show-slug>-02/
#   https://www.erai-raws.info/encodes/<show-slug>-01-hevc/
#   https://www.erai-raws.info/batches/<show-slug>-01-11/
_POST_RE = re.compile(
    r"https://www\.erai-raws\.info/"
    r"(episodes|encodes|batches|specials|raws)/([a-z0-9-]+)/")

# Suffix stripped from a post slug to recover the show slug. Only the
# section's own suffix is removed so shows whose slug ends in a number
# (mob-psycho-100) survive: episodes/specials/raws end in one episode
# number, encodes add -hevc after it, batches end in a range.
_POST_SUFFIX = {
    "episodes": re.compile(r"-\d+(?:v\d+)?$"),
    "specials": re.compile(r"-\d+(?:v\d+)?$"),
    "raws":     re.compile(r"-\d+(?:v\d+)?$"),
    "encodes":  re.compile(r"-\d+(?:v\d+)?-hevc$"),
    "batches":  re.compile(r"-\d+-\d+$"),
}


def is_erai(ep: Endpoint) -> bool:
    return ep.kind == "rss" and _HOST in ep.url


def _show_slug(section: str, post_slug: str) -> str | None:
    """Show slug from a release post slug, None when nothing was stripped
    (an unrecognized shape is not trusted as a show slug)."""
    suffix = _POST_SUFFIX.get(section)
    if suffix is None:
        return None
    slug = suffix.sub("", post_slug)
    return slug if slug and slug != post_slug else None


def per_show_feed_url(ep: Endpoint, slug: str) -> str:
    """The anime-list feed for `slug`, carrying over the endpoint URL's
    res/type/subs/token params and dropping the s= search placeholder."""
    base, _, qs = ep.url.partition("?")
    params = [(k, v) for k, v in urllib.parse.parse_qsl(qs) if k != "s"]
    origin = base.split(_HOST)[0] + _HOST
    return f"{origin}/anime-list/{slug}/feed/?{urllib.parse.urlencode(params)}"


def resolve_show_feed(ep: Endpoint, items: list[Item], fetch=None) -> str | None:
    """Per-show feed URL for the show `items` belong to, or None to make the
    caller fall back to the search feed. Costs at most one request: the first
    item with a recognizable post URL decides. `fetch` is injectable for
    tests."""
    fetch = fetch or nyaa.fetch_rss
    for item in items:
        match = _POST_RE.search(item.page)
        if not match:
            continue
        slug = _show_slug(match.group(1), match.group(2))
        if not slug:
            continue
        url = per_show_feed_url(ep, slug)
        try:
            found = fetch(url, "erai per-show probe")
        except nyaa.FetchError as e:
            log("WARN", f"erai per-show probe failed: {e}")
            return None
        if found:
            log("INFO", f"erai per-show feed for {slug!r}: {len(found)} item(s)")
            return url
        log("WARN", f"erai slug {slug!r}: empty probe, using the search feed")
        return None
    return None
