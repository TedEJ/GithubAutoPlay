"""robots.txt decision (R6.6). Text in, answer out; no network and no clock.

A small reading of RFC 9309 (the Robots Exclusion Protocol):

* The file is split into groups. A group starts with one or more `User-agent`
  lines and holds the `Allow` and `Disallow` lines that follow them. Other
  lines (`Sitemap`, `Crawl-delay`, content signals, comments) are ignored.
* The group for our product token is used. Both the product token and a full
  User-Agent line in the file (`GithubAutoPlay-news-reader/1.0`) name us: only
  the part before `/` is compared, in lower case. If there is none, the group for `*` is used.
  If there is none either, everything is allowed. Groups with the same agent
  are merged.
* In the chosen group the longest matching rule wins; on equal length `Allow`
  wins. A path that matches no rule is allowed. An empty `Disallow` allows
  everything.
* A rule path may use `*` (any characters) and a final `$` (end of the path).
  The path that is tested includes the query string.
* A leading byte order mark is ignored. Percent-encoded unreserved characters
  (`%7E` for `~`) are decoded in the rules and in the tested path before
  matching, so `/%7Ea` and `/~a` are the same path. Raw non-ASCII characters
  are first turned into their UTF-8 percent-encoded form (`/ä` is `/%C3%A4`).
"""
import re
from urllib.parse import urlsplit


def product_token(user_agent):
    """`GithubAutoPlay-news-reader/1.0` -> `githubautoplay-news-reader`."""
    return user_agent.split("/", 1)[0].strip().lower()


_UNRESERVED = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")
_PERCENT = re.compile(r"%([0-9A-Fa-f]{2})")


def normalise_path(path):
    """UTF-8 percent-encode raw non-ASCII characters, decode percent-encoded
    unreserved characters; other escapes get upper-case hex."""
    path = "".join(c if ord(c) < 128 else "".join("%%%02X" % b for b in c.encode("utf-8", "surrogatepass"))
                   for c in path)
    def decode(match):
        char = chr(int(match.group(1), 16))
        return char if char in _UNRESERVED else "%" + match.group(1).upper()
    return _PERCENT.sub(decode, path)


def _parse_groups(text):
    """text -> dict: agent token (lower case) -> list of (is_allow, path)."""
    text = text.lstrip("\ufeff")
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
            token = product_token(value)
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
    path = normalise_path(path)
    groups = _parse_groups(robots_text)
    rules = groups.get(product_token(user_agent))
    if rules is None:
        rules = groups.get("*", [])
    best_len, best_allow = -1, True
    for is_allow, rule_path in rules:
        if rule_path == "":
            continue  # empty Disallow (or Allow) changes nothing
        rule_path = normalise_path(rule_path)
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
