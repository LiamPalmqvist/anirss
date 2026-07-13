"""Tests for the hidden --_search-rss live-preview handler."""

from anirss_lib import main as main_mod
from anirss_lib.ansi import ansi_strip
from anirss_lib.endpoints import Endpoint
from anirss_lib.nyaa import FetchError
from anirss_lib.types import Item


ERAI = Endpoint(name="erai", kind="rss", url="https://e/?s={query}")
NYAA = Endpoint(name="nyaa", kind="nyaa", url="https://n/")


def _out(capsys):
    return ansi_strip(capsys.readouterr().out)


def test_preview_active_hit_no_header(monkeypatch, capsys):
    monkeypatch.setattr(main_mod.endpoints_mod, "fetch_items",
                        lambda ep, q: [Item("Show - 01 [1080p]", "l")])
    main_mod._print_search_rss_rows("show", ERAI, [ERAI, NYAA])
    out = _out(capsys)
    assert "Show - 01" in out
    assert "── nyaa" not in out


def test_preview_empty_active_falls_back_with_header(monkeypatch, capsys):
    def fake_fetch(ep, query):
        if ep.name == "nyaa":
            return [Item("Sparks of Tomorrow S01E01 1080p", "l")]
        return []

    monkeypatch.setattr(main_mod.endpoints_mod, "fetch_items", fake_fetch)
    main_mod._print_search_rss_rows("sparks", ERAI, [ERAI, NYAA])
    out = _out(capsys)
    assert "── nyaa " in out
    assert "Sparks of Tomorrow" in out
    header_pos = out.index("── nyaa ")
    assert header_pos < out.index("Sparks of Tomorrow")


def test_preview_unreachable_active_still_falls_back(monkeypatch, capsys):
    def fake_fetch(ep, query):
        if ep is ERAI:
            raise FetchError("can't reach erai: boom")
        return [Item("Sparks of Tomorrow S01E01 1080p", "l")]

    monkeypatch.setattr(main_mod.endpoints_mod, "fetch_items", fake_fetch)
    main_mod._print_search_rss_rows("sparks", ERAI, [ERAI, NYAA])
    out = _out(capsys)
    assert "can't reach erai" in out
    assert "── nyaa " in out and "Sparks of Tomorrow" in out


def test_preview_empty_everywhere_prints_note(monkeypatch, capsys):
    monkeypatch.setattr(main_mod.endpoints_mod, "fetch_items",
                        lambda ep, q: [])
    main_mod._print_search_rss_rows("nothing", ERAI, [ERAI, NYAA])
    assert "no results" in _out(capsys)


def test_preview_single_endpoint_stays_plain(monkeypatch, capsys):
    monkeypatch.setattr(main_mod.endpoints_mod, "fetch_items",
                        lambda ep, q: [])
    main_mod._print_search_rss_rows("nothing", ERAI, [ERAI])
    out = _out(capsys)
    assert "──" not in out
