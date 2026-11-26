"""Dummy users: a hidden, complete profile, the facts they mention up front,
and an opening question in one of four languages.

The correct answer for every dummy user comes from the rule engine, so each
generated conversation can be graded automatically.
"""
from __future__ import annotations

import random
from dataclasses import asdict, dataclass, field

from ..models import Profile, load_schemes
from ..rules import check_all
from .phrases import ASKS, INTRO, LANGS, RELATIONS, fact_phrase

STATES = ["Tamil Nadu", "Uttar Pradesh", "Bihar", "Maharashtra", "Rajasthan", "West Bengal", "Karnataka",
          "Madhya Pradesh", "Gujarat", "Odisha", "Kerala", "Telangana", "Delhi", "Punjab", "Assam"]

FIELDS = ["age", "gender", "state", "marital_status", "bpl", "annual_income", "ever_income_tax_payer",
          "income_tax_payer_last_year",
          "has_bank_account", "owns_cultivable_land", "is_govt_employee", "monthly_pension",
          "household_has_lpg", "pregnant_or_lactating", "children"]

# persona -> (weight, allowed relations, fields always mentioned up front)
PERSONAS = {
    "elderly_widow":   (12, ["mother", "grandmother", "self"], ["age", "marital_status"]),
    "elderly_man":     (8,  ["father", "grandfather", "self"], ["age"]),
    "senior_70plus":   (10, ["mother", "father", "grandmother", "grandfather"], ["age"]),
    "widow_mid":       (6,  ["mother", "self"], ["age", "marital_status"]),
    "young_widow":     (4,  ["self"], ["age", "marital_status"]),
    "farmer":          (12, ["self", "father"], ["owns_cultivable_land"]),
    "young_worker":    (12, ["self"], ["age"]),
    "pregnant":        (8,  ["wife", "self"], ["pregnant_or_lactating"]),
    "parent_daughter": (10, ["self"], ["children"]),
    "no_lpg":          (8,  ["self", "mother", "wife"], ["household_has_lpg"]),
    "random":          (10, list(RELATIONS), []),
}


@dataclass
class Scenario:
    id: str
    lang: str
    persona: str
    relation: str
    profile: dict                 # complete hidden truth
    revealed: list[str]           # facts in the opening message
    opening: str
    expected_eligible: list[str] = field(default_factory=list)   # with the FULL profile

    def to_dict(self) -> dict:
        return asdict(self)


def _children(r: random.Random, want_daughter: bool, parent_age: int) -> list[dict]:
    n = r.choice([1, 1, 2, 2, 3]) if want_daughter else r.choice([0, 0, 1, 2])
    lo, hi = max(0, parent_age - 45), max(0, parent_age - 18)  # a parent is 18-45 years older than the child
    kids = [{"age": r.randint(lo, hi), "gender": r.choice(["male", "female"])} for _ in range(n)]
    if want_daughter and not any(k["gender"] == "female" and k["age"] <= 12 for k in kids):
        kids[0] = {"age": r.randint(lo, min(12, hi)), "gender": "female"}
    return kids


