"""Shared dataclass-like types used across modules."""

from typing import NamedTuple


class Item(NamedTuple):
    title: str
    link: str
    # Tracker stats. None means the feed didn't carry them (unknown) —
    # never displayed as 0; may be filled in later by stats.enrich().
    seeders: int | None = None
    leechers: int | None = None
    downloads: int | None = None
    size: str = ""
    category: str = ""
    page: str = ""      # release post URL, when the feed exposes one (erai)
    source: str = ""    # endpoint these results fell back to ("" = the active one)


class Group(NamedTuple):
    label: str
    tokens: list[str]
    member_count: int
    has_poster: bool


class Pick(NamedTuple):
    """Result of pick_group: a kind and (for tokens/custom) the relevant terms."""
    kind: str  # tokens | done | exclude | show_all | best_fit | custom | back | endpoint
    tokens: list[str]


PICK_DONE = Pick("done", [])
PICK_EXCLUDE = Pick("exclude", [])
PICK_SHOW_ALL = Pick("show_all", [])
PICK_BEST_FIT = Pick("best_fit", [])
PICK_BACK = Pick("back", [])
PICK_ENDPOINT = Pick("endpoint", [])
