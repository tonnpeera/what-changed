"""Small HTTP GET helper shared by the scripts. Standard library only.

- Only http(s) URLs: ledger and watchlist files are editable text, so a
  file:// or other scheme must never be read through them.
- No local or private addresses (localhost, 127.x, 10.x, 192.168.x, 169.254.x, ...),
  checked on the first URL and on every redirect hop: precheck runs these fetches
  outside any sandbox, so a watched page must not be able to reach the user's LAN.
  Without a proxy the connection goes to an address checked at connect time, so a
  name cannot pass the check and then resolve to a private address (DNS rebinding).
  Behind a proxy, a name is still resolved here when local DNS answers and refused if
  it points to a private, loopback or link-local address; the proxy resolves it again,
  so rebinding is not prevented there.
- If WHAT_CHANGED_ALLOWED_HOSTS is set (the schedulers in adapters/ set it for the
  agent), only those hosts are fetched, so an agent fed instructions by a web page
  cannot use these scripts to send data to any other host.
- Reads at most MAX_BYTES per page.
- Takes at most `total` seconds per call (default 3 x timeout), retries and redirects included:
  the timeout bounds each socket operation, so a server sending one byte at a time could
  otherwise hold a call for hours. When the time is up the call returns TOTAL_TIMEOUT and its
  connections are cut.
- Detects truncated downloads (shorter than Content-Length, which some proxies cause
  without any error), retries, and reports "partial" instead of "ok".
- Reports a proxy/sandbox refusal as "blocked-local", not as a dead site.
- Percent-encodes non-ASCII URLs.
- If Python has no CA bundle configured (common with python.org builds on
  macOS), falls back to the system bundle at /etc/ssl/cert.pem.
"""
from __future__ import annotations

import codecs
import http.client
import ipaddress
import os
import re
import socket
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

UA = "what-changed/0.1 (+https://github.com)"
SYSTEM_CA = "/etc/ssl/cert.pem"
MAX_BYTES = 5_000_000


TOTAL_TIMEOUT = "timeout (total)"


class _Deadline:
    """One fetch call's time limit. Every socket the call opens is registered here; when the time
    is up they are all shut down, which wakes a read blocked anywhere in urllib (on Windows that
    is not certain, but fetch returns on time either way)."""

    _shutdown = socket.socket.shutdown  # the real one, also for SSL sockets (whose own shutdown unwraps)

    def __init__(self, seconds: float):
        self.end = time.monotonic() + seconds
        self.expired = False
        self._socks: list[socket.socket] = []
        self._lock = threading.Lock()

    def left(self) -> float:
        return self.end - time.monotonic()

    def track(self, sock: socket.socket) -> None:
        with self._lock:
            self._socks.append(sock)
            if not self.expired:
                return
        self._cut(sock)

    def expire(self) -> None:
        with self._lock:
            self.expired = True
            socks = list(self._socks)
        for sock in socks:
            self._cut(sock)

    @classmethod
    def _cut(cls, sock: socket.socket) -> None:
        try:
            cls._shutdown(sock, socket.SHUT_RDWR)
        except Exception:  # already closed, or handed over to an SSL socket (tracked separately)
            pass


class _Current(threading.local):
    deadline: _Deadline | None = None


_current = _Current()


def _track(sock):
    if _current.deadline is not None:
        _current.deadline.track(sock)
    return sock


class _TrackedSSLSocket(ssl.SSLSocket):
    """Wrapping a socket in TLS moves its file descriptor to a new socket object; register that
    one too, before the handshake, which the server can also send slowly."""

    def do_handshake(self, *args, **kwargs):
        _track(self)
        return super().do_handshake(*args, **kwargs)


def _context(use_system_ca: bool) -> ssl.SSLContext:
    if use_system_ca and os.path.exists(SYSTEM_CA):
        context = ssl.create_default_context(cafile=SYSTEM_CA)
    else:
        context = ssl.create_default_context()
    context.sslsocket_class = _TrackedSSLSocket
    return context


# Charsets a web page is written in. Any other codec Python knows (punycode, idna, utf-7,
# unicode_escape, base64, ...) is not page text, and some decode in quadratic time: use utf-8.
PAGE_CHARSET = re.compile(r"utf-8-sig|utf-(?:8|16|32)(?:-[lb]e)?|ascii|iso8859-\d+|cp\d+|mac-[a-z0-9]+|koi8-[a-z]|kz1048|ptcp154"
                          r"|hp-roman8|tis-620|shift_jis\w*|euc_\w+|gb2312|gbk|gb18030|big5\w*|hz|johab|iso2022_\w+")


