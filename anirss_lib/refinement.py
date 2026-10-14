"""Refinement logic with no UI: token groups, query rebuilding, and one
stateless refine step.

The fzf loop in refine.py and the HTTP API (api.py / server.py) both build
on these; nothing here prints, prompts, or touches the terminal."""

from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from statistics import median

from anirss_lib import bestfit, erai
from anirss_lib import endpoints as endpoints_mod
from anirss_lib.config import BestfitConfig
from anirss_lib.endpoints import Endpoint
from anirss_lib.errors import ValidationError
from anirss_lib.titles import RES_RE, poster_of, title_tokens
from anirss_lib.types import Group, Item


@dataclass
class AutoResolution:
    query: str
    items: list[Item]
    token: str = ""            # the <n>p appended, "" when nothing was
    skipped_missing: int = 0   # titles lacking a <n>p (why it was skipped)


def auto_resolution(query: str, items: list[Item]) -> AutoResolution:
    """If query lacks a <n>p token and every item has one, append the highest
    and keep only the items at that resolution."""
    if not items or RES_RE.search(query):
        return AutoResolution(query, items)
    per_max = [
        max((int(match.group(1)) for match in RES_RE.finditer(item.title)),
            default=None)
        for item in items
    ]
    missing = sum(1 for res in per_max if res is None)
    if missing:
        return AutoResolution(query, items, skipped_missing=missing)
    highest = max(res for res in per_max if res is not None)
    token = f"{highest}p"
    new_items = [item for item, res in zip(items, per_max) if res == highest]
    return AutoResolution(f"{query} {token}", new_items, token=token)


def _members_of(selected: list[Item], token: str) -> frozenset[int]:
    return frozenset(
        i for i, item in enumerate(selected)
        if (token.startswith("[") and poster_of(item.title) == token)
        or (not token.startswith("[")
            and (token in title_tokens(item.title)
                 or erai.metadata_hit(item, token)))
    )


def _matches_all_tokens(item: Item, tokens: list[str]) -> bool:
    poster = poster_of(item.title)
    toks = title_tokens(item.title)
    return all(
        (poster == t) if t.startswith("[")
        else (t in toks or erai.metadata_hit(item, t))
        for t in tokens
    )


def _custom_hit(item: Item, term_lc: str) -> bool:
    """Custom-term match: title substring, plus erai's structured fields
    (the polished title drops the linktype, so 'Torrent' only exists there;
    items without erai metadata match on the title alone)."""
    return term_lc in item.title.lower() or erai.metadata_hit(item, term_lc)


def compute_groups(selected: list[Item]) -> list[Group]:
    """Find tokens that partition `selected` into refinable subsets, grouped by membership."""
    total = len(selected)
    counts: Counter[str] = Counter()
    for item in selected:
        seen: set[str] = set()
        poster = poster_of(item.title)
        if poster:
            seen.add(poster)
        for token in title_tokens(item.title):
            seen.add(token)
        for token in seen:
            counts[token] += 1

    refinable = [token for token, count in counts.items() if 1 < count < total]

    by_members: dict[frozenset[int], list[str]] = defaultdict(list)
    for token in refinable:
        by_members[_members_of(selected, token)].append(token)

    groups: list[Group] = []
    for members, tokens in by_members.items():
        tokens_sorted = sorted(tokens, key=lambda x: (not x.startswith("["),
                                                     -len(x), x))
        label = "+".join(tokens_sorted)
        has_poster = any(token.startswith("[") for token in tokens)
        groups.append(Group(label, tokens_sorted, len(members), has_poster))

    groups.sort(key=lambda g: (not g.has_poster, -g.member_count, g.label))
    return groups


