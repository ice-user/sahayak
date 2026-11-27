"""Deterministic validator for data/applications.json records ("how to apply + be careful").

Every item must carry a quote that is a verbatim (normalised) substring of the scheme's official source text.
Items that fail a check are dropped (never repaired) and reported in the returned log. Checks:

* shape and enums exactly as the contract (see ``check_record``)
* every quote found verbatim (exact match, not fuzzy) in the source text
* ``portal_url`` / ``locator_url`` / grievance URLs on an official domain; portal_url must also appear in the
  source text (or be a caller-verified known portal); locator_url must be in ``live_urls`` when that is given
* document ids exist in documents.json
* ``applies_if`` uses a real Profile field and op (research/fields.py + validate.py), and its numbers are in its quote
* every number in an item's plain-language text also appears in its quote
* ``alternatives_group`` (optional on a document) only when its quote offers alternatives ("any one of", "or", "/", ...)
* ``routes`` (online / offline alternatives): steps must be the record's own steps; a route summary is either a step's
  action or a short paraphrase whose key nouns all occur in the route's quotes; derived from the steps when absent
* ``source_official`` is computed from source_url (gov.in / nic.in / a scheme's official domain), never taken on trust
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any, Iterable
from urllib.parse import urlparse

from .evidence import find_quote, normalize, numbers_in, value_in_evidence
from .application import ALT_CUE, ALT_GROUPS, derive_routes
from .fields import PROFILE_FIELDS
from .validate import _numeric_values, check_condition

MODES = ("online", "offline", "both")
STEP_MODES = ("online", "offline")
WATCH_KINDS = ("exclusion", "one_per_family", "deadline", "renewal", "repayment", "overlap", "benefit_stops", "other")
ENROL_TYPES = ("online", "csc", "bank", "post_office", "gram_panchayat", "block_office", "hospital", "anganwadi",
               "other")
MAX_FAQ = 6
OFFICIAL_SUFFIXES = (".gov.in", ".nic.in", ".gov")
OFFICIAL_HOSTS = ("enps.nsdl.com", "npscra.nsdl.co.in", "npstrust.org.in", "pfrda.org.in", "nsdl.co.in")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_OFFICE_WORDS = ("csc", "common service", "panchayat", "block", "bank", "post office", "hospital", "anganwadi",
                 "tehsil", "district", "municipal", "ward", "gas agency", "distributor", "mitra")


def is_official_url(url: Any) -> bool:
    if not isinstance(url, str) or not url.strip():
        return False
    p = urlparse(url.strip() if "://" in url else "https://" + url.strip())
    if p.scheme not in ("http", "https") or not p.hostname:
        return False
    host = p.hostname.lower().rstrip(".")
    return (any(host.endswith(s) or host == s.lstrip(".") for s in OFFICIAL_SUFFIXES)
            or any(host == h or host.endswith("." + h) for h in OFFICIAL_HOSTS))


def _url_key(url: str) -> str:
    u = normalize(url).strip()
    u = re.sub(r"^https?://", "", u)
    u = re.sub(r"^www\.", "", u)
    return u.split("#")[0].rstrip("/")


def url_in_text(url: str, source_norm: str) -> bool:
    return _url_key(url) in re.sub(r"https?://(www\.)?", "", source_norm)


def _nonempty(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


def _numbers_missing(text: str, quote: str) -> list[str]:
    missing = set(numbers_in(text)) - set(numbers_in(quote))
    return sorted(format(n, "f") for n in missing)


class _Ctx:
    def __init__(self, source: str, docs: dict, live_urls: Iterable[str] | None, known_portals: Iterable[str]):
        self.source = source
        self.norm = normalize(source)
        self.docs = docs
        self.live = None if live_urls is None else {_url_key(u) for u in live_urls}
        self.known = {_url_key(u) for u in known_portals}
        self.log: list[str] = []

    def drop(self, where: str, why: str) -> None:
        self.log.append(f"dropped {where}: {why}")

    def quote_problem(self, quote: Any) -> str | None:
        if not _nonempty(quote):
            return "quote must be a non-empty string"
        m = find_quote(quote, self.source, _normalized_source=self.norm)
        if not m.found:
            return f"quote not found verbatim ({m.method})"
        if m.method != "exact":
            return "quote only matches approximately"
        return None


def _item_checks(ctx: _Ctx, item: Any, keys: set[str], text_keys: tuple[str, ...]) -> str | None:
    if not isinstance(item, dict):
        return "item must be an object"
    if set(item) != keys:
        return f"keys must be exactly {sorted(keys)}, got {sorted(item)}"
    p = ctx.quote_problem(item.get("quote"))
    if p:
        return p
    for k in text_keys:
        if not _nonempty(item.get(k)):
            return f"{k} must be a non-empty string"
        miss = _numbers_missing(item[k], item["quote"])
        if miss:
            return f"{k}: numbers {miss} are in the text but not in the quote"
    return None


def _check_applies_if(cond: Any, quote: str) -> str | None:
    if cond is None:
        return None
    if not isinstance(cond, dict) or set(cond) != {"field", "op", "value"}:
        return "applies_if must be null or {field, op, value}"
    errs = check_condition(cond, PROFILE_FIELDS, "applies_if", top=True)
    if errs:
        return errs[0]
    for v, op, fld in _numeric_values(cond["value"], cond["op"], cond["field"]):
        if not value_in_evidence(v, quote, op=op, field=fld):
            return f"applies_if number {v} for {fld} is not in the quote"
    return None


_STOP = set("""apply applying application applies visit visiting open opening fill filling give with your from that this then them
their they have will into onto when what where which while also only need needs using use used make made take taken keep
online offline form submit submitting click clicking choose select enter provide upload download login log sign
details detail documents document required require step steps office nearest near scheme account through after before
once able more most some such like want""".split())


def _stem(w: str) -> str:
    return w[:4]


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", normalize(text))


def key_nouns(summary: str) -> list[str]:
    """Content words of a route summary: 4+ letters (or digits), not a generic verb / function word."""
    return [w for w in _words(summary) if (len(w) >= 4 or w.isdigit()) and w not in _STOP]


def summary_supported(summary: str, steps: list[dict]) -> bool:
    """A summary is supported when it is a step's own action, or all its key nouns occur in the route's quotes."""
    if any(summary.strip() == s["action"].strip() for s in steps):
        return True
    quote_words = set(_words(" ".join(s["quote"] for s in steps)))
    stems = {_stem(w) for w in quote_words}
    nouns = key_nouns(summary)
    return bool(nouns) and all(n in quote_words or _stem(n) in stems for n in nouns)


def _check_routes(ctx: _Ctx, raw: Any, steps: list[dict], portal: Any, office: Any) -> list[dict]:
    """Verified routes. Steps stay the evidence: a route step must equal one of the record's clean steps."""
    by_n = {s["n"]: s for s in steps}
    base = derive_routes(steps, portal, office)
    if not isinstance(raw, list) or not raw:
        return base
    places = {portal, office, *(s["where"] for s in steps)} - {None}
    out, seen = [], set()
    for i, r in enumerate(raw):
        if not isinstance(r, dict) or set(r) != {"mode", "summary", "where", "steps"}:
            ctx.drop(f"routes[{i}]", "keys must be exactly mode, summary, where, steps")
            continue
        if r["mode"] not in STEP_MODES or r["mode"] in seen:
            ctx.drop(f"routes[{i}]", "mode must be online or offline, once each")
            continue
        rs = [by_n[s.get("n")] for s in r["steps"] if isinstance(s, dict) and by_n.get(s.get("n")) == s
              ] if isinstance(r["steps"], list) else []
        if not rs:
            ctx.drop(f"routes[{i}]", "no steps that match the record's steps")
            continue
        summary = r["summary"]
        if not _nonempty(summary) or not summary_supported(summary, rs) or _numbers_missing(summary, " ".join(s["quote"] for s in rs)):
            ctx.drop(f"routes[{i}].summary", f"{summary!r} is not supported by the route's quotes; using the first step")
            summary = rs[0]["action"]
        where = r["where"]
        if where is not None and where not in places:
            ctx.drop(f"routes[{i}].where", f"{where!r} is not the portal, office or a step's place")
            where = None
        seen.add(r["mode"])
        out.append({"mode": r["mode"], "summary": summary, "where": where, "steps": [dict(s) for s in rs]})
    return out or base


