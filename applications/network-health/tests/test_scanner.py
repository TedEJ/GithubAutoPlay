"""The device scan with a fake network layer and a fake clock: nothing real is
pinged, connected to or sent."""

import ipaddress
import socket
import struct

from conftest import (
    FakeClock,
    FakeNetIO,
    StubPlatform,
    doc_mac,
    mac_with_prefix,
    make_target,
    neighbour,
    private_ip,
    private_mac,
)

from network_health import scanner, services, thresholds
from network_health.models import Unavailable
from network_health.netio import ProbeResult
from network_health.scan_target import ScanGuard

HTTP_OK = ProbeResult(True, b"HTTP/1.1 200 OK\r\nServer: ExampleHTTPd/1.0\r\n\r\n")


def run(platform, io, *, target=None, gateway=None, clock=None, limits=None):
    target = target or make_target()
    return scanner.scan(platform, target, ScanGuard(target), io, gateway=gateway,
                        clock=clock or FakeClock(), limits=limits)


def mdns_packet(host: str, address: str, instance: str = "Example Printer") -> bytes:
    def name(text):
        return b"".join(bytes([len(p)]) + p.encode() for p in text.split(".")) + b"\x00"

    def rec(owner, rtype, rdata):
        return owner + struct.pack("!HHIH", rtype, 1, 120, len(rdata)) + rdata

    records = [
        rec(name("_ipp._tcp.local"), 12, name(f"{instance}._ipp._tcp.local")),
        rec(name(f"{host}.local"), 1, socket.inet_aton(address)),
    ]
    return struct.pack("!HHHHHH", 0, 0x8400, 0, 2, 0, 0) + b"".join(records)


SSDP_REPLY = (b"HTTP/1.1 200 OK\r\nSERVER: Linux UPnP/1.0 ExampleBox/1.0\r\n"
              b"ST: upnp:rootdevice\r\n\r\n")


def test_scan_finds_devices_from_ping_arp_mdns_and_ssdp_and_reads_their_ports():
    router, pc, printer, tv, quiet = (private_ip(n) for n in (1, 20, 30, 40, 50))
    platform = StubPlatform(
        alive=[router, pc, printer],
        neighbours=[neighbour(1, mac_with_prefix("14CC20")),         # TP-Link
                    neighbour(20, doc_mac(0x20)),
                    neighbour(30, mac_with_prefix("00408C")),        # Axis Communications
                    neighbour(50, doc_mac(0x50))])                   # answers ARP, not ping
    io = FakeNetIO(
        ports={
            router: {80: HTTP_OK, 7547: True},
            printer: {80: HTTP_OK, 23: ProbeResult(True, b"\xff\xfd\x18ExampleCam login:")},
            tv: {8443: ProbeResult(True, tls_version="TLSv1.2")},
        },
        mdns=[(printer, mdns_packet("exampleprinter", printer))],
        ssdp=[(tv, SSDP_REPLY)])
    scan = run(platform, io, gateway=router)

    assert scan.network == str(make_target().network)
    assert scan.addresses_total == 253 and scan.addresses_pinged == 253
    assert [d.ip for d in scan.devices] == [router, pc, printer, tv, quiet]
    by_ip = {d.ip: d for d in scan.devices}

    assert by_ip[router].found_by == ["ping", "arp"] and by_ip[router].is_gateway
    assert by_ip[router].vendor == "TP-Link" and by_ip[router].kind == "router"
    assert by_ip[router].open_ports == [80, 7547]
    assert by_ip[router].services[80].http_server == "ExampleHTTPd/1.0"
    assert by_ip[router].services[80].is_http

    assert by_ip[printer].found_by == ["ping", "arp", "mdns"]
    assert by_ip[printer].name == "exampleprinter"
    assert by_ip[printer].mdns_services == ["_ipp._tcp.local"]
    assert by_ip[printer].vendor == "Axis Communications"
    assert by_ip[printer].kind == "printer"           # the mDNS service beats the vendor
    assert by_ip[printer].kind_source == "mDNS service"
    assert by_ip[printer].open_ports == [23, 80]
    assert by_ip[printer].services[23].banner == "ExampleCam login:"

    assert by_ip[tv].found_by == ["ssdp"] and by_ip[tv].upnp
    assert by_ip[tv].ssdp_server == "Linux UPnP/1.0 ExampleBox/1.0"
    assert by_ip[tv].services[8443].is_https

    assert by_ip[quiet].found_by == ["arp"] and by_ip[quiet].open_ports == []
    assert by_ip[pc].open_ports == []
    assert scan.complete and scan.stopped == ""
    assert scan.mdns_answers == 1 and scan.ssdp_answers == 1


