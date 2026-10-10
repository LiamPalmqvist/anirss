import urllib.parse

from anirss_lib import endpoints, erai, nyaa
from anirss_lib.endpoints import Endpoint
from anirss_lib.types import Item


ERAI_EP = Endpoint(
    name="erai", kind="rss",
    url=("https://www.erai-raws.info/episodes/feed/"
         "?res=1080p&type=torrent&subs%5B0%5D=us&s={query}&token=TOK"))
NYAA_EP = Endpoint(name="nyaa", kind="nyaa", url="https://nyaa.si/")

GAIKOTSU_PAGE = ("https://www.erai-raws.info/episodes/"
                 "gaikotsu-kishi-sama-tadaima-isekai-e-odekake-chuu-ii-02/")


def _erai_items():
    return [Item("Gaikotsu Kishi-sama Tadaima Isekai e Odekake-chuu II - 02 "
                 "[1080p CR WEB-DL AVC AAC][Airing]", "l", page=GAIKOTSU_PAGE)]


def test_is_erai():
    assert erai.is_erai(ERAI_EP) is True
    assert erai.is_erai(NYAA_EP) is False


def test_split_noise_strips_quality_tokens():
    terms, quality = erai.split_noise(
        "Ranma 3rd Season 1080p WEB-DL AVC AAC")
    assert terms == "Ranma 3rd Season"
    assert quality == ["1080p", "WEB-DL", "AVC", "AAC"]


def test_split_noise_keeps_searchable_text():
    # Platform tags ("NF") are real post text; a year is not a resolution;
    # quoted phrases never match the whole-token pattern.
    terms, quality = erai.split_noise('Ranma NF 2024 "Multi Subs"')
    assert terms == 'Ranma NF 2024 "Multi Subs"'
    assert quality == []


def test_split_noise_strips_category_tokens():
    terms, quality = erai.split_noise("Ranma Airing")
    assert terms == "Ranma"
    assert quality == ["Airing"]


def test_matches_token_uses_metadata():
    item = Item("Ranma - 01 [Airing]", "l", resolution="1080p",
                infomkv="NF WEB-DL AVC AAC", linktype="Torrent")
    assert erai.matches_token(item, "torrent")   # linktype (stripped from titles)
    assert erai.matches_token(item, "web-dl")    # infomkv
    assert erai.matches_token(item, "1080p")     # resolution
    assert erai.matches_token(item, "airing")    # title text
    assert not erai.matches_token(item, "hevc")


def test_metadata_hit_ignores_items_without_erai_fields():
    assert not erai.metadata_hit(Item("Show 1080p WEB-DL", "l"), "1080p")


def _s_param(url: str) -> str:
    """The value of the s= search parameter (the only part a query can
    pollute; the endpoint template's own res=/type= params are fixed)."""
    for k, v in urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query):
        if k == "s":
            return v
    return ""


def test_feed_url_erai_strips_quality_tokens():
    url, excluded = endpoints.feed_url(ERAI_EP, "Ranma 1080p WEB-DL -hevc")
    assert _s_param(url) == "Ranma"
    assert excluded == ["hevc"]


def test_fetch_items_erai_searches_clean_and_filters_quality(monkeypatch):
    urls = []

    def fake_fetch_rss(url, endpoint_name="feed"):
        urls.append(url)
        return [
            Item("Ranma - 01 [1080p NF WEB-DL AVC AAC][Airing]", "dl",
                 resolution="1080p", infomkv="NF WEB-DL AVC AAC",
                 linktype="Torrent"),
            Item("Ranma - 01 (HEVC) [1080p NF WEBRip HEVC AAC][Encoded]",
                 "rip", resolution="1080p", infomkv="NF WEBRip HEVC AAC",
                 linktype="Torrent"),
        ]

    monkeypatch.setattr(nyaa, "fetch_rss", fake_fetch_rss)
    items = endpoints.fetch_items(ERAI_EP, "Ranma 1080p WEB-DL")
    # The search went out with the show name only — the quality tokens would
    # zero it out — and the facet was applied to the results client-side.
    assert _s_param(urls[0]) == "Ranma"
    assert [it.link for it in items] == ["dl"]


