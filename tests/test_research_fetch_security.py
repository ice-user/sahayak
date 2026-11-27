"""SSRF / local-file-read hardening of research.fetch (offline: injected resolver + MockTransport)."""
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx
import pytest

from research import fetch as F
from research.fetch import FetchError, fetch, fetch_file, fetch_url
from tests.test_research_support import SENIOR
from tests.conftest import requires_symlinks

PAGE = ("<html><body><main><h1>Sample page</h1><p>" + "The applicant must be 60 years of age or above. " * 4
        + "</p></main></body></html>").encode()
PUBLIC = "93.184.216.34"


def resolver(mapping):
    def r(host, port):
        if host in mapping:
            return mapping[host]
        raise FetchError(f"cannot resolve {host}")
    return r


def client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


OK = lambda req: httpx.Response(200, content=PAGE, headers={"content-type": "text/html"})


# ------------------------------------------------------------------ scheme / host / ip filtering
@pytest.mark.parametrize("url", [
    "file:///etc/passwd", "ftp://example.org/x", "gopher://example.org/", "javascript:alert(1)",
    "http://user:pw@example.org/x", "https://example.org:22/x", "http:///nohost",
])
def test_bad_scheme_or_shape_is_rejected(url):
    with pytest.raises(FetchError):
        fetch_url(url, client=client(OK), resolver=resolver({"example.org": [PUBLIC]}))


@pytest.mark.parametrize("addr", [
    "127.0.0.1", "127.1.2.3", "10.0.0.5", "172.16.4.4", "192.168.1.1", "169.254.169.254", "0.0.0.0",
    "224.0.0.1", "240.0.0.1", "100.64.0.1", "::1", "fe80::1", "fc00::1", "ff02::1", "::ffff:127.0.0.1",
    "::ffff:10.1.1.1", "64:ff9b::7f00:1", "2002:7f00:1::",
])
def test_non_public_addresses_are_rejected(addr):
    assert not F.ip_is_public(addr)
    with pytest.raises(FetchError, match="non-public|not a public"):
        fetch_url("https://example.org/x", client=client(OK), resolver=resolver({"example.org": [addr]}))


def test_public_addresses_are_accepted():
    assert F.ip_is_public(PUBLIC) and F.ip_is_public("2606:2800:220:1:248:1893:25c8:1946")
    assert fetch_url("https://example.org/x", client=client(OK), resolver=resolver({"example.org": [PUBLIC]})).kind == "html"


def test_one_private_address_among_public_ones_rejects_the_host():
    with pytest.raises(FetchError):
        fetch_url("https://example.org/", client=client(OK), resolver=resolver({"example.org": [PUBLIC, "10.0.0.1"]}))


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "[::1]", "2130706433", "0x7f.1", "169.254.169.254"])
def test_ip_literals_and_aliases_never_reach_the_network(host):
    called = []
    def h(req):
        called.append(req.url)
        return httpx.Response(200, content=PAGE)
    with pytest.raises(FetchError):
        fetch_url(f"http://{host}/admin", client=client(h))      # default resolver: real getaddrinfo, no network needed
    assert not called


def test_real_local_server_is_not_reachable():
    class H(BaseHTTPRequestHandler):
        hits = 0
        def do_GET(self):
            H.hits += 1
            self.send_response(200); self.end_headers(); self.wfile.write(PAGE)
        def log_message(self, *a): pass
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        with pytest.raises(FetchError):
            fetch_url(f"http://127.0.0.1:{srv.server_port}/")
    finally:
        srv.shutdown()
    assert H.hits == 0


# ------------------------------------------------------------------ redirects
def test_redirects_are_followed_manually_and_each_hop_is_validated():
    def h(req):
        if req.url.host == "example.org":
            return httpx.Response(302, headers={"location": "https://internal.example.net/secret"})
        return httpx.Response(200, content=PAGE, headers={"content-type": "text/html"})
    res = resolver({"example.org": [PUBLIC], "internal.example.net": ["10.1.2.3"], "ok.example.net": [PUBLIC]})
    with pytest.raises(FetchError, match="non-public|not a public"):
        fetch_url("https://example.org/", client=client(h), resolver=res)

    def h2(req):
        if req.url.path == "/moved":
            return httpx.Response(302, headers={"location": "https://ok.example.net/final"})
        if req.url.host == "example.org":
            return httpx.Response(301, headers={"location": "/moved"})
        return httpx.Response(200, content=PAGE, headers={"content-type": "text/html"})
    f = fetch_url("https://example.org/", client=client(h2), resolver=res)
    assert f.final_url == "https://ok.example.net/final"
    assert any("redirect" in w.lower() for w in f.warnings)