def test_only_addresses_of_the_subnet_are_ever_pinged_or_probed():
    target = make_target()
    platform = StubPlatform(alive=[private_ip(20)], neighbours=[neighbour(20, doc_mac(1))])
    io = FakeNetIO(ports={private_ip(20): {80: HTTP_OK}})
    run(platform, io, target=target)
    network = target.network
    assert platform.pings, "the sweep must ping"
    assert all(ipaddress.ip_address(ip) in network for ip in platform.pings)
    assert len(set(platform.pings)) == len(platform.pings) == 253
    assert private_ip(10) not in platform.pings          # this computer
    assert private_ip(0) not in platform.pings and private_ip(255) not in platform.pings
    unicast = [c for c in io.calls if c[0] != "multicast"]
    assert unicast and all(c[1] == private_ip(20) for c in unicast)
    assert {c[2] for c in unicast} == set(services.PORTS)     # every port, once
    assert len(unicast) == len(services.PORTS)
    assert sorted(c[1:] for c in io.calls if c[0] == "multicast") == [
        ("224.0.0.251", 5353), ("239.255.255.250", 1900)]


def test_answers_and_arp_entries_from_outside_the_subnet_are_ignored():
    outside_private = private_ip(1, "172.16.0.0")
    platform = StubPlatform(
        alive=[private_ip(20)],
        neighbours=[neighbour(20, doc_mac(1)),
                    neighbour(300, doc_mac(2)),                    # next subnet
                    type(neighbour(1, "x"))(private_ip(10), "203.0.113.9", doc_mac(3))])
    io = FakeNetIO(
        mdns=[("203.0.113.5", mdns_packet("evil", "203.0.113.5")),
              (outside_private, mdns_packet("evil2", outside_private))],
        ssdp=[("8.8.8.8", SSDP_REPLY)])
    scan = run(platform, io)
    assert [d.ip for d in scan.devices] == [private_ip(20)]
    assert scan.mdns_answers == 0 and scan.ssdp_answers == 0
    assert any("3 mDNS or SSDP answers" in note for note in scan.notes)
    assert all(c[1] == private_ip(20) for c in io.calls if c[0] != "multicast")


def test_this_computer_is_not_scanned_or_listed():
    platform = StubPlatform(alive=[private_ip(10)], neighbours=[neighbour(10, doc_mac(1))])
    io = FakeNetIO(mdns=[(private_ip(10), mdns_packet("me", private_ip(10)))])
    scan = run(platform, io)
    assert scan.devices == []
    assert private_ip(10) not in platform.pings


def test_without_ping_the_scan_continues_with_arp_and_says_so():
    platform = StubPlatform(neighbours=[neighbour(20, doc_mac(1))],
                            error=Unavailable("missing-tool", "`ping` was not found."))
    scan = run(platform, FakeNetIO())
    assert [d.ip for d in scan.devices] == [private_ip(20)]
    assert any("ping sweep could not run" in n.lower() and "`ping` was not found" in n
               for n in scan.notes)
    assert scan.complete          # a missing tool is a note, not a cut-short scan


def test_multicast_failure_is_a_note_not_a_crash():
    platform = StubPlatform(alive=[private_ip(20)])
    scan = run(platform, FakeNetIO(mdns_error="no route"))
    assert any("mDNS query could not be sent: no route" in n for n in scan.notes)
    assert [d.ip for d in scan.devices] == [private_ip(20)]


def test_arp_failure_is_a_note_not_a_crash():
    class NoArp(StubPlatform):
        def neighbours(self):
            raise Unavailable("missing-tool", "`arp` was not found.")

    scan = run(NoArp(alive=[private_ip(20)]), FakeNetIO())
    assert any("ARP table could not be read" in n for n in scan.notes)
    assert [d.ip for d in scan.devices] == [private_ip(20)]


def test_a_probe_that_raises_counts_as_a_closed_port():
    class Broken(FakeNetIO):
        def connect(self, ip, port, timeout):
            raise OSError("boom")

    scan = run(StubPlatform(alive=[private_ip(20)]), Broken())
    assert scan.devices[0].open_ports == []