def check_record(rec: Any, source_text: str, docs: dict, *, live_urls: Iterable[str] | None = None,
                 known_portals: Iterable[str] = ()) -> tuple[dict | None, list[str]]:
    """Return (clean record or None, log). Bad items are dropped; a structurally broken record returns None."""
    if not isinstance(rec, dict):
        return None, ["record is not an object"]
    ctx = _Ctx(source_text, docs, live_urls, known_portals)
    out: dict[str, Any] = {}

    mode = rec.get("mode")
    if mode not in MODES:
        return None, [f"mode must be one of {MODES}, got {mode!r}"]
    out["mode"] = mode

    portal = rec.get("portal_url")
    if portal is not None and not (is_official_url(portal) and (url_in_text(portal, ctx.norm)
                                                                 or _url_key(portal) in ctx.known)):
        ctx.drop("portal_url", f"{portal!r} is not an official domain stated in the source")
        portal = None
    out["portal_url"] = portal

    office = rec.get("office")
    if office is not None:
        low = str(office).casefold()
        bad = [w for w in _OFFICE_WORDS if w in low and w not in ctx.norm]
        if not _nonempty(office) or bad:
            ctx.drop("office", f"not supported by the source ({bad or 'empty'})")
            office = None
    out["office"] = office

    helpline = rec.get("helpline")
    if helpline is not None:
        src_digits = re.sub(r"\D", "", ctx.norm)
        nums = re.findall(r"\d[\d\- ]{3,}\d", str(helpline))
        if not nums or not all(re.sub(r"\D", "", n) in src_digits for n in nums):
            ctx.drop("helpline", f"{helpline!r} digits not in the source")
            helpline = None
    out["helpline"] = helpline

    fees = rec.get("fees")
    if fees is not None and (not _nonempty(fees) or set(numbers_in(fees)) - set(numbers_in(source_text))):
        ctx.drop("fees", f"{fees!r} is empty or has numbers not in the source")
        fees = None
    out["fees"] = fees

    steps = []
    for i, s in enumerate(rec.get("steps") or []):
        why = _item_checks(ctx, s, {"n", "action", "where", "mode", "quote"}, ("action",))
        if not why and (not isinstance(s["n"], int) or isinstance(s["n"], bool)):
            why = "n must be an int"
        if not why and s["mode"] not in STEP_MODES:
            why = f"mode must be one of {STEP_MODES}"
        if not why and s["where"] is not None and not _nonempty(s["where"]):
            why = "where must be null or a string"
        if why:
            ctx.drop(f"steps[{i}]", why)
        else:
            steps.append(dict(s))
    steps.sort(key=lambda s: s["n"])
    for k, s in enumerate(steps, 1):
        s["n"] = k
    out["steps"] = steps
    out["routes"] = _check_routes(ctx, rec.get("routes"), steps, portal, office)

    documents, seen = [], set()
    for i, d in enumerate(rec.get("documents") or []):
        keys = {"doc", "as_written", "mandatory", "quote"} | ({"alternatives_group"} if "alternatives_group" in d else set())
        why = _item_checks(ctx, d, keys, ("as_written",))
        if not why and "alternatives_group" in d:
            g = d["alternatives_group"]
            if g not in ALT_GROUPS:
                why = f"alternatives_group must be one of {sorted(ALT_GROUPS)}"
            elif not ALT_CUE.search(d["quote"]):
                why = "alternatives_group set but the quote offers no alternatives (any one of / or / / / either)"
        if not why and d["doc"] not in docs:
            why = f"doc id {d['doc']!r} is not in documents.json"
        if not why and not isinstance(d["mandatory"], bool):
            why = "mandatory must be a bool"
        if not why and (d["doc"], d["as_written"]) in seen:
            why = "duplicate document"
        if why:
            ctx.drop(f"documents[{i}]", why)
        else:
            seen.add((d["doc"], d["as_written"]))
            documents.append(dict(d))
    out["documents"] = documents

    watch = []
    for i, w in enumerate(rec.get("watch_outs") or []):
        why = _item_checks(ctx, w, {"kind", "text", "quote", "applies_if"}, ("text",))
        if not why and w["kind"] not in WATCH_KINDS:
            why = f"kind must be one of {WATCH_KINDS}"
        if not why:
            why = _check_applies_if(w["applies_if"], w["quote"])
        if why:
            ctx.drop(f"watch_outs[{i}]", why)
        else:
            watch.append(dict(w))
    out["watch_outs"] = watch

    faq = []
    for i, f in enumerate(rec.get("faq") or []):
        why = _item_checks(ctx, f, {"q", "a", "quote"}, ("q", "a"))
        if not why and len(faq) >= MAX_FAQ:
            why = f"more than {MAX_FAQ} faq items"
        if why:
            ctx.drop(f"faq[{i}]", why)
        else:
            faq.append(dict(f))
    out["faq"] = faq

    enrol = []
    for i, e in enumerate(rec.get("enrol_points") or []):
        why = _item_checks(ctx, e, {"type", "name", "locator_url", "quote"}, ("name",))
        if not why and e["type"] not in ENROL_TYPES:
            why = f"type must be one of {ENROL_TYPES}"
        if why:
            ctx.drop(f"enrol_points[{i}]", why)
            continue
        e = dict(e)
        u = e["locator_url"]
        if u is not None:
            if not is_official_url(u):
                ctx.drop(f"enrol_points[{i}].locator_url", f"{u!r} is not on an official domain")
                e["locator_url"] = None
            elif ctx.live is not None and _url_key(u) not in ctx.live:
                ctx.drop(f"enrol_points[{i}].locator_url", f"{u!r} was not confirmed live (HTTP 200)")
                e["locator_url"] = None
        enrol.append(e)
    out["enrol_points"] = enrol

    g = rec.get("grievance")
    if g is not None:
        why = _item_checks(ctx, g, {"text", "url_or_number", "quote"}, ("text",))
        if not why:
            v = g["url_or_number"]
            digits = re.sub(r"\D", "", v) if isinstance(v, str) else ""
            if not _nonempty(v):
                why = "url_or_number must be a non-empty string"
            elif re.search(r"[a-z]\.[a-z]|://", v.casefold()):
                host = v.split("@")[-1] if "@" in v else v
                if not is_official_url(host):
                    why = f"{v!r} is not on an official domain"
                elif not url_in_text(host, ctx.norm) and "@" not in v:
                    why = f"{v!r} is not in the source"
            elif not digits or digits not in re.sub(r"\D", "", ctx.norm):
                why = f"{v!r} is not in the source"
        if why:
            ctx.drop("grievance", why)
            g = None
        else:
            g = dict(g)
    out["grievance"] = g

    if not _nonempty(rec.get("source_url")) or not str(rec["source_url"]).startswith("http"):
        return None, ctx.log + ["source_url missing"]
    if not (isinstance(rec.get("verified_at"), str) and _DATE.match(rec["verified_at"])):
        return None, ctx.log + ["verified_at must be YYYY-MM-DD"]
    out["source_url"], out["verified_at"] = rec["source_url"], rec["verified_at"]
    out["source_official"] = is_official_url(rec["source_url"])
    return out, ctx.log