def _decode(data: bytes, charset: str) -> str:
    try:
        charset = codecs.lookup(charset).name
    except LookupError:
        charset = "utf-8"
    if not PAGE_CHARSET.fullmatch(charset):
        charset = "utf-8"
    return data.decode(charset, errors="replace")


BLOCKED_LOCAL = "blocked by a local proxy or sandbox, not the site: allow this host"
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
    "Accept-Language": "en,*;q=0.5",
}


@dataclass
class Fetched:
    text: str | None
    status: str          # "ok", "partial", "blocked-local", or an error label
    final_url: str = ""
    received: int = 0    # bytes received
    expected: int | None = None  # Content-Length, when the server sent one
    content_type: str = ""


def encode_url(url: str) -> str:
    """Percent-encode non-ASCII characters (e.g. Thai paths) and leave the rest alone."""
    return urllib.parse.quote(url, safe=":/?#[]@!$&'()*+,;=%~")


# IPv6 ranges whose last 32 bits are an IPv4 address: NAT64, IPv4-compatible (::a.b.c.d)
# and IPv4-translated (::ffff:0:a.b.c.d). Mapped (::ffff:a.b.c.d) and 6to4 are handled by ipaddress.
EMBEDS_IPV4 = [ipaddress.IPv6Network(n) for n in ("64:ff9b::/96", "::/96", "::ffff:0:0:0/96")]
SAFE_HOST = re.compile(r"^([a-z0-9._-]+|[0-9a-f:.]+(%[a-z0-9._-]+)?)$")
NUMERIC_HOST = re.compile(r"^(0x[0-9a-f]+|[0-9]+)(\.(0x[0-9a-f]+|[0-9]+))*$")


def _private_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address):
        # IPv6 forms that carry an IPv4 address: mapped, 6to4, and NAT64 (64:ff9b::/96).
        if ip.is_site_local:  # fec0::/10, deprecated but still routed locally by some systems
            return True
        embedded = ip.ipv4_mapped or ip.sixtofour
        if embedded is None and any(ip in n for n in EMBEDS_IPV4):
            embedded = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
        if embedded is not None:
            ip = embedded
    return not ip.is_global


# Proxy apps in "fake-ip" mode answer every name with an address from 198.18.0.0/15 and
# resolve the real one themselves, so behind a proxy that range says nothing about the target.
FAKE_IP = ipaddress.IPv4Network("198.18.0.0/15")