def test_text_from_the_network_is_cleaned():
    platform = StubPlatform(alive=[private_ip(20)])
    io = FakeNetIO(ports={private_ip(20): {
        21: ProbeResult(True, b"220 \x1b]0;pwned\x07ExampleFTP ready\r\n")}})
    scan = run(platform, io)
    banner = scan.devices[0].services[21].banner
    assert "\x1b" not in banner and "\x07" not in banner and "ExampleFTP ready" in banner


# ---------------------------------------------------------------- identification

def test_identify_vendor_private_mac_and_gateway():
    from conftest import make_device
    nas = make_device(20, mac=mac_with_prefix("001132"))
    scanner.identify(nas)
    assert (nas.vendor, nas.kind, nas.kind_source) == ("Synology", "nas", "vendor")

    phone = make_device(21, mac=private_mac())
    scanner.identify(phone)
    assert phone.private_mac and phone.vendor == "" and phone.kind == ""

    named = make_device(22, mac=mac_with_prefix("14CC20"), name="Example-NAS-1")
    scanner.identify(named)
    assert named.kind == "nas" and named.kind_source == "name"     # a name beats the vendor

    gateway = make_device(1, mac=mac_with_prefix("001132"), is_gateway=True)
    scanner.identify(gateway)
    assert gateway.kind == "router" and gateway.kind_source == "default gateway"

    none = make_device(23)
    scanner.identify(none)
    assert none.vendor == "" and none.kind == "" and not none.private_mac


# ---------------------------------------------------------------- the limits

def test_pacer_keeps_operations_apart_and_clock_never_goes_backwards():
    clock = FakeClock()
    pacer = scanner.Pacer(clock, 0.02)
    start = clock.monotonic()
    for _ in range(11):
        pacer.wait()
    assert clock.monotonic() - start >= 10 * 0.02 - 1e-9


def test_deadline_stops_new_work_in_time():
    clock = FakeClock()
    deadline = scanner.Deadline(clock, clock.monotonic(), 100.0, 6.0)
    assert not deadline.expired()
    clock.advance(93.9)
    assert not deadline.expired()
    clock.advance(0.2)
    assert deadline.expired()


def test_time_limit_cuts_the_ping_sweep_and_the_scan_ends_within_the_limit():
    clock = FakeClock()
    start = clock.monotonic()
    # One at a time, 1 s per ping: 253 pings would take 253 s.
    limits = scanner.ScanLimits(sweep_workers=1, port_workers=1)
    platform = StubPlatform(alive=[private_ip(20)], clock=clock, ping_cost=1.0)
    scan = run(platform, FakeNetIO(clock=clock), clock=clock, limits=limits)
    elapsed = clock.monotonic() - start
    assert not scan.complete and "ping sweep" in scan.stopped
    assert scan.addresses_pinged < 253
    assert elapsed <= limits.sweep_budget_s + 1       # the sweep stops at its budget
    assert elapsed <= thresholds.SCAN_TIME_LIMIT_S


def test_time_limit_cuts_the_port_checks_and_marks_the_devices():
    clock = FakeClock()
    start = clock.monotonic()
    limits = scanner.ScanLimits(sweep_workers=1, port_workers=1, time_limit_s=60.0)
    alive = [private_ip(n) for n in range(20, 60)]
    platform = StubPlatform(alive=alive)
    io = FakeNetIO(clock=clock, cost=1.0, multicast_cost=4.0)    # 14 s per device
    scan = run(platform, io, clock=clock, limits=limits)
    elapsed = clock.monotonic() - start
    assert not scan.complete and "port checks" in scan.stopped
    assert elapsed <= 60.0
    assert any(not d.ports_complete for d in scan.devices)
    assert scan.devices[0].ports_complete
    # every device is still listed, also the ones whose ports were not checked
    assert len(scan.devices) == len(alive)


def test_full_slash_24_scan_ends_within_the_time_limit():
    """A /24 with 60 devices, the slowest answers a network can give: every dead
    address takes 3 s to ping, every port is filtered (one second to time out,
    a second more for the banner ports). The fake layer charges each call
    its cost divided by the number of workers (they run in parallel), so the
    clock shows the time the scan would take."""
    limits = scanner.ScanLimits()
    assert (limits.sweep_workers, limits.port_workers) == (32, 16)
    clock = FakeClock()
    start = clock.monotonic()
    alive = [private_ip(n) for n in range(20, 80)]
    platform = StubPlatform(alive=alive, clock=clock,
                            ping_cost=3.0 / limits.sweep_workers)
    io = FakeNetIO(clock=clock, cost=2.0 / limits.port_workers, multicast_cost=4.0)
    scan = run(platform, io, clock=clock, limits=limits)
    elapsed = clock.monotonic() - start
    assert scan.complete, scan.stopped
    assert len(scan.devices) == 60
    assert elapsed <= thresholds.SCAN_TIME_LIMIT_S
    assert 10 < elapsed < 200          # also: it really did all the work


