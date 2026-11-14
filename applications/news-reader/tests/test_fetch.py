"""The real fetch layer with a fake opener: no socket is ever opened."""
import http.client
import ssl
import urllib.error
import urllib.request

import pytest

from newsreader import fetch
from newsreader.fetch import FetchError, fetch_url, make_opener
from newsreader.parse import MAX_RESPONSE_BYTES

CHUNK = fetch.CHUNK_BYTES
URL = "https://news.example.invalid/feed.xml"
HOSTS = ["example.invalid"]


class FakeResponse:
    def __init__(self, body=b"<rss/>", status=200, headers=None, url=URL, fail_after=None):
        self.body, self.status, self.headers, self._url = body, status, headers or {}, url
        self.pos, self.reads, self.closed, self.fail_after = 0, 0, False, fail_after

    def geturl(self):
        return self._url

    def getcode(self):
        return self.status

    def read(self, n):
        self.reads += 1
        if self.fail_after is not None and self.pos >= self.fail_after:
            raise TimeoutError("slow")
        chunk = self.body[self.pos:self.pos + n]
        self.pos += len(chunk)
        return chunk

    def close(self):
        self.closed = True


class FakeOpener:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.requests, self.timeouts = response, error, [], []

    def open(self, request, timeout=None):
        self.requests.append(request)
        self.timeouts.append(timeout)
        if self.error:
            raise self.error
        return self.response


def test_success_sends_user_agent_and_timeout_and_no_cookie():
    opener = FakeOpener(FakeResponse(b"hello"))
    assert fetch_url(URL, HOSTS, opener=opener) == b"hello"
    request = opener.requests[0]
    assert request.get_header("User-agent") == "GithubAutoPlay-news-reader/1.0"
    assert not request.has_header("Cookie")
    assert opener.timeouts == [15]
    assert len(opener.requests) == 1  # one request


def test_default_opener_has_no_cookie_handler_and_has_the_redirect_rule():
    handlers = make_opener(HOSTS).handlers
    assert not any(isinstance(h, urllib.request.HTTPCookieProcessor) for h in handlers)
    assert any(isinstance(h, fetch._AllowedHostsRedirects) for h in handlers)


@pytest.mark.parametrize("status", [204, 301, 404, 500])
def test_status_other_than_200_fails(status):
    with pytest.raises(FetchError) as info:
        fetch_url(URL, HOSTS, opener=FakeOpener(FakeResponse(status=status)))
    assert info.value.kind == "status"


def test_http_error_is_a_status_failure():
    error = urllib.error.HTTPError(URL, 503, "unavailable", {}, None)
    with pytest.raises(FetchError) as info:
        fetch_url(URL, HOSTS, opener=FakeOpener(error=error))
    assert info.value.kind == "status" and "503" in str(info.value) and info.value.status == 503


def test_timeouts():
    for error in (TimeoutError("t"), urllib.error.URLError(TimeoutError("t"))):
        with pytest.raises(FetchError) as info:
            fetch_url(URL, HOSTS, opener=FakeOpener(error=error))
        assert info.value.kind == "timeout"


def test_timeout_while_reading_the_body():
    with pytest.raises(FetchError) as info:
        fetch_url(URL, HOSTS, opener=FakeOpener(FakeResponse(b"x" * 200000, fail_after=70000)))
    assert info.value.kind == "timeout"


def test_network_error():
    for error in (urllib.error.URLError("no route"), ConnectionResetError("reset")):
        with pytest.raises(FetchError) as info:
            fetch_url(URL, HOSTS, opener=FakeOpener(error=error))
        assert info.value.kind == "network"


def test_limit_is_enforced_while_streaming():
    big = FakeResponse(b"x" * (MAX_RESPONSE_BYTES * 3))  # no Content-Length header
    with pytest.raises(FetchError) as info:
        fetch_url(URL, HOSTS, opener=FakeOpener(big))
    assert info.value.kind == "too-large"
    assert big.pos <= MAX_RESPONSE_BYTES + fetch.CHUNK_BYTES  # the download stopped early
    assert big.closed


def test_exactly_the_limit_is_accepted():
    body = b"x" * MAX_RESPONSE_BYTES
    assert fetch_url(URL, HOSTS, opener=FakeOpener(FakeResponse(body))) == body


def test_declared_length_over_the_limit_is_refused_before_reading():
    response = FakeResponse(b"x", headers={"Content-Length": str(MAX_RESPONSE_BYTES + 1)})
    with pytest.raises(FetchError) as info:
        fetch_url(URL, HOSTS, opener=FakeOpener(response))
    assert info.value.kind == "too-large" and response.reads == 0


def test_redirect_handler_allows_allowed_hosts_only():
    handler = fetch._AllowedHostsRedirects(HOSTS)
    request = urllib.request.Request(URL)
    new = handler.redirect_request(request, None, 301, "moved", {}, "https://www.example.invalid/new.xml")
    assert new.full_url == "https://www.example.invalid/new.xml"
    for target in ("https://other.example.org/x", "http://news.example.invalid/x",
                   "https://example.invalid.evil.example.org/x", "file:///etc/passwd"):
        with pytest.raises(FetchError) as info:
            handler.redirect_request(request, None, 301, "moved", {}, target)
        assert info.value.kind == "redirect"


