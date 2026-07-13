from anirss_lib import nyaa


NYAA_XML = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:nyaa="https://nyaa.si/xmlns/nyaa">
<channel>
  <item>
    <title>[Erai-raws] Show - 05 [1080p][Multiple Subtitle]</title>
    <link>https://nyaa.si/download/1837471.torrent</link>
    <nyaa:seeders>923</nyaa:seeders>
    <nyaa:leechers>12</nyaa:leechers>
    <nyaa:downloads>4051</nyaa:downloads>
    <nyaa:size>1.4 GiB</nyaa:size>
    <nyaa:category>Anime - English-translated</nyaa:category>
  </item>
</channel>
</rss>"""

ANIRENA_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
<channel>
  <title>AniRena</title>
  <item>
    <title>[Anime &gt; Subs] Sayonara Lara - 02 [1080p CR WEBRip][768DB037]</title>
    <link>https://www.anirena.com/torrents/019f57b3</link>
    <description><![CDATA[Size: 485.1 MB | Uploader: Erai-raws | Category: Anime &gt; Subs]]></description>
    <enclosure url="https://www.anirena.com/torrents/019f57b3.torrent" type="application/x-bittorrent" length="0"/>
  </item>
  <item>
    <title>Bare Title Without Prefix - 03</title>
    <link>https://www.anirena.com/torrents/019f57a5</link>
  </item>
</channel>
</rss>"""


ERAI_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:erai="https://www.erai-raws.info/rss-page/">
<channel>
  <title>Episodes &#8211; Erai-raws Torrent RSS</title>
  <item>
    <title>[Torrent] Gaikotsu Kishi-sama Tadaima Isekai e Odekake-chuu II - 02 [1080p CR WEB-DL AVC AAC][us][br][mx][Airing]</title>
    <link>https://t.erai-raws.info/Torrent/2026/Summer/Gaikotsu Kishi-sama/file.mkv.torrent</link>
    <erai:resolution>1080p</erai:resolution>
    <erai:infomkv>CR WEB-DL AVC AAC</erai:infomkv>
    <erai:linktype>Torrent</erai:linktype>
    <erai:size>1.36GB</erai:size>
    <erai:infohash>88b0c4737b638b6c5bc38c458e812e2dc635f0dc</erai:infohash>
    <erai:subtitles>[us][br][mx]</erai:subtitles>
    <erai:category>[Airing]</erai:category>
    <description><![CDATA[<a href="https://www.erai-raws.info/episodes/gaikotsu-kishi-sama-tadaima-isekai-e-odekake-chuu-ii-02/">[Erai-raws] Gaikotsu Kishi-sama Tadaima Isekai e Odekake-chuu II - 02 [1080p CR WEB-DL AVC AAC][MultiSub][B8B9B54A].mkv</a> | Subtitles: [us][br][mx] | Size: 1.36GB | InfoHash: 88b0c4737b638b6c5bc38c458e812e2dc635f0dc | Categories: [Airing] ]]></description>
  </item>
</channel>
</rss>"""


def test_parse_nyaa_feed_unchanged():
    items = nyaa.parse_rss(NYAA_XML)
    assert len(items) == 1
    it = items[0]
    assert it.title == "[Erai-raws] Show - 05 [1080p][Multiple Subtitle]"
    assert it.link == "https://nyaa.si/download/1837471.torrent"
    assert (it.seeders, it.leechers, it.downloads) == (923, 12, 4051)
    assert it.size == "1.4 GiB"
    assert it.category == "Anime - English-translated"


def test_parse_generic_feed_prefers_torrent_enclosure():
    it = nyaa.parse_rss(ANIRENA_XML)[0]
    assert it.link == "https://www.anirena.com/torrents/019f57b3.torrent"


def test_parse_generic_feed_description_fallbacks():
    it = nyaa.parse_rss(ANIRENA_XML)[0]
    assert it.size == "485.1 MB"
    assert it.category == "Anime > Subs"
    assert (it.seeders, it.leechers, it.downloads) == (0, 0, 0)


def test_parse_generic_feed_strips_category_title_prefix():
    it = nyaa.parse_rss(ANIRENA_XML)[0]
    assert it.title == "Sayonara Lara - 02 [1080p CR WEBRip][768DB037]"


def test_parse_generic_feed_item_without_extras():
    it = nyaa.parse_rss(ANIRENA_XML)[1]
    assert it.title == "Bare Title Without Prefix - 03"
    assert it.link == "https://www.anirena.com/torrents/019f57a5"
    assert it.size == "" and it.category == ""


def test_parse_erai_feed_cleans_title():
    # Linktype prefix and the subtitle-language run go; the category tag stays
    # (a real refine facet: [Airing] vs [Encoded] vs [Batch]).
    it = nyaa.parse_rss(ERAI_XML)[0]
    assert it.title == ("Gaikotsu Kishi-sama Tadaima Isekai e Odekake-chuu II"
                        " - 02 [1080p CR WEB-DL AVC AAC][Airing]")


def test_parse_erai_feed_reads_erai_extensions():
    it = nyaa.parse_rss(ERAI_XML)[0]
    assert it.size == "1.36GB"
    assert it.category == "Airing"
    assert it.link.endswith(".torrent")


def test_parse_erai_feed_records_post_page():
    it = nyaa.parse_rss(ERAI_XML)[0]
    assert it.page == ("https://www.erai-raws.info/episodes/"
                       "gaikotsu-kishi-sama-tadaima-isekai-e-odekake-chuu-ii-02/")


def test_parse_rss_bad_xml_raises_fetch_error():
    import pytest
    with pytest.raises(nyaa.FetchError):
        nyaa.parse_rss("<not-xml", endpoint_name="anirena")


def test_fetch_rss_url_error_raises_fetch_error(monkeypatch):
    import pytest
    import urllib.error
    import urllib.request

    def fake_urlopen(req, timeout=30):
        raise urllib.error.URLError("boom")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(nyaa.FetchError, match="anirena"):
        nyaa.fetch_rss("https://example.invalid/rss", "anirena")
