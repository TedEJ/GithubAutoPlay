"""Privacy guard for applications/network-health/ (issue #149).

The repository is public. The network-health tool reads real network data
(IP and MAC addresses, Wi-Fi names, keys), and none of it may be committed.
This test scans every file under applications/network-health/ that git
tracks or would add (`git ls-files -co --exclude-standard`: tracked files
plus untracked files that .gitignore does not exclude, so local-data/ and
caches are left out; without git it walks the folder and skips those) and
fails on:

* IPv4 addresses outside the allowed set below (leading zeros, as in
  192.0.2.001, are read as the address they stand for),
* IPv6 addresses outside the allowed set below,
* MAC addresses outside the documented made-up ranges, written with ':', '-'
  or '.' separators, or as 12 hex digits without separators (the registry
  NetworkAddress form; see "Bare MAC addresses" below),
* strings that look like passwords, Wi-Fi keys, tokens or private keys,
  quoted or unquoted (NAME=value lines where NAME contains password, passwd,
  secret, token or key; see "Unquoted secrets" below).

Files are read as UTF-8, or as UTF-16 when they start with a UTF-16 byte
order mark or contain NUL bytes (Windows PowerShell 5.1 writes UTF-16 with
`command > file.txt`, the usual way to capture output).

Real SSIDs, host names and device vendors cannot be told apart from made-up
ones by a pattern. They are not detected here and rely on review: fixtures
use names such as ExampleHome.

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

Bare MAC addresses: exactly 12 hex digits with no letter, digit, '_', '-',
'.' or ':' right before or after, that contain at least one digit and at
least one of a-f. So all-decimal numbers (such as 922337203685), plain words
(such as deadbeefcafe), GUID parts and longer hex strings (40- or 64-digit
hashes) do not count. A 12-digit abbreviated git hash would count; use a
7-digit or full hash in this folder, or the exception marker.

Unquoted secrets: a whole line `NAME=value`, `NAME: value` or
`export NAME=value` whose NAME contains password, passwd, pwd, passphrase,
secret, token, psk or credential, or has key as one of its parts (WIFI_KEY,
apiKey; not monkey). It is not flagged when the value is shorter than 4
characters, a placeholder (<...>, {...}, ${VAR}, ***, xxx, redacted,
example), a code word (None, True, lambda, str, ...), contains brackets,
commas or semicolons (a call such as getpass() or a keyword argument), or
when the line is a code assignment with spaces around '=' and the value is a
plain name (password = new_password). Quoted values are always checked.

Exception mechanism (narrow on purpose): a line that contains
`privacy-guard: allow <value>` (several values separated by commas) may hold
exactly those values. Nothing else on the line is excused. Use it only for
something that looks like an address but is not one, and say why on the line.

Findings are printed with the value masked, so a real address that slipped in
is not repeated in the public CI log.
"""

from __future__ import annotations

import codecs
import ipaddress
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
APP = "applications/network-health"
# Only for the walk without git; with git, .gitignore decides.
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
MAC_BARE_RE = re.compile(r"(?<![0-9A-Za-z_.:-])([0-9A-Fa-f]{12})(?![0-9A-Za-z_.:-])")

_SECRET_WORDS = (r"password|passwd|pwd|passphrase|secret|token|api[_-]?key|"
                 r"access[_-]?key|private[_-]?key|psk|wpa[_-]?key|pre[_-]?shared[_-]?key")
