"""The safety rules of --active: what may be scanned, and the guard.

Private addresses are built at run time (see conftest.py), because the
repository itself may only contain documentation addresses.
"""

import ipaddress

import pytest
from conftest import make_target, private_ip

from network_health import netio, thresholds
from network_health.models import AdapterConfig, IPv4Entry, Unavailable
from network_health.netio import RealNetIO
from network_health.scan_target import (
    ScanGuard,
    ScanRefused,
    check_network_allowed,
    choose_scan_target,
)


def adapter(address: str, prefix: int, alias="Wi-Fi", gateway=None, metric=10):
    return AdapterConfig(alias, metric=metric, ipv4=[IPv4Entry(address, prefix, "Dhcp")],
                         ipv4_gateways=[gateway] if gateway else [])


# ---------------------------------------------------------------- what is allowed

@pytest.mark.parametrize("base,own", [
    ("10.0.0.0", 7), ("172.16.0.0", 300), ("192.168.0.0", 25), ("10.0.0.0", 1)])
def test_private_attached_ranges_are_accepted(base, own):
    target = choose_scan_target([adapter(private_ip(own, base), 24, gateway="x")])
    assert target.network == ipaddress.ip_interface(f"{private_ip(own, base)}/24").network
    assert target.own_address == private_ip(own, base)
    assert target.interface == "Wi-Fi"
    assert target.host_count == 254
    hosts = target.hosts()
    assert len(hosts) == 253                       # this computer is left out
    assert ipaddress.ip_address(private_ip(own, base)) not in hosts
    assert target.network.network_address not in hosts
    assert target.network.broadcast_address not in hosts


@pytest.mark.parametrize("address,why", [
    ("203.0.113.5", "not a private range"),      # public (documentation range)
    ("192.0.2.10", "not a private range"),
    ("8.8.8.8", "not a private range"),
    (private_ip(5, "100.64.0.0"), "carrier-grade NAT"),
    (private_ip(5, "169.254.0.0"), "self-assigned"),
    ("127.0.0.1", "loopback"),
    (private_ip(2**20 + 5, "172.16.0.0"), "not a private range"),   # just outside 172.16/12
    ("224.0.0.9", "multicast"),
])
def test_everything_else_is_refused_with_a_reason(address, why):
    with pytest.raises(ScanRefused) as error:
        choose_scan_target([adapter(address, 24, gateway="x")])
    assert why in str(error.value)
    assert "Refusing to scan" in str(error.value)


@pytest.mark.parametrize("prefix", [8, 16, 21])
def test_subnets_larger_than_a_slash_22_are_refused_and_the_way_forward_is_named(prefix):
    with pytest.raises(ScanRefused) as error:
        choose_scan_target([adapter(private_ip(5), prefix, gateway="x")])
    text = str(error.value)
    assert "1022" in text and "/22" in text and "smaller" in text


def test_a_slash_22_is_the_largest_that_is_accepted():
    target = choose_scan_target([adapter(private_ip(5), 22, gateway="x")])
    assert target.host_count == thresholds.SCAN_MAX_HOSTS == 1022


@pytest.mark.parametrize("prefix", [31, 32])
def test_a_subnet_with_no_other_address_is_refused(prefix):
    with pytest.raises(ScanRefused):
        choose_scan_target([adapter(private_ip(5), prefix, gateway="x")])


def test_only_the_main_adapter_is_used():
    main = adapter(private_ip(5), 24, alias="Wi-Fi", gateway="x", metric=10)
    other = adapter(private_ip(5, "172.16.0.0"), 24, alias="vEthernet", metric=5000)
    target = choose_scan_target([other, main])
    assert target.interface == "Wi-Fi"
    assert str(target.network).startswith(private_ip(0)[:5])


def test_main_adapter_on_a_public_address_is_refused_even_if_another_is_private():
    public = adapter("203.0.113.9", 24, alias="Ethernet", gateway="x", metric=10)
    private = adapter(private_ip(5), 24, alias="vEthernet", metric=5000)
    with pytest.raises(ScanRefused):
        choose_scan_target([public, private])


def test_unreadable_configuration_or_no_ipv4_is_refused():
    with pytest.raises(ScanRefused):
        choose_scan_target(Unavailable("error", "boom"))
    with pytest.raises(ScanRefused):
        choose_scan_target([])
    with pytest.raises(ScanRefused):
        choose_scan_target([AdapterConfig("Wi-Fi", ipv4_gateways=["x"])])