def _best_fit_query_for(query: str, selected: list[Item],
                        cfg: BestfitConfig) -> str:
    """The query [★ Try Best Fit] would refetch with, or "" when running it
    would be a no-op (nothing to rank, empty rebuild, or the current query
    already matching the top release's profile)."""
    best = bestfit.best_item(selected, cfg)
    if best is None:
        return ""
    new_query = bestfit.best_fit_query(best)
    if not new_query or new_query.lower() == query.lower():
        return ""
    return new_query


def _field_text(field: str) -> str:
    """The matchable core of a query field: drop a leading `-` and any quotes."""
    core = field.removeprefix("-")
    if len(core) >= 2 and core[0] == '"' and core[-1] == '"':
        core = core[1:-1]
    return core.lower()


def _title_position(text: str, selected: list[Item]) -> float:
    """Median index at which `text` appears across the selected titles.

    inf when no title contains it. Using the median (rather than one sample)
    keeps the ordering stable when release groups format titles differently.
    """
    spots = [
        item.title.lower().index(text)
        for item in selected
        if text and text in item.title.lower()
    ]
    return median(spots) if spots else float("inf")


def _insert_positional(query: str, token: str, selected: list[Item]) -> str:
    """Slot `token` into `query` ahead of the first existing field that occurs
    *later* in the titles, so the query mirrors real release-name order (e.g.
    1080p before multisub) instead of being blindly appended. Posters are never
    crossed; exclusions (`-tag`) always stay at the tail.
    """
    fields = endpoints_mod.FIELD_RE.findall(query)
    token_pos = _title_position(token.lower(), selected)
    insert_at = len(fields)
    for i, field in enumerate(fields):
        if field.startswith("["):          # never slot in front of a poster
            continue
        if field.startswith("-"):          # exclusions stay at the end
            insert_at = i
            break
        if _title_position(_field_text(field), selected) > token_pos:
            insert_at = i
            break
    fields.insert(insert_at, token)
    return " ".join(fields)


def build_refined_query(query: str, tokens: list[str], selected: list[Item]
                        ) -> str:
    """Extend `query` with `tokens`, each placed where it belongs.

    A poster (`[...]`) leads the title, so it goes to the front unless the query
    already starts with one. Every other token is positioned by where it occurs
    in the titles (see `_insert_positional`). Returns the rebuilt query string;
    the caller refetches nyaa with it rather than filtering locally, so episodes
    beyond the first RSS page can surface.
    """
    new_query = query
    for token in tokens:
        if token.startswith("["):
            if not new_query.lstrip().startswith("["):
                new_query = f"{token} {new_query}"
            continue
        new_query = _insert_positional(new_query, token, selected)
    return new_query


def add_exclude_to_query(query: str, term: str) -> str:
    """Append nyaa-style -tag to query. Returns query unchanged if term is empty after stripping."""
    term = term.strip().lstrip("-").strip()
    if not term:
        return query
    flag = f'-"{term}"' if " " in term else f"-{term}"
    return f"{query} {flag}"


def add_term_to_query(query: str, term: str) -> str:
    """Append a positive search term to query, quoting if it contains spaces."""
    term = term.strip()
    if not term:
        return query
    flag = f'"{term}"' if " " in term else term
    return f"{query} {flag}"


# --- one stateless refine step -----------------------------------------

OP_TYPES = ("tokens", "term", "exclude", "best_fit")


def is_client_side(ep: Endpoint) -> bool:
    """Generic RSS endpoints (Erai-raws, AniRena, …) are word-AND over post
    text, so refinements filter the fetched items locally; nyaa refetches
    server-side so a narrower query can surface older episodes."""
    return ep.kind != "nyaa"


@dataclass
class RefineOutcome:
    """Result of apply(). When `applied` is False, `query`/`items` are the
    inputs unchanged and `reason` says why: noop | zero_results | no_match |
    empty_term."""
    applied: bool
    query: str
    items: list[Item]
    mode: str                  # "refetch" | "client"
    previous_count: int
    reason: str | None = None

    @property
    def delta(self) -> int:
        return len(self.items) - self.previous_count


