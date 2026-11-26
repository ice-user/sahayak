"""Fetching and cleaning: URL or local file -> plain text + content hash.

HTML parsing uses BeautifulSoup with the stdlib ``html.parser`` backend: it tolerates the broken
markup found on government sites, needs no C extension, and is fast enough for single pages
(selectolax is faster but a binary dependency we do not need at this scale). PDFs use ``pypdf``.

Single-page-app sites (myscheme.gov.in is a Next.js app) often ship the page content as JSON in a
``__NEXT_DATA__`` script instead of visible HTML; when the visible text is tiny we fall back to
the strings inside that JSON.
"""
from __future__ import annotations

import hashlib
import io
import ipaddress
import json
import os
import re
import socket
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import urljoin, urlparse

USER_AGENT = "SahayakResearchBot/0.1 (scheme research; contact: set RESEARCH_CONTACT)"
MAX_BYTES = 8 * 1024 * 1024
MAX_TEXT_CHARS = 60_000
TIMEOUT_S = 30.0           # per network operation (connect / read)
DEADLINE_S = 60.0          # wall-clock budget for the whole fetch, redirects included
MAX_REDIRECTS = 5
ALLOWED_PORTS = (80, 443)
GOV_SUFFIXES = ("gov.in", "nic.in")
REDIRECT_CODES = (301, 302, 303, 307, 308)
REPO_ROOT = Path(__file__).resolve().parent.parent
_DROP_TAGS = ["script", "style", "noscript", "nav", "header", "footer", "aside", "form",
              "svg", "iframe", "template", "button", "select"]
_MIN_VISIBLE_CHARS = 400
_BLOCK_TAGS = ["p", "div", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "table", "section",
               "article", "dt", "dd", "blockquote", "pre", "caption"]


class FetchError(Exception):
    """Raised for anything that stops us getting usable text (network, size, empty, scanned PDF)."""


@dataclass
class Fetched:
    text: str
    content_hash: str          # sha256 of the cleaned text
    fetched_at: str
    kind: str                  # html | pdf | text
    truncated: bool = False
    final_url: str | None = None     # URL of the response actually read (after redirects)
    warnings: list[str] = field(default_factory=list)


def is_url(source: str) -> bool:
    return bool(re.match(r"^https?://", source.strip(), re.I))


# ------------------------------------------------------------------ network safety (SSRF)
Resolver = Callable[[str, int], list]


