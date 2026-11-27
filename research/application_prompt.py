"""Prompt for extracting a "how to apply + be careful" record from one scheme's official page text."""
from __future__ import annotations

import json

from .fields import describe_fields

SYSTEM = """You extract practical application guidance for Indian government schemes from ONE official page.
Return a single JSON object and nothing else. Hard rules:
- Every item has a "quote": an exact contiguous copy of text from the page (same words, numbers and spelling; no
  paraphrase, no ellipsis). If you cannot copy a supporting sentence, leave the item out.
- Plain-language fields ("action", "text", "a", "name") are ONE short sentence for a citizen; any number you write
  there MUST also appear in the quote. Do not add facts the quote does not contain.
- Never invent URLs, phone numbers, fees or offices. Use null when the page does not say.
- Do not repeat eligibility rules; only things a person must know or watch while applying and afterwards.

JSON shape:
{
 "mode": "online"|"offline"|"both",
 "portal_url": official website named on the page, or null,
 "office": where to go offline (e.g. "Gram Panchayat / Block office / CSC") only if the page says, else null,
 "helpline": helpline number as written on the page, or null,
 "fees": fee/charge/premium-to-apply text only if the page states it, else null,
 "steps": [{"n": 1, "action": str, "where": str|null, "mode": "online"|"offline", "quote": str}],
 "doc_map": [{"line": <a leftover document line, copied>, "doc": <id from the allowed list or null>,
              "mandatory": true|false}],
 "watch_outs": [{"kind": "exclusion"|"one_per_family"|"deadline"|"renewal"|"repayment"|"overlap"|"benefit_stops"|"other",
                 "text": str, "quote": str, "applies_if": null | {"field": str, "op": str, "value": any}}],
 "faq": [{"q": str, "a": str, "quote": str}],   // at most 6; "quote" must contain the answer text
 "enrol_points": [{"type": "online"|"csc"|"bank"|"post_office"|"gram_panchayat"|"block_office"|"hospital"|
                   "anganwadi"|"other", "name": str, "quote": str}],  // WHERE a citizen goes to enrol/apply
 "grievance": null | {"text": str, "url_or_number": str, "quote": str}
}
watch_outs: exclusions, one-benefit-per-family, deadlines, renewals/annual re-checks, repayment/clawback,
overlap with other schemes, things that stop the benefit. "applies_if" is null unless the watch-out only matters
to people matching a profile condition; then use ONLY these profile fields/ops (ops: eq, ne, gte, lte, in,
any_child):
{fields}
FAQ: quote the answer sentence (at least 25 characters, containing every number you mention in q or a). Use
applies_if when a watch-out clearly depends on age, tax-payer status, government employment, etc.
Steps follow the page order and keep the page's own online/offline split. At most 10 steps, 8 watch_outs.
"""


def build_messages(name: str, sections: dict[str, str], doc_ids: list[str], leftover_lines: list[str]) -> list[dict]:
    page = "\n\n".join(f"## {h}\n{b}" for h, b in sections.items() if b)
    user = (f"Scheme: {name}\n\nPAGE TEXT:\n{page}\n\n"
            f"Allowed document ids: {', '.join(doc_ids)}\n"
            f"Leftover document lines to map in doc_map (JSON): {json.dumps(leftover_lines, ensure_ascii=False)}\n"
            "Return the JSON object now.")
    return [{"role": "system", "content": SYSTEM.replace("{fields}", describe_fields())},
            {"role": "user", "content": user}]
