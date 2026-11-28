"""Compact few-shot prompt for labelling ONE eligibility bullet (teacher for the fine-tuning set)."""
from __future__ import annotations

import json

from .fields import describe_fields

RULES_TEXT = """You convert ONE eligibility bullet of an Indian government scheme into JSON. Output JSON only:
{"rules":[{"field":..,"op":..,"value":..,"quote":..}],"unmapped":[{"quote":..,"reason":..}]}
- rules: only conditions a field below can express. op is one of eq, ne, gte, lte, in, any_child.
  Integers for numbers (rupees as plain integers: 2.5 lakh = 250000; age in years). "below 18" = lte 17, "above 60" = gte 61, "60 and above" = gte 60. A limit per month goes on monthly_income as written (no x12); a limit per year on annual_income.
- quote: copy-paste a contiguous span of the bullet, character for character. Every number in a rule must be inside its quote.
- unmapped: every other condition the bullet carries (caste, occupation, disability, education, documents, institutions, ...), with a short reason (max 8 words). Quote verbatim too.
- Every condition in the bullet goes to rules or unmapped. A bullet with no condition gives both lists empty. Never invent a field.
Fields:
"""

SHOTS = [
    ("The applicant should be a woman aged between 18 and 60 years with annual family income below Rs. 2,50,000.",
     {"rules": [
         {"field": "gender", "op": "eq", "value": "female", "quote": "should be a woman"},
         {"field": "age", "op": "gte", "value": 18, "quote": "aged between 18 and 60 years"},
         {"field": "age", "op": "lte", "value": 60, "quote": "aged between 18 and 60 years"},
         {"field": "annual_income", "op": "lte", "value": 249999, "quote": "annual family income below Rs. 2,50,000"}],
      "unmapped": []}),
    ("The applicant must be a permanent resident of Assam and belong to the Scheduled Tribe community.",
     {"rules": [{"field": "state", "op": "eq", "value": "Assam", "quote": "resident of Assam"}],
      "unmapped": [{"quote": "belong to the Scheduled Tribe community", "reason": "caste category not a profile field"}]}),
    ("The family should have a girl child below 10 years of age.",
     {"rules": [{"field": "children", "op": "any_child", "value": [
         {"field": "gender", "op": "eq", "value": "female"}, {"field": "age", "op": "lte", "value": 9}],
         "quote": "girl child below 10 years of age"}],
      "unmapped": []}),
    ("Applicant should be a farmer owning cultivable land and having a savings bank account.",
     {"rules": [
         {"field": "owns_cultivable_land", "op": "eq", "value": True, "quote": "owning cultivable land"},
         {"field": "has_bank_account", "op": "eq", "value": True, "quote": "having a savings bank account"}],
      "unmapped": [{"quote": "should be a farmer", "reason": "occupation not a profile field"}]}),
    ("Beneficiaries will be selected on first come first serve basis.",
     {"rules": [], "unmapped": []}),
]


def system_prompt() -> str:
    return RULES_TEXT + describe_fields()


def build_messages(bullet: str) -> list[dict]:
    msgs: list[dict] = [{"role": "system", "content": system_prompt()}]
    for b, out in SHOTS:
        msgs.append({"role": "user", "content": f"Bullet: {b}"})
        msgs.append({"role": "assistant", "content": json.dumps(out, ensure_ascii=False)})
    msgs.append({"role": "user", "content": f"Bullet: {bullet}"})
    return msgs