def test_final_url_on_another_host_is_refused():
    response = FakeResponse(url="https://other.example.org/feed.xml")
    with pytest.raises(FetchError) as info:
        fetch_url(URL, HOSTS, opener=FakeOpener(response))
    assert info.value.kind == "redirect"


def test_start_url_outside_allowed_hosts_is_not_requested():
    opener = FakeOpener(FakeResponse())
    with pytest.raises(FetchError):
        fetch_url("https://other.example.org/feed.xml", HOSTS, opener=opener)
    with pytest.raises(FetchError):
        fetch_url("http://news.example.invalid/feed.xml", HOSTS, opener=opener)
    assert opener.requests == []


class Clock:
    """A fake clock that moves on by `step` seconds each time it is read."""

    def __init__(self, step):
        self.now, self.step = 0.0, step

    def __call__(self):
        self.now += self.step
        return self.now


def test_total_time_limit_for_a_slow_download():
    body = b"x" * (CHUNK * 50)
    response = FakeResponse(body)
    with pytest.raises(FetchError) as info:
        fetch_url(URL, HOSTS, opener=FakeOpener(response), clock=Clock(10), total_seconds=60)
    assert info.value.kind == "timeout" and "60 seconds" in str(info.value)
    assert response.pos < len(body) and response.closed


def test_a_fast_download_is_inside_the_total_limit():
    assert fetch_url(URL, HOSTS, opener=FakeOpener(FakeResponse(b"ok")), clock=Clock(0.001)) == b"ok"


@pytest.mark.parametrize("error", [
    http.client.InvalidURL("bad"),
    http.client.BadStatusLine("x"),
    http.client.IncompleteRead(b"abc", 10),
    ValueError("odd"),
    ConnectionAbortedError("abort"),
])
def test_other_errors_while_opening_become_fetch_errors(error):
    with pytest.raises(FetchError) as info:
        fetch_url(URL, HOSTS, opener=FakeOpener(error=error))
    assert info.value.kind == "network"


class BrokenBody(FakeResponse):
    def __init__(self, error):
        super().__init__(b"x" * 10)
        self.error = error

    def read(self, n):
        raise self.error


@pytest.mark.parametrize("error", [
    http.client.IncompleteRead(b"abc", 10), http.client.HTTPException("x"), ValueError("v"),
    ConnectionResetError("r")])
def test_errors_while_reading_become_fetch_errors(error):
    response = BrokenBody(error)
    with pytest.raises(FetchError) as info:
        fetch_url(URL, HOSTS, opener=FakeOpener(response))
    assert info.value.kind == "network" and response.closed



class SlowSocketResponse(FakeResponse):
    """Data arrives one byte per `delay` seconds on a fake clock. `read(n)` blocks until it
    has all n bytes (as a real socket read does); `read1(n)` returns after the first byte."""

    def __init__(self, clock, delay=0.2, size=200000):
        super().__init__(b"x" * size)
        self.clock, self.delay = clock, delay

    def _take(self, count):
        count = min(count, len(self.body) - self.pos)
        self.clock.now += count * self.delay
        self.pos += count
        return b"x" * count

    def read(self, n):
        return self._take(n)

    def read1(self, n):
        return self._take(1)


def test_total_limit_holds_against_a_server_that_sends_one_byte_at_a_time():
    clock = Clock(0)
    response = SlowSocketResponse(clock)
    with pytest.raises(FetchError) as info:
        fetch_url(URL, HOSTS, opener=FakeOpener(response), clock=clock, total_seconds=2)
    assert info.value.kind == "timeout"
    assert response.pos <= 12  # stopped after about 2 s of data; read() would have waited for 64 KiB
    assert clock.now < 3
    assert response.closed


# ---- certificate errors (verification stays on, the message is fixed) -------------

def _verify_error():
    return ssl.SSLCertVerificationError(
        1, "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer "
           "certificate for hostile.example.invalid https://evil.example.invalid/x")


@pytest.mark.parametrize("error", [
    urllib.error.URLError(_verify_error()),          # how urllib wraps it
    _verify_error(),                                  # raised bare
])
def test_certificate_failure_is_its_own_kind_with_a_fixed_message(error):
    with pytest.raises(FetchError) as info:
        fetch_url(URL, HOSTS, opener=FakeOpener(error=error))
    assert info.value.kind == "certificate"
    assert str(info.value) == fetch.CERTIFICATE_MESSAGE
    assert "full certificate chain" in str(info.value) and "README" in str(info.value)
    for text in ("http", "example", "hostile", "CERTIFICATE_VERIFY", "issuer"):
        assert text not in str(info.value)


@pytest.mark.parametrize("error", [urllib.error.URLError(ssl.SSLError("handshake failure")),
                                   ssl.SSLError("handshake failure")])
