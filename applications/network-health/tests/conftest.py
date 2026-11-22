"""Shared test helpers: a fake Runner fed with recorded, made-up output.

No test starts a real command or opens a network connection. All addresses
in the fixtures are from the documentation ranges (192.0.2.0/24,
198.51.100.0/24, 203.0.113.0/24, 2001:db8::/32), the MAC addresses are from
the RFC 7042 documentation range 00:00:5e:00:53:xx, and the names are made up.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from network_health.collect import collect
from network_health.models import BandwidthResult, DnsTiming
from network_health.platforms.windows import WindowsPlatform
from network_health.runner import CommandResult

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "windows"


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def ok(name: str, returncode: int = 0) -> CommandResult:
    """A CommandResult whose stdout is a fixture file."""
    return CommandResult(args=(), returncode=returncode, stdout=fixture_text(name))


def out(text: str, returncode: int = 0, stderr: str = "", error=None) -> CommandResult:
    """A CommandResult with the given text."""
    return CommandResult(args=(), returncode=returncode, stdout=text,
                         stderr=stderr, error=error)


class FakeRunner:
    """Answers commands from rules: the first rule whose text is part of the
    command line wins. Unknown commands fail the test."""

    def __init__(self, rules):
        self.rules = list(rules)
        self.calls: list[tuple[str, ...]] = []

    def run(self, args, *, timeout=30.0, encoding=None):
        args = tuple(args)
        self.calls.append(args)
        line = " ".join(args)
        for needle, answer in self.rules:
            if needle in line:
                result = answer(args) if callable(answer) else answer
                return CommandResult(args, result.returncode, result.stdout,
                                     result.stderr, result.error, result.elapsed_s)
        raise AssertionError(f"unexpected command in a test: {line}")


HOME_RULES = [
    ("ping -n 20 -w 1000 192.0.2.1", ok("ping_gateway.txt")),
    ("ping -n 20 -w 1000 1.1.1.1", ok("ping_cloudflare.txt")),
    ("ping -n 20 -w 1000 8.8.8.8", ok("ping_google.txt")),
    ("-f -l", ok("ping_df_ok.txt")),
    ("netsh wlan show interfaces", ok("wlan_interfaces_connected.txt")),
    ("netsh wlan show networks", ok("wlan_networks.txt")),
    ("Get-NetIPConfiguration", ok("ps_ipconfig.json")),
    ("Get-NetConnectionProfile", ok("ps_profiles.json")),
    ("Get-NetFirewallProfile", ok("ps_firewall.json")),
    ("Get-NetTCPConnection", ok("ps_listening.json")),
    ("reg query", ok("reg_internet_settings.txt")),
    ("netsh winhttp show proxy", ok("winhttp_direct.txt")),
    ("arp -a", ok("arp.txt")),
]


def home_platform(*overrides, environ=None) -> tuple[WindowsPlatform, FakeRunner]:
    """The made-up home network; overrides (needle, result) come first."""
    runner = FakeRunner(list(overrides) + HOME_RULES)
    return WindowsPlatform(runner, environ=environ or {}), runner


def fake_dns(server, names):
    return DnsTiming(server=server, times_ms=[12.0, 15.0, 11.0])


def fake_bandwidth():
    return BandwidthResult(
        server="Cloudflare speed test (speed.cloudflare.com)",
        download_mbps=180.0, upload_mbps=40.0,
        download_bytes=25_000_000, upload_bytes=10_000_000,
        loaded_latency_ms=[20.0, 22.0, 25.0],
    )


def home_facts(*overrides, skip_bandwidth=False, bandwidth=fake_bandwidth,
               dns_probe=fake_dns, environ=None):
    platform, runner = home_platform(*overrides, environ=environ)
    facts = collect(platform, skip_bandwidth=skip_bandwidth, dns_probe=dns_probe,
                    bandwidth=bandwidth)
    return facts, runner


@pytest.fixture
def home():
    return home_facts()


# ---------------------------------------------------------------- real sockets are off

@pytest.fixture(autouse=True)
def no_real_sockets(monkeypatch):
    """A test that tries to open a real connection or send a datagram fails."""
    import socket

    def refuse(*_args, **_kwargs):
        raise AssertionError("a test tried to use a real socket")

    for name in ("connect", "connect_ex", "sendto", "send", "sendall"):
        monkeypatch.setattr(socket.socket, name, refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


# ---------------------------------------------------------------- active scan helpers
#
# The scan only accepts a private RFC 1918 range, but the repository may not
# contain such addresses (privacy guard). The tests therefore build them at run
# time from the base address 10.0.0.0, which the guard allows: private_ip(10) is
# the tenth address of that range. They are made-up and used only in memory.
#
# MAC addresses with a real vendor prefix are built the same way, from the
# 6-digit prefix and a made-up suffix in the RFC 7042 style (005301 ...).

import ipaddress  # noqa: E402
import threading  # noqa: E402

from network_health.devices import Device  # noqa: E402
from network_health.models import Neighbour  # noqa: E402
from network_health.netio import NetIO, NetIOError, ProbeResult  # noqa: E402
from network_health.scan_target import MDNS_GROUP, SSDP_GROUP, ScanTarget  # noqa: E402

PRIVATE_BASE = "10.0.0.0"


def private_ip(offset: int, base: str = PRIVATE_BASE) -> str:
    return str(ipaddress.ip_address(base) + offset)


def make_target(prefix: int = 24, own: int = 10, base: str = PRIVATE_BASE) -> ScanTarget:
    own_ip = private_ip(own, base)
    network = ipaddress.ip_interface(f"{own_ip}/{prefix}").network
    return ScanTarget(network, own_ip, "Wi-Fi", (own_ip,))


def mac_with_prefix(prefix: str, last: int = 1) -> str:
    """A MAC address with the given 6-hex-digit vendor prefix and a made-up
    suffix, built at run time (colon separated, lower case)."""
    digits = prefix.lower() + f"0053{last:02x}"
    return ":".join(digits[i:i + 2] for i in range(0, 12, 2))


def private_mac(last: int = 1) -> str:
    """A locally administered ("private") MAC address, as phones use; built at
    run time, with a made-up suffix."""
    return mac_with_prefix("DAA119", last)


def doc_mac(last: int) -> str:
    """A MAC address of the RFC 7042 documentation range."""
    return f"00:00:5e:00:53:{last:02x}"


def neighbour(offset: int, mac: str, own: int = 10) -> Neighbour:
    return Neighbour(interface_ip=private_ip(own), ip=private_ip(offset), mac=mac)


class FakeClock:
    """Time that only moves when a test says so (advance) or something sleeps."""

    def __init__(self):
        self.now = 1000.0
        self._lock = threading.Lock()

    def monotonic(self) -> float:
        with self._lock:
            return self.now

    def sleep_until(self, moment: float) -> None:
        with self._lock:
            self.now = max(self.now, moment)

    def advance(self, seconds: float) -> None:
        with self._lock:
            self.now += seconds


class StubPlatform:
    """The two things the scanner asks the platform: ping_host and neighbours."""

    name = "Stub"

    def __init__(self, alive=(), neighbours=(), clock=None, ping_cost=0.0, error=None):
        self.alive = set(alive)
        self._neighbours = list(neighbours)
        self.clock = clock
        self.ping_cost = ping_cost
        self.error = error
        self.pings: list[str] = []
        self.arp_calls = 0
        self._lock = threading.Lock()

    def ping_host(self, target, timeout_ms):
        with self._lock:
            self.pings.append(target)
        if self.clock and self.ping_cost:
            self.clock.advance(self.ping_cost)
        if self.error:
            raise self.error
        return target in self.alive

    def neighbours(self):
        self.arp_calls += 1
        return list(self._neighbours)


class FakeNetIO(NetIO):
    """Answers from made-up data and records every call. ports maps an address
    to {port: ProbeResult or True}; mdns and ssdp are lists of (sender, packet)."""

    def __init__(self, ports=None, mdns=(), ssdp=(), clock=None, cost=0.0, mdns_error=None,
                 multicast_cost=0.0):
        self.ports = ports or {}
        self.mdns = list(mdns)
        self.ssdp = list(ssdp)
        self.clock = clock
        self.cost = cost
        self.mdns_error = mdns_error
        self.multicast_cost = multicast_cost
        self.calls: list[tuple] = []
        self._lock = threading.Lock()

    def _answer(self, kind, ip, port):
        with self._lock:
            self.calls.append((kind, ip, port))
        if self.clock and self.cost:
            self.clock.advance(self.cost)
        answer = self.ports.get(ip, {}).get(port)
        if answer is None:
            return ProbeResult(False)
        return ProbeResult(True) if answer is True else answer

    def connect(self, ip, port, timeout):
        return self._answer("connect", ip, port)

    def banner(self, ip, port, timeout, wait, max_bytes):
        return self._answer("banner", ip, port)

    def http_head(self, ip, port, timeout, wait, max_bytes):
        return self._answer("http", ip, port)

    def tls_handshake(self, ip, port, timeout):
        return self._answer("tls", ip, port)

    def multicast_query(self, group, port, payload, *, local_ip, sends, wait, max_packets):
        with self._lock:
            self.calls.append(("multicast", group, port))
        if self.clock and self.multicast_cost:
            self.clock.advance(self.multicast_cost)
        if (group, port) == MDNS_GROUP:
            if self.mdns_error:
                raise NetIOError(self.mdns_error)
            return list(self.mdns)
        if (group, port) == SSDP_GROUP:
            return list(self.ssdp)
        raise AssertionError(f"unexpected group {group}:{port}")


def make_device(offset=20, **fields) -> Device:
    device = Device(private_ip(offset), **fields)
    return device