def apply(ep: Endpoint, query: str, items: list[Item], op: str, *,
          tokens: list[str] | None = None, term: str = "",
          bestfit_cfg: BestfitConfig,
          fetch: Callable[[Endpoint, str], list[Item]] | None = None,
          enrich: Callable[[list[Item]], list[Item]] | None = None,
          ) -> RefineOutcome:
    """Apply one refine action the way the TUI's refine loop does.

    op: "tokens" (a compute_groups() group's tokens), "term" (custom
    substring), "exclude" (drop a term), "best_fit" (pin the top release's
    profile). nyaa endpoints refetch with the rebuilt query; rss endpoints
    filter `items` client-side. Raises FetchError when a refetch fails."""
    fetch = fetch or endpoints_mod.fetch_items
    prev = len(items)
    mode = "client" if is_client_side(ep) else "refetch"

    def unchanged(reason: str) -> RefineOutcome:
        return RefineOutcome(False, query, items, mode, prev, reason)

    def refetch(new_query: str) -> RefineOutcome:
        new_items = fetch(ep, new_query)
        if not new_items:
            return unchanged("zero_results")
        if enrich is not None:
            new_items = enrich(new_items)
        return RefineOutcome(True, new_query, new_items, mode, prev)

    if op == "tokens":
        tokens = [t for t in (tokens or []) if t]
        if not tokens:
            raise ValidationError("op 'tokens' needs a non-empty `tokens` list")
        new_query = build_refined_query(query, tokens, items)
        if mode == "refetch":
            return refetch(new_query)
        kept = [it for it in items if _matches_all_tokens(it, tokens)]
        if not kept or kept == items:
            return unchanged("noop")
        return RefineOutcome(True, new_query, kept, mode, prev)

    if op == "term":
        term = term.strip()
        if not term:
            return unchanged("empty_term")
        term_lc = term.lower()
        if not any(_custom_hit(it, term_lc) for it in items):
            return unchanged("no_match")
        new_query = add_term_to_query(query, term)
        if mode == "refetch":
            return refetch(new_query)
        kept = [it for it in items if _custom_hit(it, term_lc)]
        return RefineOutcome(True, new_query, kept, mode, prev)

    if op == "exclude":
        new_query = add_exclude_to_query(query, term)
        if new_query == query:
            return unchanged("empty_term")
        if mode == "refetch":
            return refetch(new_query)
        term_lc = term.strip().lstrip("-").strip().lower()
        kept = [it for it in items if term_lc not in it.title.lower()]
        if not kept:
            return unchanged("zero_results")
        return RefineOutcome(True, new_query, kept, mode, prev)

    if op == "best_fit":
        best_query = _best_fit_query_for(query, items, bestfit_cfg)
        if not best_query:
            return unchanged("noop")
        if mode == "refetch":
            return refetch(best_query)
        best = bestfit.best_item(items, bestfit_cfg)
        parts = bestfit.profile_parts(best)
        kept = [it for it in items if bestfit.matches_profile(it.title, parts)]
        if not kept or len(kept) == len(items):
            return unchanged("noop")
        return RefineOutcome(True, best_query, kept, mode, prev)

    raise ValidationError(f"unknown refine op {op!r} (valid: {', '.join(OP_TYPES)})")


def best_fit_info(query: str, items: list[Item], cfg: BestfitConfig) -> dict:
    """What [★ Try Best Fit] would do: {available, query, item, profile}."""
    best = bestfit.best_item(items, cfg)
    best_query = _best_fit_query_for(query, items, cfg)
    return {
        "available": bool(best_query),
        "query": best_query,
        "item": best,
        "profile": bestfit.profile_parts(best) if best is not None else [],
    }


def group_members(items: list[Item], group: Group) -> list[int]:
    """Indexes into `items` of the releases a group's tokens select."""
    return sorted(_members_of(items, group.tokens[0])) if group.tokens else []
