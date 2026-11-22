"""The one place where the active scan opens a socket.

Everything the device scan sends goes through a NetIO object, like system
commands go through the Runner. Tests replace it with a fake that answers
from made-up data, so no test opens a real socket. (The ping sweep is the
exception: it uses the system ping through the platform layer and the
Runner.)

RealNetIO sends only:

* a TCP connect to one port of one address of the scanned subnet, and then
  - for a banner port: waits for what the service volunteers (nothing is
    sent),
  - for an HTTP port: sends one HEAD request,
  - for an HTTPS port: does a TLS handshake without checking the
    certificate and sends nothing after it (no credentials, no request);
* one UDP query to the mDNS group 224.0.0.251:5353 and one to the SSDP group
  239.255.255.250:1900, on the local link only (TTL 1).

Every destination is checked by the ScanGuard before a socket is opened.
Nothing is read beyond a small limit.
"""

from __future__ import annotations

import socket
import ssl
import time
from dataclasses import dataclass

from .scan_target import ScanGuard


class NetIOError(Exception):
    """The multicast socket could not be set up (the scan goes on without it)."""


@dataclass
class ProbeResult:
    open: bool                  # the TCP connection was accepted
    data: bytes = b""           # banner or HTTP answer (at most the read limit)
    tls_version: str = ""       # set when a TLS handshake worked


class NetIO:
    """The interface the scanner uses. RealNetIO implements it; tests use a
    fake."""

    def connect(self, ip: str, port: int, timeout: float) -> ProbeResult:
        raise NotImplementedError

    def banner(self, ip: str, port: int, timeout: float, wait: float,
               max_bytes: int) -> ProbeResult:
        raise NotImplementedError

    def http_head(self, ip: str, port: int, timeout: float, wait: float,
                  max_bytes: int) -> ProbeResult:
        raise NotImplementedError

    def tls_handshake(self, ip: str, port: int, timeout: float) -> ProbeResult:
        raise NotImplementedError

    def multicast_query(self, group: str, port: int, payload: bytes, *,
                        local_ip: str, sends: int, wait: float,
                        max_packets: int) -> list[tuple[str, bytes]]:
        """Send payload to the group `sends` times and return (sender, data)
        of the answers that arrived within `wait` seconds after each send."""
        raise NotImplementedError


HTTP_REQUEST = (
    "HEAD / HTTP/1.0\r\n"
    "Host: {host}\r\n"
    "User-Agent: network-health\r\n"
    "Accept: */*\r\n"
    "Connection: close\r\n"
    "\r\n"
)


class RealNetIO(NetIO):
    def __init__(self, guard: ScanGuard):
        self.guard = guard

    # -- TCP

    def _open(self, ip: str, port: int, timeout: float) -> socket.socket | None:
        address = str(self.guard.check_host(ip))
        try:
            return socket.create_connection((address, port), timeout=timeout)
        except OSError:
            return None

    def connect(self, ip, port, timeout):
        sock = self._open(ip, port, timeout)
        if sock is None:
            return ProbeResult(False)
        sock.close()
        return ProbeResult(True)

    def banner(self, ip, port, timeout, wait, max_bytes):
        sock = self._open(ip, port, timeout)
        if sock is None:
            return ProbeResult(False)
        with sock:
            return ProbeResult(True, _read(sock, wait, max_bytes, stop_at_headers=False))

    def http_head(self, ip, port, timeout, wait, max_bytes):
        sock = self._open(ip, port, timeout)
        if sock is None:
            return ProbeResult(False)
        with sock:
            try:
                sock.settimeout(wait)
                sock.sendall(HTTP_REQUEST.format(host=ip).encode("ascii"))
            except OSError:
                return ProbeResult(True)
            return ProbeResult(True, _read(sock, wait, max_bytes, stop_at_headers=True))

    def tls_handshake(self, ip, port, timeout):
        sock = self._open(ip, port, timeout)
        if sock is None:
            return ProbeResult(False)
        with sock:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            # The certificate of a home device is almost always self-signed:
            # it is not checked, because nothing is sent over this connection
            # but the handshake itself.
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            try:
                context.minimum_version = ssl.TLSVersion.TLSv1  # old devices
                context.set_ciphers("DEFAULT:@SECLEVEL=0")
            except (ssl.SSLError, ValueError, AttributeError):
                pass
            try:
                sock.settimeout(timeout)
                with context.wrap_socket(sock, server_hostname=None) as tls:
                    return ProbeResult(True, tls_version=tls.version() or "TLS")
            except (OSError, ssl.SSLError, ValueError):
                return ProbeResult(True)

    # -- multicast

    def multicast_query(self, group, port, payload, *, local_ip, sends, wait,
                        max_packets):
        ScanGuard.check_multicast(group, port)
        self.guard.check_own(local_ip)
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        except OSError as exc:
            raise NetIOError(str(exc)) from exc
        answers: list[tuple[str, bytes]] = []
        with sock:
            try:
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 0)
                sock.bind((local_ip, 0))
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF,
                                socket.inet_aton(local_ip))
            except OSError as exc:
                raise NetIOError(str(exc)) from exc
            for _ in range(sends):
                try:
                    sock.sendto(payload, (group, port))
                except OSError as exc:
                    raise NetIOError(str(exc)) from exc
                end = time.monotonic() + wait
                while len(answers) < max_packets:
                    left = end - time.monotonic()
                    if left <= 0:
                        break
                    sock.settimeout(left)
                    try:
                        data, sender = sock.recvfrom(4096)
                    except (socket.timeout, BlockingIOError):
                        break
                    except OSError:
                        break  # for example a connection-reset notice on Windows
                    answers.append((sender[0], data))
        return answers


def _read(sock: socket.socket, wait: float, max_bytes: int, *,
          stop_at_headers: bool) -> bytes:
    """Read at most max_bytes within about `wait` seconds."""
    chunks: list[bytes] = []
    total = 0
    end = time.monotonic() + wait
    while total < max_bytes:
        left = end - time.monotonic()
        if left <= 0:
            break
        sock.settimeout(left)
        try:
            chunk = sock.recv(max_bytes - total)
        except OSError:
            break
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if stop_at_headers and b"\r\n\r\n" in b"".join(chunks):
            break
    return b"".join(chunks)