def test_other_tls_errors_stay_network(error):
    with pytest.raises(FetchError) as info:
        fetch_url(URL, HOSTS, opener=FakeOpener(error=error))
    assert info.value.kind == "network" and str(info.value) == "network error"


def test_make_fetch_passes_the_context_to_the_opener_used_by_fetch_url(monkeypatch):
    context = ssl.create_default_context()
    seen = []

    def fake_make_opener(allowed_hosts, ctx=None):
        seen.append((tuple(allowed_hosts), ctx))
        return FakeOpener(FakeResponse(b"<rss/>"))

    monkeypatch.setattr(fetch, "make_opener", fake_make_opener)
    assert fetch.make_fetch(context)(URL, HOSTS) == b"<rss/>"
    assert seen == [(tuple(HOSTS), context)]
    assert seen[0][1] is context


def test_make_opener_uses_the_given_context():
    context = ssl.create_default_context()
    opener = make_opener(HOSTS, context)
    handlers = [h for h in opener.handlers if isinstance(h, urllib.request.HTTPSHandler)]
    assert len(handlers) == 1 and handlers[0]._context is context
    assert any(isinstance(h, fetch._AllowedHostsRedirects) for h in opener.handlers)


def test_make_ssl_context_keeps_verification_on(tmp_path):
    path = tmp_path / "extra.pem"
    path.write_text(TEST_CERTIFICATE_PEM, encoding="ascii")
    context = fetch.make_ssl_context(str(path))
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname is True


def test_make_ssl_context_refuses_bad_files(tmp_path):
    (tmp_path / "text.pem").write_text("this is not a certificate\n", encoding="ascii")
    import base64
    der = base64.b64decode("".join(l for l in TEST_CERTIFICATE_PEM.splitlines() if "-----" not in l))
    (tmp_path / "cert.der").write_bytes(der)  # the same certificate, binary: not accepted
    for bad in (tmp_path / "missing.pem", tmp_path, tmp_path / "text.pem", tmp_path / "cert.der"):
        with pytest.raises(fetch.CaFileError) as info:
            fetch.make_ssl_context(str(bad))
        assert str(tmp_path) not in str(info.value)


# A throwaway self-signed certificate made for these tests only: public, no private key
# exists anywhere, and it is not trusted by anything.
TEST_CERTIFICATE_PEM = """-----BEGIN CERTIFICATE-----
MIIDTzCCAjegAwIBAgIUUhtVL2rNKYxiXCMoKobGbWE/Pe4wDQYJKoZIhvcNAQEL
BQAwNjE0MDIGA1UEAwwrbmV3c3JlYWRlciB0ZXN0IGNlcnRpZmljYXRlIChub3Qg
YSByZWFsIENBKTAgFw0yNjExMTQyMDE3MDBaGA8yMTI2MTAyMTIwMTcwMFowNjE0
MDIGA1UEAwwrbmV3c3JlYWRlciB0ZXN0IGNlcnRpZmljYXRlIChub3QgYSByZWFs
IENBKTCCASIwDQYJKoZIhvcNAQEBBQADggEPADCCAQoCggEBAJzZT345AbInMnA9
21Gz2ExtdBAERaeyfumBR4q6ZPYK+//ukG2rFLyNlXvN4WzRTsSnk74tfL9ZLngd
zQxnxNhlctbczCkFvHLIvW1x49hK15xPrwFQ9/97rVgk1vJAU7Fim2BQSs1ffasC
GXKPbNbtKn3Zesa4cZk1V78UWddR5nuX5PPhVIIWqr6mHpjPNf1aiicxFGPbm3/7
0B2oMA9L+YQnhgFcJHggC3S+8VurqhfuUstjhb17o3CVVEdV0n9wcybKZy4TLmDq
zIjqoVr4qn+GZ9AZvYicKOCpv14l5CbYSFFyof/V+CoMQI669bk4cRh0IaSxX+QT
8nNixcECAwEAAaNTMFEwHQYDVR0OBBYEFOG8Ks5crUqdrAGtTv6QqCFEy07TMB8G
A1UdIwQYMBaAFOG8Ks5crUqdrAGtTv6QqCFEy07TMA8GA1UdEwEB/wQFMAMBAf8w
DQYJKoZIhvcNAQELBQADggEBAIDGkWm20zxRwjHwKdZkeVYIV3BbV1jZ05HCm/l4
HooO9KaLFZ/IQ/tzkJyA/ro5sqVzxENtOpW7wewlKzOpBg4NmAUBqyFCRC8wjhcp
Hg/XFFSxeYVrOc8pQ8wJhAAz2ey5eJ3EHWVVFVYBT0Ln81O5fOFtwt5c4IM/brk5
iOQIPZMRwEzETJ4sBhGVHd7l7aa53yAnJh56qlKhEOda8TY87m1XhbeGFjlTKu8w
geJHAIpUALjy0cGjWVcOW89kLaDgV0QUXllAdvWSx6284S3EDKw0U68DTbpSqZ/O
vPVjC4EBYJKSVoTCJ+6geRP2JwIBP8YrARTeO/i0QTsL1nU=
-----END CERTIFICATE-----
"""
