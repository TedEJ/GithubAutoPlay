"""DNS timing with a fake socket and clock: no packet is sent."""

import socket
import struct

from network_health import dnsprobe


def test_build_query_layout():
    packet = dnsprobe.build_query("example.com", 0x1234)
    query_id, flags, qd, an, ns, ar = struct.unpack(">HHHHHH", packet[:12])
    assert (query_id, flags, qd, an, ns, ar) == (0x1234, 0x0100, 1, 0, 0, 0)
    assert packet[12:] == b"\x07example\x03com\x00\x00\x01\x00\x01"


def test_is_answer():
    reply = struct.pack(">HHHHHH", 7, 0x8180, 1, 1, 0, 0)
    assert dnsprobe.is_answer(reply, 7)
    assert not dnsprobe.is_answer(reply, 8)
    assert not dnsprobe.is_answer(struct.pack(">HHHHHH", 7, 0x0100, 1, 0, 0, 0), 7)
    assert not dnsprobe.is_answer(b"\x00", 7)


class FakeClock:
    def __init__(self, step):
        self.now = 100.0
        self.step = step

    def __call__(self):
        value = self.now
        self.now += self.step
        return value


class FakeSocket:
    """Answers each query once (or never), and records where it was sent."""
    sent_to = []

    def __init__(self, family, kind, answer=True, wrong_id_first=False):
        self.family = family
        self.answer = answer
        self.wrong_id_first = wrong_id_first
        self.packet = None
        self.closed = False

    def settimeout(self, value):
        self.timeout = value

    def sendto(self, packet, address):
        FakeSocket.sent_to.append(address)
        self.packet = packet

    def recvfrom(self, size):
        if not self.answer:
            raise socket.timeout()
        query_id = struct.unpack(">H", self.packet[:2])[0]
        if self.wrong_id_first:
            self.wrong_id_first = False
            query_id ^= 1
        return struct.pack(">HHHHHH", query_id, 0x8180, 1, 1, 0, 0), ("x", 53)

    def close(self):
        self.closed = True


def test_query_time_measures_and_sends_to_the_resolver_only():
    FakeSocket.sent_to = []
    ms = dnsprobe.query_time("192.0.2.1", "example.com",
                             socket_factory=FakeSocket, clock=FakeClock(0.012))
    assert round(ms) == 12
    assert FakeSocket.sent_to == [("192.0.2.1", 53)]


def test_query_time_ignores_unrelated_packets():
    ms = dnsprobe.query_time(
        "192.0.2.1", "example.com",
        socket_factory=lambda f, k: FakeSocket(f, k, wrong_id_first=True),
        clock=FakeClock(0.01))
    assert ms is not None


def test_query_time_without_answer_is_none():
    assert dnsprobe.query_time(
        "192.0.2.1", "example.com",
        socket_factory=lambda f, k: FakeSocket(f, k, answer=False),
        clock=FakeClock(0.01)) is None


def test_query_time_ipv6_resolver_uses_ipv6_socket():
    families = []

    def factory(family, kind):
        families.append(family)
        return FakeSocket(family, kind)
    dnsprobe.query_time("2001:db8::53", "example.com", socket_factory=factory,
                        clock=FakeClock(0.01))
    assert families == [socket.AF_INET6]


def test_measure_resolver_counts_failures():
    answers = iter([True, False, True])
    timing = dnsprobe.measure_resolver(
        "192.0.2.1", ["a.example", "b.example", "c.example"],
        socket_factory=lambda f, k: FakeSocket(f, k, answer=next(answers)),
        clock=FakeClock(0.02))
    assert timing.failures == 1
    assert len(timing.times_ms) == 2
    assert round(timing.median_ms) == 20


def test_measure_resolver_with_bad_address_counts_failures():
    timing = dnsprobe.measure_resolver("not-an-address", ["a.example"],
                                       socket_factory=FakeSocket)
    assert timing.failures == 1 and timing.median_ms is None
