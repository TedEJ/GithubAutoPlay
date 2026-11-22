"""The bandwidth test with a fake opener and clock: no connection is opened."""

import urllib.error

import pytest

from network_health import bandwidth, known_hosts
from network_health.models import PingStats, Unavailable


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class FakeResponse:
    def __init__(self, clock, total, seconds_per_chunk):
        self.clock = clock
        self.left = total
        self.seconds_per_chunk = seconds_per_chunk

    def read(self, size=-1):
        if size is None or size < 0:
            self.clock.now += self.seconds_per_chunk
            return b"ok"
        if self.left <= 0:
            return b""
        n = min(size, self.left)
        self.left -= n
        self.clock.now += self.seconds_per_chunk
        return bytes(n)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeOpener:
    """Download: serves the requested bytes. Upload: reads the body in blocks
    the way http.client does, after setup_s of connection set-up."""

    def __init__(self, clock, *, download_seconds_per_chunk=0.01,
                 upload_bytes_per_s=5_000_000, setup_s=0.0, fail=None):
        self.clock = clock
        self.download_seconds_per_chunk = download_seconds_per_chunk
        self.upload_bytes_per_s = upload_bytes_per_s
        self.setup_s = setup_s
        self.fail = fail or set()
        self.requests = []
        self.upload_sizes = []

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        method = request.get_method()
        if method in self.fail:
            raise urllib.error.URLError("no route (fake)")
        self.clock.now += self.setup_s  # DNS, TCP and TLS
        if method == "GET":
            size = int(request.full_url.split("bytes=")[1])
            return FakeResponse(self.clock, size, self.download_seconds_per_chunk)
        sent = 0
        while True:
            block = request.data.read(8192)
            if not block:
                break
            sent += len(block)
            self.clock.now += len(block) / self.upload_bytes_per_s
        assert int(request.get_header("Content-length")) == sent
        self.upload_sizes.append(sent)
        return FakeResponse(self.clock, 0, 0.0)


def test_download_reads_all_bytes_on_a_fast_link():
    clock = Clock()
    opener = FakeOpener(clock, download_seconds_per_chunk=0.001)
    size, seconds = bandwidth.download(opener, clock)
    assert size == bandwidth.DOWNLOAD_MAX_BYTES
    assert opener.requests[0].full_url.startswith("https://speed.cloudflare.com/")
    assert bandwidth.mbps(size, seconds) > 25


def test_download_stops_early_on_a_slow_link():
    clock = Clock()
    opener = FakeOpener(clock, download_seconds_per_chunk=1.0)
    size, seconds = bandwidth.download(opener, clock)
    assert size < bandwidth.DOWNLOAD_MAX_BYTES
    assert seconds == pytest.approx(bandwidth.TIME_LIMIT_S)
    assert size == 10 * bandwidth.CHUNK_BYTES


def test_upload_scales_size_after_probe_and_respects_maximum():
    clock = Clock()
    opener = FakeOpener(clock, upload_bytes_per_s=50_000_000)
    size, seconds = bandwidth.upload(opener, clock)
    assert size == bandwidth.UPLOAD_MAX_BYTES
    assert opener.upload_sizes == [bandwidth.UPLOAD_PROBE_BYTES, bandwidth.UPLOAD_MAX_BYTES]
    assert opener.requests[0].full_url == known_hosts.SPEED_TEST_UPLOAD_URL


def test_upload_stops_after_probe_on_a_slow_link():
    clock = Clock()
    opener = FakeOpener(clock, upload_bytes_per_s=12_500)  # 0.1 Mbit/s
    size, seconds = bandwidth.upload(opener, clock)
    assert size == bandwidth.UPLOAD_PROBE_BYTES
    assert len(opener.requests) == 1
    assert bandwidth.mbps(size, seconds) == pytest.approx(0.1)
    assert seconds <= 10


def test_upload_medium_link_aims_at_target_duration():
    clock = Clock()
    opener = FakeOpener(clock, upload_bytes_per_s=500_000)  # 4 Mbit/s
    size, _ = bandwidth.upload(opener, clock)
    assert size == pytest.approx(500_000 * bandwidth.UPLOAD_TARGET_S, abs=10)


