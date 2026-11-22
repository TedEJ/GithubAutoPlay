"""Privacy guard for applications/network-health/ (issue #149).

The repository is public. The network-health tool reads real network data
(IP and MAC addresses, Wi-Fi names, keys), and none of it may be committed.
This test scans every file under applications/network-health/ (the files git
tracks, plus files not yet tracked, but not local-data/ or caches) and fails
on:

* IPv4 addresses outside the allowed set below,
* IPv6 addresses outside the allowed set below,
* MAC addresses outside the documented made-up ranges,
* strings that look like passwords, Wi-Fi keys, tokens or private keys.

Allowed addresses (the single list; change it only together with the design
document, applications/network-health/network-health-design.md, section
"External servers"):

* IPv4 documentation ranges 192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24
  (RFC 5737), loopback 127.0.0.0/8, 0.0.0.0, broadcast 255.255.255.255,
  link-local 169.254.0.0/16, multicast 224.0.0.0/4, netmasks (255.x.x.x with
  contiguous ones), and the base addresses of the private ranges
  (NETWORK_BASES) so code can name those ranges.
* IPv6 documentation range 2001:db8::/32 (RFC 3849), ::1, ::, ::/8, multicast
  ff00::/8, link-local fe80::/10 only with a short example interface id (at
  most 4 hex digits, such as fe80::1) or one built from an RFC 7042 MAC, the
  Windows placeholder DNS servers fec0:0:0:ffff::1-3, and fc00:: (the base of
  the unique local range).
* ALLOWED_PUBLIC: the public ping targets and DNS resolvers that the design
  document names.
* MAC addresses: 00:00:5e:00:53:xx and 01:00:5e:90:10:xx (RFC 7042
  documentation ranges), ff:ff:ff:ff:ff:ff, 00:00:00:00:00:00, IPv4 multicast
  01:00:5e:00:00:00-01:00:5e:7f:ff:ff and IPv6 multicast 33:33:xx:xx:xx:xx.

Exception mechanism (narrow on purpose): a line that contains
`privacy-guard: allow <value>` (several values separated by commas) may hold
exactly those values. Nothing else on the line is excused. Use it only for
something that looks like an address but is not one, and say why on the line.

Findings are printed with the value masked, so a real address that slipped in
is not repeated in the public CI log.
"""

from __future__ import annotations

import ipaddress
import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
APP = "applications/network-health"
SKIP_DIRS = {"local-data", "__pycache__", ".pytest_cache", ".git"}