def _private_behind_proxy(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return _private_ip(ip) and not (isinstance(ip, ipaddress.IPv4Address) and ip in FAKE_IP)


def _allowed_hosts() -> list[str] | None:
    """WHAT_CHANGED_ALLOWED_HOSTS as a list; None means no limit (unset or "*")."""
    value = os.environ.get("WHAT_CHANGED_ALLOWED_HOSTS")
    if value is None or value.strip() == "*":
        return None
    return [h.strip().lower().rstrip(".") for h in value.split(",") if h.strip()]


def _host_allowed(host: str, allowed: list[str]) -> bool:
    """Matches like Claude Code's WebFetch(domain:...) rules: "example.com" is that host only,
    "*.example.com" any subdomain at any depth but not example.com itself."""
    return any(host.endswith(a[1:]) if a.startswith("*.") else host == a for a in allowed)


def refused(url: str) -> str | None:
    """Why this URL must not be fetched, or None. Checked before the request and on every
    redirect. Literal addresses and localhost are always refused, and names are resolved and
    refused if any answer is private, with or without a proxy. Behind a proxy (e.g. a sandbox)
    local DNS may not answer at all; the name is then left to the proxy."""
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return "refused: malformed URL"
    if parts.scheme not in ("http", "https"):
        return "refused: only http(s) URLs are fetched"
    # Check the host urllib will actually connect to, parsed by urllib itself: urlsplit and
    # urllib.request disagree on userinfo and percent-escapes (127.0.0.1%23@evil.com).
    try:
        host = http.client.HTTPConnection(urllib.request.Request(url).host or "").host
    except (ValueError, http.client.InvalidURL):
        return "refused: malformed host"
    # DNS maps full-width or circled digits (０.０.０.０) to ASCII, so normalise them first.
    if not host.isascii():
        try:
            host = host.encode("idna").decode("ascii")
        except UnicodeError:
            return f"refused: host cannot be normalised {host!r}"
    host = host.lower()
    if not SAFE_HOST.fullmatch(host):
        return f"refused: unexpected characters in host {host!r}"
    host = host.rstrip(".")
    if not host:
        return "refused: URL has no host"
    allowed = _allowed_hosts()
    if allowed is not None and not _host_allowed(host, allowed):
        return f"refused: {host} is not in the allowed hosts (WHAT_CHANGED_ALLOWED_HOSTS)"
    try:
        if _private_ip(ipaddress.ip_address(host.split("%")[0])):
            return f"refused: private address {host}"
        return None
    except ValueError:
        pass
    # Shorthand forms such as 2130706433 or 0x7f.1 also reach 127.0.0.1.
    if host == "localhost" or host.endswith(".localhost") or NUMERIC_HOST.fullmatch(host):
        return f"refused: local or numeric host {host}"
    proxies = urllib.request.getproxies()
    via_proxy = bool(proxies.get(parts.scheme)) and not urllib.request.proxy_bypass(host)
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError):
        return None  # urlopen (or the proxy) reports the DNS failure itself
    # An early, clear answer. Without a proxy the connection itself resolves and checks again and
    # connects only to the address it checked (_pinned_connection), so a second answer cannot slip
    # through. Behind a proxy this check is the only one: the proxy connects wherever it resolves.
    private = _private_behind_proxy if via_proxy else _private_ip
    for info in infos:
        if private(ipaddress.ip_address(str(info[4][0]).split("%")[0])):
            return f"refused: {host} resolves to a private address"
    return None


class _Refused(Exception):
    pass


_DEFAULT_TIMEOUT = getattr(socket, "_GLOBAL_DEFAULT_TIMEOUT", object())


def _pinned_connection(address, timeout=_DEFAULT_TIMEOUT, source_address=None, *args, **kwargs):
    """socket.create_connection, but resolving the name once, refusing it if any answer is a
    private address, and connecting only to the answers it checked. A plain connection would
    resolve the name again, and a DNS server can answer public first and private second."""
    host, port = address[0], address[1]
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    for info in infos:
        if _private_ip(ipaddress.ip_address(str(info[4][0]).split("%")[0])):
            raise _Refused(f"refused: {host} resolves to a private address (checked when connecting)")
    error: OSError | None = None
    for family, socktype, proto, _, sockaddr in infos:
        sock = None
        try:
            deadline = _current.deadline
            if deadline is not None and deadline.left() <= 0:  # many addresses that do not answer
                raise TimeoutError("total time limit reached while connecting")
            sock = _track(socket.socket(family, socktype, proto))  # fails for IPv6 answers on an IPv4-only host
            if timeout is not _DEFAULT_TIMEOUT:
                sock.settimeout(timeout if deadline is None else max(min(timeout, deadline.left()), 0.01))
            if source_address:
                sock.bind(source_address)
            sock.connect(sockaddr)
            return sock
        except OSError as e:
            error = e
            if sock is not None:
                sock.close()
    raise error or OSError(f"no address for {host}")


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_connection = _pinned_connection


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    # TLS still verifies the certificate against the name (server_hostname is self.host).
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_connection = _pinned_connection


def _tracked_connection(*args, **kwargs):
    return _track(socket.create_connection(*args, **kwargs))


class _ProxiedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_connection = _tracked_connection


class _ProxiedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_connection = _tracked_connection


def _via_proxy(req: urllib.request.Request) -> bool:
    """True when urllib sends this request through a proxy: the proxy, not us, resolves the
    name then, and the proxy's own address (often 127.0.0.1) must stay reachable."""
    return req.has_proxy() or bool(getattr(req, "_tunnel_host", None))


class _PinnedHTTPHandler(urllib.request.HTTPHandler):
    def http_open(self, req):
        return self.do_open(_ProxiedHTTPConnection if _via_proxy(req) else _PinnedHTTPConnection, req)


class _PinnedHTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):
        cls = _ProxiedHTTPSConnection if _via_proxy(req) else _PinnedHTTPSConnection
        return self.do_open(cls, req, context=self._context)