def check_documents_file(docs: Any) -> list[str]:
    """Problems with data/documents.json shape (empty list = fine)."""
    if not isinstance(docs, dict) or not docs:
        return ["documents.json must be a non-empty object"]
    errs = []
    for k, d in docs.items():
        if not isinstance(d, dict) or set(d) != {"name", "aliases", "how_to_get"}:
            errs.append(f"{k}: keys must be name, aliases, how_to_get")
            continue
        if not isinstance(d["name"], dict) or set(d["name"]) != {"en", "hi", "ta", "hinglish"} \
                or not all(_nonempty(v) for v in d["name"].values()):
            errs.append(f"{k}: name needs non-empty en, hi, ta, hinglish")
        if not isinstance(d["aliases"], list) or not all(_nonempty(a) for a in d["aliases"]):
            errs.append(f"{k}: aliases must be a list of strings")
        h = d["how_to_get"]
        if h is not None and (not isinstance(h, dict) or set(h) != {"text", "source_url"}
                              or not _nonempty(h.get("text")) or not str(h.get("source_url", "")).startswith("http")):
            errs.append(f"{k}: how_to_get must be null or {{text, source_url}}")
    return errs


def tally(rec: dict) -> Counter:
    return Counter({k: len(rec[k]) for k in ("steps", "documents", "watch_outs", "faq", "enrol_points")})
