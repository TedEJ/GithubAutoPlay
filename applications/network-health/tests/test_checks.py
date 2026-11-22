"""Every check gives good, warn or bad (and info where it is only a note),
and a skipped result with a reason when its fact is missing."""

import copy
import ipaddress

import pytest

from conftest import fixture_text, home_facts, ok, out
from network_health import checks
from network_health.checks import run_checks
from network_health.models import (
    BAD,
    GOOD,
    INFO,
    SKIPPED,
    WARN,
    BandwidthResult,
    DnsTiming,
    IPv4Entry,
    MtuResult,
    NetworkProfile,
    ProxySettings,
    Unavailable,
    WifiStatus,
)


@pytest.fixture(scope="module")
def base():
    facts, _ = home_facts()
    return facts


def facts_with(base, **changes):
    facts = copy.deepcopy(base)
    for key, value in changes.items():
        setattr(facts, key, value)
    return facts


def by_id(results, check_id):
    found = [r for r in results if r.id == check_id]
    assert found, f"no result {check_id} in {[r.id for r in results]}"
    return found[0]


def status(results, check_id):
    return by_id(results, check_id).status


def _finding_scenarios(base):
    """Facts that together give every kind of info, warn and bad finding."""
    yield base, None
    other = {"network": {"gateway": "198.51.100.1", "ssid": "Other"}}
    yield base, other
    changed = {"network": checks.network_identity(base), "gateway_mac": "00:00:5e:00:53:99"}
    yield base, changed
    yield facts_with(base, mtu=MtuResult("1.1.1.1", 1492)), None
    yield facts_with(base, mtu=MtuResult("1.1.1.1", 1300)), None
    yield facts_with(base, wifi=_wifi(band="2.4 GHz", channel=6, signal_pct=40,
                                      receive_mbps=11, transmit_mbps=11,
                                      authentication="Open", cipher="None")), None
    yield facts_with(base, wifi=_wifi(authentication="OWE", cipher="CCMP")), None
    yield facts_with(base, bandwidth=_bw(5, 1, [300.0, 280.0, 290.0])), None
    yield facts_with(base, dns={"192.0.2.1": DnsTiming("192.0.2.1", [], 3)}), None
    no_v6 = copy.deepcopy(base)
    no_v6.primary.ipv6_global = []
    no_v6.primary.dns_servers = ["198.51.100.53"]
    yield no_v6, None
    for entry in (IPv4Entry("192.0.2.10", 24, "Dhcp", 1800),
                  IPv4Entry("192.0.2.10", 24, "Manual", None),
                  IPv4Entry(str(ipaddress.ip_address("169.254.0.0") + 7), 16,
                            "WellKnown", None)):
        yield _with_ipv4(base, entry), None
    yield _with_ipv4(base), None
    no_dns = copy.deepcopy(base)
    no_dns.primary.dns_servers = []
    yield no_dns, None
    yield facts_with(base, proxy=ProxySettings(user_proxy_enabled=True,
                                               user_proxy_server="proxy.example.invalid:8080")), None
    rdp, _ = home_facts(("Get-NetTCPConnection", ok("ps_listening_rdp.json")),
                        ("Get-NetFirewallProfile", ok("ps_firewall_off.json")),
                        ("arp -a", ok("arp_spoofed.txt")),
                        ("ping -n 20 -w 1000 192.0.2.1", ok("ping_all_lost.txt", 1)))
    yield rdp, None
    bad_link, _ = home_facts(("ping -n 20 -w 1000 192.0.2.1", ok("ping_gateway_bad.txt")))
    yield bad_link, None
    dup = copy.deepcopy(base)
    dup.neighbours[2].mac = dup.neighbours[1].mac
    yield dup, None


def test_every_result_has_text_and_every_finding_has_a_fix_tip(base):
    """The issue asks for a fix tip on every finding: bad, warn and info."""
    seen = set()
    for facts, previous in _finding_scenarios(base):
        for result in run_checks(facts, previous):
            assert result.summary
            assert result.area in checks.AREAS
            if result.status in (INFO, WARN, BAD):
                assert result.fix, f"{result.id} ({result.status}) has no fix tip"
                seen.add(result.status)
            if result.status in (WARN, BAD):
                assert result.why, result.id
    assert seen == {INFO, WARN, BAD}


