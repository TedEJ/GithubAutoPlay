"""RealNetIO with fake sockets: what it sends and how much it reads. The real
socket functions are replaced, so nothing leaves the computer."""

import socket
import ssl

import pytest
from conftest import make_target, private_ip

from network_health import netio, thresholds
from network_health.netio import NetIOError, RealNetIO
from network_health.scan_target import ScanGuard


class FakeTcp:
    def __init__(self, chunks=(), send_error=None):
        self.chunks = list(chunks)
        self.sent = []
        self.timeouts = []
        self.closed = False
        self.send_error = send_error

    def settimeout(self, value):
        self.timeouts.append(value)

    def sendall(self, data):
        if self.send_error:
            raise self.send_error
        self.sent.append(data)

    def recv(self, n):
        if not self.chunks:
            raise socket.timeout()
        return self.chunks.pop(0)[:n]

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


@pytest.fixture
def io():
    return RealNetIO(ScanGuard(make_target()))


def connects_to(monkeypatch, sock):
    opened = []

    def create_connection(address, timeout=None):
        opened.append((address, timeout))
        if sock is None:
            raise ConnectionRefusedError()
        return sock

    monkeypatch.setattr(socket, "create_connection", create_connection)
    return opened


def test_closed_port_is_reported_closed(monkeypatch, io):
    connects_to(monkeypatch, None)
    assert io.connect(private_ip(20), 23, 1.0).open is False
    assert io.banner(private_ip(20), 23, 1.0, 1.0, 256).open is False


def test_connect_only_connects_and_sends_nothing(monkeypatch, io):
    sock = FakeTcp()
    opened = connects_to(monkeypatch, sock)
    assert io.connect(private_ip(20), 445, 1.0).open is True
    assert opened == [((private_ip(20), 445), 1.0)]
    assert sock.sent == [] and sock.closed


def test_banner_port_sends_nothing_and_reads_at_most_the_limit(monkeypatch, io):
    sock = FakeTcp([b"A" * 100, b"B" * 400])
    connects_to(monkeypatch, sock)
    result = io.banner(private_ip(20), 21, 1.0, 1.0, 256)
    assert result.open and sock.sent == []
    assert len(result.data) == 256 and result.data.startswith(b"A" * 100 + b"B")


def test_silent_service_gives_an_empty_banner(monkeypatch, io):
    connects_to(monkeypatch, FakeTcp())
    result = io.banner(private_ip(20), 22, 1.0, 0.05, 256)
    assert result.open and result.data == b""


def test_http_head_sends_one_small_head_request(monkeypatch, io):
    sock = FakeTcp([b"HTTP/1.0 200 OK\r\nServer: X\r\n\r\n", b"body that is never read"])
    connects_to(monkeypatch, sock)
    result = io.http_head(private_ip(20), 80, 1.0, 2.0, thresholds.HTTP_MAX_BYTES)
    [request] = sock.sent
    assert request.startswith(b"HEAD / HTTP/1.0\r\n") and request.endswith(b"\r\n\r\n")
    assert b"Authorization" not in request and b"Cookie" not in request
    assert len(request) < 200
    assert result.data.startswith(b"HTTP/1.0 200 OK") and b"never read" not in result.data


def test_http_head_survives_a_failing_send(monkeypatch, io):
    connects_to(monkeypatch, FakeTcp(send_error=OSError("reset")))
    result = io.http_head(private_ip(20), 80, 1.0, 2.0, 2048)
    assert result.open and result.data == b""


class FakeContext:
    instances = []
    fail = None

    def __init__(self, protocol):
        self.protocol = protocol
        self.sent_nothing = True
        FakeContext.instances.append(self)

    def set_ciphers(self, ciphers):
        pass

    def wrap_socket(self, sock, server_hostname=None):
        if FakeContext.fail:
            raise FakeContext.fail
        context = self

        class Wrapped:
            def version(self):
                return "TLSv1.2"

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        assert server_hostname is None
        assert context.verify_mode == ssl.CERT_NONE and context.check_hostname is False
        return Wrapped()


def test_tls_handshake_does_not_verify_and_sends_nothing(monkeypatch, io):
    sock = FakeTcp()
    connects_to(monkeypatch, sock)
    FakeContext.fail = None
    monkeypatch.setattr(netio.ssl, "SSLContext", FakeContext)
    result = io.tls_handshake(private_ip(20), 443, 2.0)
    assert result.open and result.tls_version == "TLSv1.2"
    assert sock.sent == []


def test_failed_handshake_still_reports_the_port_open(monkeypatch, io):
    connects_to(monkeypatch, FakeTcp())
    FakeContext.fail = ssl.SSLError("not tls")
    monkeypatch.setattr(netio.ssl, "SSLContext", FakeContext)
    result = io.tls_handshake(private_ip(20), 8443, 2.0)
    assert result.open and result.tls_version == ""
    FakeContext.fail = None


class FakeUdp:
    def __init__(self, packets=(), fail_on=None):
        self.packets = list(packets)
        self.options = []
        self.bound = None
        self.sent = []
        self.fail_on = fail_on

    def setsockopt(self, level, option, value):
        if self.fail_on == "setsockopt":
            raise OSError("no multicast")
        self.options.append((option, value))

    def bind(self, address):
        self.bound = address

    def settimeout(self, value):
        pass

    def sendto(self, data, address):
        if self.fail_on == "sendto":
            raise OSError("network is unreachable")
        self.sent.append((data, address))

    def recvfrom(self, n):
        if not self.packets:
            raise socket.timeout()
        return self.packets.pop(0)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_multicast_query_stays_on_the_link_and_collects_answers(monkeypatch, io):
    udp = FakeUdp([(b"one", (private_ip(30), 5353)), (b"two", (private_ip(31), 5353))])
    monkeypatch.setattr(socket, "socket", lambda *a, **k: udp)
    answers = io.multicast_query("224.0.0.251", 5353, b"query", local_ip=private_ip(10),
                                 sends=2, wait=0.05, max_packets=10)
    assert answers == [(private_ip(30), b"one"), (private_ip(31), b"two")]
    assert udp.sent == [(b"query", ("224.0.0.251", 5353))] * 2     # sent twice, to the group
    assert (socket.IP_MULTICAST_TTL, 1) in udp.options             # not past the router
    assert udp.bound == (private_ip(10), 0)


def test_multicast_query_stops_at_the_packet_limit(monkeypatch, io):
    udp = FakeUdp([(b"x", (private_ip(30), 1))] * 20)
    monkeypatch.setattr(socket, "socket", lambda *a, **k: udp)
    answers = io.multicast_query("239.255.255.250", 1900, b"q", local_ip=private_ip(10),
                                 sends=1, wait=0.05, max_packets=5)
    assert len(answers) == 5


@pytest.mark.parametrize("fail_on", ["setsockopt", "sendto"])
def test_multicast_problems_become_netio_error(monkeypatch, io, fail_on):
    udp = FakeUdp(fail_on=fail_on)
    monkeypatch.setattr(socket, "socket", lambda *a, **k: udp)
    with pytest.raises(NetIOError):
        io.multicast_query("224.0.0.251", 5353, b"q", local_ip=private_ip(10), sends=1,
                           wait=0.05, max_packets=5)