def test_defaults_match_the_design_document_numbers():
    limits = scanner.ScanLimits()
    assert limits.time_limit_s == 300.0
    assert limits.sweep_workers == 32 and limits.port_workers == 16
    assert limits.connect_timeout_s == 1.0 and limits.multicast_sends == 2
    assert thresholds.SCAN_MAX_HOSTS == 1022 and thresholds.SCAN_MIN_PREFIX == 22


def test_a_refusal_inside_the_network_layer_stops_the_scan():
    import pytest
    from network_health.scan_target import ScanRefused

    class Refusing(FakeNetIO):
        def multicast_query(self, *args, **kwargs):
            raise ScanRefused("outside")

    with pytest.raises(ScanRefused):
        run(StubPlatform(alive=[private_ip(20)]), Refusing())


def test_an_unexpected_error_in_a_multicast_query_is_a_note():
    class Broken(FakeNetIO):
        def multicast_query(self, *args, **kwargs):
            raise RuntimeError("boom")

    scan = run(StubPlatform(alive=[private_ip(20)]), Broken())
    assert any("RuntimeError: boom" in n for n in scan.notes)


def test_failed_pings_are_counted_apart_from_addresses_skipped_by_the_deadline():
    class Flaky(StubPlatform):
        def ping_host(self, target, timeout_ms):
            if int(target.rsplit(".", 1)[1]) % 2:
                raise Unavailable("error", "`ping` did not finish in time.")
            return target in self.alive

    scan = run(Flaky(alive=[private_ip(20)]), FakeNetIO())
    assert scan.addresses_failed > 100 and scan.addresses_skipped == 0
    assert scan.addresses_pinged + scan.addresses_failed == scan.addresses_total
    assert scan.complete and scan.stopped == ""        # not the time limit
    assert any("pings could not run" in n and "did not finish in time" in n for n in scan.notes)
    assert scan.meta_dict()["addresses_failed"] == scan.addresses_failed


def test_stopped_at_the_time_limit_is_only_said_when_the_deadline_was_the_cause():
    clock = FakeClock()
    limits = scanner.ScanLimits(sweep_workers=1, port_workers=1)
    platform = StubPlatform(alive=[private_ip(20)], clock=clock, ping_cost=1.0)
    scan = run(platform, FakeNetIO(clock=clock), clock=clock, limits=limits)
    assert scan.addresses_skipped > 0 and "ping sweep" in scan.stopped
    assert scan.addresses_pinged + scan.addresses_skipped == scan.addresses_total


def test_the_deadline_is_checked_again_after_the_rate_limit_wait():
    clock = FakeClock()
    # Starts are 10 s apart; the scan may last 20 s and no operation may start in
    # the last 6 s. Pings at 0 s and 10 s are fine; the one that waits until 20 s
    # must not start.
    limits = scanner.ScanLimits(sweep_workers=1, port_workers=1, time_limit_s=20.0,
                                sweep_budget_s=20.0, sweep_interval_s=10.0)
    platform = StubPlatform(alive=[private_ip(20)], clock=clock)
    start = clock.monotonic()
    scan = run(platform, FakeNetIO(clock=clock), clock=clock, limits=limits)
    assert len(platform.pings) == 2
    assert scan.addresses_skipped == 251 and not scan.complete
    assert clock.monotonic() - start <= 20.0


def test_the_arp_table_is_not_read_after_the_deadline():
    clock = FakeClock()
    limits = scanner.ScanLimits(sweep_workers=1, port_workers=1, time_limit_s=10.0,
                                sweep_budget_s=10.0)
    platform = StubPlatform(alive=[], neighbours=[neighbour(20, doc_mac(1))],
                            clock=clock, ping_cost=5.0)
    scan = run(platform, FakeNetIO(clock=clock), clock=clock, limits=limits)
    assert platform.arp_calls == 0 and scan.devices == []
    assert not scan.complete and "ARP table" in scan.stopped
    # With time left, it is read as before.
    platform = StubPlatform(alive=[], neighbours=[neighbour(20, doc_mac(1))])
    run(platform, FakeNetIO())
    assert platform.arp_calls == 1