# ---------------------------------------------------------------- ping

def test_ping_good_on_home_network(base):
    results = checks.check_ping(base)
    for key in ("gateway", "1.1.1.1", "8.8.8.8"):
        for metric in ("latency", "jitter", "loss"):
            assert status(results, f"perf.ping.{key}.{metric}") == GOOD


def test_ping_bad_link():
    facts, _ = home_facts(
        ("ping -n 20 -w 1000 192.0.2.1", ok("ping_gateway_bad.txt")),
        ("ping -n 20 -w 1000 1.1.1.1", ok("ping_cloudflare_bad.txt")))
    results = checks.check_ping(facts)
    assert status(results, "perf.ping.gateway.latency") == BAD    # ~54 ms
    assert status(results, "perf.ping.gateway.jitter") == BAD
    assert status(results, "perf.ping.gateway.loss") == BAD       # 15 %
    assert status(results, "perf.ping.1.1.1.1.latency") == BAD    # ~165 ms
    assert status(results, "perf.ping.1.1.1.1.loss") == BAD
    assert status(results, "perf.ping.8.8.8.8.latency") == GOOD


def test_ping_thresholds_warn():
    assert checks.grade_low(20, 10, 30) == WARN
    assert checks.grade_low(10, 10, 30) == GOOD
    assert checks.grade_low(31, 10, 30) == BAD
    assert checks.grade_high(10, 25, 10) == WARN
    assert checks.grade_high(9.9, 25, 10) == BAD


def test_gateway_that_ignores_ping_is_only_info():
    facts, _ = home_facts(("ping -n 20 -w 1000 192.0.2.1", ok("ping_all_lost.txt", 1)))
    result = by_id(checks.check_ping(facts), "perf.ping.gateway.loss")
    assert result.status == INFO


def test_no_replies_anywhere_is_bad():
    def lost(args):  # the recorded output, for whichever target was pinged
        return out(fixture_text("ping_all_lost.txt").replace("192.0.2.1", args[-1]), 1)
    facts, _ = home_facts(("ping -n 20", lost))
    results = checks.check_ping(facts)
    assert status(results, "perf.ping.gateway.loss") == BAD
    assert status(results, "perf.ping.8.8.8.8.loss") == BAD


def test_ping_unavailable_is_skipped(base):
    facts = facts_with(base, ping_gateway=Unavailable("missing-tool", "`ping` was not found."))
    result = by_id(checks.check_ping(facts), "perf.ping.gateway")
    assert result.status == SKIPPED and "not found" in result.summary


# ---------------------------------------------------------------- DNS time

@pytest.mark.parametrize("times,failures,expected", [
    ([12.0, 15.0, 11.0], 0, GOOD),
    ([90.0, 100.0, 120.0], 0, WARN),
    ([300.0, 250.0, 400.0], 0, BAD),
    ([12.0, 15.0], 1, WARN),
    ([], 3, BAD),
])
def test_dns_time(base, times, failures, expected):
    facts = facts_with(base, dns={"192.0.2.1": DnsTiming("192.0.2.1", times, failures)})
    assert status(checks.check_dns_time(facts), "perf.dns.192.0.2.1") == expected


def test_dns_time_skipped(base):
    assert status(checks.check_dns_time(facts_with(base, dns={})), "perf.dns") == SKIPPED
    facts = facts_with(base, dns=Unavailable("error", "x"))
    assert status(checks.check_dns_time(facts), "perf.dns") == SKIPPED


# ---------------------------------------------------------------- MTU

@pytest.mark.parametrize("mtu,expected", [(1500, GOOD), (1492, INFO), (1300, WARN)])
def test_mtu(base, mtu, expected):
    facts = facts_with(base, mtu=MtuResult("1.1.1.1", mtu))
    assert status(checks.check_mtu(facts), "perf.mtu") == expected


