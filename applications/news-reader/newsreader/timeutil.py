"""Time handling (R2). No I/O; "now" is always passed in.

Uses only the standard library. Europe/Stockholm comes from `zoneinfo`, which
reads the system time zone database (or the `tzdata` package if installed).

The rules are written out explicitly so the JavaScript version (S9) can give
the same results (see the README):

* Accepted input: RFC 822/2822 dates, and ISO 8601 date-times (see below).
* A time without a zone is read as Europe/Stockholm wall-clock time.
  - A local time that does not exist (the hour skipped when summer time
    starts, 02:00-02:59 on the last Sunday of March) is read with the winter
    offset (+01:00), so 02:30 becomes 01:30Z, shown as 03:30.
  - A local time that exists twice (the hour repeated when summer time ends,
    02:00-02:59 on the last Sunday of October) is read as the first
    occurrence, with the summer offset (+02:00), so 02:30 becomes 00:30Z.
* Anything else, or an impossible date or time, gives None.
"""
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

STOCKHOLM = ZoneInfo("Europe/Stockholm")
UTC = timezone.utc
MISSING_DISPLAY = "Tid saknas"
FUTURE_LIMIT = timedelta(minutes=10)

_MONTHS = {m: i + 1 for i, m in enumerate(
    "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split())}

# RFC 822 zone names (case-insensitive) and their offsets in minutes.
_ZONE_NAMES = {
    "UT": 0, "UTC": 0, "GMT": 0, "Z": 0,
    "EST": -300, "EDT": -240, "CST": -360, "CDT": -300,
    "MST": -420, "MDT": -360, "PST": -480, "PDT": -420,
}

# ASCII digits only ([0-9], not \d), so JavaScript can use the same patterns.
_RFC822 = re.compile(
    r"^(?:[A-Za-z]{3},[ ]+)?([0-9]{1,2})[ ]+([A-Za-z]{3})[ ]+([0-9]{4})[ ]+"
    r"([0-9]{2}):([0-9]{2})(?::([0-9]{2}))?(?:[ ]+([A-Za-z]+|[+-][0-9]{4}))?$")
_ISO = re.compile(
    r"^([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2})(?::([0-9]{2}))?"
    r"(?:\.[0-9]+)?(Z|z|[+-][0-9]{2}(?::?[0-9]{2})?)?$")
_UTC_TEXT = re.compile(
    r"^([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})Z$")

_WHITESPACE = " \t\n\r\f\v"  # same trimming set as the cleaning code, without U+00A0


def _offset(text):
    """'+0100', '+01:00', '+01' -> timedelta."""
    sign = -1 if text[0] == "-" else 1
    digits = text[1:].replace(":", "")
    hours = int(digits[:2])
    minutes = int(digits[2:4]) if len(digits) > 2 else 0
    if hours > 23 or minutes > 59:
        raise ValueError("offset")
    return sign * timedelta(hours=hours, minutes=minutes)


def _build(year, month, day, hour, minute, second, offset):
    """Naive fields plus an offset (timedelta) or None (Stockholm) -> UTC datetime."""
    if second == 60 or hour > 23 or minute > 59 or second > 59:
        raise ValueError("time")
    naive = datetime(year, month, day, hour, minute, second)  # checks day/month/leap day
    if offset is None:
        # fold=0: a missing hour uses the offset from before the switch, a
        # repeated hour uses the first occurrence (see the module docstring).
        return naive.replace(tzinfo=STOCKHOLM, fold=0).astimezone(UTC)
    return (naive - offset).replace(tzinfo=UTC)


def parse_time(text):
    """Time text -> aware UTC datetime, or None when it is missing or unusable.

    Accepts RFC 822/2822 (`Fri, 13 Nov 2026 14:05:00 +0100`, zone names such
    as GMT, UT, Z, EST...; the weekday is not checked) and ISO 8601
    (`2026-11-13T14:05:00+01:00`, `...Z`, fractions of a second are ignored).
    """
    if not isinstance(text, str):
        return None
    text = text.strip(_WHITESPACE)
    try:
        m = _RFC822.match(text)
        if m:
            day, mon, year, hh, mm, ss, zone = m.groups()
            month = _MONTHS.get(mon.capitalize())
            if month is None:
                return None
            if zone is None:
                offset = None
            elif zone[0] in "+-":
                offset = _offset(zone)
            elif zone.upper() in _ZONE_NAMES:
                offset = timedelta(minutes=_ZONE_NAMES[zone.upper()])
            else:
                return None
            return _build(int(year), month, int(day), int(hh), int(mm), int(ss or 0), offset)
        m = _ISO.match(text)
        if m:
            year, month, day, hh, mm, ss, zone = m.groups()
            if zone is None:
                offset = None
            elif zone in ("Z", "z"):
                offset = timedelta(0)
            else:
                offset = _offset(zone)
            return _build(int(year), int(month), int(day), int(hh), int(mm), int(ss or 0), offset)
    except ValueError:
        return None
    return None


def format_utc(moment):
    """Aware datetime -> `YYYY-MM-DDTHH:MM:SSZ` in UTC (R2.1)."""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def published_utc(text, now):
    """Time text -> `published` (R2.1, R2.2, R2.6): ISO UTC text, or None.

    `now` is an aware datetime. A time more than 10 minutes after `now` is
    treated as missing; exactly 10 minutes ahead is kept.
    """
    moment = parse_time(text)
    if moment is None or moment > now.astimezone(UTC) + FUTURE_LIMIT:
        return None
    return format_utc(moment)


def display_time(published):
    """`published` (UTC text of R2.1 or None) -> `publishedDisplay` (R2.4, R2.5)."""
    if published is None:
        return MISSING_DISPLAY
    m = _UTC_TEXT.match(published)
    if not m:
        raise ValueError("not a UTC time: %r" % (published,))
    moment = datetime(*map(int, m.groups()), tzinfo=UTC)
    return moment.astimezone(STOCKHOLM).strftime("%Y-%m-%d %H:%M")


def generated_at(now):
    """`generatedAt` (R2.7): `now` in UTC, whole seconds."""
    return format_utc(now)


def generated_at_display(now):
    """`generatedAtDisplay` (R2.7): `now` in the form of R2.4."""
    return display_time(format_utc(now))