DOC_V4 = tuple(ipaddress.ip_network(n) for n in
               ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24"))
ALLOWED_V4_NETS = DOC_V4 + tuple(ipaddress.ip_network(n) for n in
                                 ("127.0.0.0/8", "169.254.0.0/16", "224.0.0.0/4"))
NETWORK_BASES = frozenset(ipaddress.ip_address(a) for a in (
    "10.0.0.0", "172.16.0.0", "192.168.0.0", "100.64.0.0", "169.254.0.0", "fc00::"))
WINDOWS_PLACEHOLDER_DNS = frozenset(ipaddress.ip_address(a) for a in (
    "fec0:0:0:ffff::1", "fec0:0:0:ffff::2", "fec0:0:0:ffff::3"))

# Public addresses named in network-health-design.md ("External servers").
ALLOWED_PUBLIC = frozenset(ipaddress.ip_address(a) for a in (
    "1.1.1.1", "1.0.0.1",                          # Cloudflare
    "8.8.8.8", "8.8.4.4",                          # Google Public DNS
    "9.9.9.9", "149.112.112.112",                  # Quad9
    "208.67.222.222", "208.67.220.220",            # OpenDNS (Cisco)
    "2606:4700:4700::1111", "2606:4700:4700::1001",
    "2001:4860:4860::8888", "2001:4860:4860::8844",
    "2620:fe::fe", "2620:fe::9",
    "2620:119:35::35", "2620:119:53::53",
))

IPV4_RE = re.compile(r"(?<![\d.])(\d{1,3}(?:\.\d{1,3}){3})(?!\.?\d)")
IPV6_RE = re.compile(
    r"(?<![0-9A-Za-z:.])"
    r"((?:[0-9A-Fa-f]{0,4}:){2,7}(?:[0-9A-Fa-f]{1,4}|\d{1,3}(?:\.\d{1,3}){3})?)"
    r"(?:%[0-9A-Za-z]+)?"
    r"(?![0-9A-Za-z:]|\.\d)")
MAC_RE = re.compile(
    r"(?<![0-9A-Fa-f:-])([0-9A-Fa-f]{2}([:-])(?:[0-9A-Fa-f]{2}\2){4}[0-9A-Fa-f]{2})"
    r"(?![0-9A-Fa-f:-])"
    r"|(?<![0-9A-Fa-f.])([0-9A-Fa-f]{4}\.[0-9A-Fa-f]{4}\.[0-9A-Fa-f]{4})(?![0-9A-Fa-f.])")

_SECRET_WORDS = (r"password|passwd|pwd|passphrase|secret|token|api[_-]?key|"
                 r"access[_-]?key|private[_-]?key|psk|wpa[_-]?key|pre[_-]?shared[_-]?key")
SECRET_RES = (
    # A secret word assigned a quoted value: password = "..."
    re.compile(r"(?i)(?<![a-z])(?:" + _SECRET_WORDS + r")(?![a-z])[\"']?\s*[:=]\s*"
               r"([\"'])(?P<value>[^\"'\s]{6,})\1"),
    # A secret word with an unquoted value on its own line: password: ...
    re.compile(r"(?im)^\s*(?:" + _SECRET_WORDS + r")\s*[:=]\s*(?P<value>[^\s\"'<>]{6,})\s*$"),
    # The Wi-Fi key as `netsh wlan show profile key=clear` prints it.
    re.compile(r"(?im)^\s*Key Content\s*:\s*(?P<value>\S.*?)\s*$"),
    # Well-known token formats.
    re.compile(r"(?P<value>\bgh[pousr]_[A-Za-z0-9]{30,})"),
    re.compile(r"(?P<value>\bgithub_pat_[A-Za-z0-9_]{20,})"),
    re.compile(r"(?P<value>\bAKIA[0-9A-Z]{16}\b)"),
    re.compile(r"(?P<value>\bxox[abprs]-[A-Za-z0-9-]{10,})"),
    re.compile(r"(?P<value>\bsk-[A-Za-z0-9_-]{20,})"),
    re.compile(r"(?P<value>-----BEGIN [A-Z ]*PRIVATE KEY-----)"),
)
PLACEHOLDER_RE = re.compile(
    r"^(<[^>]*>|\{[^}]*\}|\$\{?\w+\}?|\*+|x+|\.+|redacted|example|placeholder)$",
    re.IGNORECASE)
EXCEPTION_RE = re.compile(r"privacy-guard: allow ([^\s#]+(?:\s*,\s*[^\s#]+)*)")


# ---------------------------------------------------------------- rules

def ipv4_allowed(ip: ipaddress.IPv4Address) -> bool:
    if ip in ALLOWED_PUBLIC or ip in NETWORK_BASES:
        return True
    if any(ip in net for net in ALLOWED_V4_NETS):
        return True
    if str(ip) in ("0.0.0.0", "255.255.255.255"):
        return True
    inverted = ~int(ip) & 0xFFFFFFFF
    return str(ip).startswith("255.") and inverted & (inverted + 1) == 0  # netmask


def _eui64_from_doc_mac(interface_id: int) -> bool:
    # An RFC 7042 MAC 00:00:5e:00:53:xx gives the interface id 0200:5eff:fe00:53xx.
    return interface_id >> 8 == 0x02005EFFFE0053


def ipv6_allowed(ip: ipaddress.IPv6Address) -> bool:
    if ip.ipv4_mapped is not None:
        return ipv4_allowed(ip.ipv4_mapped)
    if ip in ALLOWED_PUBLIC or ip in NETWORK_BASES or ip in WINDOWS_PLACEHOLDER_DNS:
        return True
    if ip in ipaddress.ip_network("2001:db8::/32"):
        return True
    if ip.is_loopback or ip.is_unspecified or ip.is_multicast:
        return True
    if ip in ipaddress.ip_network("::/8"):
        return True
    if ip.is_link_local:
        interface_id = int(ip) & ((1 << 64) - 1)
        return interface_id <= 0xFFFF or _eui64_from_doc_mac(interface_id)
    return False


def mac_allowed(mac: str) -> bool:
    digits = re.sub(r"[^0-9a-f]", "", mac.lower())
    if digits in ("ffffffffffff", "000000000000"):
        return True
    if digits.startswith("00005e0053") or digits.startswith("01005e9010"):
        return True
    if digits.startswith("01005e") and int(digits[6], 16) < 8:  # IPv4 multicast
        return True
    return digits.startswith("3333")  # IPv6 multicast


def mask(kind: str, value: str) -> str:
    if kind == "IPv4":
        return value.split(".")[0] + ".x.x.x"
    if kind == "IPv6":
        return value.split(":")[0] + ":x:..."
    if kind == "MAC":
        return value[:2] + ":xx:xx:xx:xx:xx"
    return value[:3] + "***"


def find_problems(text: str) -> list[tuple[int, str, str]]:
    """Return (line number, kind, value) for every problem in text."""
    problems: list[tuple[int, str, str]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        excused = set()
        for match in EXCEPTION_RE.finditer(line):
            excused |= {v.strip().lower() for v in match.group(1).split(",")}

        def report(kind: str, value: str) -> None:
            if value.lower() not in excused:
                problems.append((number, kind, value))

        for match in IPV4_RE.finditer(line):
            try:
                ip = ipaddress.IPv4Address(match.group(1))
            except ValueError:
                continue  # 1.2.3.400 or 01.02.03.04: not an address
            if not ipv4_allowed(ip):
                report("IPv4", match.group(1))
        for match in IPV6_RE.finditer(line):
            try:
                ip = ipaddress.IPv6Address(match.group(1))
            except ValueError:
                continue  # times, MAC addresses and the like
            if not ipv6_allowed(ip):
                report("IPv6", match.group(1))
        for match in MAC_RE.finditer(line):
            value = match.group(1) or match.group(3)
            if not mac_allowed(value):
                report("MAC", value)
        for pattern in SECRET_RES:
            for match in pattern.finditer(line):
                value = match.group("value")
                if not PLACEHOLDER_RE.match(value):
                    report("secret", value)
    return problems


# ---------------------------------------------------------------- files

def app_files(root: Path = ROOT) -> list[Path]:
    """Tracked files plus files not yet tracked, without local data and caches."""
    folder = root / APP
    files: set[Path] = set()
    try:
        listed = subprocess.run(["git", "ls-files", "-z", "--", APP], cwd=root,
                                capture_output=True, check=True).stdout
        files |= {root / name for name in listed.decode("utf-8").split("\0") if name}
    except (OSError, subprocess.CalledProcessError):
        pass  # no git: the walk below still finds every file
    for directory, dirs, names in os.walk(folder):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        files |= {Path(directory) / n for n in names}
    return sorted(f for f in files
                  if f.is_file() and not SKIP_DIRS & set(f.relative_to(root).parts))


def test_network_health_folder_exists():
    assert (ROOT / APP).is_dir()
    assert any(f.name == "network-health-design.md" for f in app_files())


def test_network_health_contains_no_real_network_data_or_secrets():
    found = []
    for path in app_files():
        text = path.read_bytes().decode("utf-8", errors="replace")
        for number, kind, value in find_problems(text):
            found.append(f"{path.relative_to(ROOT).as_posix()}:{number}: "
                         f"{kind} {mask(kind, value)}")
    assert not found, ("Possible real network data or secrets (values masked). Use "
                       "documentation addresses and made-up names; see the docstring "
                       "of this test:\n" + "\n".join(found))


def test_every_allowed_public_address_is_named_in_the_design_document():
    design = (ROOT / APP / "network-health-design.md").read_text(encoding="utf-8")
    named = {str(ipaddress.ip_address(m)) for m in IPV4_RE.findall(design)}
    for match in IPV6_RE.finditer(design):
        try:
            named.add(str(ipaddress.IPv6Address(match.group(1))))
        except ValueError:
            pass
    missing = sorted(str(a) for a in ALLOWED_PUBLIC if str(a) not in named)
    assert not missing, f"allowed but not named in the design document: {missing}"


# ---------------------------------------------------------------- the guard catches things

def _join(*parts, sep="."):
    """Build a planted value at run time, so the literal is not in the repo."""
    return sep.join(str(p) for p in parts)


PLANTED_PUBLIC_V4 = _join(81, 2, 69, 160)
PLANTED_PRIVATE_V4 = _join(192, 168, 1, 23)
PLANTED_V6 = _join("2a02", "1406", "f3c", "", "7", sep=":")
PLANTED_MAC = _join("3c", "22", "fb", "12", "34", "56", sep=":")


def kinds(text):
    return [kind for _, kind, _ in find_problems(text)]


@pytest.mark.parametrize("value", [PLANTED_PUBLIC_V4, PLANTED_PRIVATE_V4,
                                   _join(10, 0, 0, 138), _join(172, 20, 1, 5)])
def test_guard_catches_planted_ipv4(value):
    assert kinds(f"Reply from {value}: bytes=32 time=3ms TTL=64") == ["IPv4"]
    assert kinds(f"The router is {value}.") == ["IPv4"]


@pytest.mark.parametrize("value", [
    PLANTED_V6,
    _join("fe80", "", "1c2d", "3e4f", "5a6b", "7c8d", sep=":"),   # random link-local id
    _join("fe80", "", "3e22", "fbff", "fe12", "3456", sep=":"),   # EUI-64 of a real MAC
    "::ffff:" + PLANTED_PUBLIC_V4,
    _join("fd12", "3456", "789a", "1", "", "1", sep=":"),         # unique local
])
def test_guard_catches_planted_ipv6(value):
    assert "IPv6" in kinds(f"address {value} on the adapter")


@pytest.mark.parametrize("value", [PLANTED_MAC, PLANTED_MAC.replace(":", "-"),
                                   PLANTED_MAC.upper(), "3c22.fb12.3456"])
def test_guard_catches_planted_mac(value):
    assert kinds(f"  192.0.2.1   {value}   dynamic") == ["MAC"]


@pytest.mark.parametrize("line", [
    'password = "' + "hunter" + "2hunter2" + '"',
    "WIFI_PSK: '" + "correct" + "horse" + "'",
    "router_password=" + '"' + "S3cret" + "!pass" + '"',
    "    Key Content            : " + "MyHome" + "Wifi2024",
    "token: " + "abc123" + "def456",
    "gh" + "p_" + "A1b2C3d4" * 5,
    "AKIA" + "ABCDEFGHIJKLMNOP",
    "-----BEGIN " + "RSA PRIVATE KEY-----",
])
def test_guard_catches_planted_secrets(line):
    assert "secret" in kinds(line)


@pytest.mark.parametrize("text", [
    "Reply from 192.0.2.1: bytes=32 time<1ms TTL=64",
    "DNS 198.51.100.53 and 203.0.113.7, mask 255.255.255.0, any 0.0.0.0",
    "loopback 127.0.0.1 and ::1, self-assigned 169.254.12.34, mDNS 224.0.0.251",
    "Cloudflare 1.1.1.1 and 2606:4700:4700::1111, Quad9 2620:fe::fe",
    "IPv6 2001:db8:1::10 and fe80::1%12 and fe80::200:5eff:fe00:5301",
    "placeholder DNS fec0:0:0:ffff::1, unique local base fc00::/7",
    "private range 10.0.0.0/8 and 192.168.0.0/16",
    "BSSID 00:00:5e:00:53:01, multicast 01-00-5e-7f-ff-fa, ff-ff-ff-ff-ff-ff",
    "Python 3.10.12 and Windows 10.0.22631.4460 and v1.2.3.4.5",
    "time 12:30:45, slice [::2], dict {'a': 1}, URL https://speed.cloudflare.com/__up",
    'password = "<your password>"',
    "The password is asked with getpass and never stored.",
    "Key Content : ***",
])
def test_guard_allows_documentation_values_and_ordinary_text(text):
    assert find_problems(text) == []


def test_exception_marker_excuses_only_the_named_value():
    other = _join(81, 2, 69, 161)
    line = f"build {PLANTED_PUBLIC_V4} and {other}  # privacy-guard: allow {PLANTED_PUBLIC_V4}"
    assert [v for _, _, v in find_problems(line)] == [other]
    assert find_problems(f"x {PLANTED_PUBLIC_V4}") != []


def test_four_part_version_looks_like_an_address_and_needs_the_marker():
    version = _join(4, 2, 1, 7)
    assert kinds(f"version {version}") == ["IPv4"]
    assert kinds(f"version {version}  # privacy-guard: allow {version} (a version)") == []


def test_findings_are_masked():
    assert mask("IPv4", PLANTED_PUBLIC_V4) == "81.x.x.x"
    assert PLANTED_MAC not in mask("MAC", PLANTED_MAC)
    assert mask("secret", "hunter2hunter2") == "hun***"


def test_untracked_files_are_scanned_and_local_data_is_not(tmp_path):
    app = tmp_path / APP
    for folder in ("local-data", "network_health/__pycache__"):
        (app / folder).mkdir(parents=True)
    (app / "local-data" / "snapshot.json").write_text("x", encoding="utf-8")
    (app / "network_health" / "__pycache__" / "x.pyc").write_bytes(b"x")
    (app / "new.txt").write_text("x", encoding="utf-8")
    names = [f.relative_to(tmp_path).as_posix() for f in app_files(tmp_path)]
    assert names == [f"{APP}/new.txt"]