def test_mtu_skipped(base):
    facts = facts_with(base, mtu=Unavailable("error", "no reply"))
    assert status(checks.check_mtu(facts), "perf.mtu") == SKIPPED


# ---------------------------------------------------------------- bandwidth and bufferbloat

def _bw(down, up, loaded):
    return BandwidthResult(server="Cloudflare speed test (speed.cloudflare.com)",
                           download_mbps=down, upload_mbps=up,
                           download_bytes=1, upload_bytes=1, loaded_latency_ms=loaded)


@pytest.mark.parametrize("down,up,expected_down,expected_up", [
    (180, 40, GOOD, GOOD), (15, 3, WARN, WARN), (5, 1, BAD, BAD)])
def test_bandwidth(base, down, up, expected_down, expected_up):
    results = checks.check_bandwidth(facts_with(base, bandwidth=_bw(down, up, [20, 22])))
    assert status(results, "perf.download") == expected_down
    assert status(results, "perf.upload") == expected_up
    assert "speed.cloudflare.com" in by_id(results, "perf.download").summary


@pytest.mark.parametrize("loaded,expected", [
    ([20.0, 25.0, 22.0], GOOD), ([80.0, 90.0, 85.0], WARN), ([300.0, 280.0, 290.0], BAD)])
def test_bufferbloat(base, loaded, expected):
    results = checks.check_bandwidth(facts_with(base, bandwidth=_bw(100, 20, loaded)))
    assert status(results, "perf.bufferbloat") == expected


def test_bufferbloat_needs_samples(base):
    results = checks.check_bandwidth(facts_with(base, bandwidth=_bw(100, 20, [20.0])))
    assert status(results, "perf.bufferbloat") == SKIPPED


def test_bandwidth_turned_off_skips_three_checks(base):
    off = Unavailable("turned-off", "Turned off with --skip-bandwidth.")
    results = checks.check_bandwidth(facts_with(base, bandwidth=off))
    assert [r.status for r in results] == [SKIPPED] * 3
    assert all("--skip-bandwidth" in r.summary for r in results)


def test_bandwidth_one_direction_failed(base):
    bw = _bw(100, None, [20, 21])
    bw.upload_error = "the speed-test server could not be used (fake)"
    results = checks.check_bandwidth(facts_with(base, bandwidth=bw))
    assert status(results, "perf.download") == GOOD
    assert status(results, "perf.upload") == SKIPPED


# ---------------------------------------------------------------- Wi-Fi

def _wifi(**kw):
    values = dict(connected=True, ssid="ExampleHome", bssid="00:00:5e:00:53:01",
                  band="5 GHz", channel=36, radio_type="802.11ax",
                  authentication="WPA2-Personal", cipher="CCMP",
                  receive_mbps=866.7, transmit_mbps=866.7, signal_pct=88)
    values.update(kw)
    return WifiStatus(**values)


@pytest.mark.parametrize("signal,expected", [(88, GOOD), (60, WARN), (35, BAD)])
def test_wifi_signal(base, signal, expected):
    results = checks.check_wifi(facts_with(base, wifi=_wifi(signal_pct=signal)))
    assert status(results, "wifi.signal") == expected


@pytest.mark.parametrize("rate,expected", [(866.7, GOOD), (54, WARN), (11, BAD)])
def test_wifi_link_rate(base, rate, expected):
    results = checks.check_wifi(facts_with(base, wifi=_wifi(receive_mbps=rate, transmit_mbps=rate)))
    assert status(results, "wifi.link_rate") == expected


def test_wifi_band(base):
    assert status(checks.check_wifi(facts_with(base, wifi=_wifi(band="6 GHz"))), "wifi.band") == GOOD
    assert status(checks.check_wifi(facts_with(base, wifi=_wifi(band="2.4 GHz", channel=6))),
                  "wifi.band") == INFO


def test_wifi_congestion_good_on_home_network(base):
    result = by_id(checks.check_wifi(base), "wifi.congestion")
    assert result.status == GOOD
    assert result.details["other_networks"] == 1  # ExampleNeighbour on 36


