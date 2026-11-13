"""RSS 2.0 parser (R11.1, R9.4, R10.1) with hand-written samples. No network."""
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from newsreader.model import RawEntry
from newsreader.parse import MAX_RESPONSE_BYTES, FeedError, parse_rss
from newsreader.select import clean_headline

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def load(name):
    return (FIXTURES / name).read_bytes()


def test_sample_feed_gives_raw_entries():
    entries = parse_rss(load("rss_sample.xml"))
    assert [e.link for e in entries] == [
        "https://example.invalid/nyheter/a",
        "https://example.invalid/nyheter/b",
        "https://example.invalid/nyheter/c",
    ]
    first = entries[0]
    assert isinstance(first, RawEntry)
    assert first.title == "Exempelrubrik om riksdagen"
    assert first.time_text == "Fri, 13 Nov 2026 14:05:00 +0100"
    assert first.description == "Kort exempeltext om en debatt."


def test_entry_has_only_the_four_fields():
    assert set(RawEntry.__dataclass_fields__) == {"title", "link", "time_text", "description"}


def test_cdata_is_read_as_text_and_cleaning_is_left_to_the_caller():
    entry = parse_rss(load("rss_sample.xml"))[1]
    assert entry.title == "Fet <b>rubrik</b> &amp; åäö"  # CDATA keeps the text literally
    assert clean_headline(entry.title) == "Fet rubrik & åäö"
    assert entry.description == "<p>Text med <i>markup</i></p>"
    assert entry.link == "https://example.invalid/nyheter/b"
    assert entry.time_text == "Fri, 03 Jul 2026 10:00:00 +0200"


def test_missing_fields_are_empty_strings():
    entry = parse_rss(load("rss_sample.xml"))[2]
    assert entry.title == "Rubrik utan tid och beskrivning"
    assert entry.time_text == ""
    assert entry.description == ""


def test_guid_image_and_category_are_not_read():
    entry = parse_rss(load("rss_sample.xml"))[0]
    flat = " ".join([entry.title, entry.link, entry.time_text, entry.description])
    assert "thumbnail" not in flat and "bild.jpg" not in flat and "Inrikes" not in flat


def test_iso_8859_1_is_decoded_by_the_declaration():
    raw = load("rss_iso8859.xml")
    assert b"\xc5sa" in raw  # the fixture really is Latin-1, not UTF-8
    entry = parse_rss(raw)[0]
    assert entry.title == "Åsa och Örjan åt på café i Västerås ÄÖ"
    assert entry.description == "Beskrivning med åäö och é"


def test_utf_8_without_declaration_is_utf_8():
    data = "<rss><channel><item><title>Åäö é</title><link>https://example.invalid/u</link></item></channel></rss>".encode("utf-8")
    assert parse_rss(data)[0].title == "Åäö é"


def test_utf_8_with_declaration_and_bom():
    data = b"\xef\xbb\xbf" + "<?xml version='1.0' encoding='UTF-8'?><rss><channel><item><title>Åäö</title></item></channel></rss>".encode("utf-8")
    assert parse_rss(data)[0].title == "Åäö"


def test_unknown_encoding_is_a_failed_fetch():
    with pytest.raises(FeedError):
        parse_rss(load("unknown_encoding.xml"))


def test_empty_and_malformed_items():
    entries = parse_rss(load("rss_edge_cases.xml"))
    # Items with none of the four fields (empty, self-closing, white space only) are skipped.
    assert [(e.title.strip(), e.link) for e in entries] == [
        ("", "https://example.invalid/e/empty-title"),
        ("Title without link", ""),
        ("", "https://example.invalid/e/no-title"),
        ("Unusable link kept for later steps", "javascript:alert(1)"),
        ("Duplicate URL one", "https://example.invalid/e/dup?x=1"),
        ("Duplicate URL two", "https://example.invalid/e/dup?x=2"),
        ("First title", "https://example.invalid/e/two-titles"),
    ]


def test_channel_without_items_gives_no_entries():
    assert parse_rss(b"<rss version='2.0'><channel><title>x</title></channel></rss>") == []


def test_html_page_is_a_failed_fetch():
    with pytest.raises(FeedError):
        parse_rss(load("not_a_feed.html"))


def test_atom_document_is_a_failed_fetch():
    with pytest.raises(FeedError, match="not <rss>"):
        parse_rss(load("atom_in_build.xml"))


def test_namespaced_rss_root_is_a_failed_fetch():
    with pytest.raises(FeedError):
        parse_rss(b"<rss xmlns='http://example.invalid/ns'><channel/></rss>")


def test_broken_xml_is_a_failed_fetch():
    with pytest.raises(FeedError, match="well-formed"):
        parse_rss(load("broken.xml"))


@pytest.mark.parametrize("data", [b"", b"   \n  "])
def test_empty_response_is_a_failed_fetch(data):
    with pytest.raises(FeedError, match="empty"):
        parse_rss(data)


def test_text_instead_of_bytes_is_a_programming_error():
    with pytest.raises(TypeError):
        parse_rss("<rss/>")


def test_external_entity_is_not_resolved():
    with pytest.raises(FeedError, match="entity"):
        parse_rss(load("xxe_external_entity.xml"))


def test_entity_expansion_is_refused():
    with pytest.raises(FeedError, match="entity"):
        parse_rss(load("entity_expansion.xml"))


def test_expat_itself_does_not_read_external_files():
    # Belt and braces for R9.4: even without the declaration check, the file
    # content must not reach an entry.
    try:
        text = "".join(ET.fromstring(load("xxe_external_entity.xml")).itertext())
    except ET.ParseError:
        text = ""
    assert "root:" not in text


def _feed_of_size(size):
    head = b"<rss><channel><item><title>"
    tail = b"</title></item></channel></rss>"
    return head + b"a" * (size - len(head) - len(tail)) + tail


def test_response_at_the_limit_is_accepted():
    data = _feed_of_size(MAX_RESPONSE_BYTES)
    assert len(data) == MAX_RESPONSE_BYTES
    assert len(parse_rss(data)) == 1


def test_response_over_the_limit_is_refused():
    with pytest.raises(FeedError, match="2 MB"):
        parse_rss(_feed_of_size(MAX_RESPONSE_BYTES + 1))


def test_limit_is_two_megabytes():
    assert MAX_RESPONSE_BYTES == 2 * 1024 * 1024
