"""The external servers the tool knows about.

This is the only file with public addresses. They are the ones named in
network-health-design.md ("External servers"), and the privacy guard
(scripts/tests/test_network_health_privacy.py) allows exactly these. Change
all three places together.
"""

from __future__ import annotations

import ipaddress

# Public ping targets: anycast addresses run for public use, close to almost
# every network, and they answer ping.
PING_TARGETS = (
    ("1.1.1.1", "Cloudflare"),
    ("8.8.8.8", "Google"),
)
# Latency under load (bufferbloat) and path MTU are measured against the
# first target.
BUFFERBLOAT_TARGET = PING_TARGETS[0][0]
MTU_TARGET = PING_TARGETS[0][0]

# Well-known public DNS resolvers, used to name the DNS servers in use.
PUBLIC_RESOLVERS = {
    "1.1.1.1": "Cloudflare",
    "1.0.0.1": "Cloudflare",
    "8.8.8.8": "Google Public DNS",
    "8.8.4.4": "Google Public DNS",
    "9.9.9.9": "Quad9",
    "149.112.112.112": "Quad9",
    "208.67.222.222": "OpenDNS (Cisco)",
    "208.67.220.220": "OpenDNS (Cisco)",
    "2606:4700:4700::1111": "Cloudflare",
    "2606:4700:4700::1001": "Cloudflare",
    "2001:4860:4860::8888": "Google Public DNS",
    "2001:4860:4860::8844": "Google Public DNS",
    "2620:fe::fe": "Quad9",
    "2620:fe::9": "Quad9",
    "2620:119:35::35": "OpenDNS (Cisco)",
    "2620:119:53::53": "OpenDNS (Cisco)",
}

# Windows lists these deprecated site-local addresses as IPv6 DNS servers on
# an adapter that has no IPv6 DNS server. They are placeholders, not servers.
WINDOWS_PLACEHOLDER_DNS = frozenset(
    ipaddress.ip_address(a)
    for a in ("fec0:0:0:ffff::1", "fec0:0:0:ffff::2", "fec0:0:0:ffff::3")
)

# Private address ranges (RFC 1918, shared address space RFC 6598, unique
# local IPv6 RFC 4193). Python's is_private also counts the documentation
# ranges, which the test fixtures use as a home network, so the ranges are
# listed here explicitly.
PRIVATE_NETWORKS = tuple(
    ipaddress.ip_network(n)
    for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
              "100.64.0.0/10", "fc00::/7")
)

# Names looked up when the DNS servers are timed.
DNS_TEST_NAMES = ("example.com", "www.iana.org", "www.wikipedia.org")

# The bandwidth test: Cloudflare's public speed-test endpoints. HTTPS, no
# account, no install, usable with urllib.
SPEED_TEST_NAME = "Cloudflare speed test (speed.cloudflare.com)"
SPEED_TEST_DOWNLOAD_URL = "https://speed.cloudflare.com/__down?bytes={bytes}"
SPEED_TEST_UPLOAD_URL = "https://speed.cloudflare.com/__up"


def resolver_name(address: str) -> str | None:
    try:
        wanted = ipaddress.ip_address(address.split("%")[0])
    except ValueError:
        return None
    for known, name in PUBLIC_RESOLVERS.items():
        if ipaddress.ip_address(known) == wanted:
            return name
    return None


def is_private_range(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address.split("%")[0])
    except ValueError:
        return False
    return any(ip in net for net in PRIVATE_NETWORKS if net.version == ip.version)
