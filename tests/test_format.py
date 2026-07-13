from anirss_lib.ansi import ansi_strip
from anirss_lib.format import show_titles
from anirss_lib.types import Item


def _lines(capsys):
    return [ansi_strip(line) for line in capsys.readouterr().out.splitlines()]


def test_show_titles_renders_source_header_once(capsys):
    items = [Item("Show - 01 [1080p]", "l", source="nyaa"),
             Item("Show - 02 [1080p]", "l", source="nyaa")]
    show_titles(items, cap=10)
    out = _lines(capsys)
    headers = [line for line in out if "── nyaa " in line]
    assert len(headers) == 1
    first_item = next(line for line in out if "Show - 01" in line)
    assert out.index(headers[0]) < out.index(first_item)


def test_show_titles_header_on_source_transition(capsys):
    items = [Item("A - 01 [1080p]", "l"),
             Item("B - 01 [1080p]", "l", source="nyaa")]
    show_titles(items, cap=10)
    out = _lines(capsys)
    header = next(line for line in out if "── nyaa " in line)
    a_row = next(line for line in out if "A - 01" in line)
    b_row = next(line for line in out if "B - 01" in line)
    assert out.index(a_row) < out.index(header) < out.index(b_row)


def test_show_titles_no_header_without_source(capsys):
    show_titles([Item("Show - 01 [1080p]", "l")], cap=10)
    assert not any("nyaa" in line for line in _lines(capsys))


def test_show_titles_truncation_footer_counts_items_not_rows(capsys):
    # cap=4: header + 3 item rows fit, so 2 of 5 items overflow.
    items = [Item(f"Show - {i:02d} [1080p]", "l", source="nyaa")
             for i in range(1, 6)]
    show_titles(items, cap=4)
    out = _lines(capsys)
    assert any("and 2 more" in line for line in out)
