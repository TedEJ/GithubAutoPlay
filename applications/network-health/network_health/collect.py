"""Collect the facts the checks need, in passive mode.

Network traffic in this mode: ping to the default gateway and to the public
ping targets, DNS queries to the configured resolvers, ping with
do-not-fragment to the MTU target, and (unless --skip-bandwidth) the
bandwidth test against the speed-test server. Nothing else is sent to other
devices on the local network: the Wi-Fi list, the ARP table and the
configuration are read from what the computer already has.
"""

from __future__ import annotations

import ipaddress
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable

from . import bandwidth as bandwidth_module
from . import dnsprobe, known_hosts, thresholds
from .models import AdapterConfig, MtuResult, Unavailable


@dataclass
class Facts:
    platform: str = ""
    adapters: Any = None          # list[AdapterConfig] | Unavailable
    primary: AdapterConfig | None = None
    gateway: str | None = None
    ping_gateway: Any = None      # PingStats | Unavailable
    ping_public: dict = field(default_factory=dict)   # target -> PingStats | Unavailable
    dns: Any = None               # dict[str, DnsTiming] | Unavailable
    mtu: Any = None               # MtuResult | Unavailable
    bandwidth: Any = None         # BandwidthResult | Unavailable
    wifi: Any = None              # WifiStatus | Unavailable
    wifi_networks: Any = None     # list[WifiNetwork] | Unavailable
    profiles: Any = None
    firewall: Any = None
    proxy: Any = None
    listening: Any = None
    neighbours: Any = None
    contacted: list[str] = field(default_factory=list)


def attempt(fn: Callable, *args, **kwargs):
    """Call fn; return its value, or an Unavailable instead of raising."""
    try:
        return fn(*args, **kwargs)
    except Unavailable as exc:
        return exc
    except Exception as exc:  # never crash on one fact
        return Unavailable("error", f"Unexpected error: {type(exc).__name__}: {exc}")


def choose_primary(adapters: list[AdapterConfig]) -> AdapterConfig | None:
    """The adapter with an IPv4 default gateway and the lowest metric."""
    with_gateway = [a for a in adapters if a.ipv4_gateways]
    if not with_gateway:
        return adapters[0] if adapters else None
    return min(with_gateway, key=lambda a: (a.metric if a.metric is not None else 10**6))


def usable_dns_servers(adapter: AdapterConfig | None) -> list[str]:
    if adapter is None:
        return []
    servers = []
    for server in adapter.dns_servers:
        try:
            ip = ipaddress.ip_address(server.split("%")[0])
        except ValueError:
            continue
        if ip in known_hosts.WINDOWS_PLACEHOLDER_DNS or server in servers:
            continue
        servers.append(server)
    return servers


def measure_mtu(platform, target: str) -> MtuResult:
    """Largest packet that reaches target without fragmentation."""
    low = thresholds.MTU_PROBE_MIN_PAYLOAD
    high = thresholds.MTU_PROBE_MAX_PAYLOAD
    overhead = thresholds.ICMP_IPV4_OVERHEAD
    if platform.ping_dont_fragment(target, high):
        return MtuResult(target, high + overhead)
    if not platform.ping_dont_fragment(target, low):
        raise Unavailable("error", f"{target} did not answer ping with "
                                   "do-not-fragment set, so the MTU is unknown.")
    # low works, high does not: binary search in between.
    while high - low > 1:
        middle = (low + high) // 2
        if platform.ping_dont_fragment(target, middle):
            low = middle
        else:
            high = middle
    return MtuResult(target, low + overhead)


def _dns_all(servers: list[str], probe: Callable) -> dict:
    return {s: attempt(probe, s, known_hosts.DNS_TEST_NAMES) for s in servers}


def collect(
    platform,
    *,
    skip_bandwidth: bool = False,
    dns_probe: Callable = dnsprobe.measure_resolver,
    bandwidth: Callable | None = None,
    progress: Callable[[str], None] | None = None,
) -> Facts:
    say = progress or (lambda _message: None)
    facts = Facts(platform=platform.name)

    say("Reading the network configuration ...")
    facts.adapters = attempt(platform.ip_configuration)
    if not isinstance(facts.adapters, Unavailable):
        facts.primary = choose_primary(facts.adapters)
        if facts.primary and facts.primary.ipv4_gateways:
            facts.gateway = facts.primary.ipv4_gateways[0]

    say(f"Measuring latency with {thresholds.PING_COUNT} pings per target "
        f"(about {thresholds.PING_COUNT} seconds) ...")
    targets = [t for t, _ in known_hosts.PING_TARGETS]
    with ThreadPoolExecutor(max_workers=len(targets) + 1) as pool:
        gateway_future = (pool.submit(attempt, platform.ping, facts.gateway,
                                      thresholds.PING_COUNT)
                          if facts.gateway else None)
        public_futures = {t: pool.submit(attempt, platform.ping, t, thresholds.PING_COUNT)
                          for t in targets}
        if gateway_future is not None:
            facts.ping_gateway = gateway_future.result()
            facts.contacted.append(f"{facts.gateway} (default gateway): ping")
        else:
            facts.ping_gateway = Unavailable(
                "not-applicable", "No default gateway was found, so the gateway "
                "could not be pinged. Is the computer connected to a network?")
        for target, future in public_futures.items():
            facts.ping_public[target] = future.result()
            facts.contacted.append(f"{target} ({dict(known_hosts.PING_TARGETS)[target]}): ping")

    servers = usable_dns_servers(facts.primary)
    if isinstance(facts.adapters, Unavailable):
        facts.dns = facts.adapters
    elif not servers:
        facts.dns = {}
    else:
        say("Timing the DNS servers ...")
        facts.dns = _dns_all(servers, dns_probe)
        facts.contacted.append("configured DNS servers (" + ", ".join(servers)
                               + "): DNS queries")

    say("Measuring the path MTU ...")
    facts.mtu = attempt(measure_mtu, platform, known_hosts.MTU_TARGET)
    facts.contacted.append(f"{known_hosts.MTU_TARGET}: ping with do-not-fragment")

    if skip_bandwidth:
        facts.bandwidth = Unavailable("turned-off", "Turned off with --skip-bandwidth.")
    else:
        say("Measuring bandwidth against " + known_hosts.SPEED_TEST_NAME
            + " (up to about 30 seconds) ...")
        runner = bandwidth or (lambda: bandwidth_module.measure_bandwidth(
            sampler_factory=lambda: bandwidth_module.LoadSampler(
                platform, known_hosts.BUFFERBLOAT_TARGET)))
        facts.bandwidth = attempt(runner)
        facts.contacted.append(known_hosts.SPEED_TEST_NAME + ": bandwidth test")

    say("Reading Wi-Fi, firewall, proxy, ports and the ARP table ...")
    facts.wifi = attempt(platform.wifi_status)
    if isinstance(facts.wifi, Unavailable):
        facts.wifi_networks = facts.wifi
    elif facts.wifi.connected:
        facts.wifi_networks = attempt(platform.wifi_networks)
    else:
        facts.wifi_networks = []
    facts.profiles = attempt(platform.network_profiles)
    facts.firewall = attempt(platform.firewall_profiles)
    facts.proxy = attempt(platform.proxy_settings)
    facts.listening = attempt(platform.listening_ports)
    facts.neighbours = attempt(platform.neighbours)
    return facts