def test_wifi_congestion_bad_on_crowded_24ghz_with_channel_tip():
    facts, _ = home_facts(
        ("netsh wlan show interfaces", ok("wlan_interfaces_weak_open_24.txt")),
        ("netsh wlan show networks", ok("wlan_networks_crowded_24.txt")))
    result = by_id(checks.check_wifi(facts), "wifi.congestion")
    # Overlapping channel 6 (2..10): 6, 6, 4, 7, 8, 6, 3 -> 7 networks.
    assert result.details["other_networks"] == 7
    assert result.status == WARN
    assert "channel 11" in result.fix or "channel 1 " in result.fix


def test_wifi_congestion_bad_threshold(base):
    many = [copy.deepcopy(base.wifi_networks[2]) for _ in range(9)]
    for n, net in enumerate(many):
        net.ssid, net.channel, net.band = f"ExampleNet{n}", 36, "5 GHz"
    result = by_id(checks.check_wifi(facts_with(base, wifi_networks=many)), "wifi.congestion")
    assert result.status == BAD


def test_wifi_congestion_skipped_without_scan(base):
    facts = facts_with(base, wifi_networks=Unavailable("rights", "Location is off."))
    assert status(checks.check_wifi(facts), "wifi.congestion") == SKIPPED


@pytest.mark.parametrize("auth,cipher,expected", [
    ("Open", "None", BAD),
    ("Open", "WEP", BAD),
    ("Shared", "WEP", BAD),
    ("WPA-Personal", "CCMP", BAD),
    ("WPA2-Personal", "TKIP", BAD),
    ("WPA2-Personal", "CCMP", GOOD),
    ("WPA2-Enterprise", "GCMP-256", GOOD),
    ("WPA3-Personal", "GCMP-256", GOOD),
    ("OWE", "CCMP", WARN),
])
def test_wifi_security(base, auth, cipher, expected):
    results = checks.check_wifi(facts_with(base, wifi=_wifi(authentication=auth, cipher=cipher)))
    assert status(results, "wifi.security") == expected


def test_wifi_security_unknown_is_skipped(base):
    results = checks.check_wifi(facts_with(base, wifi=_wifi(authentication="Okänd", cipher="?")))
    assert status(results, "wifi.security") == SKIPPED


def test_wifi_not_connected_gives_one_skipped_result(base):
    results = checks.check_wifi(facts_with(base, wifi=WifiStatus(connected=False)))
    assert len(results) == 1 and results[0].status == SKIPPED
    assert "not connected over Wi-Fi" in results[0].summary


def test_wifi_unrecognized_output_is_skipped_with_language_hint():
    facts, _ = home_facts(("netsh wlan show interfaces", ok("wlan_interfaces_swedish.txt")))
    results = checks.check_wifi(facts)
    assert results[0].status == SKIPPED and "English" in results[0].summary


# ---------------------------------------------------------------- configuration

def test_profile(base):
    assert checks.check_profile(base).status == INFO   # Private at home
    public = [NetworkProfile("ExampleHome", "Wi-Fi", "Public")]
    assert checks.check_profile(facts_with(base, profiles=public)).status == GOOD
    open_wifi = facts_with(base, wifi=_wifi(authentication="Open", cipher="None"))
    assert checks.check_profile(open_wifi).status == WARN
    assert checks.check_profile(facts_with(base, profiles=[])).status == SKIPPED


def test_firewall():
    facts, _ = home_facts()
    assert checks.check_firewall(facts).status == GOOD
    off, _ = home_facts(("Get-NetFirewallProfile", ok("ps_firewall_off.json")))
    result = checks.check_firewall(off)
    assert result.status == BAD
    assert result.details["off"] == ["Private", "Public"]


def test_dns_servers_router_is_good(base):
    result = checks.check_dns_servers(base)
    assert result.status == GOOD
    assert "the router" in result.summary


