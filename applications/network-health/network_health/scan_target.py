"""What --active may scan: the safety rules in one place.

The target is never typed by the user. It is computed from the IPv4 address
and prefix of this computer's main adapter, and it is only accepted when it

* is inside 10.0.0.0/8, 172.16.0.0/12 or 192.168.0.0/16 (RFC 1918), so never
  a public range, the shared range 100.64.0.0/10 (carrier-grade NAT),
  loopback, link-local or multicast;
* contains an address of this computer (it is directly attached);
* is at most a /22 (1022 addresses), and has at least two usable addresses.

ScanGuard repeats the check for every single address and multicast group
before something is sent, so a bug elsewhere cannot make the tool send to an
address outside the target. IPv6 is never swept (a /64 has too many
addresses).
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass

from . import thresholds
from .collect import choose_primary
from .models import AdapterConfig, Unavailable

# The only private ranges that may be scanned.
ALLOWED_RANGES = tuple(ipaddress.ip_network(n) for n in
                       ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
CGNAT = ipaddress.ip_network("100.64.0.0/10")

# The only multicast destinations the tool ever sends to: mDNS and SSDP, on
# the local link.
MDNS_GROUP = ("224.0.0.251", 5353)
SSDP_GROUP = ("239.255.255.250", 1900)
ALLOWED_MULTICAST = frozenset({MDNS_GROUP, SSDP_GROUP})


class ScanRefused(Exception):
    """The scan is not allowed (the message says why and what to do)."""


@dataclass(frozen=True)
class ScanTarget:
    network: ipaddress.IPv4Network
    own_address: str
    interface: str
    own_addresses: tuple[str, ...] = ()

    @property
    def host_count(self) -> int:
        return max(self.network.num_addresses - 2, 0)

    def hosts(self) -> list[ipaddress.IPv4Address]:
        """The addresses to sweep: every usable address except this computer's."""
        own = set(self.own_addresses) | {self.own_address}
        return [h for h in self.network.hosts() if str(h) not in own]


def check_network_allowed(network: ipaddress.IPv4Network) -> None:
    """Raise ScanRefused unless network may be scanned (see the module text)."""
    if not isinstance(network, ipaddress.IPv4Network):
        raise ScanRefused("Refusing to scan: only IPv4 subnets are swept. IPv6 "
                          "networks are too large to sweep.")
    if network.subnet_of(CGNAT):
        raise ScanRefused(
            f"Refusing to scan {network}: 100.64.0.0/10 is shared address space "
            "that internet providers use (carrier-grade NAT). It is not your own "
            "network. Connect to your home router's network instead.")
    if not any(network.subnet_of(allowed) for allowed in ALLOWED_RANGES):
        reason = "it is not a private range (10.0.0.0/8, 172.16.0.0/12 or 192.168.0.0/16)"
        if network.is_loopback:
            reason = "it is the loopback range of this computer"
        elif network.is_link_local:
            reason = ("it is a self-assigned (link-local) range, which means no "
                      "DHCP server answered")
        elif network.is_multicast:
            reason = "it is a multicast range"
        raise ScanRefused(
            f"Refusing to scan {network}: {reason}. The tool only scans a private "
            "range that this computer is directly connected to, and never the "
            "internet.")
    if network.prefixlen > 30:
        raise ScanRefused(f"Refusing to scan {network}: it has no other usable "
                          "address than this computer's.")
    if network.prefixlen < thresholds.SCAN_MIN_PREFIX:
        raise ScanRefused(
            f"Refusing to scan {network}: it has {network.num_addresses - 2} "
            f"usable addresses and the tool sweeps at most "
            f"{thresholds.SCAN_MAX_HOSTS} (a /{thresholds.SCAN_MIN_PREFIX}). A home "
            "network is usually a /24 (254 addresses). Use a smaller subnet on the "
            "router, or connect to a smaller network. The tool has no option to "
            "choose another range.")


def choose_scan_target(adapters, primary: AdapterConfig | None = None) -> ScanTarget:
    """The subnet of this computer's main adapter, or ScanRefused.

    adapters is the list from the platform layer (or an Unavailable). Only
    the main adapter is used (the one with an IPv4 default gateway and the
    lowest metric); other adapters, such as virtual switches, are not scanned.
    """
    if isinstance(adapters, Unavailable) or adapters is None:
        reason = adapters.reason if isinstance(adapters, Unavailable) else "not read"
        raise ScanRefused("Cannot scan: this computer's network configuration "
                          f"could not be read ({reason}).")
    primary = primary or choose_primary(adapters)
    if primary is None or not primary.ipv4:
        raise ScanRefused("Cannot scan: the main network adapter has no IPv4 "
                          "address. Is the computer connected to a network?")
    first_error: ScanRefused | None = None
    for entry in primary.ipv4:
        try:
            interface = ipaddress.ip_interface(f"{entry.address}/{entry.prefix_length}")
        except ValueError:
            continue
        if not isinstance(interface, ipaddress.IPv4Interface):
            continue
        try:
            check_network_allowed(interface.network)
        except ScanRefused as exc:
            first_error = first_error or exc
            continue
        own = tuple(e.address for e in primary.ipv4
                    if _in_network(e.address, interface.network))
        return ScanTarget(interface.network, str(interface.ip), primary.alias, own)
    raise first_error or ScanRefused("Cannot scan: the main network adapter has no "
                                     "usable IPv4 address.")


def _in_network(address: str, network: ipaddress.IPv4Network) -> bool:
    try:
        return ipaddress.ip_address(address) in network
    except ValueError:
        return False


class ScanGuard:
    """Checks every destination before anything is sent to it."""

    def __init__(self, target: ScanTarget):
        check_network_allowed(target.network)
        self.target = target

    def check_host(self, address: str) -> ipaddress.IPv4Address:
        """The address as an object, or ScanRefused when it is not a usable
        address of the target subnet."""
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            raise ScanRefused(f"Refusing to send to {address!r}: not an IP address.")
        net = self.target.network
        if (not isinstance(ip, ipaddress.IPv4Address) or ip not in net
                or ip in (net.network_address, net.broadcast_address)):
            raise ScanRefused(f"Refusing to send to {ip}: it is not a usable address "
                              f"of the scanned subnet {net}.")
        return ip

    def check_own(self, address: str) -> None:
        """The address a multicast query leaves from must be this computer's
        own address in the scanned subnet."""
        own = set(self.target.own_addresses) | {self.target.own_address}
        if address not in own:
            raise ScanRefused(f"Refusing to send from {address}: it is not this "
                              "computer's address in the scanned subnet.")

    @staticmethod
    def check_multicast(group: str, port: int) -> None:
        if (group, port) not in ALLOWED_MULTICAST:
            raise ScanRefused(f"Refusing to send to {group}:{port}: only the mDNS "
                              "and SSDP multicast groups are used.")

    def in_target(self, address: str) -> bool:
        try:
            self.check_host(address)
        except ScanRefused:
            return False
        return True
