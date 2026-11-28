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
MAX_HECTARES = 100000

# Strict: JSON true/false are never read as 1/0, "62" is not 62, 62.5 is not 62.
Age = Annotated[int, Field(strict=True, ge=0, le=120)]
Rupees = Annotated[int, Field(strict=True, ge=0, le=MAX_MONEY)]
Percent = Annotated[int, Field(strict=True, ge=0, le=100)]
HouseholdSize = Annotated[int, Field(strict=True, ge=1, le=50)]
Hectares = Annotated[float, Field(strict=True, ge=0, le=MAX_HECTARES)]

OCCUPATIONS = (
    "street_vendor", "artisan_craftsperson", "fisherman", "coir_worker", "agricultural_labourer", "farmer",
    "construction_worker", "domestic_worker", "small_trader_shopkeeper", "self_employed", "salaried_private",
    "govt_employee", "student", "unemployed", "homemaker", "retired", "other",
)
SOCIAL_CATEGORIES = ("general", "obc", "sc", "st", "ews")
RATION_CARD_TYPES = ("aay", "phh", "apl", "none")
HOUSE_TYPES = ("pucca", "kutcha", "none_homeless")


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
    monthly_income: Optional[Rupees] = Field(
        None, description="Household (or the person's own, as the source words it) income in rupees per MONTH. "
                          "Rules treat monthly_income x 12 as annual_income when only one of the two is known")
    household_size: Optional[HouseholdSize] = Field(None, description="Number of people in the household")
    ever_income_tax_payer: Optional[StrictBool] = Field(
        None, description="Is or has EVER been an income tax payer (wording: 'has ever paid income tax', "
                          "Atal Pension Yojana)")
    income_tax_payer_last_year: Optional[StrictBool] = Field(
        None, description="Paid income tax in the last assessment year (wording: 'paid income tax in the "
                          "last/previous assessment year', PM-KISAN)")
    is_current_income_tax_payer: Optional[StrictBool] = Field(
        None, description="Currently pays income tax (wording: 'is an income tax payer', 'paying income tax', "
                          "'income tax assessee'; present tense, no year given)")
    has_bank_account: Optional[StrictBool] = None
    owns_cultivable_land: Optional[StrictBool] = None
    land_holding_hectares: Optional[Hectares] = Field(
        None, description="Total cultivable land held, in HECTARES (1 hectare = 2.47 acres); 0 if none")
    is_govt_employee: Optional[StrictBool] = None
    monthly_pension: Optional[Rupees] = Field(None, description="Monthly pension in rupees; 0 if none")
    household_has_lpg: Optional[StrictBool] = None
    pregnant_or_lactating: Optional[StrictBool] = None
    in_regular_govt_employment: Optional[StrictBool] = None
    children: Optional[list[Child]] = Field(None, max_length=MAX_CHILDREN)
    occupation: Optional[Literal[OCCUPATIONS]] = Field(  # type: ignore[valid-type]
        None, description="Main work: " + ", ".join(OCCUPATIONS))
    is_unorganised_worker: Optional[StrictBool] = Field(
        None, description="Works in the unorganised sector (no regular employer, no social security)")
    is_epfo_esic_nps_member: Optional[StrictBool] = Field(
        None, description="Is a member of EPFO, ESIC or the National Pension System")
    disability_percentage: Optional[Percent] = Field(
        None, description="Disability percentage on the disability certificate (0-100); 0 if no disability")
    social_category: Optional[Literal[SOCIAL_CATEGORIES]] = Field(  # type: ignore[valid-type]
        None, description="Caste category: general, obc, sc, st or ews")
    ration_card_type: Optional[Literal[RATION_CARD_TYPES]] = Field(  # type: ignore[valid-type]
        None, description="Ration card: aay (Antyodaya), phh (priority household / BPL), apl, none")
    breadwinner_deceased: Optional[StrictBool] = Field(
        None, description="The main earning member of the household has died")
    breadwinner_age_at_death: Optional[Age] = Field(None, description="Age of that earning member when they died")
    house_type: Optional[Literal[HOUSE_TYPES]] = Field(  # type: ignore[valid-type]
        None, description="pucca (permanent), kutcha (mud/thatch) or none_homeless")
    has_pucca_house: Optional[StrictBool] = Field(None, description="Household owns a pucca (permanent) house")

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
        if self.is_current_income_tax_payer is True and self.ever_income_tax_payer is False:
            raise ValueError("is_current_income_tax_payer=true contradicts ever_income_tax_payer=false")
        return self

    @model_validator(mode="after")
    def _house_facts_agree(self):
        if self.house_type == "pucca" and self.has_pucca_house is False:
            raise ValueError("house_type=pucca contradicts has_pucca_house=false")
        if self.house_type in ("kutcha", "none_homeless") and self.has_pucca_house is True:
            raise ValueError(f"house_type={self.house_type} contradicts has_pucca_house=true")
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