def test_check_network_allowed_rejects_ipv6_and_mixed_ranges():
    with pytest.raises(ScanRefused):
        check_network_allowed(ipaddress.ip_network("fe80::/64"))
    with pytest.raises(ScanRefused):
        check_network_allowed(ipaddress.ip_network("2001:db8::/32"))
    # a range that only partly lies in a private range
    with pytest.raises(ScanRefused):
        check_network_allowed(ipaddress.ip_network("192.168.0.0/15"))


# ---------------------------------------------------------------- the guard

def test_guard_only_lets_usable_addresses_of_the_subnet_through():
    target = make_target()
    guard = ScanGuard(target)
    assert str(guard.check_host(private_ip(77))) == private_ip(77)
    for bad in (private_ip(0),            # network address
                private_ip(255),          # broadcast address
                private_ip(256),          # next subnet
                "203.0.113.5", "8.8.8.8", "224.0.0.251", "not-an-address",
                "fe80::1"):
        with pytest.raises(ScanRefused):
            guard.check_host(bad)
    assert guard.in_target(private_ip(77)) and not guard.in_target("8.8.8.8")


def test_guard_cannot_be_built_for_a_public_or_too_large_network():
    public = make_target(base="10.0.0.0")
    object.__setattr__(public, "network", ipaddress.ip_network("203.0.113.0/24"))
    with pytest.raises(ScanRefused):
        ScanGuard(public)
    large = make_target(prefix=16)
    with pytest.raises(ScanRefused):
        ScanGuard(large)


def test_guard_allows_only_the_two_multicast_groups_and_the_own_address():
    guard = ScanGuard(make_target())
    guard.check_multicast("224.0.0.251", 5353)
    guard.check_multicast("239.255.255.250", 1900)
    for group, port in (("224.0.0.251", 80), ("239.255.255.250", 5353),
                        ("224.0.0.1", 5353), ("255.255.255.255", 1900)):
        with pytest.raises(ScanRefused):
            guard.check_multicast(group, port)
    guard.check_own(private_ip(10))
    with pytest.raises(ScanRefused):
        guard.check_own(private_ip(11))


def test_real_netio_refuses_before_a_socket_is_opened():
    """The autouse fixture makes any real socket fail the test, so these
    calls can only pass by being refused first."""
    io = RealNetIO(ScanGuard(make_target()))
    for call in (lambda ip: io.connect(ip, 80, 1.0),
                 lambda ip: io.banner(ip, 21, 1.0, 1.0, 256),
                 lambda ip: io.http_head(ip, 80, 1.0, 1.0, 2048),
                 lambda ip: io.tls_handshake(ip, 443, 1.0)):
        for outside in ("8.8.8.8", "203.0.113.5", private_ip(300)):
            with pytest.raises(ScanRefused):
                call(outside)
    with pytest.raises(ScanRefused):
        io.multicast_query("224.0.0.1", 5353, b"x", local_ip=private_ip(10), sends=1,
                           wait=0.1, max_packets=1)
    with pytest.raises(ScanRefused):
        io.multicast_query("224.0.0.251", 5353, b"x", local_ip=private_ip(99), sends=1,
                           wait=0.1, max_packets=1)


def test_netio_error_is_an_exception_class():
    assert issubclass(netio.NetIOError, Exception)


def test_the_172_16_range_starts_exactly_at_172_16():
    just_below = private_ip(-5, "172.16.0.0")            # just below the range
    assert just_below.startswith("172.15.")
    with pytest.raises(ScanRefused) as error:
        choose_scan_target([adapter(just_below, 24, gateway="x")])
    assert "not a private range" in str(error.value)
    choose_scan_target([adapter(private_ip(5, "172.16.0.0"), 24, gateway="x")])      # first address range
    last = private_ip(2**20 - 5, "172.16.0.0")           # the last 172.16/12 range
    assert last.startswith("172.31.")
    choose_scan_target([adapter(last, 24, gateway="x")])


def test_no_default_gateway_means_no_scan_but_passive_choice_is_unchanged():
    from network_health.collect import choose_primary
    only = adapter(private_ip(5), 24, alias="Ethernet")              # no gateway at all
    assert choose_primary([only]) is only                             # passive: the fallback stays
    with pytest.raises(ScanRefused) as error:
        choose_scan_target([only])
    assert "default gateway" in str(error.value) and "Ethernet" in str(error.value)
    # An adapter with a gateway is used even when another one has a lower metric.
    other = adapter(private_ip(5, "172.16.0.0"), 24, alias="vEthernet", metric=1)
    main = adapter(private_ip(5), 24, alias="Wi-Fi", gateway="x", metric=50)
    assert choose_scan_target([other, main]).interface == "Wi-Fi"
