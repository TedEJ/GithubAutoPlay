"""The only network module of the build (R6.2, R6.5, R9.4).

Standard library only (`urllib`). One call fetches one URL and returns the
undecoded body as bytes, or raises `FetchError`, whatever goes wrong inside (an invalid address, a
broken connection and an incomplete body included). Rules:

* `User-Agent: GithubAutoPlay-news-reader/1.0`, no cookies (no cookie handler
  is installed, and no `Cookie` header is sent).
* Timeout of 15 seconds per network operation, and 60 seconds in total for the
  whole download (checked after every piece of data that arrives).
* Redirects are followed only to `https` addresses on the source's
  `allowedHosts` (or a subdomain of one); any other redirect is an error.
* The body is read in chunks and the download stops as soon as it is larger
  than `MAX_RESPONSE_BYTES` (2 MiB); a larger `Content-Length` is refused
  before reading.
* Only status 200 is a success.
* Certificate verification is always on. A failed verification (or any TLS handshake
  problem) is the kind `certificate` with a fixed message; nothing from the exception
  (which can name the host) is copied. `make_ssl_context(ca_file)` builds the context of
  the command line option `--ca-file`: the default context (CERT_REQUIRED, host name
  checked, system store) plus the owner's file as an additional trust anchor.

The build calls `fetch_url` through an injected function, so every test uses a
fake with the same signature and never touches the network.
"""
import http.client
import ssl
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from .parse import MAX_RESPONSE_BYTES

USER_AGENT = "GithubAutoPlay-news-reader/1.0"
TIMEOUT_SECONDS = 15
TOTAL_SECONDS = 60  # for the whole request including the download
CHUNK_BYTES = 64 * 1024


class FetchError(Exception):
    """A request failed. `kind` is one of: network, timeout, status, too-large, redirect, certificate."""

    def __init__(self, kind, message, status=None):
        super().__init__(message)
        self.kind = kind
        self.status = status  # the HTTP status for kind "status", else None


def host_allowed(url, allowed_hosts):
    """True if `url` is https and its host is an allowed host or a subdomain of one."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not host:
        return False
    return any(host == h or host.endswith("." + h) for h in allowed_hosts)


CERTIFICATE_MESSAGE = ("certificate could not be verified (the server may not send its full "
                       "certificate chain; see the README)")


class CaFileError(Exception):
    """The file given to `--ca-file` cannot be used. The message is fixed text (no path, no
    exception text)."""


def make_ssl_context(ca_file):
    """The default context (verification on, host name checked, system store) with the
    certificates of `ca_file` trusted in addition. Raises `CaFileError` for a path that is
    not a readable file or a file with no certificate."""
    try:
        context = ssl.create_default_context()
        context.load_verify_locations(cafile=ca_file)
    except ssl.SSLError as exc:
        raise CaFileError("the file has no usable certificate (PEM or DER)") from exc
    except (OSError, ValueError) as exc:
        raise CaFileError("the file does not exist or cannot be read") from exc
    return context


def _is_tls_error(exc):
    """True if `exc`, or the reason it wraps, is an ssl error (certificate or handshake)."""
    return isinstance(exc, ssl.SSLError) or isinstance(getattr(exc, "reason", None), ssl.SSLError)


class _AllowedHostsRedirects(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed_hosts):
        self.allowed_hosts = tuple(allowed_hosts)

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not host_allowed(newurl, self.allowed_hosts):
            raise FetchError("redirect", "redirect to a host that is not allowed")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def make_opener(allowed_hosts, context=None):
    """An opener with the redirect rule and without cookie handling. With `context` (an
    `ssl.SSLContext`) https requests use it; without, urllib's default (verifying) context."""
    handlers = [_AllowedHostsRedirects(allowed_hosts)]
    if context is not None:
        handlers.append(urllib.request.HTTPSHandler(context=context))
    return urllib.request.build_opener(*handlers)


def make_fetch(context=None):
    """A function `fetch(url, allowed_hosts) -> bytes` that uses `context` for https."""
    def fetch(url, allowed_hosts):
        return fetch_url(url, allowed_hosts, opener=make_opener(allowed_hosts, context))
    return fetch


def fetch_url(url, allowed_hosts, timeout=TIMEOUT_SECONDS, max_bytes=MAX_RESPONSE_BYTES, opener=None,
              total_seconds=TOTAL_SECONDS, clock=time.monotonic):
    """GET `url` and return the body as bytes (see the module text).

    `opener` and `clock` are for tests: any object with `open(request, timeout=...)`,
    and a function that returns seconds.
    """
    if not host_allowed(url, allowed_hosts):
        raise FetchError("redirect", "the address is not an https address on an allowed host")
    if opener is None:
        opener = make_opener(allowed_hosts)
    deadline = clock() + total_seconds
    try:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT}, method="GET")
        response = opener.open(request, timeout=timeout)
    except FetchError:
        raise
    except urllib.error.HTTPError as exc:
        raise FetchError("status", "HTTP status %s" % exc.code, exc.code) from exc
    except TimeoutError as exc:  # socket.timeout is TimeoutError
        raise FetchError("timeout", "timeout") from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            raise FetchError("timeout", "timeout") from exc
        if _is_tls_error(exc):
            raise FetchError("certificate", CERTIFICATE_MESSAGE) from exc
        raise FetchError("network", "network error") from exc
    except (OSError, ValueError, http.client.HTTPException) as exc:
        if _is_tls_error(exc):  # ssl.SSLError is an OSError
            raise FetchError("certificate", CERTIFICATE_MESSAGE) from exc
        # OSError: connection problems; ValueError: includes http.client.InvalidURL;
        # HTTPException: includes IncompleteRead and BadStatusLine.
        raise FetchError("network", "network error") from exc
    try:
        status = getattr(response, "status", None) or response.getcode()
        if status != 200:
            raise FetchError("status", "HTTP status %s" % status, status)
        final_url = response.geturl() if hasattr(response, "geturl") else url
        if not host_allowed(final_url, allowed_hosts):
            raise FetchError("redirect", "ended on a host that is not allowed")
        length = response.headers.get("Content-Length") if getattr(response, "headers", None) else None
        if length is not None and length.isdigit() and int(length) > max_bytes:
            raise FetchError("too-large", "response larger than 2 MB")
        chunks, total = [], 0
        # read1 returns as soon as any data has arrived (read would wait for a whole
        # chunk, and the per-operation timeout starts again on every byte), so the
        # total time limit below is checked after every piece of data.
        read = getattr(response, "read1", None) or response.read
        try:
            while True:
                if clock() > deadline:
                    raise FetchError("timeout", "download took longer than %d seconds" % total_seconds)
                chunk = read(CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise FetchError("too-large", "response larger than 2 MB")
                chunks.append(chunk)
        except TimeoutError as exc:
            raise FetchError("timeout", "timeout") from exc
        except (OSError, ValueError, http.client.HTTPException) as exc:
            raise FetchError("network", "network error") from exc
        return b"".join(chunks)
    except (OSError, ValueError, http.client.HTTPException) as exc:
        raise FetchError("network", "network error") from exc
    finally:
        close = getattr(response, "close", None)
        if close:
            close()