def test_connection_setup_is_not_counted_in_either_direction():
    clock = Clock()
    opener = FakeOpener(clock, upload_bytes_per_s=1_000_000, setup_s=2.0,
                        download_seconds_per_chunk=0.0)
    _, upload_seconds = bandwidth.upload(opener, clock, probe_bytes=100_000,
                                         max_bytes=100_000)
    assert upload_seconds == pytest.approx(0.1)  # not 2.1
    _, download_seconds = bandwidth.download(opener, clock, max_bytes=100_000)
    assert download_seconds == pytest.approx(0.0)


def test_timed_body_reads_in_blocks_and_notes_the_start():
    clock = Clock()
    clock.now = 5.0
    body = bandwidth.TimedBody(10, clock)
    assert body.started is None
    assert body.read(4) == bytes(4)
    assert body.started == 5.0
    assert body.read() == bytes(6)
    assert body.read(4) == b""


def test_whole_test_stays_near_30_seconds_on_a_very_slow_link():
    clock = Clock()
    rate = 12_500  # 0.1 Mbit/s in both directions
    opener = FakeOpener(clock, download_seconds_per_chunk=bandwidth.CHUNK_BYTES / rate,
                        upload_bytes_per_s=rate, setup_s=0.5)
    result = bandwidth.measure_bandwidth(opener=opener, clock=clock)
    assert result.download_mbps == pytest.approx(0.1, rel=0.05)
    assert result.upload_mbps == pytest.approx(0.1, rel=0.05)
    assert clock.now <= 30


class FakeSampler:
    def __init__(self, samples):
        self.samples = samples
        self.started = False

    def start(self):
        self.started = True

    def stop(self):
        return list(self.samples)


def test_measure_bandwidth_collects_both_directions_and_loaded_latency():
    clock = Clock()
    samplers = []

    def factory():
        samplers.append(FakeSampler([30.0, 32.0]))
        return samplers[-1]
    result = bandwidth.measure_bandwidth(opener=FakeOpener(clock), clock=clock,
                                         sampler_factory=factory)
    assert result.download_mbps > 0 and result.upload_mbps > 0
    assert result.server == known_hosts.SPEED_TEST_NAME
    assert len(samplers) == 2 and all(s.started for s in samplers)
    assert result.loaded_latency_ms == [30.0, 32.0, 30.0, 32.0]
    assert result.download_seconds > 0 and result.upload_seconds > 0


def test_measure_bandwidth_upload_failure_is_kept_as_error():
    clock = Clock()
    result = bandwidth.measure_bandwidth(opener=FakeOpener(clock, fail={"POST"}), clock=clock)
    assert result.download_mbps is not None
    assert result.upload_mbps is None
    assert "could not be used" in result.upload_error


def test_measure_bandwidth_total_failure_is_unavailable():
    clock = Clock()
    with pytest.raises(Unavailable) as info:
        bandwidth.measure_bandwidth(opener=FakeOpener(clock, fail={"GET", "POST"}),
                                    clock=clock)
    assert info.value.kind == "error"


class PingPlatform:
    def __init__(self, fail=False):
        self.fail = fail
        self.count = 0

    def ping(self, target, count, timeout_ms=1000):
        if self.fail:
            raise Unavailable("missing-tool", "no ping")
        self.count += 1
        return PingStats(target=target, sent=1, times_ms=[40.0])


def test_load_sampler_collects_until_max_samples():
    platform = PingPlatform()
    sampler = bandwidth.LoadSampler(platform, "1.1.1.1", interval_s=0, max_samples=3)
    sampler.start()
    sampler._thread.join(timeout=5)
    assert sampler.stop() == [40.0, 40.0, 40.0]


def test_load_sampler_stops_quietly_when_ping_is_missing():
    sampler = bandwidth.LoadSampler(PingPlatform(fail=True), "1.1.1.1", interval_s=0)
    sampler.start()
    assert sampler.stop() == []
