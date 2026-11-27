"""Indian states and union territories: one canonical spelling per place, plus common aliases.

Used by the rule engine (a scheme limited to some states compares canonical names, so "UP", "u.p." and
"Uttar Pradesh" all match) and by the research validator (a rule value must be a canonical name).
"""
from __future__ import annotations

import re

STATES: tuple[str, ...] = (
    "Andaman and Nicobar Islands", "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chandigarh",
    "Chhattisgarh", "Dadra and Nagar Haveli and Daman and Diu", "Delhi", "Goa", "Gujarat", "Haryana",
    "Himachal Pradesh", "Jammu and Kashmir", "Jharkhand", "Karnataka", "Kerala", "Ladakh", "Lakshadweep",
    "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Puducherry",
    "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand",
    "West Bengal",
)

_RAW_ALIASES: dict[str, str] = {
    "andaman": "Andaman and Nicobar Islands", "nicobar": "Andaman and Nicobar Islands",
    "andaman nicobar islands": "Andaman and Nicobar Islands", "a n islands": "Andaman and Nicobar Islands",
    "andhra": "Andhra Pradesh", "ap": "Andhra Pradesh",
    "arunachal": "Arunachal Pradesh",
    "bihar": "Bihar",
    "cg": "Chhattisgarh", "chattisgarh": "Chhattisgarh", "chhatisgarh": "Chhattisgarh",
    "dadra nagar haveli": "Dadra and Nagar Haveli and Daman and Diu",
    "dadra and nagar haveli": "Dadra and Nagar Haveli and Daman and Diu",
    "daman and diu": "Dadra and Nagar Haveli and Daman and Diu",
    "daman diu": "Dadra and Nagar Haveli and Daman and Diu",
    "dnh": "Dadra and Nagar Haveli and Daman and Diu", "dnhdd": "Dadra and Nagar Haveli and Daman and Diu",
    "nct of delhi": "Delhi", "new delhi": "Delhi", "delhi ncr": "Delhi", "nct delhi": "Delhi",
    "hp": "Himachal Pradesh", "himachal": "Himachal Pradesh",
    "jk": "Jammu and Kashmir", "j and k": "Jammu and Kashmir", "jammu kashmir": "Jammu and Kashmir",
    "jammu": "Jammu and Kashmir", "kashmir": "Jammu and Kashmir",
    "mp": "Madhya Pradesh", "mh": "Maharashtra",
    "orissa": "Odisha", "odisa": "Odisha",
    "pondicherry": "Puducherry", "pondy": "Puducherry",
    "tn": "Tamil Nadu", "tamilnadu": "Tamil Nadu", "tamil nad": "Tamil Nadu",
    "ts": "Telangana", "telengana": "Telangana",
    "up": "Uttar Pradesh", "uttarpradesh": "Uttar Pradesh",
    "uk": "Uttarakhand", "uttaranchal": "Uttarakhand", "uttrakhand": "Uttarakhand",
    "wb": "West Bengal", "bengal": "West Bengal",
    "kl": "Kerala", "kerela": "Kerala", "ka": "Karnataka", "rj": "Rajasthan", "gj": "Gujarat",
}


def _key(s: str) -> str:
    s = s.casefold().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return re.sub(r"\s+", " ", s)


_LOOKUP: dict[str, str] = {_key(s): s for s in STATES}
_LOOKUP.update({_key(k): v for k, v in _RAW_ALIASES.items()})
_LOOKUP.update({_key(s).replace(" ", ""): s for s in STATES})   # "tamilnadu", "uttarpradesh"


def normalise_state(name: object) -> str | None:
    """Canonical state/UT name for ``name`` (case, punctuation, '&' and common abbreviations tolerated),
    or None if it is not recognised."""
    if not isinstance(name, str):
        return None
    k = _key(name)
    if not k:
        return None
    return _LOOKUP.get(k) or _LOOKUP.get(k.replace(" ", ""))


def is_canonical(name: object) -> bool:
    return isinstance(name, str) and name in STATES