def default_resolver(host: str, port: int) -> list[str]:
    """Every address ``host`` resolves to (stdlib getaddrinfo; also expands 2130706433, 0x7f.1, ...)."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError, OSError) as e:
        raise FetchError(f"cannot resolve host {host!r}: {e}") from e
    return list(dict.fromkeys(i[4][0] for i in infos))


def ip_is_public(addr: str) -> bool:
    """True only for globally routable unicast addresses. Loopback, private, link-local (169.254/16, cloud
    metadata), CGNAT, multicast, reserved, unspecified and their IPv6 equivalents are all refused, including
    IPv4 addresses wrapped in IPv4-mapped, NAT64 (64:ff9b::/96) and 6to4 (2002::/16) IPv6 forms."""
    try:
        ip = ipaddress.ip_address(addr.split("%")[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address):
        embedded = ip.ipv4_mapped or ip.sixtofour
        if ip in ipaddress.ip_network("64:ff9b::/96"):
            embedded = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
        if ip.teredo:
            return False
        if embedded is not None:
            return ip_is_public(str(embedded))
    return ip.is_global and not (ip.is_multicast or ip.is_loopback or ip.is_private or ip.is_link_local
                                 or ip.is_reserved or ip.is_unspecified)


def _allowed_domains() -> list[str]:
    raw = os.environ.get("RESEARCH_ALLOWED_DOMAINS", "")
    return [d.strip().lower().lstrip(".") for d in raw.split(",") if d.strip()]


def domain_allowed(host: str, domains: list[str]) -> bool:
    host = host.lower().rstrip(".")
    return any(host == d or host.endswith("." + d) for d in domains)


def is_gov_host(host: str) -> bool:
    return domain_allowed(host, list(GOV_SUFFIXES))


def check_url(url: str, resolver: Resolver | None = None) -> str:
    """Validate one hop before any request is sent; returns the normalised host. Raises FetchError."""
    p = urlparse(url.strip())
    if p.scheme not in ("http", "https"):
        raise FetchError(f"only http/https URLs can be fetched, not {p.scheme or 'a bare path'}: {url[:80]!r}")
    if p.username or p.password:
        raise FetchError("URLs with embedded credentials are refused")
    host = (p.hostname or "").rstrip(".").lower()
    if not host:
        raise FetchError(f"URL has no host: {url[:80]!r}")
    try:
        port = p.port or (443 if p.scheme == "https" else 80)
    except ValueError as e:
        raise FetchError(f"bad port in URL: {e}") from e
    if port not in ALLOWED_PORTS:
        raise FetchError(f"port {port} is not allowed (only {ALLOWED_PORTS})")
    allow = _allowed_domains()
    if allow and not domain_allowed(host, allow):
        raise FetchError(f"{host} is not on the domain allowlist RESEARCH_ALLOWED_DOMAINS={','.join(allow)}")
    addrs = (resolver or default_resolver)(host, port)
    bad = [a for a in addrs if not ip_is_public(a)]
    if not addrs or bad:
        raise FetchError(f"{host} resolves to a non-public address ({', '.join(bad) or 'none'}); "
                         "refusing to fetch (not a public internet host)")
    return host


class PinnedBackend:
    """httpcore network backend that resolves, validates and connects to the validated IP in one step.

    Because the socket is opened to the IP that was just checked (TLS still verifies the certificate against
    the original hostname), a DNS answer that changes between the pre-flight check and the connection
    (DNS rebinding) cannot redirect the request to an internal address."""

    def __init__(self, resolver: Resolver | None = None, inner=None):
        import httpcore
        self._resolver = resolver or default_resolver
        self._inner = inner or httpcore.SyncBackend()

    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        addrs = self._resolver(host, port)
        if not addrs or any(not ip_is_public(a) for a in addrs):
            raise FetchError(f"{host} resolves to a non-public address at connect time; refusing to connect")
        return self._inner.connect_tcp(addrs[0], port, timeout=timeout, local_address=local_address,
                                       socket_options=socket_options)

    def connect_unix_socket(self, *a, **k):  # pragma: no cover - never allowed
        raise FetchError("unix sockets are not allowed")

    def sleep(self, seconds):
        time.sleep(seconds)


_SAFE_CLS = None


def _transport_cls():
    global _SAFE_CLS
    if _SAFE_CLS is not None:
        return _SAFE_CLS
    import httpcore
    import httpx

    class SafeTransport(httpx.HTTPTransport):
        """HTTPTransport whose connection pool uses :class:`PinnedBackend`."""

        def __init__(self, resolver: Resolver | None = None, **kw):
            super().__init__(**kw)
            self._pool = httpcore.ConnectionPool(ssl_context=httpx.create_ssl_context(),
                                                 network_backend=PinnedBackend(resolver), http2=False)
    _SAFE_CLS = SafeTransport
    return SafeTransport


def __getattr__(name):  # lazy so importing this module does not import httpx
    if name == "SafeTransport":
        return _transport_cls()
    raise AttributeError(name)


def make_client(*, timeout: float = TIMEOUT_S, resolver: Resolver | None = None):
    """httpx client that never follows redirects itself, ignores proxy env vars (a proxy would resolve DNS for
    us and defeat IP validation) and connects only to validated public IPs."""
    import httpx

    return httpx.Client(transport=_transport_cls()(resolver), follow_redirects=False, timeout=timeout,
                        trust_env=False,
                        headers={"User-Agent": USER_AGENT, "Accept-Language": "en-IN,en;q=0.9,hi;q=0.8"})


def _clean_lines(text: str) -> str:
    lines = [re.sub(r"[ \t ]+", " ", ln).strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln).strip()


def _json_strings(node, out: list[str]) -> None:
    if isinstance(node, str):
        if len(node) > 2 and not node.startswith(("http", "/", "_")):
            out.append(node)
    elif isinstance(node, dict):
        for v in node.values():
            _json_strings(v, out)
    elif isinstance(node, list):
        for v in node:
            _json_strings(v, out)


def html_to_text(html: str) -> str:
    """Strip navigation/scripts and return readable text, one block per line."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    embedded: list[str] = []
    nd = soup.find("script", id="__NEXT_DATA__")
    if nd and nd.string:
        try:
            raw: list[str] = []
            _json_strings(json.loads(nd.string), raw)
            embedded = [BeautifulSoup(s, "html.parser").get_text(" ", strip=True) for s in raw]
        except (ValueError, TypeError):
            pass
    for tag in soup(_DROP_TAGS):
        tag.decompose()
    root = soup.find("main") or soup.body or soup
    for br in root.find_all("br"):
        br.replace_with("\n")
    for tag in root.find_all(_BLOCK_TAGS):
        tag.insert_before("\n- " if tag.name == "li" else "\n")
        tag.insert_after("\n")
    for cell in root.find_all(["td", "th"]):
        cell.insert_after(" | ")
    text = _clean_lines(root.get_text(""))
    if len(text) < _MIN_VISIBLE_CHARS and embedded:
        text = _clean_lines("\n".join(dict.fromkeys(s for s in embedded if s)))
    return text