def test_dns_servers_isp_and_public_resolver():
    facts, _ = home_facts(("Get-NetIPConfiguration", ok("ps_ipconfig_single.json")),
                          ("ping -n 20 -w 1000 203.0.113.1", ok("ping_all_lost.txt")))
    result = checks.check_dns_servers(facts)
    assert result.status == INFO
    assert result.details["servers"] == {"198.51.100.53": "isp", "9.9.9.9": "public"}
    assert "Quad9" in result.summary


def test_dns_server_classification(base):
    private = str(ipaddress.ip_address("10.0.0.0") + 53)  # built, not written
    assert checks.classify_dns(private, base)[0] == "private"
    assert checks.classify_dns("192.0.2.53", base)[0] == "local"
    assert checks.classify_dns("fe80::1", base)[0] == "router"
    assert checks.classify_dns("2606:4700:4700::1111", base)[1] == "public resolver Cloudflare"
    assert checks.classify_dns("bad", base)[0] == "unknown"


def test_dns_servers_none_is_bad(base):
    facts = copy.deepcopy(base)
    facts.primary.dns_servers = ["fec0:0:0:ffff::1"]
    assert checks.check_dns_servers(facts).status == BAD


def test_ipv6(base):
    assert checks.check_ipv6(base).status == GOOD
    facts = copy.deepcopy(base)
    facts.primary.ipv6_global = []
    assert checks.check_ipv6(facts).status == INFO
    assert checks.check_ipv6(facts_with(base, primary=None)).status == SKIPPED


def _with_ipv4(base, *entries):
    facts = copy.deepcopy(base)
    facts.primary.ipv4 = list(entries)
    return facts


def test_dhcp(base):
    assert checks.check_dhcp(base).status == GOOD
    short = _with_ipv4(base, IPv4Entry("192.0.2.10", 24, "Dhcp", 1800))
    assert checks.check_dhcp(short).status == INFO
    manual = _with_ipv4(base, IPv4Entry("192.0.2.10", 24, "Manual", None))
    assert checks.check_dhcp(manual).status == INFO
    apipa = _with_ipv4(base, IPv4Entry(str(ipaddress.ip_address("169.254.0.0") + 7), 16,
                                       "WellKnown", None))
    assert checks.check_dhcp(apipa).status == BAD
    assert checks.check_dhcp(_with_ipv4(base)).status == BAD


def test_proxy(base):
    assert checks.check_proxy(base).status == GOOD
    proxy = ProxySettings(user_proxy_enabled=True, user_proxy_server="proxy.example.invalid:8080",
                          environment={"HTTPS_PROXY": "http://user:pw@proxy.example.invalid:3128"})
    result = checks.check_proxy(facts_with(base, proxy=proxy))
    assert result.status == WARN
    assert "user:pw" not in result.summary and "***@proxy.example.invalid" in result.summary


def test_proxy_unknown_winhttp_is_mentioned(base):
    result = checks.check_proxy(facts_with(base, proxy=ProxySettings(winhttp_known=False)))
    assert result.status == GOOD and "WinHTTP" in result.summary


def test_listening_ports_home(base):
    results = checks.check_listening_ports(base)
    assert status(results, "config.ports.sharing") == INFO
    other = by_id(results, "config.ports.other")
    assert other.details["ports"] == [135]  # loopback-only ports are left out


def test_listening_ports_remote_access_warns():
    facts, _ = home_facts(("Get-NetTCPConnection", ok("ps_listening_rdp.json")))
    results = checks.check_listening_ports(facts)
    assert status(results, "config.ports.remote") == WARN
    assert "Remote Desktop" in by_id(results, "config.ports.remote").summary
    assert by_id(results, "config.ports.other").details["ports"] == [8080]


def test_listening_ports_none_exposed_is_good(base):
    facts = facts_with(base, listening=[p for p in base.listening if p.port > 9000])
    assert status(checks.check_listening_ports(facts), "config.ports") == GOOD


# ---------------------------------------------------------------- local network

def test_local_network_home(base):
    results = checks.check_local_network(base, None)
    assert by_id(results, "lan.neighbours").details["count"] == 3
    assert status(results, "lan.duplicate_mac") == GOOD
    assert status(results, "lan.gateway_mac") == INFO  # no snapshot yet