def test_subscription_feed_erai_fallback_puts_quality_in_must(monkeypatch):
    monkeypatch.setattr(erai, "resolve_show_feed",
                        lambda ep, items, fetch=None: None)
    url, must, excluded = endpoints.subscription_feed(
        ERAI_EP, "Ranma 1080p WEB-DL -hevc", [])
    assert _s_param(url) == "Ranma"
    # qB enforces the quality facets against the raw feed titles instead.
    assert must == "1080p WEB-DL"
    assert excluded == ["hevc"]


def test_show_slug_per_section():
    assert erai._show_slug("episodes", "gaikotsu-kishi-sama-02") == \
        "gaikotsu-kishi-sama"
    # A show whose own slug ends in a number must survive the strip.
    assert erai._show_slug("episodes", "mob-psycho-100-05") == "mob-psycho-100"
    assert erai._show_slug("encodes", "gaikotsu-kishi-sama-01-hevc") == \
        "gaikotsu-kishi-sama"
    assert erai._show_slug("batches", "86-eighty-six-01-11") == "86-eighty-six"


def test_per_show_feed_url_carries_params_drops_search():
    url = erai.per_show_feed_url(ERAI_EP, "86-eighty-six")
    assert url.startswith(
        "https://www.erai-raws.info/anime-list/86-eighty-six/feed/?")
    assert "res=1080p" in url and "type=torrent" in url
    assert "subs%5B0%5D=us" in url and "token=TOK" in url
    assert "{query}" not in url and "&s=" not in url and "?s=" not in url


def test_resolve_show_feed_success():
    calls = []

    def fetch(url, name="feed"):
        calls.append(url)
        return [Item("x", "l")]

    url = erai.resolve_show_feed(ERAI_EP, _erai_items(), fetch=fetch)
    assert url is not None
    assert ("/anime-list/gaikotsu-kishi-sama-tadaima-isekai-e-odekake-chuu-ii"
            "/feed/") in url
    assert calls == [url]


def test_resolve_show_feed_empty_probe_falls_back():
    assert erai.resolve_show_feed(
        ERAI_EP, _erai_items(), fetch=lambda url, name="feed": []) is None


def test_resolve_show_feed_fetch_error_falls_back():
    def fetch(url, name="feed"):
        raise nyaa.FetchError("boom")

    assert erai.resolve_show_feed(ERAI_EP, _erai_items(), fetch=fetch) is None


def test_resolve_show_feed_without_page_makes_no_request():
    def fetch(url, name="feed"):
        raise AssertionError("must not fetch")

    assert erai.resolve_show_feed(ERAI_EP, [Item("t", "l")], fetch=fetch) is None


def test_subscription_feed_erai_uses_per_show_and_must_contain(monkeypatch):
    monkeypatch.setattr(
        erai, "resolve_show_feed",
        lambda ep, items, fetch=None: "https://www.erai-raws.info/anime-list/x/feed/?res=1080p")
    url, must, excluded = endpoints.subscription_feed(
        ERAI_EP, "Gaikotsu 1080p CR WEB-DL -hevc", _erai_items())
    assert url == "https://www.erai-raws.info/anime-list/x/feed/?res=1080p"
    assert must == "Gaikotsu 1080p CR WEB-DL"
    assert excluded == ["hevc"]


def test_subscription_feed_must_contain_drops_poster_and_quotes(monkeypatch):
    monkeypatch.setattr(erai, "resolve_show_feed",
                        lambda ep, items, fetch=None: "https://e/f")
    _, must, _ = endpoints.subscription_feed(
        ERAI_EP, '[Erai-raws] Show "Multi Subs" 1080p', [])
    assert must == "Show Multi Subs 1080p"


def test_subscription_feed_erai_falls_back_to_search_feed(monkeypatch):
    monkeypatch.setattr(erai, "resolve_show_feed",
                        lambda ep, items, fetch=None: None)
    url, must, excluded = endpoints.subscription_feed(
        ERAI_EP, "gaikotsu -hevc", [])
    assert "s=gaikotsu" in url
    assert must == ""
    assert excluded == ["hevc"]


def test_subscription_feed_non_erai_unchanged():
    url, must, excluded = endpoints.subscription_feed(NYAA_EP, "show -bad", [])
    assert url == endpoints.feed_url(NYAA_EP, "show -bad")[0]
    assert must == ""
    assert excluded == []
