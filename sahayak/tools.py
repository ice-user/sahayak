"""Tools the agent can call, plus their JSON schemas (OpenAI tool format)."""
from __future__ import annotations

import inspect
import json
import logging
from typing import Any, Callable

from pydantic import ValidationError

from .hybrid import build_index
from .models import MAX_CHILDREN, MAX_MONEY, Profile, Scheme, load_schemes
from .rules import check_all

log = logging.getLogger("sahayak.tools")

MAX_TOP_K = 10
MAX_SCHEME_IDS = 25

_PROFILE_PROPS = {
    "age": {"type": "integer", "minimum": 0, "maximum": 120},
    "gender": {"type": "string", "enum": ["male", "female", "other"]},
    "state": {"type": "string", "maxLength": 60},
    "marital_status": {"type": "string", "enum": ["single", "married", "widowed", "divorced", "separated"]},
    "bpl": {"type": "boolean", "description": "Below Poverty Line household / BPL card"},
    "annual_income": {"type": "integer", "minimum": 0, "maximum": MAX_MONEY,
                      "description": "Household income, rupees per year"},
    "ever_income_tax_payer": {"type": "boolean",
                              "description": "Is or has EVER been an income tax payer (matters for Atal Pension Yojana)"},
    "income_tax_payer_last_year": {"type": "boolean",
                                   "description": "Paid income tax in the last assessment year (matters for PM-KISAN)"},
    "has_bank_account": {"type": "boolean"},
    "owns_cultivable_land": {"type": "boolean"},
    "is_govt_employee": {"type": "boolean", "description": "Serving/retired govt employee (not MTS/Class IV/Group D)"},
    "monthly_pension": {"type": "integer", "minimum": 0, "maximum": MAX_MONEY,
                        "description": "Rupees per month; 0 if none"},
    "household_has_lpg": {"type": "boolean"},
    "pregnant_or_lactating": {"type": "boolean"},
    "in_regular_govt_employment": {"type": "boolean"},
    "children": {
        "type": "array", "maxItems": MAX_CHILDREN,
        "items": {"type": "object", "additionalProperties": False, "properties": {
            "age": {"type": "integer", "minimum": 0, "maximum": 120},
            "gender": {"type": "string", "enum": ["male", "female", "other"]},
        }},
    },
}

TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "search_schemes",
        "description": "Find government schemes relevant to a need, e.g. 'widow pension', 'health insurance for elderly', 'girl child savings'. Query in English.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"},
            "top_k": {"type": "integer", "default": 5, "minimum": 1, "maximum": MAX_TOP_K},
        }, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "get_scheme_details",
        "description": ("Get benefits, documents, how to apply and the official source for one scheme. Not needed "
                        "for schemes check_eligibility already returned under 'eligible' (they include all of these)."),
        "parameters": {"type": "object", "properties": {
            "scheme_id": {"type": "string"},
        }, "required": ["scheme_id"]},
    }},
    {"type": "function", "function": {
        "name": "check_eligibility",
        "description": ("Decide eligibility using the official rules. This is the ONLY way to decide eligibility. "
                        "Pass only facts the user actually stated; leave unknown fields out. "
                        "Omit scheme_ids to check every scheme at once. Eligible items include benefits, documents, "
                        "how_to_apply and source_url."),
        "parameters": {"type": "object", "properties": {
            "profile": {"type": "object", "properties": _PROFILE_PROPS, "additionalProperties": False},
            "scheme_ids": {"type": "array", "items": {"type": "string"}, "maxItems": MAX_SCHEME_IDS},
        }, "required": ["profile"]},
    }},
]


