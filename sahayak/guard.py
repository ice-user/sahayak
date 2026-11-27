"""Deterministic post-check on every final answer: the model may only offer schemes the rule engine confirmed.

  violations(answer, verdicts)   schemes the answer offers as available that the latest check_eligibility
                                 did not return as "eligible" (or that were never checked at all)
  neutralize_urls(answer, hosts) replaces links that are not tool-provided source URLs or official domains

Polarity comes from sahayak.mentions (clause level), shared with the datagen grader.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

from .mentions import offered_schemes

ALLOWED_DOMAINS = ("gov.in", "nic.in", "myscheme.gov.in")
LINK_REMOVED = "[link removed]"

_TLDS = ("com|net|org|in|co|io|app|xyz|info|biz|me|link|site|online|top|club|ly|gl|to|cc|ru|cn|tk|ml|ga|cf|gq|"
         "shop|store|live|page|dev|click|work|vip|win|buzz|fun|icu")
_URL = re.compile(
    r"\[(?P<text>[^\]]*)\]\((?P<md>[^)\s]+)\)"                            # markdown link
    r"|(?P<url>https?://[^\s<>\"']+)"                                      # explicit URL
    r"|(?P<www>\bwww\.[^\s<>\"']+)"
    rf"|(?P<bare>\b(?:[a-z0-9-]+\.)+(?:{_TLDS})\b(?:/[^\s<>\"']*)?)", re.I)
_TRAIL = ".,;:!?)]}"


def violations(answer: str, verdicts: dict[str, str]) -> list[str]:
    """Scheme ids offered in `answer` that `verdicts` (scheme_id -> eligible/need_info/not_eligible) doesn't confirm."""
    return [sid for sid in offered_schemes(answer) if verdicts.get(sid) != "eligible"]


def _host(url: str) -> str:
    if not re.match(r"https?://", url, re.I):
        url = "http://" + url
    return (urlparse(url).hostname or "").lower().rstrip(".")


def host_allowed(host: str, extra_hosts: set[str] | frozenset[str] = frozenset()) -> bool:
    """Official domains, hosts the tools returned as a source_url, and the hosts of the curated help resources
    (data/help_resources.json, each verified against an official page)."""
    from .vulnerability import help_hosts  # late import: keeps guard importable on its own
    return any(host == d or host.endswith("." + d) for d in (*ALLOWED_DOMAINS, *extra_hosts, *help_hosts()))


def neutralize_urls(text: str, extra_hosts: set[str] | frozenset[str] = frozenset()) -> str:
    """Remove links unless they are on an official domain (gov.in, nic.in) or a host the tools returned as a source_url."""
    extra = {h.lower() for h in extra_hosts}

    def repl(m: re.Match) -> str:
        if m.group("md") is not None:
            return m.group(0) if host_allowed(_host(m.group("md")), extra) else m.group("text")
        raw = m.group(0)
        core = raw.rstrip(_TRAIL)
        tail = raw[len(core):]
        return raw if host_allowed(_host(core), extra) else LINK_REMOVED + tail

    return _URL.sub(repl, text)


def hosts_of(*urls: str) -> set[str]:
    return {h for h in (_host(u) for u in urls if isinstance(u, str) and u) if h}