def pdf_to_text(data: bytes) -> str:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [(p.extract_text() or "") for p in reader.pages]
    except Exception as e:  # pypdf raises many types on corrupt files
        raise FetchError(f"could not read PDF: {e}") from e
    text = _clean_lines("\n\n".join(pages))
    if not text:
        raise FetchError("PDF has no extractable text (scanned image? run OCR first and pass the .txt)")
    return text


def _finish(text: str, kind: str, final_url: str | None, max_chars: int) -> Fetched:
    text = text.strip()
    if len(text) < 50:
        raise FetchError(f"extracted only {len(text)} characters of text; page is empty or script-rendered "
                         "(save it as PDF/text from a browser and pass that file instead)")
    truncated = len(text) > max_chars
    if truncated:
        text = text[:max_chars]
    return Fetched(text=text, content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                   fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   kind=kind, truncated=truncated, final_url=final_url)


def _decode(data: bytes, content_type: str = "") -> str:
    m = re.search(r"charset=([\w-]+)", content_type or "", re.I)
    for enc in ([m.group(1)] if m else []) + ["utf-8", "cp1252"]:
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


def _bytes_to_fetched(data: bytes, content_type: str, name: str, final_url: str | None,
                      max_chars: int) -> Fetched:
    lower = name.lower()
    if data[:5] == b"%PDF-" or "pdf" in content_type.lower() or lower.endswith(".pdf"):
        return _finish(pdf_to_text(data), "pdf", final_url, max_chars)
    body = _decode(data, content_type)
    if "html" in content_type.lower() or lower.endswith((".html", ".htm")) or "<html" in body[:2000].lower() \
            or "<body" in body[:2000].lower():
        return _finish(html_to_text(body), "html", final_url, max_chars)
    return _finish(_clean_lines(body), "text", final_url, max_chars)


def _guarded_get(url: str, *, client=None, max_bytes: int = MAX_BYTES, timeout: float = TIMEOUT_S,
                 resolver: Resolver | None = None, deadline_s: float = DEADLINE_S,
                 max_redirects: int = MAX_REDIRECTS) -> tuple[bytes, str, str, list[str]]:
    """GET with every hop validated: scheme/host/IP/port checks, redirects followed by hand (<= max_redirects,
    each target re-validated), size cap, and one wall-clock deadline. Returns (body, content_type, final_url,
    warnings)."""
    import httpx

    own = client is None
    client = client or make_client(timeout=timeout, resolver=resolver)
    started = time.monotonic()
    warnings: list[str] = []
    current = url.strip()
    try:
        for _hop in range(max_redirects + 1):
            remaining = deadline_s - (time.monotonic() - started)
            if remaining <= 0:
                raise FetchError(f"deadline of {deadline_s:.0f}s exceeded fetching {url}")
            check_url(current, resolver)
            with client.stream("GET", current, follow_redirects=False, timeout=min(timeout, remaining)) as resp:
                if resp.status_code in REDIRECT_CODES and resp.headers.get("location"):
                    nxt = urljoin(current, resp.headers["location"])
                    warnings.append(f"redirected: {current} -> {nxt}")
                    current = nxt
                    continue
                if resp.status_code >= 400 or 300 <= resp.status_code < 400:
                    raise FetchError(f"HTTP {resp.status_code} for {current}")
                declared = resp.headers.get("content-length")
                if declared and declared.isdigit() and int(declared) > max_bytes:
                    raise FetchError(f"{current} is {declared} bytes, over the {max_bytes} byte limit")
                buf = bytearray()
                for chunk in resp.iter_bytes():
                    buf.extend(chunk)
                    if len(buf) > max_bytes:
                        raise FetchError(f"{current} exceeded the {max_bytes} byte limit")
                    if time.monotonic() - started > deadline_s:
                        raise FetchError(f"deadline of {deadline_s:.0f}s exceeded while reading {current}")
                return bytes(buf), resp.headers.get("content-type", ""), current, warnings
        raise FetchError(f"too many redirects (more than {max_redirects}) starting from {url}")
    except httpx.HTTPError as e:
        raise FetchError(f"network error fetching {current}: {e}") from e
    finally:
        if own:
            client.close()


