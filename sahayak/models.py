"""Data models: the citizen profile and scheme records."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr, field_validator, model_validator

from .states import normalise_state

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "schemes.json"

MAX_CHILDREN = 15
MAX_MONEY = 10**9

# Strict: JSON true/false are never read as 1/0, "62" is not 62, 62.5 is not 62.
Age = Annotated[int, Field(strict=True, ge=0, le=120)]
Rupees = Annotated[int, Field(strict=True, ge=0, le=MAX_MONEY)]


class Child(BaseModel):
    model_config = ConfigDict(extra="forbid")
    age: Optional[Age] = None
    gender: Optional[Literal["male", "female", "other"]] = None


class Profile(BaseModel):
    """Everything the eligibility engine may need. Every field is optional:
    a missing field makes a rule 'unknown', never silently true or false.
    Unknown keys are rejected (a silently ignored "income" would give a wrong verdict)."""

    model_config = ConfigDict(extra="forbid")

    age: Optional[Age] = None
    gender: Optional[Literal["male", "female", "other"]] = None
    state: Optional[StrictStr] = Field(None, max_length=60)
    marital_status: Optional[Literal["single", "married", "widowed", "divorced", "separated"]] = None
    bpl: Optional[StrictBool] = Field(None, description="Household is Below Poverty Line / holds a BPL card")
    annual_income: Optional[Rupees] = Field(None, description="Household income in rupees per year")
    ever_income_tax_payer: Optional[StrictBool] = Field(
        None, description="Is or has EVER been an income tax payer (Atal Pension Yojana)")
    income_tax_payer_last_year: Optional[StrictBool] = Field(
        None, description="Paid income tax in the last assessment year (PM-KISAN)")
    has_bank_account: Optional[StrictBool] = None
    owns_cultivable_land: Optional[StrictBool] = None
    is_govt_employee: Optional[StrictBool] = None
    monthly_pension: Optional[Rupees] = Field(None, description="Monthly pension in rupees; 0 if none")
    household_has_lpg: Optional[StrictBool] = None
    pregnant_or_lactating: Optional[StrictBool] = None
    in_regular_govt_employment: Optional[StrictBool] = None
    children: Optional[list[Child]] = Field(None, max_length=MAX_CHILDREN)

    @field_validator("state")
    @classmethod
    def _canonical_state(cls, v):
        """'UP', 'up' and 'Uttar Pradesh' are one place. A name we do not recognise is kept as typed
        (the rule engine then treats the state as unknown instead of guessing)."""
        if v is None:
            return None
        return normalise_state(v) or (v.strip() or None)

    @model_validator(mode="after")
    def _tax_facts_agree(self):
        if self.income_tax_payer_last_year is True and self.ever_income_tax_payer is False:
            raise ValueError("income_tax_payer_last_year=true contradicts ever_income_tax_payer=false")
        return self


class Scheme(BaseModel):
    id: str
    name: str
    ministry: str
    category: str
    summary: str
    benefits: str
    rules: list[dict]
    caveats: list[str] = []
    documents: list[str] = []
    how_to_apply: str = ""
    source_url: str
    tags: list[str] = []
    aliases: list[str] = []


def load_schemes(path: Path = DATA_PATH) -> dict[str, Scheme]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return {s["id"]: Scheme(**s) for s in raw["schemes"]}