def test_spoofed_gateway_is_bad():
    facts, _ = home_facts(("arp -a", ok("arp_spoofed.txt")))
    results = checks.check_local_network(facts, None)
    assert status(results, "lan.duplicate_mac") == BAD


def test_duplicate_mac_not_involving_gateway_is_warn(base):
    facts = copy.deepcopy(base)
    facts.neighbours[2].mac = facts.neighbours[1].mac
    assert status(checks.check_local_network(facts, None), "lan.duplicate_mac") == WARN


def test_gateway_mac_compared_with_snapshot(base):
    identity = checks.network_identity(base)
    same = {"network": identity, "gateway_mac": "00:00:5e:00:53:01", "generated": "x"}
    changed = {"network": identity, "gateway_mac": "00:00:5e:00:53:99", "generated": "x"}
    other = {"network": {"gateway": "198.51.100.1", "ssid": "Other"}, "gateway_mac": "x"}
    assert status(checks.check_local_network(base, same), "lan.gateway_mac") == GOOD
    assert status(checks.check_local_network(base, changed), "lan.gateway_mac") == WARN
    assert status(checks.check_local_network(base, other), "lan.gateway_mac") == INFO


def test_local_network_skipped_without_arp(base):
    facts = facts_with(base, neighbours=Unavailable("missing-tool", "`arp -a` was not found."))
    assert status(checks.check_local_network(facts, None), "lan.neighbours") == SKIPPED


# ---------------------------------------------------------------- acceptance overview

def test_every_listed_check_can_produce_a_real_verdict(base):
    """Acceptance: with fixtures, every check in the issue gives good, warn or
    bad (info counts as good with a note)."""
    snapshot = {"network": checks.network_identity(base),
                "gateway_mac": "00:00:5e:00:53:01"}
    results = run_checks(base, snapshot)
    wanted = ["perf.ping.gateway.latency", "perf.ping.gateway.jitter",
              "perf.ping.gateway.loss", "perf.ping.1.1.1.1.latency",
              "perf.ping.8.8.8.8.latency", "perf.dns.192.0.2.1", "perf.mtu",
              "perf.download", "perf.upload", "perf.bufferbloat",
              "wifi.signal", "wifi.link_rate", "wifi.band", "wifi.congestion",
              "wifi.security", "config.profile", "config.firewall",
              "config.dns_servers", "config.ipv6", "config.dhcp", "config.proxy",
              "config.ports.sharing", "lan.neighbours", "lan.duplicate_mac",
              "lan.gateway_mac"]
    for check_id in wanted:
        assert status(results, check_id) in (GOOD, INFO, WARN, BAD), check_id


def test_run_checks_never_crashes_when_nothing_could_be_read():
    missing = Unavailable("missing-tool", "not found")
    from network_health.collect import Facts
    facts = Facts(platform="Windows", adapters=missing, ping_gateway=missing,
                  ping_public={"1.1.1.1": missing, "8.8.8.8": missing}, dns=missing,
                  mtu=missing, bandwidth=missing, wifi=missing, wifi_networks=missing,
                  profiles=missing, firewall=missing, proxy=missing, listening=missing,
                  neighbours=missing)
    results = run_checks(facts)
    assert results and all(r.status == SKIPPED for r in results)



def test_bufferbloat_on_a_very_fast_link_is_skipped_with_the_reason(base):
    bw = _bw(900, 400, [20.0])
    bw.download_seconds, bw.upload_seconds = 0.2, 0.3
    result = by_id(checks.check_bandwidth(facts_with(base, bandwidth=bw)), "perf.bufferbloat")
    assert result.status == SKIPPED
    assert "so fast" in result.summary and "0.2 s down" in result.summary


def test_bufferbloat_without_replies_during_load_says_so(base):
    bw = _bw(50, 10, [])
    bw.download_seconds, bw.upload_seconds = 10.0, 8.0
    result = by_id(checks.check_bandwidth(facts_with(base, bandwidth=bw)), "perf.bufferbloat")
    assert result.status == SKIPPED and "no replies" in result.summary
