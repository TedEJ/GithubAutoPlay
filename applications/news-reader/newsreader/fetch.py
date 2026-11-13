"""The only network module of the build (R6.2, R6.5, R9.4).

Standard library only (`urllib`). One call fetches one URL and returns the
undecoded body as bytes, or raises `FetchError`. Rules:

* `User-Agent: GithubAutoPlay-news-reader/1.0`, no cookies (no cookie handler
  is installed, and no `Cookie` header is sent).
* Timeout of 15 seconds per request.
* Redirects are followed only to `https` addresses on the source's
  `allowedHosts` (or a subdomain of one); any other redirect is an error.
* The body is read in chunks and the download stops as soon as it is larger
  than `MAX_RESPONSE_BYTES` (2 MiB); a larger `Content-Length` is refused
  before reading.
* Only status 200 is a success.

The build calls `fetch_url` through an injected function, so every test uses a
fake with the same signature and never touches the network.
"""
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from .parse import MAX_RESPONSE_BYTES

USER_AGENT = "GithubAutoPlay-news-reader/1.0"
TIMEOUT_SECONDS = 15
CHUNK_BYTES = 64 * 1024


class FetchError(Exception):
    """A request failed. `kind` is one of: network, timeout, status, too-large, redirect."""

    def __init__(self, kind, message):
        super().__init__(message)
        self.kind = kind


def host_allowed(url, allowed_hosts):
    """True if `url` is https and its host is an allowed host or a subdomain of one."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not host:
        return False
    return any(host == h or host.endswith("." + h) for h in allowed_hosts)


class _AllowedHostsRedirects(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed_hosts):
        self.allowed_hosts = tuple(allowed_hosts)

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not host_allowed(newurl, self.allowed_hosts):
            raise FetchError("redirect", "redirect to a host that is not allowed")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def make_opener(allowed_hosts):
    """An opener with the redirect rule and without cookie handling."""
    return urllib.request.build_opener(_AllowedHostsRedirects(allowed_hosts))


def fetch_url(url, allowed_hosts, timeout=TIMEOUT_SECONDS, max_bytes=MAX_RESPONSE_BYTES, opener=None):
    """GET `url` and return the body as bytes (see the module text).

    `opener` is for tests: any object with `open(request, timeout=...)`.
    """
    if not host_allowed(url, allowed_hosts):
        raise FetchError("redirect", "the address is not an https address on an allowed host")
    if opener is None:
        opener = make_opener(allowed_hosts)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT}, method="GET")
    try:
        response = opener.open(request, timeout=timeout)
    except FetchError:
        raise
    except urllib.error.HTTPError as exc:
        raise FetchError("status", "HTTP status %s" % exc.code) from exc
    except TimeoutError as exc:  # socket.timeout is TimeoutError
        raise FetchError("timeout", "timeout") from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            raise FetchError("timeout", "timeout") from exc
        raise FetchError("network", "network error") from exc
    except OSError as exc:
        raise FetchError("network", "network error") from exc
    try:
        status = getattr(response, "status", None) or response.getcode()
        if status != 200:
            raise FetchError("status", "HTTP status %s" % status)
        final_url = response.geturl() if hasattr(response, "geturl") else url
        if not host_allowed(final_url, allowed_hosts):
            raise FetchError("redirect", "ended on a host that is not allowed")
        length = response.headers.get("Content-Length") if getattr(response, "headers", None) else None
        if length is not None and length.isdigit() and int(length) > max_bytes:
            raise FetchError("too-large", "response larger than 2 MB")
        chunks, total = [], 0
        try:
            while True:
                chunk = response.read(CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise FetchError("too-large", "response larger than 2 MB")
                chunks.append(chunk)
        except TimeoutError as exc:
            raise FetchError("timeout", "timeout") from exc
        except OSError as exc:
            raise FetchError("network", "network error") from exc
        return b"".join(chunks)
    finally:
        close = getattr(response, "close", None)
        if close:
            close()
