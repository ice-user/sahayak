"""Free-text hygiene: URLs, e-mail addresses and phone numbers in citizen-facing fields.

Hostile source pages can plant a "helpline" or "apply here" link that ends up in how_to_apply, benefits or a
caveat and is then repeated to citizens. Every URL / phone / e-mail in the free text of a candidate is
flagged for the reviewer; URLs outside the government allowlist (gov.in, nic.in, myscheme.gov.in) and the
scheme's own source domain are BLOCKING unless the reviewer approves them explicitly (``--allow-url``).
"""
from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlparse

GOV_DOMAINS = ("gov.in", "nic.in", "myscheme.gov.in")
URL_ERR_PREFIX = "free-text URL not on the government allowlist"

_TLDS = ("com|org|net|in|gov|edu|co|io|info|biz|me|xyz|app|online|site|link|ly|tk|ru|cn|top|club|shop|store|"
         "live|cc|us|uk|ml|ga|cf|gq|pw|ws|vip|click|page|dev|cloud|tech")
_EMAIL = re.compile(r"[\w.+-]+@(?:[\w-]+\.)+[a-z]{2,}", re.I)
_URL = re.compile(rf"(?i)(?:\bhttps?://|\bwww\.)[^\s<>\"'\]\[{{}}|\\^`]+|"
                  rf"\b(?:[a-z0-9-]+\.)+(?:{_TLDS})\b(?:/[^\s<>\"'\]\[{{}}|\\^`]*)?")
_PHONES = [
    re.compile(r"(?<![\d])(?:\+?91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?!\d)"),                 # Indian mobile
    re.compile(r"(?<![\d])1800[\s-]?\d{3}[\s-]?\d{3,4}(?!\d)"),                           # toll free
    re.compile(r"(?<![\d])0\d{2,4}[\s-]?\d{6,8}(?!\d)"),                                  # landline with STD
    re.compile(r"(?<![\w])\+\d{1,3}[\s-]?\d(?:[\s-]?\d){6,13}(?!\d)"),                    # international
    re.compile(r"(?i)(?:helpline|toll[\s-]?free|call|dial|phone|tel|telephone|mobile|contact|whatsapp|sms)"
               r"\W{0,12}((?:\d[\s-]?){4,12}\d)(?!\d)"),                                   # keyword-led short codes
]
_TRAIL = ".,;:!?)\"'"


def _digits(text: str) -> str:
    return "".join(str(unicodedata.decimal(c)) if unicodedata.category(c) == "Nd" else c for c in text)


def host_of(url: str) -> str:
    u = url if re.match(r"(?i)https?://", url) else "http://" + url
    return (urlparse(u).hostname or "").lower().rstrip(".")


def _host_ok(host: str, domains) -> bool:
    return any(host == d or host.endswith("." + d) for d in domains)


def free_text_fields(rec: dict) -> list[tuple[str, str]]:
    """(label, text) for every citizen-facing free-text field of a database-format record."""
    out: list[tuple[str, str]] = []
    for k in ("name", "ministry", "summary", "benefits", "how_to_apply"):
        if rec.get(k):
            out.append((k, str(rec[k])))
    for k in ("caveats", "documents"):
        out += [(f"{k}[{i}]", str(x)) for i, x in enumerate(rec.get(k) or [])]
    out += [(f"rules[{i}].reason", str(r.get("reason", ""))) for i, r in enumerate(rec.get("rules") or [])
            if isinstance(r, dict)]
    return out


def scan_free_text(rec: dict, *, source_hosts: list[str] | tuple = (), approved_urls=(),
                   source_text: str = "") -> list[dict]:
    """Every URL/e-mail/phone in the record's free text.

    Returns dicts {kind, value, field, status, in_source}; status for URLs is ok | blocked | approved, for
    phones and e-mails ``verify``. ``in_source`` says whether the same value occurs in the source text."""
    src_l = _digits(source_text).lower()
    src_digits = re.sub(r"\D", "", src_l)
    own = {h.removeprefix("www.") for h in source_hosts if h}      # the source's own host: exact, not subdomains
    approved = {a.strip().rstrip("/").lower() for a in approved_urls}
    flags: list[dict] = []
    seen: set[tuple] = set()

    def add(kind, value, label, status, in_source):
        key = (kind, value.lower() if kind != "phone" else re.sub(r"\D", "", value)[-10:], label)
        if key not in seen:
            seen.add(key)
            flags.append({"kind": kind, "value": value, "field": label, "status": status, "in_source": in_source})

    for label, text in free_text_fields(rec):
        text = _digits(text)
        for m in _EMAIL.finditer(text):
            add("email", m.group(0), label, "verify", m.group(0).lower() in src_l)
        rest = _EMAIL.sub(" ", text)
        for m in _URL.finditer(rest):
            url = m.group(0).rstrip(_TRAIL)
            if not url:
                continue
            host = host_of(url)
            if _host_ok(host, GOV_DOMAINS) or host.removeprefix("www.") in own:
                status = "ok"
            elif url.rstrip("/").lower() in approved or ("http://" + url).rstrip("/").lower() in approved:
                status = "approved"
            else:
                status = "blocked"
            add("url", url, label, status, url.lower() in src_l or host in src_l)
        rest = _URL.sub(" ", rest)
        for rx in _PHONES:
            for m in rx.finditer(rest):
                raw = (m.group(1) if rx.groups else m.group(0)).strip()
                d = re.sub(r"\D", "", raw)
                if 4 <= len(d) <= 15:
                    add("phone", raw, label, "verify", d in src_digits)
    return flags


def url_errors(flags: list[dict]) -> list[str]:
    return [f"{URL_ERR_PREFIX}: {f['value']} (in {f['field']}). Remove it with --edit, or approve it explicitly "
            f"with `review --approve --allow-url {f['value']}`" for f in flags if f["kind"] == "url" and f["status"] == "blocked"]


def blocked_urls(flags: list[dict]) -> list[str]:
    return list(dict.fromkeys(f["value"] for f in flags if f["kind"] == "url" and f["status"] == "blocked"))