SECRET_RES = (
    # A secret word assigned a quoted value: password = "..."
    re.compile(r"(?i)(?<![a-z])(?:" + _SECRET_WORDS + r")(?![a-z])[\"']?\s*[:=]\s*"
               r"([\"'])(?P<value>[^\"'\s]{6,})\1"),
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
# NAME=value, NAME: value or export NAME=value on a line of its own.
ENV_LINE_RE = re.compile(
    r"^\s*(?:export\s+)?(?P<name>[A-Za-z_][A-Za-z0-9_.-]*)(?P<sep>\s*[:=]\s*)"
    r"(?P<value>[^\s\"'#]+)\s*(?:#.*)?$")
SECRET_NAME_PARTS = ("password", "passwd", "pwd", "passphrase", "secret", "token",
                     "psk", "credential")
CODE_WORDS = frozenset(("none", "null", "nil", "true", "false", "lambda", "str", "bytes",
                        "int", "bool", "float", "dict", "list", "tuple", "set",
                        "object", "any", "optional", "self", "cls"))
IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*")
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


def secret_name(name: str) -> bool:
    lower = name.lower()
    if any(word in lower for word in SECRET_NAME_PARTS):
        return True
    parts = re.split(r"[_.-]+|(?<=[a-z0-9])(?=[A-Z])", name)
    return any(part.lower() in ("key", "apikey") for part in parts)


def env_secret(line: str) -> str | None:
    """The value of an unquoted NAME=value secret on this line, or None."""
    match = ENV_LINE_RE.match(line)
    if not match or not secret_name(match.group("name")):
        return None
    value, sep = match.group("value"), match.group("sep")
    if (len(value) < 4 or PLACEHOLDER_RE.match(value)
            or value.lower() in CODE_WORDS or any(c in value for c in "()[]{},;")):
        return None
    if sep.strip() == "=" and sep[0].isspace() and IDENTIFIER_RE.fullmatch(value):
        return None  # code: password = new_password
    return value


def decode(data: bytes) -> str:
    """Text of a file: UTF-16 with a byte order mark or with NUL bytes,
    otherwise UTF-8. Undecodable bytes become replacement characters."""
    if data.startswith(codecs.BOM_UTF8):
        return data[len(codecs.BOM_UTF8):].decode("utf-8", errors="replace")
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return data.decode("utf-16", errors="replace")  # the BOM gives the byte order
    if b"\x00" in data:
        zeros_even, zeros_odd = data[0::2].count(0), data[1::2].count(0)
        if zeros_odd > zeros_even:
            return data.decode("utf-16-le", errors="replace")
        if zeros_even > zeros_odd:
            return data.decode("utf-16-be", errors="replace")
        data = data.replace(b"\x00", b"")
    return data.decode("utf-8", errors="replace")


def _ipv4(text: str) -> ipaddress.IPv4Address | None:
    """The address a dotted quad stands for, also with leading zeros."""
    octets = [int(part) for part in text.split(".")]
    if any(octet > 255 for octet in octets):
        return None
    return ipaddress.IPv4Address(".".join(str(octet) for octet in octets))


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
            ip = _ipv4(match.group(1))
            if ip is not None and not ipv4_allowed(ip):  # None: 1.2.3.400
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
        for match in MAC_BARE_RE.finditer(line):
            value = match.group(1)
            if (re.search(r"[0-9]", value) and re.search(r"[A-Fa-f]", value)
                    and not mac_allowed(value)):
                report("MAC", value)
        for pattern in SECRET_RES:
            for match in pattern.finditer(line):
                value = match.group("value")
                if not PLACEHOLDER_RE.match(value):
                    report("secret", value)
        value = env_secret(line)
        if value is not None:
            report("secret", value)
    return problems


# ---------------------------------------------------------------- files

def _git_files(root: Path) -> list[Path] | None:
    """Tracked plus untracked-but-not-ignored files, or None without git."""
    if shutil.which("git") is None:
        return None
    try:
        listed = subprocess.run(
            ["git", "ls-files", "-z", "-c", "-o", "--exclude-standard", "--", APP],
            cwd=root, capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None  # not a git work tree
    return [root / name for name in listed.decode("utf-8").split("\0") if name]


def _walked_files(root: Path) -> list[Path]:
    files = []
    for directory, dirs, names in os.walk(root / APP):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        files += [Path(directory) / n for n in names]
    return files


def app_files(root: Path = ROOT, use_git: bool = True) -> list[Path]:
    """The files of the application that git would commit."""
    files = _git_files(root) if use_git else None
    if files is None:
        files = _walked_files(root)
    # A tracked file deleted in the work tree is still listed by git.
    return sorted({f for f in files if f.is_file()})


def test_network_health_folder_exists():
    assert (ROOT / APP).is_dir()
    assert any(f.name == "network-health-design.md" for f in app_files())


def test_network_health_contains_no_real_network_data_or_secrets():
    found = []
    for path in app_files():
        text = decode(path.read_bytes())
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


def _layout(root: Path) -> None:
    app = root / APP
    for folder in ("local-data", "network_health/__pycache__"):
        (app / folder).mkdir(parents=True)
    (app / "local-data" / "snapshot.json").write_text("x", encoding="utf-8")
    (app / "network_health" / "__pycache__" / "x.pyc").write_bytes(b"x")
    (app / "new.txt").write_text("x", encoding="utf-8")


def test_walk_without_git_skips_local_data_and_caches(tmp_path):
    _layout(tmp_path)
    names = [f.relative_to(tmp_path).as_posix() for f in app_files(tmp_path, use_git=False)]
    assert names == [f"{APP}/new.txt"]


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_git_lists_tracked_and_untracked_but_not_ignored_files(tmp_path):
    _layout(tmp_path)
    (tmp_path / ".gitignore").write_text("local-data/\n__pycache__/\n", encoding="utf-8")
    (tmp_path / APP / "tracked.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", f"{APP}/tracked.txt"], cwd=tmp_path, check=True)
    names = [f.relative_to(tmp_path).as_posix() for f in app_files(tmp_path)]
    assert names == [f"{APP}/new.txt", f"{APP}/tracked.txt"]


# ---------------------------------------------------------------- round 2 of the review

@pytest.mark.parametrize("encoding,bom", [
    ("utf-16-le", codecs.BOM_UTF16_LE), ("utf-16-be", codecs.BOM_UTF16_BE),
    ("utf-16-le", b""), ("utf-8", codecs.BOM_UTF8)])
def test_utf16_and_bom_files_are_decoded(encoding, bom):
    text = f"Reply from {PLANTED_PUBLIC_V4}: bytes=32 time=3ms TTL=64\r\n"
    assert kinds(decode(bom + text.encode(encoding))) == ["IPv4"]


def test_utf16_file_with_planted_value_is_caught_by_the_folder_scan(tmp_path):
    """Windows PowerShell 5.1 writes UTF-16LE with a BOM for `cmd > file.txt`."""
    app = tmp_path / APP
    app.mkdir(parents=True)
    content = f"Interface: 192.0.2.10 --- 0xc\r\n  {PLANTED_PRIVATE_V4}   {PLANTED_MAC}\r\n"
    (app / "captured.txt").write_bytes(codecs.BOM_UTF16_LE + content.encode("utf-16-le"))
    files = app_files(tmp_path, use_git=False)
    assert [f.name for f in files] == ["captured.txt"]
    raw = files[0].read_bytes()
    assert find_problems(raw.decode("utf-8", errors="replace")) == []  # the old bug
    assert sorted(kinds(decode(raw))) == ["IPv4", "MAC"]


def test_plain_utf8_and_binary_noise_do_not_crash():
    assert decode("192.0.2.1 ok".encode("utf-8")) == "192.0.2.1 ok"
    assert isinstance(decode(b"\x00\x01\x02\xff"), str)


@pytest.mark.parametrize("value", [
    _join("192", "168", "001", "023"), _join("081", "002", "069", "160"),
    _join("010", "000", "000", "001")])
def test_ipv4_with_leading_zeros_is_checked(value):
    assert kinds(f"gateway {value}") == ["IPv4"]


def test_ipv4_with_leading_zeros_in_allowed_range_passes():
    assert kinds("gateway 192.000.002.001") == []
    assert kinds("not an address 1.2.3.400") == []


@pytest.mark.parametrize("value", [
    PLANTED_MAC.replace(":", ""), PLANTED_MAC.replace(":", "").upper()])
def test_guard_catches_bare_mac(value):
    assert kinds(f"    NetworkAddress    REG_SZ    {value}") == ["MAC"]
    assert kinds(f"mac={value}") == ["MAC"]


@pytest.mark.parametrize("text", [
    "NetworkAddress REG_SZ 00005E005301",                 # documentation range
    "ValidLifetimeSeconds: 922337203685",                 # all decimal
    "GUID : 00000000-0000-0000-0000-00000000001a",        # GUID part
    "word deadbeefcafe",                                  # letters only
    "sha " + "0123456789abcdef" * 4,                      # 64-digit hash
    "commit " + "0123456789abcdef0123456789abcdef01234567",  # 40-digit git hash
    "short commit 1a2b3c4",                               # 7-digit git hash
    "hex 0x1a2b3c4d5e6f",                                 # 0x prefix
])
def test_bare_mac_detection_avoids_numbers_hashes_and_guids(text):
    assert kinds(text) == []


@pytest.mark.parametrize("line", [
    "ROUTER_PASSWORD=" + "S3cret" + "pass",
    "export WIFI_KEY=" + "Corr3ct" + "Horse",
    "API_TOKEN: " + "abc123" + "xyz456",
    "routerPassword=" + "hunter" + "22",
    "SECRET = " + "S3cret!" + "pass",
    "wpa_psk=" + "MyHome" + "Wifi2024",
    "db_passwd: " + "pa55" + "word",
])
def test_guard_catches_unquoted_env_style_secrets(line):
    assert kinds(line) == ["secret"]


@pytest.mark.parametrize("line", [
    "password = getpass()",
    "    password = getpass.getpass('Router password: ')",
    "best = min(load, key=load.get)",
    "    key=lambda m: m.group(1),",
    "key=lambda r: r.id",
    "ROUTER_PASSWORD=",
    "ROUTER_PASSWORD=<your password>",
    "WIFI_KEY=${WIFI_KEY}",
    "API_TOKEN: ***",
    "token: None",
    "password: str",
    "password = new_password",
    "self.token = token",
    "monkey=banana42",
    "keyboard: layout1",
    "    password=args.password,",
])
def test_unquoted_secret_rule_ignores_code_and_placeholders(line):
    assert kinds(line) == []