def sample_profile(r: random.Random, persona: str, relation: str) -> dict:
    gender = RELATIONS[relation][4] or r.choice(["female", "male"])
    age = r.randint(18, 75)
    marital = r.choices(["married", "single", "widowed", "divorced"], [60, 25, 10, 5])[0]
    pregnant = False

    if persona == "elderly_widow":
        gender, age, marital = "female", r.randint(60, 90), "widowed"
    elif persona == "elderly_man":
        gender, age, marital = "male", r.randint(60, 90), r.choice(["married", "widowed"])
    elif persona == "senior_70plus":
        age = r.randint(68, 95)  # 68/69 are useful near-miss cases for the 70+ rule
        marital = r.choice(["married", "widowed"])
    elif persona == "widow_mid":
        gender, age, marital = "female", r.randint(38, 59), "widowed"
    elif persona == "young_widow":
        gender, age, marital = "female", r.randint(22, 39), "widowed"
    elif persona == "young_worker":
        age = r.randint(18, 45)
    elif persona == "pregnant":
        gender, age, marital, pregnant = "female", r.randint(19, 38), "married", True
    elif persona == "parent_daughter":
        age, marital = r.randint(24, 45), "married"
    elif persona == "farmer":
        age = r.randint(25, 72)
    elif persona == "no_lpg":
        gender, age = "female", r.randint(18, 60)
    if relation == "wife":
        marital = "married"
    if relation in ("mother", "father", "grandmother", "grandfather") and age < 40:
        age = r.randint(45, 85)
    if relation in ("grandmother", "grandfather") and age < 60:
        age = r.randint(60, 90)

    bpl = r.random() < 0.55
    income = r.randint(30_000, 150_000) if bpl else r.choice([r.randint(150_000, 600_000), r.randint(600_000, 2_500_000)])
    taxpayer = income > 700_000 and r.random() < 0.85 or (not bpl and r.random() < 0.15)
    govt = r.random() < 0.08 and 21 <= age <= 70
    pension = r.choice([0, 0, 0, 3000, 12000, 25000]) if (age >= 60 and not bpl) else 0
    if persona == "farmer":
        taxpayer = taxpayer and r.random() < 0.3
        govt = govt and r.random() < 0.3
    ever_taxpayer = bool(taxpayer) or r.random() < 0.1  # paid tax last year => has paid tax at some point
    if gender == "female" and 18 <= age <= 45 and persona != "pregnant":
        pregnant = r.random() < 0.05

    return {
        "age": age,
        "gender": gender,
        "state": r.choice(STATES),
        "marital_status": marital,
        "bpl": bpl,
        "annual_income": round(income, -3),
        "ever_income_tax_payer": ever_taxpayer,
        "income_tax_payer_last_year": bool(taxpayer),
        "has_bank_account": r.random() < 0.85,
        "owns_cultivable_land": persona == "farmer" or r.random() < 0.2,
        "is_govt_employee": govt,
        "in_regular_govt_employment": govt,
        "monthly_pension": pension,
        "household_has_lpg": persona != "no_lpg" and r.random() < 0.75,
        "pregnant_or_lactating": pregnant,
        "children": _children(r, persona == "parent_daughter", age) if age >= 20 else [],
    }


def implied_by(field: str, value) -> list[str]:
    """Other facts a user also states by saying this one (kept in step with the phrases in phrases.py)."""
    if field == "is_govt_employee":
        return ["in_regular_govt_employment"]           # the same phrase states both
    if field == "in_regular_govt_employment":
        return ["is_govt_employee"]
    if field == "income_tax_payer_last_year" and value is True:
        return ["ever_income_tax_payer"]                 # paid last year => has paid at some point
    if field == "ever_income_tax_payer" and value is False:
        return ["income_tax_payer_last_year"]            # never paid => did not pay last year
    return []


def _gender_is_implied(relation: str, revealed: list[str]) -> bool:
    return relation != "self" or bool({"gender", "pregnant_or_lactating"} & set(revealed)) or \
        "marital_status" in revealed  # widow/widower and similar words are gendered in all four languages


def opening_text(profile: dict, stated: list[str], relation: str, lang: str, r: random.Random) -> str:
    phrases = [fact_phrase(f, profile[f], lang, profile["gender"]) for f in stated if f != "in_regular_govt_employment"]
    phrases = [p for p in phrases if p]
    sep = {"en": ", ", "hi": ", ", "hinglish": ", ", "ta": ", "}[lang]
    end = "।" if lang == "hi" else "."
    ask = r.choice(ASKS[lang]["self" if relation == "self" else "other"])
    return f"{INTRO[lang](relation)} {sep.join(phrases)}{end} {ask}"


def make_scenario(idx: int, r: random.Random, schemes=None, lang: str | None = None) -> Scenario:
    persona = r.choices(list(PERSONAS), [v[0] for v in PERSONAS.values()])[0]
    _, relations, must = PERSONAS[persona]
    relation = r.choice(relations)
    lang = lang or r.choices(LANGS, [30, 30, 25, 15])[0]
    profile = sample_profile(r, persona, relation)

    optional = [f for f in FIELDS if f not in must and f != "gender"]
    extra = [f for f in optional if r.random() < r.choice([0.15, 0.3, 0.5])]
    stated = list(dict.fromkeys(must + extra))          # said out loud, in this order
    if relation == "self" and r.random() < 0.6:
        stated.insert(0, "gender")
    revealed = list(stated)                             # stated + implied by the wording
    for f in stated:
        revealed += [i for i in implied_by(f, profile[f]) if i not in revealed]
    if _gender_is_implied(relation, revealed) and "gender" not in revealed:
        revealed.append("gender")

    schemes = schemes or load_schemes()
    truth = check_all(Profile(**profile), schemes)
    return Scenario(
        id=f"s{idx:05d}", lang=lang, persona=persona, relation=relation, profile=profile,
        revealed=revealed, opening=opening_text(profile, stated, relation, lang, r),
        expected_eligible=[t.scheme_id for t in truth if t.verdict == "eligible"],
    )


def generate(n: int, seed: int = 0) -> list[Scenario]:
    r = random.Random(seed)
    schemes = load_schemes()
    return [make_scenario(i, r, schemes) for i in range(n)]
