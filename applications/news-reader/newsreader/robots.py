"""robots.txt decision (R6.6). Text in, answer out; no network and no clock.

A small reading of RFC 9309 (the Robots Exclusion Protocol):

* The file is split into groups. A group starts with one or more `User-agent`
  lines and holds the `Allow` and `Disallow` lines that follow them. Other
  lines (`Sitemap`, `Crawl-delay`, content signals, comments) are ignored.
* The group for our product token (the part of the User-Agent before `/`,
  compared in lower case) is used. If there is none, the group for `*` is used.
  If there is none either, everything is allowed. Groups with the same agent
  are merged.
* In the chosen group the longest matching rule wins; on equal length `Allow`
  wins. A path that matches no rule is allowed. An empty `Disallow` allows
  everything.
* A rule path may use `*` (any characters) and a final `$` (end of the path).
  The path that is tested includes the query string.
"""
import re
from urllib.parse import urlsplit


def product_token(user_agent):
    """`GithubAutoPlay-news-reader/1.0` -> `githubautoplay-news-reader`."""
    return user_agent.split("/", 1)[0].strip().lower()


def _parse_groups(text):
    """text -> dict: agent token (lower case) -> list of (is_allow, path)."""
    groups = {}
    current = []        # agents of the group being read
    in_rules = False    # True once the group has seen a rule line
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        field, _, value = line.partition(":")
        field, value = field.strip().lower(), value.strip()
        if field == "user-agent":
            if in_rules:
                current, in_rules = [], False
            token = value.lower()
            current.append(token)
            groups.setdefault(token, [])
        elif field in ("allow", "disallow"):
            in_rules = True
            for agent in current:
                groups[agent].append((field == "allow", value))
    return groups


def _rule_regex(path):
    anchored = path.endswith("$")
    if anchored:
        path = path[:-1]
    pattern = ".*".join(re.escape(part) for part in path.split("*"))
    return re.compile(pattern + ("\\Z" if anchored else ""), re.DOTALL)


def is_allowed(robots_text, user_agent, path):
    """True if `user_agent` may fetch `path` (with query, starting with `/`)."""
    groups = _parse_groups(robots_text)
    rules = groups.get(product_token(user_agent))
    if rules is None:
        rules = groups.get("*", [])
    best_len, best_allow = -1, True
    for is_allow, rule_path in rules:
        if rule_path == "":
            continue  # empty Disallow (or Allow) changes nothing
        if _rule_regex(rule_path).match(path):
            length = len(rule_path)
            if length > best_len or (length == best_len and is_allow):
                best_len, best_allow = length, is_allow
    return best_allow


def robots_url(url):
    """The robots.txt address of the host of `url`."""
    parts = urlsplit(url)
    return "%s://%s/robots.txt" % (parts.scheme, parts.netloc)


def url_path(url):
    """Path plus query of `url`, the text a robots rule is tested against."""
    parts = urlsplit(url)
    path = parts.path or "/"
    return path + ("?" + parts.query if parts.query else "")