def _source_warnings(final_url: str) -> list[str]:
    host = (urlparse(final_url).hostname or "").lower()
    if host and not is_gov_host(host):
        return [f"source domain {host} is not a government domain ({' / '.join(GOV_SUFFIXES)}); "
                "confirm it is the official source before approving (set RESEARCH_ALLOWED_DOMAINS to enforce)"]
    return []


def fetch_url(url: str, *, client=None, max_bytes: int = MAX_BYTES, timeout: float = TIMEOUT_S,
              max_chars: int = MAX_TEXT_CHARS, resolver: Resolver | None = None,
              deadline_s: float = DEADLINE_S, max_redirects: int = MAX_REDIRECTS) -> Fetched:
    """Safely GET a public http(s) URL and clean it. ``client``/``resolver`` are injectable for tests."""
    data, ctype, final, warns = _guarded_get(url, client=client, max_bytes=max_bytes, timeout=timeout,
                                             resolver=resolver, deadline_s=deadline_s, max_redirects=max_redirects)
    f = _bytes_to_fetched(data, ctype, final, final, max_chars)
    f.warnings = warns + _source_warnings(final)
    return f


def fetch_url_raw(url: str, **kw) -> str:
    """Decoded body of a guarded GET (used to harvest links from a listing page)."""
    data, ctype, _final, _w = _guarded_get(url, **kw)
    return _decode(data, ctype)


def default_allowed_dirs() -> list[Path]:
    """Directories a local source file may live in: RESEARCH_ALLOWED_DIRS (os.pathsep separated) or, by
    default, the repo's data/ and tests/fixtures/."""
    raw = os.environ.get("RESEARCH_ALLOWED_DIRS", "")
    if raw.strip():
        return [Path(p).expanduser().resolve() for p in raw.split(os.pathsep) if p.strip()]
    return [(REPO_ROOT / "data").resolve(), (REPO_ROOT / "tests" / "fixtures").resolve()]


def fetch_file(path: str | Path, *, max_chars: int = MAX_TEXT_CHARS, allowed_dirs: list | None = None) -> Fetched:
    """Read a local source file, only from an allowed directory (symlinks and ``..`` are resolved first)."""
    dirs = [Path(d).resolve() for d in (allowed_dirs if allowed_dirs is not None else default_allowed_dirs())]
    try:
        p = Path(path).expanduser().resolve()
    except (OSError, RuntimeError) as e:
        raise FetchError(f"bad path {path!r}: {e}") from e
    if not any(p == d or d in p.parents for d in dirs):
        raise FetchError(f"{path} is outside the allowed directories ({', '.join(map(str, dirs))}); "
                         "set RESEARCH_ALLOWED_DIRS to permit another folder")
    if not p.is_file():
        raise FetchError(f"no such file: {p}")
    if p.stat().st_size > MAX_BYTES:
        raise FetchError(f"{p} is over the {MAX_BYTES} byte limit")
    return _bytes_to_fetched(p.read_bytes(), "", p.name, None, max_chars)


def fetch(source: str, **kw) -> Fetched:
    """Fetch a public http(s) URL. Local paths are NOT accepted here: use ``fetch_file`` via ``--file``."""
    if not is_url(source):
        raise FetchError(f"{source[:80]!r} is not an http(s) URL; local files must be passed explicitly "
                         "with --file (and live under an allowed directory)")
    return fetch_url(source, **kw)