def test_redirect_to_file_scheme_and_redirect_loops_are_rejected():
    res = resolver({"example.org": [PUBLIC]})
    with pytest.raises(FetchError):
        fetch_url("https://example.org/", client=client(lambda r: httpx.Response(302, headers={"location": "file:///etc/passwd"})), resolver=res)
    with pytest.raises(FetchError, match="redirect"):
        fetch_url("https://example.org/", client=client(lambda r: httpx.Response(302, headers={"location": "/again"})), resolver=res)


def test_redirect_cap_is_five():
    seen = []
    def h(req):
        seen.append(req.url.path)
        return httpx.Response(302, headers={"location": f"/{len(seen)}"})
    with pytest.raises(FetchError, match="redirect"):
        fetch_url("https://example.org/", client=client(h), resolver=resolver({"example.org": [PUBLIC]}))
    assert len(seen) == 6          # the first request plus 5 redirects


# ------------------------------------------------------------------ DNS rebinding: connect-time pinning
class _Recorder:
    def __init__(self):
        self.connected = []
    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        self.connected.append((host, port))
        return "stream"


def test_connection_is_pinned_to_the_validated_ip_and_rechecked_at_connect_time():
    rec = _Recorder()
    be = F.PinnedBackend(resolver=resolver({"example.org": [PUBLIC]}), inner=rec)
    assert be.connect_tcp("example.org", 443, timeout=3) == "stream"
    assert rec.connected == [(PUBLIC, 443)]                      # the IP, never the name
    # rebinding: pre-flight saw a public address, the connect-time lookup now returns an internal one
    answers = iter([[PUBLIC], ["169.254.169.254"]])
    rebind = F.PinnedBackend(resolver=lambda h, p: next(answers), inner=_Recorder())
    rebind.connect_tcp("evil.example", 443)
    with pytest.raises(FetchError, match="non-public|not a public"):
        rebind.connect_tcp("evil.example", 443)