class Toolbox:
    def __init__(self, schemes: dict[str, Scheme] | None = None, index=None, search_mode: str | None = None):
        self.schemes = schemes or load_schemes()
        self.index = index or build_index(self.schemes, search_mode)
        self._fns: dict[str, Callable[..., Any]] = {
            "search_schemes": self.search_schemes,
            "get_scheme_details": self.get_scheme_details,
            "check_eligibility": self.check_eligibility,
        }

    def search_schemes(self, query: str, top_k: int = 5) -> list[dict] | dict:
        if not isinstance(top_k, int) or isinstance(top_k, bool):
            return {"error": "top_k must be an integer between 1 and %d." % MAX_TOP_K}
        top_k = max(1, min(top_k, MAX_TOP_K))
        hits = self.index.search(query, top_k)
        return [{"scheme_id": i, "name": self.schemes[i].name, "summary": self.schemes[i].summary, "score": s}
                for i, s in hits]

    def get_scheme_details(self, scheme_id: str) -> dict:
        s = self.schemes.get(scheme_id)
        if not s:
            return {"error": f"Unknown scheme_id '{scheme_id}'", "valid_ids": list(self.schemes)}
        return s.model_dump(exclude={"rules", "tags"})

    def check_eligibility(self, profile: dict, scheme_ids: list[str] | None = None) -> dict:
        if not isinstance(profile, dict):
            return {"error": "profile must be an object of facts the user stated, e.g. {\"age\": 62}.",
                    "valid_fields": sorted(Profile.model_fields)}
        if scheme_ids is not None:
            if not isinstance(scheme_ids, list) or not all(isinstance(i, str) for i in scheme_ids):
                return {"error": "scheme_ids must be a list of scheme id strings (or omitted to check all)."}
            if len(scheme_ids) > MAX_SCHEME_IDS:
                return {"error": f"Too many scheme_ids (max {MAX_SCHEME_IDS}); omit it to check every scheme."}
            unknown = sorted({i for i in scheme_ids if i not in self.schemes})
            if unknown:
                return {"error": f"Unknown scheme_id(s): {', '.join(unknown)}", "valid_ids": list(self.schemes)}
            scheme_ids = list(dict.fromkeys(scheme_ids))
        try:
            p = Profile(**profile)
        except ValidationError as e:
            return {"error": "Invalid profile. Fix the listed fields and call again.",
                    "details": [{"field": ".".join(str(x) for x in d["loc"]), "problem": d["msg"]} for d in e.errors()],
                    "valid_fields": sorted(Profile.model_fields)}
        except TypeError:  # keys that aren't strings
            return {"error": "profile keys must be field names.", "valid_fields": sorted(Profile.model_fields)}
        results = [r.to_dict() for r in check_all(p, self.schemes, scheme_ids)]
        # eligible items carry documents and how_to_apply, so the model never needs get_scheme_details for them
        eligible = [{**r, "documents": list(self.schemes[r["scheme_id"]].documents),
                     "how_to_apply": self.schemes[r["scheme_id"]].how_to_apply}
                    for r in results if r["verdict"] == "eligible"]
        return {
            "eligible": eligible,
            "need_info": [{"scheme_id": r["scheme_id"], "scheme_name": r["scheme_name"], "missing_fields": r["missing_fields"]}
                          for r in results if r["verdict"] == "need_info"],
            "not_eligible": [{"scheme_id": r["scheme_id"], "scheme_name": r["scheme_name"],
                              "reasons": r["failed_reasons"], "caveats": r["caveats"]}
                             for r in results if r["verdict"] == "not_eligible"],
        }

    def call(self, name: str, arguments: str | dict) -> str:
        """Run a tool by name. Always returns a JSON string, never raises.
        Errors are short and actionable for the model; Python details go to the server log only."""
        fn = self._fns.get(name)
        if fn is None:
            return json.dumps({"error": f"Unknown tool '{name}'", "valid_tools": list(self._fns)})
        try:
            args = json.loads(arguments) if isinstance(arguments, str) else (arguments or {})
        except json.JSONDecodeError:
            return json.dumps({"error": "Arguments were not valid JSON. Send a JSON object."})
        if not isinstance(args, dict):
            return json.dumps({"error": "Arguments must be a JSON object."})
        params = inspect.signature(fn).parameters
        unknown = sorted(set(args) - set(params))
        if unknown:
            return json.dumps({"error": f"Unknown argument(s): {', '.join(map(str, unknown))}. "
                                        f"Allowed: {', '.join(params)}."})
        missing = [n for n, p in params.items() if p.default is inspect.Parameter.empty and n not in args]
        if missing:
            return json.dumps({"error": f"Missing required argument(s): {', '.join(missing)}."})
        try:
            return json.dumps(fn(**args), ensure_ascii=False)
        except Exception:  # report generically to the model so it can recover; details stay in the log
            log.exception("tool %s failed", name)
            return json.dumps({"error": f"The {name} tool failed. Try again, or answer without it and say so."})
