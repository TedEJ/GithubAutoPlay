"""Time DNS lookups against one resolver, with the standard library only.

A small DNS query (type A) is sent over UDP straight to the resolver, so the
time measured is the resolver's answer time, not the time to start a program.
Only the resolvers the computer is configured with are asked. Tests pass a
fake socket factory and clock, so no packet is sent.
"""

from __future__ import annotations

import random
import socket
import struct
import time
from typing import Callable, Iterable

from .models import DnsTiming

DNS_PORT = 53


def build_query(name: str, query_id: int) -> bytes:
    header = struct.pack(">HHHHHH", query_id, 0x0100, 1, 0, 0, 0)  # RD set
    labels = b"".join(
        bytes([len(part)]) + part.encode("ascii")
        for part in name.rstrip(".").split(".") if part
    )
    return header + labels + b"\x00" + struct.pack(">HH", 1, 1)  # A, IN


def is_answer(data: bytes, query_id: int) -> bool:
    """True when data is a DNS response to query_id (any return code)."""
    if len(data) < 12:
        return False
    answer_id, flags = struct.unpack(">HH", data[:4])
    return answer_id == query_id and bool(flags & 0x8000)


def _sockaddr(server: str):
    # AI_NUMERICHOST: the server is an address, so no lookup is made here.
    info = socket.getaddrinfo(server, DNS_PORT, type=socket.SOCK_DGRAM,
                              flags=socket.AI_NUMERICHOST)
    family, _, _, _, sockaddr = info[0]
    return family, sockaddr


def query_time(
    server: str,
    name: str,
    *,
    socket_factory: Callable = socket.socket,
    clock: Callable[[], float] = time.perf_counter,
    timeout: float = 2.0,
) -> float | None:
    """Milliseconds until the resolver answered, or None without an answer."""
    family, sockaddr = _sockaddr(server)
    query_id = random.randrange(0, 0x10000)
    packet = build_query(name, query_id)
    sock = socket_factory(family, socket.SOCK_DGRAM)
    try:
        sock.settimeout(timeout)
        start = clock()
        sock.sendto(packet, sockaddr)
        deadline = start + timeout
        while True:
            try:
                data, _ = sock.recvfrom(4096)
            except (socket.timeout, TimeoutError, OSError):
                return None
            if is_answer(data, query_id):
                return (clock() - start) * 1000.0
            if clock() >= deadline:
                return None
    finally:
        sock.close()


def measure_resolver(server: str, names: Iterable[str], **kwargs) -> DnsTiming:
    timing = DnsTiming(server=server)
    for name in names:
        try:
            elapsed = query_time(server, name, **kwargs)
        except (OSError, ValueError):
            elapsed = None
        if elapsed is None:
            timing.failures += 1
        else:
            timing.times_ms.append(elapsed)
    return timing
