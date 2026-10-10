"""Client-side refinement for generic-rss endpoints (Erai-raws, AniRena, …).

Their query engines are plain word-AND over post text, so nyaa-shaped
refetches 0-out; token/custom/exclude/best-fit must filter the fetched
results locally instead of hitting the endpoint again.
"""

from anirss_lib import endpoints as endpoints_mod
from anirss_lib import refine as refine_mod
from anirss_lib.config import DEFAULT_CONFIG
from anirss_lib.endpoints import Endpoint, EndpointState
from anirss_lib.types import Item


ERAI = Endpoint(name="erai", kind="rss",
                url="https://erai.example/feed/?s={query}")
NYAA = Endpoint(name="nyaa", kind="nyaa", url="https://nyaa.example/")

ITEMS = [
    Item("Show - 01 [1080p][Hevc]", "l1"),
    Item("Show - 02 [1080p][Hevc]", "l2"),
    Item("Show - 03 [1080p][Avc]", "l3"),
]

BESTFIT_CFG = DEFAULT_CONFIG["bestfit"]


def _run(monkeypatch, state, picks, items=ITEMS):
    """Drive refine() through `picks` (pick_group side_effect), return
    (final_query, final_items, fetches) — fetches lists every refetch."""
    from anirss_lib.types import PICK_DONE

    fetches = []

    def fake_fetch(ep, query):
        fetches.append((ep.name, query))
        return list(items)

    monkeypatch.setattr(endpoints_mod, "fetch_items", fake_fetch)
    pick_seq = iter([*picks, PICK_DONE])
    monkeypatch.setattr(refine_mod, "pick_group",
                        lambda *a, **k: next(pick_seq))
    # The exclude flow prompts for the term after picking [✗ Exclude Term…].
    monkeypatch.setattr(refine_mod, "prompt", lambda *a, **k: "Hevc")
    # All items share 1080p so auto-resolution is a no-op on the query.
    query, selected, status = refine_mod.refine("Show 1080p", items, state,
                                                BESTFIT_CFG)
    return query, selected, status, fetches


def test_rss_token_pick_filters_client_side(monkeypatch):
    state = EndpointState([ERAI, NYAA])
    from anirss_lib.types import Pick
    query, selected, status, fetches = _run(
        monkeypatch, state, [Pick("tokens", ["Hevc"])])
    assert status == "done"
    assert [it.title for it in selected] == [ITEMS[0].title, ITEMS[1].title]
    assert fetches == [], "rss refine must not refetch"


def test_rss_custom_term_filters_client_side(monkeypatch):
    state = EndpointState([ERAI, NYAA])
    from anirss_lib.types import Pick
    query, selected, status, fetches = _run(
        monkeypatch, state, [Pick("custom", ["Hevc"])])
    assert status == "done"
    assert len(selected) == 2
    assert "Hevc" in query
    assert fetches == []


def test_rss_exclude_filters_client_side(monkeypatch):
    state = EndpointState([ERAI, NYAA])
    from anirss_lib.types import Pick
    query, selected, status, fetches = _run(
        monkeypatch, state, [Pick("exclude", [])])
    assert status == "done"
    assert [it.title for it in selected] == [ITEMS[2].title]
    assert fetches == []


def test_rss_best_fit_filters_to_best_profile(monkeypatch):
    state = EndpointState([ERAI, NYAA])
    from anirss_lib.types import Pick
    query, selected, status, fetches = _run(
        monkeypatch, state, [Pick("best_fit", [])])
    assert status == "done"
    assert fetches == []
    # Best fit pins the profile of the top-ranked item; every kept item
    # matches it. (No fake poster here, so no group pin.)
    assert 0 < len(selected) <= len(ITEMS)


def test_nyaa_token_pick_still_refetches(monkeypatch):
    state = EndpointState([NYAA])
    from anirss_lib.types import Pick
    query, selected, status, fetches = _run(
        monkeypatch, state, [Pick("tokens", ["Hevc"])])
    assert status == "done"
    assert fetches == [("nyaa", "Show 1080p Hevc")], \
        "nyaa keeps its server-side refetch"


def test_rss_token_pick_that_changes_nothing_is_skipped(monkeypatch):
    state = EndpointState([ERAI, NYAA])
    from anirss_lib.types import Pick
    # A token no title carries: kept == selected -> skipped, no refetch.
    query, selected, status, fetches = _run(
        monkeypatch, state, [Pick("tokens", ["Nonexistent"])])
    assert status == "done"
    assert len(selected) == len(ITEMS)
    assert fetches == []


def test_rss_token_pick_matches_erai_metadata(monkeypatch):
    # 'Torrent' never appears in a polished erai title (the linktype prefix
    # is stripped at parse time) — it only exists in erai:linktype metadata.
    meta_items = [
        Item("Show - 01 [1080p]", "l1", linktype="Torrent"),
        Item("Show - 02 [1080p]", "l2", linktype="Torrent"),
        Item("Show - 03 [1080p]", "l3", linktype="Magnet"),
    ]
    state = EndpointState([ERAI, NYAA])
    from anirss_lib.types import Pick
    _query, selected, status, fetches = _run(
        monkeypatch, state, [Pick("tokens", ["Torrent"])], items=meta_items)
    assert status == "done"
    assert [it.link for it in selected] == ["l1", "l2"]
    assert fetches == []