class _CheckedRedirect(urllib.request.HTTPRedirectHandler):
    """Re-check every redirect target (urllib would otherwise follow ftp:// or a LAN address)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        why = refused(newurl)
        if why:
            raise _Refused(f"{why} (redirect)")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open(req: urllib.request.Request, timeout: float, context: ssl.SSLContext):
    opener = urllib.request.build_opener(_CheckedRedirect, _PinnedHTTPHandler, _PinnedHTTPSHandler(context=context))
    return opener.open(req, timeout=timeout)


def fetch(url: str, timeout: float = 20.0, retries: int = 2, total: float | None = None) -> Fetched:
    """GET a page. A download shorter than its Content-Length is retried and, if it
    stays short, reported as "partial" (some proxies cut responses without an error).
    The whole call takes at most `total` seconds (default 3 x timeout); after that the
    status is TOTAL_TIMEOUT, even if part of the page arrived."""
    url = encode_url(url)
    why = refused(url)
    if why:
        return Fetched(None, why, url)
    deadline = _Deadline(3 * timeout if total is None else total)
    got: list[Fetched] = []

    def attempts() -> None:  # in its own thread, so the caller can stop waiting on time
        _current.deadline = deadline
        try:
            got.append(_attempts(url, timeout, retries, deadline))
        except BaseException as e:
            got.append(Fetched(None, type(e).__name__, url))
    worker = threading.Thread(target=attempts, name="what-changed fetch", daemon=True)
    worker.start()
    worker.join(max(deadline.left(), 0.0))
    if worker.is_alive() or deadline.expired or not got:
        deadline.expire()  # cut its connections, so the abandoned thread ends too
        return Fetched(None, TOTAL_TIMEOUT, url)
    return got[0]


def _attempts(url: str, timeout: float, retries: int, deadline: _Deadline) -> Fetched:
    use_system_ca = False
    best: Fetched | None = None
    charset = "utf-8"
    for _ in range(retries + 2):
        if deadline.left() <= 0:
            deadline.expire()
            break
        req = urllib.request.Request(url, headers=HEADERS)
        try:
            with _open(req, max(min(timeout, deadline.left()), 0.01), _context(use_system_ca)) as resp:
                final = resp.geturl()
                if urllib.parse.urlsplit(final).scheme not in ("http", "https"):
                    return Fetched(None, "refused: redirected to a non-http(s) URL", final)
                charset = resp.headers.get_content_charset() or "utf-8"
                ctype = resp.headers.get_content_type()
                length = resp.headers.get("Content-Length")
                expected = int(length) if length and length.isdigit() and not resp.headers.get("Content-Encoding") else None
                try:
                    data = resp.read(MAX_BYTES + 1)
                except http.client.IncompleteRead as e:
                    data = e.partial
                    expected = expected or len(data) + 1
                if len(data) > MAX_BYTES:
                    return Fetched(_decode(data[:MAX_BYTES], charset), "partial", final, MAX_BYTES, expected, ctype)
                got = Fetched(_decode(data, charset), "ok", final, len(data), expected, ctype)
                if expected is None or len(data) >= expected:
                    return got
                got.status = "partial"
                if best is None or got.received > best.received:
                    best = got
                continue
        except _Refused as e:
            return Fetched(None, str(e), url)
        except urllib.error.HTTPError as e:
            return Fetched(None, f"HTTP {e.code}", e.geturl() or url)
        except urllib.error.URLError as e:
            if isinstance(e.reason, ssl.SSLCertVerificationError) and not use_system_ca:
                use_system_ca = True
                continue
            if "Tunnel connection failed" in str(e.reason):
                return Fetched(None, f"blocked-local ({BLOCKED_LOCAL}: {urllib.parse.urlsplit(url).hostname})", url)
            return Fetched(None, f"URLError: {e.reason}", url)
        except Exception as e:  # timeouts, connection resets
            return Fetched(None, type(e).__name__, url)
    return best or Fetched(None, "failed after retries", url)


def get(url: str, timeout: float = 20.0, retries: int = 2) -> tuple[str | None, str]:
    """Return (text, status). status is "ok", "partial", "blocked-local (...)" or an error label."""
    r = fetch(url, timeout, retries)
    return r.text, r.status