def test_default_client_uses_the_pinned_transport_and_ignores_proxy_env(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
    c = F.make_client(timeout=5)
    try:
        assert isinstance(c._transport, F.SafeTransport) and not c._mounts
    finally:
        c.close()


# ------------------------------------------------------------------ deadline / size
def test_overall_deadline_stops_a_slow_drip(monkeypatch):
    def slow_stream():
        for _ in range(100):
            time.sleep(0.05)
            yield b"x" * 10
    def h(req):
        return httpx.Response(200, content=slow_stream(), headers={"content-type": "text/plain"})
    t0 = time.monotonic()
    with pytest.raises(FetchError, match="deadline|time"):
        fetch_url("https://example.org/", client=client(h), resolver=resolver({"example.org": [PUBLIC]}),
                  deadline_s=0.3)
    assert time.monotonic() - t0 < 2


# ------------------------------------------------------------------ domain allowlist + warnings
def test_allowlist_env_restricts_every_hop(monkeypatch):
    monkeypatch.setenv("RESEARCH_ALLOWED_DOMAINS", "gov.in, nic.in")
    res = resolver({"www.myscheme.gov.in": [PUBLIC], "example.org": [PUBLIC], "x.nic.in": [PUBLIC]})
    f = fetch_url("https://www.myscheme.gov.in/a", client=client(OK), resolver=res)
    assert not any("not a government" in w for w in f.warnings)
    with pytest.raises(FetchError, match="allowlist|RESEARCH_ALLOWED_DOMAINS"):
        fetch_url("https://example.org/a", client=client(OK), resolver=res)
    with pytest.raises(FetchError, match="allowlist|RESEARCH_ALLOWED_DOMAINS"):          # a hop leaving the list
        fetch_url("https://x.nic.in/a", client=client(lambda r: httpx.Response(302, headers={"location": "https://example.org/"})), resolver=res)
    assert not F.domain_allowed("evilgov.in", ["gov.in"]) and F.domain_allowed("a.b.gov.in", ["gov.in"])


def test_non_government_domain_yields_a_warning_by_default(monkeypatch):
    monkeypatch.delenv("RESEARCH_ALLOWED_DOMAINS", raising=False)
    f = fetch_url("https://example.org/a", client=client(OK), resolver=resolver({"example.org": [PUBLIC]}))
    assert any("not a government domain" in w for w in f.warnings)


# ------------------------------------------------------------------ local files
def test_plain_fetch_never_reads_local_paths():
    for src in ["/etc/passwd", "../../etc/passwd", "127.0.0.1", "file:///etc/passwd", str(SENIOR)]:
        with pytest.raises(FetchError, match="--file|http"):
            fetch(src)


@requires_symlinks
def test_fetch_file_only_inside_allowed_directories(tmp_path):
    ok = tmp_path / "ok.txt"
    ok.write_text("Applicant must be 60 years of age or above. " * 3)
    assert fetch_file(ok, allowed_dirs=[tmp_path]).kind == "text"
    with pytest.raises(FetchError, match="outside"):
        fetch_file("/etc/passwd", allowed_dirs=[tmp_path])
    with pytest.raises(FetchError, match="outside"):
        fetch_file(tmp_path / ".." / "etc" / "passwd", allowed_dirs=[tmp_path])
    link = tmp_path / "evil.txt"
    inner = tmp_path / "allowed"
    inner.mkdir()
    link.symlink_to("/etc/passwd")
    with pytest.raises(FetchError, match="outside"):
        fetch_file(link, allowed_dirs=[inner, tmp_path / "x"])
    # a symlink inside the allowed dir that points out of it is refused as well
    (inner / "l.txt").symlink_to("/etc/passwd")
    with pytest.raises(FetchError, match="outside"):
        fetch_file(inner / "l.txt", allowed_dirs=[inner])


def test_default_allowed_dirs_are_data_and_fixtures_and_env_overrides(monkeypatch, tmp_path):
    monkeypatch.delenv("RESEARCH_ALLOWED_DIRS", raising=False)
    names = [d.parts[-2:] for d in F.default_allowed_dirs()]
    assert ("tests", "fixtures") in names and any(n[-1] == "data" for n in names)
    assert fetch_file(SENIOR).kind == "html"                     # fixtures are allowed by default
    with pytest.raises(FetchError, match="outside"):
        fetch_file("/etc/hostname")
    monkeypatch.setenv("RESEARCH_ALLOWED_DIRS", str(tmp_path))
    assert F.default_allowed_dirs() == [tmp_path.resolve()]


def test_pinned_transport_works_end_to_end_against_a_local_server(monkeypatch):
    """Real sockets through SafeTransport/PinnedBackend (the 'public' check is faked so loopback is reachable):
    proves the hostname is resolved once, connected by IP, and the request/response path works."""
    class H(BaseHTTPRequestHandler):
        seen_host = None
        def do_GET(self):
            H.seen_host = self.headers.get("Host")
            self.send_response(200); self.send_header("Content-Type", "text/html"); self.end_headers()
            self.wfile.write(PAGE)
        def log_message(self, *a): pass
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    lookups = []
    def res(host, port):
        lookups.append(host)
        return ["127.0.0.1"]
    monkeypatch.setattr(F, "ip_is_public", lambda a: True)
    monkeypatch.setattr(F, "ALLOWED_PORTS", (srv.server_port,))
    try:
        c = F.make_client(timeout=5, resolver=res)
        f = fetch_url(f"http://pinned.example:{srv.server_port}/p", client=c, resolver=res)
        c.close()
    finally:
        srv.shutdown()
    assert f.kind == "html" and H.seen_host.startswith("pinned.example")      # Host header keeps the name
    assert len(lookups) >= 2                                                  # pre-flight + connect-time check
