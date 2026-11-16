"""robots.txt decisions (R6.6), text in and answer out."""
import pytest

from newsreader.robots import is_allowed, product_token, robots_url, url_path

UA = "GithubAutoPlay-news-reader/1.0"


def test_product_token():
    assert product_token(UA) == "githubautoplay-news-reader"


@pytest.mark.parametrize("text,path,expected", [
    ("", "/feed.xml", True),
    ("User-agent: *\nDisallow:\n", "/feed.xml", True),
    ("User-agent: *\nAllow: /\n", "/feed.xml", True),
    ("User-agent: *\nDisallow: /\n", "/feed.xml", False),
    ("User-agent: *\nDisallow: /nyheter/\n", "/nyheter/rss.xml", False),
    ("User-agent: *\nDisallow: /nyheter/\n", "/other/rss.xml", True),
    # longest match wins, Allow wins a tie
    ("User-agent: *\nDisallow: /nyheter/\nAllow: /nyheter/rss.xml\n", "/nyheter/rss.xml", True),
    ("User-agent: *\nAllow: /a\nDisallow: /a\n", "/a", True),
    # wildcard and end anchor
    ("User-agent: *\nDisallow: /*.xml$\n", "/x/rss.xml", False),
    ("User-agent: *\nDisallow: /*.xml$\n", "/x/rss.xml?a=1", True),
    # comments, case, other fields
    ("# c\nUSER-AGENT: *  # all\nDISALLOW: /x # no\nSitemap: https://a.example.invalid/s\n", "/x/y", False),
    # own group beats *
    ("User-agent: *\nDisallow: /\n\nUser-agent: githubautoplay-news-reader\nAllow: /\n", "/feed.xml", True),
    ("User-agent: *\nAllow: /\n\nUser-agent: GithubAutoPlay-news-reader\nDisallow: /\n", "/feed.xml", False),
    # another agent's group is ignored
    ("User-agent: otherbot\nDisallow: /\n", "/feed.xml", True),
    # several agents share one group
    ("User-agent: otherbot\nUser-agent: githubautoplay-news-reader\nDisallow: /feed\n", "/feed.xml", False),
    # a rule line before any user-agent is ignored
    ("Disallow: /\n", "/feed.xml", True),
])
def test_is_allowed(text, path, expected):
    assert is_allowed(text, UA, path) is expected


def test_byte_order_mark_is_ignored():
    assert is_allowed("\ufeffUser-agent: *\nDisallow: /\n", UA, "/feed.xml") is False
    assert is_allowed("\ufeffUser-agent: githubautoplay-news-reader\nDisallow: /\n", UA, "/x") is False


@pytest.mark.parametrize("agent_line", [
    "GithubAutoPlay-news-reader", "githubautoplay-news-reader", "GITHUBAUTOPLAY-NEWS-READER/1.0",
    "GithubAutoPlay-news-reader/1.0", "GithubAutoPlay-news-reader/2.5"])
def test_group_names_us_by_token_or_full_agent_line(agent_line):
    text = "User-agent: *\nAllow: /\n\nUser-agent: %s\nDisallow: /\n" % agent_line
    assert is_allowed(text, UA, "/feed.xml") is False


def test_a_different_agent_with_a_similar_name_is_not_us():
    text = "User-agent: *\nAllow: /\n\nUser-agent: GithubAutoPlay\nDisallow: /\n"
    assert is_allowed(text, UA, "/feed.xml") is True


@pytest.mark.parametrize("rule,path,expected", [
    ("/%7Ea", "/~a", False),
    ("/~a", "/%7Ea", False),
    ("/%7ea", "/%7Ea", False),
    ("/%41b", "/Ab", False),
    ("/a%2Fb", "/a%2fb", False),   # reserved characters stay encoded, hex case ignored
    ("/a%2Fb", "/a/b", True),
    ("/%7Ea", "/~b", True),
])
def test_percent_encoding_of_unreserved_characters_is_normalised(rule, path, expected):
    assert is_allowed("User-agent: *\nDisallow: %s\n" % rule, UA, path) is expected


@pytest.mark.parametrize("rule,path,expected", [
    ("/ä", "/%C3%A4", False),
    ("/%C3%A4", "/ä", False),
    ("/%c3%a4", "/ä", False),
    ("/ä", "/ä", False),
    ("/ä/*.xml$", "/ä/x.xml", False),
    ("/ä", "/a", True),
    ("/€", "/%E2%82%AC", False),
])
def test_raw_non_ascii_is_matched_as_utf8_percent_encoding(rule, path, expected):
    assert is_allowed("User-agent: *\nDisallow: %s\n" % rule, UA, path) is expected


def test_urls():
    assert robots_url("https://news.example.invalid/a/b?x=1") == "https://news.example.invalid/robots.txt"
    assert url_path("https://news.example.invalid/a/b?x=1") == "/a/b?x=1"
    assert url_path("https://news.example.invalid") == "/"


# --- linear wildcard matching (issue #119) ---

import re
import time


def _old_regex_match(rule, path):
    """The regular expression the matcher replaced, kept as a reference."""
    anchored = rule.endswith("$")
    if anchored:
        rule = rule[:-1]
    pattern = ".*".join(re.escape(part) for part in rule.split("*"))
    return re.compile(pattern + ("\Z" if anchored else ""), re.DOTALL).match(path) is not None


@pytest.mark.parametrize("rule,path,expected", [
    ("/a**b", "/ab", True),
    ("/a***b", "/aXXb", True),
    ("/a***b", "/aXXc", False),
    ("*", "/anything", True),
    ("*/x", "/y/x", True),
    ("*/x", "/y/z", False),
    ("/a*", "/a", True),
    ("/a*", "/abc", True),
    ("/a*$", "/abc", True),
    ("/*.xml$", "/x.xml", True),
    ("/*.xml$", "/x.xml?a", False),
    ("/a*b*c$", "/abxbc", True),
    ("/a*b*c$", "/abcx", False),
    ("/ab*b$", "/ab", False),
    ("/a*a$", "/a", False),
    ("/a*b$", "/ab", True),
    ("$", "", True),
    ("$", "/", False),
    ("/a$b", "/a$b", True),
    ("/a$b*", "/a$bc", True),
    ("/a*b", "/a\nb", True),
    ("/a$", "/a", True),
    ("/a$", "/ab", False),
])
def test_wildcard_cases_match_the_old_regex(rule, path, expected):
    from newsreader.robots import _rule_matches
    assert _rule_matches(rule, path) is expected
    assert _old_regex_match(rule, path) is expected


def test_new_matcher_agrees_with_old_regex_on_many_inputs():
    import itertools
    from newsreader.robots import _rule_matches
    rules = ["".join(c) for n in range(0, 6) for c in itertools.product("a*$/", repeat=n)]
    paths = ["".join(c) for n in range(0, 7) for c in itertools.product("a/$", repeat=n)] + ["a\na", "/a\n$"]
    for rule in rules:
        for path in paths:
            assert _rule_matches(rule, path) == _old_regex_match(rule, path), (rule, path)


def test_many_wildcards_on_long_path_finish_quickly():
    rule = "/" + "a*" * 40 + "b"
    path = "/" + "a" * 20000
    start = time.perf_counter()
    assert is_allowed("User-agent: *\nDisallow: %s\n" % rule, UA, path) is True
    assert is_allowed("User-agent: *\nDisallow: %s$\n" % rule, UA, path) is True
    assert time.perf_counter() - start < 1.0
