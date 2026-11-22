"""Bandwidth (download and upload) and latency under load (bufferbloat).

The only check that sends noticeable traffic to a third party. The server is
named in known_hosts.py and in the report, and --skip-bandwidth turns it off.

Limits: the download stops at DOWNLOAD_MAX_BYTES or after TIME_LIMIT_S,
whichever comes first. The upload first sends a small probe (100 kB); on a
slow link it stops there, otherwise it sends about UPLOAD_TARGET_S worth of
data, at most UPLOAD_MAX_BYTES. Even at about 0.1 Mbit/s the whole test stays
near 30 seconds.

Timing: neither direction counts connection set-up (DNS, TCP, TLS). The
download clock starts when the response headers have arrived; the upload
clock starts when urllib reads the first block of the body, which happens
after the connection is open and the request headers are sent.

The opener (urllib.request.urlopen by default), the clock and the latency
sampler are parameters, so tests run without a network.
"""

from __future__ import annotations

import threading
import time
import urllib.error
import urllib.request
from typing import Callable

from . import known_hosts
from .models import BandwidthResult, Unavailable

DOWNLOAD_MAX_BYTES = 25_000_000
UPLOAD_PROBE_BYTES = 100_000
UPLOAD_MAX_BYTES = 10_000_000
TIME_LIMIT_S = 10.0
UPLOAD_TARGET_S = 8.0
UPLOAD_SLOW_PROBE_S = 4.0
CHUNK_BYTES = 16 * 1024  # small, so a slow link overshoots the time limit little
REQUEST_TIMEOUT_S = 30.0
SAMPLE_INTERVAL_S = 0.05
USER_AGENT = "network-health/0.1 (Python urllib)"

_NETWORK_ERRORS = (urllib.error.URLError, OSError, TimeoutError, ValueError)


def mbps(byte_count: int, seconds: float) -> float:
    return byte_count * 8 / max(seconds, 1e-6) / 1_000_000


def download(opener: Callable, clock: Callable[[], float], *,
             max_bytes: int = DOWNLOAD_MAX_BYTES,
             time_limit: float = TIME_LIMIT_S) -> tuple[int, float]:
    url = known_hosts.SPEED_TEST_DOWNLOAD_URL.format(bytes=max_bytes)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    total = 0
    with opener(request, timeout=REQUEST_TIMEOUT_S) as response:
        start = clock()  # after the headers: connection set-up is not counted
        while total < max_bytes:
            chunk = response.read(CHUNK_BYTES)
            if not chunk:
                break
            total += len(chunk)
            if clock() - start >= time_limit:
                break  # slow link: stop early
        elapsed = clock() - start
    return total, elapsed


class TimedBody:
    """An upload body that notes when its first block is read.

    http.client reads a file-like body only after it has opened the
    connection and sent the headers, so the first read marks the start of
    the transfer itself.
    """

    def __init__(self, size: int, clock: Callable[[], float]):
        self.size = size
        self.left = size
        self.clock = clock
        self.started: float | None = None

    def read(self, block: int = -1) -> bytes:
        if self.started is None:
            self.started = self.clock()
        if block is None or block < 0:
            block = self.left
        n = min(block, self.left)
        self.left -= n
        return bytes(n)


def _post(opener: Callable, clock: Callable[[], float], size: int) -> float:
    body = TimedBody(size, clock)
    request = urllib.request.Request(
        known_hosts.SPEED_TEST_UPLOAD_URL,
        data=body,
        method="POST",
        headers={"User-Agent": USER_AGENT,
                 "Content-Type": "application/octet-stream",
                 "Content-Length": str(size)},
    )
    before = clock()
    with opener(request, timeout=REQUEST_TIMEOUT_S) as response:
        response.read()
    end = clock()
    return end - (body.started if body.started is not None else before)


def upload(opener: Callable, clock: Callable[[], float], *,
           probe_bytes: int = UPLOAD_PROBE_BYTES,
           max_bytes: int = UPLOAD_MAX_BYTES) -> tuple[int, float]:
    probe_time = _post(opener, clock, probe_bytes)
    if probe_time >= UPLOAD_SLOW_PROBE_S:
        return probe_bytes, probe_time  # slow link: the probe is the result
    rate = probe_bytes / max(probe_time, 1e-6)  # bytes per second
    size = int(min(max(rate * UPLOAD_TARGET_S, probe_bytes), max_bytes))
    return size, _post(opener, clock, size)


class LoadSampler:
    """Pings a target again and again while a transfer runs."""

    def __init__(self, platform, target: str, interval_s: float = SAMPLE_INTERVAL_S,
                 max_samples: int = 400):
        self.platform = platform
        self.target = target
        self.interval_s = interval_s
        self.max_samples = max_samples
        self.samples: list[float] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _loop(self) -> None:
        while not self._stop.is_set() and len(self.samples) < self.max_samples:
            try:
                stats = self.platform.ping(self.target, 1)
            except Unavailable:
                return
            if self._stop.is_set():
                return  # the reply may come from after the load ended
            self.samples.extend(stats.times_ms)
            self._stop.wait(self.interval_s)

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> list[float]:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        return list(self.samples)


def measure_bandwidth(
    *,
    opener: Callable = urllib.request.urlopen,
    clock: Callable[[], float] = time.perf_counter,
    sampler_factory: Callable[[], object] | None = None,
) -> BandwidthResult:
    """Run the download and the upload. Raises Unavailable when neither works."""
    result = BandwidthResult(server=known_hosts.SPEED_TEST_NAME)
    for direction in ("download", "upload"):
        sampler = sampler_factory() if sampler_factory else None
        if sampler is not None:
            sampler.start()
        try:
            if direction == "download":
                size, seconds = download(opener, clock)
                result.download_bytes = size
                result.download_seconds = seconds
                result.download_mbps = mbps(size, seconds)
            else:
                size, seconds = upload(opener, clock)
                result.upload_bytes = size
                result.upload_seconds = seconds
                result.upload_mbps = mbps(size, seconds)
        except _NETWORK_ERRORS as exc:
            message = f"the speed-test server could not be used ({exc})"
            if direction == "download":
                result.download_error = message
            else:
                result.upload_error = message
        finally:
            if sampler is not None:
                result.loaded_latency_ms.extend(sampler.stop())
    if result.download_mbps is None and result.upload_mbps is None:
        raise Unavailable("error", "The bandwidth test failed: "
                                   f"{result.download_error}.")
    return result
