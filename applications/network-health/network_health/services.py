"""The ports that are checked, and how an answer is read.

The list is short and documented in network-health-design.md (section 9). It
holds the ports that matter on a home network: remote access, file sharing,
web interfaces, cameras, and the router management port.

Nothing is sent to a device beyond what is needed to read what the service
volunteers (see netio.py). Everything read is cleaned with safe_text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import thresholds
from .devices import ServiceInfo
from .safe_text import clean_text

BANNER, HTTP, TLS, CONNECT = "banner", "http", "tls", "connect"


@dataclass(frozen=True)
class PortSpec:
    port: int
    name: str
    method: str      # how the port is examined once it accepts a connection
    why: str


# Ports and why each is checked. Order: the order of the checks of one device.
PORT_PLAN = (
    PortSpec(21, "ftp", BANNER, "file transfer without encryption"),
    PortSpec(22, "ssh", BANNER, "remote login (encrypted)"),
    PortSpec(23, "telnet", BANNER, "remote login without encryption"),
    PortSpec(80, "http", HTTP, "web interface without encryption"),
    PortSpec(443, "https", TLS, "web interface with encryption"),
    PortSpec(445, "smb", CONNECT, "Windows file sharing"),
    PortSpec(554, "rtsp", CONNECT, "camera video stream"),
    PortSpec(1900, "upnp", CONNECT, "UPnP (usually UDP; some devices also listen on TCP)"),
    PortSpec(3389, "rdp", CONNECT, "Windows remote desktop"),
    PortSpec(5000, "http-alt", HTTP, "web interface of NAS devices, UPnP descriptions"),
    PortSpec(5900, "vnc", BANNER, "remote desktop (VNC)"),
    PortSpec(7547, "tr-069", CONNECT, "the provider's router management (TR-069)"),
    PortSpec(8080, "http-alt", HTTP, "web interface on an alternative port"),
    PortSpec(8443, "https-alt", TLS, "web interface with encryption on an alternative port"),
)
PORTS = tuple(spec.port for spec in PORT_PLAN)
SPEC_BY_PORT = {spec.port: spec for spec in PORT_PLAN}

# Port groups the hazard rules use.
TELNET, FTP, SMB, RDP, VNC, TR069 = 23, 21, 445, 3389, 5900, 7547
HTTP_PORTS = (80, 5000, 8080)
HTTPS_PORTS = (443, 8443)

_STATUS = re.compile(r"^HTTP/1\.[01]\s+(\d{3})")


def strip_telnet_negotiation(data: bytes) -> bytes:
    """Remove telnet option negotiation (IAC + 2 bytes) from a banner."""
    out = bytearray()
    i = 0
    while i < len(data):
        if data[i] == 0xFF:  # IAC, a command byte and an option byte
            i += 3
            continue
        out.append(data[i])
        i += 1
    return bytes(out)


def parse_banner(data: bytes, port: int) -> str:
    """The first non-empty line a service volunteered, cleaned."""
    if port == TELNET:
        data = strip_telnet_negotiation(data)
    text = data.decode("utf-8", errors="replace")
    for line in text.replace("\r", "\n").split("\n"):
        cleaned = clean_text(line, thresholds.MAX_BANNER_CHARS)
        if cleaned:
            return cleaned
    return ""


def parse_http(data: bytes) -> dict | None:
    """Status, Server, Location and WWW-Authenticate of an HTTP answer, or
    None when the data is not HTTP."""
    text = data[: thresholds.HTTP_MAX_BYTES].decode("latin-1")
    lines = text.replace("\r\n", "\n").split("\n")
    match = _STATUS.match(lines[0].strip()) if lines else None
    if not match:
        return None
    info = {"status": int(match.group(1)), "server": "", "location": "", "auth": False}
    for line in lines[1:]:
        if not line.strip():
            break
        key, sep, value = line.partition(":")
        if not sep:
            continue
        key = key.strip().lower()
        if key == "server" and not info["server"]:
            info["server"] = clean_text(value, thresholds.MAX_BANNER_CHARS)
        elif key == "location" and not info["location"]:
            info["location"] = clean_text(value, thresholds.MAX_BANNER_CHARS)
        elif key == "www-authenticate":
            info["auth"] = True
    return info


def service_from_probe(spec: PortSpec, probe) -> ServiceInfo:
    """Turn what a probe returned into a ServiceInfo."""
    info = ServiceInfo(spec.port, spec.name)
    if spec.method == BANNER:
        info.banner = parse_banner(probe.data, spec.port)
    elif spec.method == HTTP:
        parsed = parse_http(probe.data)
        if parsed:
            info.http_status = parsed["status"]
            info.http_server = parsed["server"]
            info.http_location = parsed["location"]
            info.http_auth = parsed["auth"]
    elif spec.method == TLS:
        info.tls_version = clean_text(probe.tls_version, 16)
    return info


def redirects_to_https(info: ServiceInfo) -> bool:
    return (info.http_status is not None and 300 <= info.http_status < 400
            and info.http_location.lower().startswith("https://"))
