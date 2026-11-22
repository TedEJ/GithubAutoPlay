import ipaddress

from conftest import fake_bandwidth, fake_dns, home_facts, home_platform, ok, out
from network_health import known_hosts
from network_health.collect import (
    attempt,
    choose_primary,
    collect,
    measure_mtu,
    usable_dns_servers,
)
from network_health.models import AdapterConfig, MtuResult, Unavailable


def test_choose_primary_prefers_gateway_and_low_metric():
    a = AdapterConfig("A", metric=50, ipv4_gateways=["192.0.2.1"])
    b = AdapterConfig("B", metric=10, ipv4_gateways=["198.51.100.1"])
    c = AdapterConfig("C", metric=1)
    assert choose_primary([a, b, c]).alias == "B"
    assert choose_primary([c]).alias == "C"
    assert choose_primary([]) is None


def test_windows_placeholder_dns_servers_are_left_out():
    adapter = AdapterConfig("Wi-Fi", dns_servers=[
        "192.0.2.1", "fec0:0:0:ffff::1", "fec0:0:0:ffff::2", "192.0.2.1", "not-an-ip"])
    assert usable_dns_servers(adapter) == ["192.0.2.1"]
    assert usable_dns_servers(None) == []


class DfPlatform:
    """Answers ping-with-DF like a path with the given MTU."""

    def __init__(self, mtu):
        self.mtu = mtu
        self.payloads = []

    def ping_dont_fragment(self, target, payload):
        self.payloads.append(payload)
        return self.mtu is not None and payload + 28 <= self.mtu


def test_mtu_full_needs_one_probe():
    platform = DfPlatform(1500)
    assert measure_mtu(platform, "1.1.1.1") == MtuResult("1.1.1.1", 1500)
    assert platform.payloads == [1472]


def test_mtu_binary_search_finds_pppoe_and_small_values():
    assert measure_mtu(DfPlatform(1492), "1.1.1.1").mtu == 1492
    assert measure_mtu(DfPlatform(1300), "1.1.1.1").mtu == 1300


def test_mtu_without_any_reply_is_unavailable():
    result = attempt(measure_mtu, DfPlatform(None), "1.1.1.1")
    assert isinstance(result, Unavailable)


def test_attempt_turns_unexpected_errors_into_unavailable():
    def boom():
        raise KeyError("x")
    result = attempt(boom)
    assert isinstance(result, Unavailable)
    assert "KeyError" in result.reason


def test_collect_home_network(home):
    facts, _ = home
    assert facts.platform == "Windows"
    assert facts.primary.alias == "Wi-Fi"
    assert facts.gateway == "192.0.2.1"
    assert facts.ping_gateway.received == 20
    assert set(facts.ping_public) == {"1.1.1.1", "8.8.8.8"}
    assert list(facts.dns) == ["192.0.2.1"]
    assert facts.mtu.mtu == 1500
    assert facts.bandwidth.download_mbps == 180
    assert facts.wifi.connected
    assert len(facts.wifi_networks) == 5
    assert len(facts.neighbours) == 4


def test_passive_mode_only_contacts_gateway_public_targets_and_resolvers():
    """Acceptance: no packets to other local devices beyond ping to the
    gateway and DNS queries to the configured resolvers."""
    dns_servers = []

    def recording_dns(server, names):
        dns_servers.append(server)
        return fake_dns(server, names)

    facts, runner = home_facts(dns_probe=recording_dns)
    allowed_ping = {facts.gateway} | {t for t, _ in known_hosts.PING_TARGETS}
    for args in runner.calls:
        if args[0] == "ping":
            assert args[-1] in allowed_ping, args
        else:
            # Everything else only reads local state.
            assert args[0] in ("netsh", "powershell", "reg", "arp"), args
            assert "connect" not in " ".join(args[:3]).lower()
    assert dns_servers == usable_dns_servers(facts.primary)
    local = [t for t in allowed_ping
             if ipaddress.ip_address(t) in ipaddress.ip_network("192.0.2.0/24")]
    assert local == ["192.0.2.1"]


def test_skip_bandwidth_does_not_call_the_bandwidth_test():
    called = []
    facts, _ = home_facts(skip_bandwidth=True, bandwidth=lambda: called.append(1))
    assert called == []
    assert isinstance(facts.bandwidth, Unavailable)
    assert facts.bandwidth.kind == "turned-off"
    assert not any("bandwidth" in c for c in facts.contacted)


def test_contacted_list_names_the_speed_test_server(home):
    facts, _ = home
    assert any("speed.cloudflare.com" in c for c in facts.contacted)


def test_no_gateway_skips_gateway_ping_and_wired_skips_wifi_scan():
    platform, runner = home_platform(
        ("Get-NetIPConfiguration", ok("ps_ipconfig_single.json")),
        ("netsh wlan show interfaces", ok("wlan_interfaces_disconnected.txt")),
        ("ping -n 20 -w 1000 203.0.113.1", ok("ping_all_lost.txt")),
    )
    facts = collect(platform, dns_probe=fake_dns, bandwidth=fake_bandwidth)
    assert facts.gateway == "203.0.113.1"
    assert facts.wifi_networks == []
    assert not any("networks" in " ".join(c) for c in runner.calls)


def test_missing_powershell_does_not_crash():
    platform, _ = home_platform(("powershell", out("", error="not-found")))
    facts = collect(platform, dns_probe=fake_dns, bandwidth=fake_bandwidth)
    assert isinstance(facts.adapters, Unavailable)
    assert facts.adapters.kind == "missing-tool"
    assert facts.gateway is None
    assert isinstance(facts.ping_gateway, Unavailable)
    assert isinstance(facts.dns, Unavailable)
    assert isinstance(facts.firewall, Unavailable)


def test_progress_messages_are_reported():
    platform, _ = home_platform()
    messages = []
    collect(platform, skip_bandwidth=True, dns_probe=fake_dns, progress=messages.append)
    assert any("latency" in m for m in messages)
