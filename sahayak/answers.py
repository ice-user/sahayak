"""Plain answers to profile enums, in English, Hindi (Devanagari), Hinglish and Tamil.

The model is told the enums, but small models still pass what the user said ("sabzi bechti hai") instead of the
enum value. ``normalise_enums`` repairs that in code before the profile is validated, so a street vendor who
answers in Hinglish is a street_vendor. A phrase that matches nothing is left alone (validation then reports it),
never guessed. Order matters inside each table: the first matching entry wins, so specific entries come first.
"""
from __future__ import annotations

import re

# value -> phrases. Latin phrases match at a word start (so "retire" covers "retired"); others match anywhere.
_OCCUPATION: list[tuple[str, tuple[str, ...]]] = [
    ("street_vendor", ("street vend", "hawker", "sell veg", "sells veg", "sell fruit", "vegetable vendor", "sells on the street", "sabzi bech", "sabji bech", "phal bech", "thela", "rehri", "pheri",
                       "sabzi ki dukan lagat", "सब्ज़ी बेच", "सब्जी बेच", "फल बेच", "ठेला", "रेहड़ी", "फेरी",
                       "தெருவோர", "காய்கறி விற்", "தள்ளுவண்டி")),
    ("coir_worker", ("coir", "nariyal ke resh", "नारियल के रेशे", "कॉयर", "தேங்காய் நார்", "கயிறு")),
    ("fisherman", ("fisher", "machhua", "machhli pakad", "machli pakad", "मछुआ", "मछली पकड़", "மீனவ", "மீன் பிடி")),
    ("agricultural_labourer", ("agricultural labour", "farm labour", "khet mazdoor", "khet mein mazdoori",
                               "kheti mein mazdoori", "daily wage in field", "खेतिहर मज़दूर", "खेतिहर मजदूर",
                               "खेत मजदूर", "खेत में मजदूरी", "விவசாயக் கூலி", "விவசாய கூலி", "வயலில் கூலி")),
    ("domestic_worker", ("domestic worker", "domestic help", "maid", "kaamwali", "kaam wali", "ghar ghar kaam",
                         "ghar ka kaam karti", "house help", "घरों में काम", "काम वाली", "कामवाली", "नौकरानी",
                         "வீட்டு வேலை")),
    ("construction_worker", ("construction", "mistri", "raj mistri", "building worker", "nirman mazdoor", "निर्माण",
                             "मिस्त्री", "கட்டுமான", "கொத்தனார்")),
    ("artisan_craftsperson", ("artisan", "craft", "carpenter", "potter", "blacksmith", "weaver", "tailor", "cobbler",
                              "barber", "goldsmith", "mason", "kumhar", "lohar", "sunar", "darzi", "badhai", "nai ",
                              "बढ़ई", "कुम्हार", "लोहार", "सुनार", "दर्जी", "बुनकर", "कारीगर", "शिल्प", "தச்சர்",
                              "குயவர்", "நெசவாளர்", "தையல்", "கைவினை", "கொல்லர்")),
    ("govt_employee", ("government employee", "govt employee", "government job", "govt job", "sarkari naukri",
                       "sarkari karmchari", "सरकारी नौकरी", "सरकारी कर्मचारी", "அரசு ஊழியர்", "அரசு வேலை")),
    ("salaried_private", ("private job", "private company", "private naukri", "private sector", "salaried",
                          "company mein job", "निजी नौकरी", "प्राइवेट", "प्राईवेट", "தனியார்")),
    ("farmer", ("farmer", "farming", "kisan", "kheti kar", "kheti baadi", "kheti-baadi", "cultivat", "किसान",
                "खेती कर", "खेती-बाड़ी", "விவசாயி", "விவசாயம்")),
    ("small_trader_shopkeeper", ("shopkeeper", "shop owner", "small shop", "trader", "kirana", "dukan", "dukaan",
                                 "vyapar", "दुकान", "व्यापार", "கடை", "வியாபார")),
    ("self_employed", ("self employ", "self-employ", "own business", "apna kaam", "apna business", "swarozgar",
                       "स्वरोज़गार", "स्वरोजगार", "अपना काम", "अपना व्यवसाय", "சுயதொழில்", "சொந்தத் தொழில்")),
    ("student", ("student", "padhai", "padh raha", "padh rahi", "studying", "छात्र", "विद्यार्थी", "पढ़ाई",
                 "पढ़ रहा", "पढ़ रही", "மாணவ", "படிக்கிறேன்")),
    ("unemployed", ("unemployed", "jobless", "berozgar", "no job", "koi kaam nahi", "बेरोज़गार", "बेरोजगार",
                    "कोई काम नहीं", "வேலையில்லை", "வேலை இல்லை")),
    ("homemaker", ("homemaker", "housewife", "house wife", "grihini", "ghar sambhal", "गृहिणी", "गृहणी",
                   "घर संभाल", "இல்லத்தரசி")),
    ("retired", ("retire", "pensioner", "sevanivrit", "सेवानिवृत्त", "रिटायर", "ஓய்வு பெற்ற", "ஓய்வு")),
]

_NEGATION = re.compile(r"(?<![a-z])(?:no|not|without|nahi|nahin|illai|nothing)(?![a-z])|नहीं|नही|இல்லை|இல்ல")

_SOCIAL = [
    ("st", ("scheduled tribe", "adivasi", "anusuchit janjati", "tribal", "अनुसूचित जनजाति", "आदिवासी", "जनजाति",
            "பழங்குடி", "(?<![a-z])st(?![a-z])")),
    ("sc", ("scheduled caste", "anusuchit jati", "anusuchit jaati", "dalit", "अनुसूचित जाति", "दलित",
            "பட்டியல் சாதி", "பட்டியலின", "ஆதி திராவிட", "(?<![a-z])sc(?![a-z])")),
    ("obc", ("obc", "other backward", "pichhda", "pichda", "backward class", "पिछड़ा", "पिछड़े",
             "பிற்படுத்தப்பட்ட", "மிகவும் பிற்படுத்தப்பட்ட")),
    ("ews", ("ews", "economically weaker", "आर्थिक रूप से कमज़ोर", "आर्थिक रूप से कमजोर", "பொருளாதாரத்தில் நலிவடைந்த")),
    ("general", ("general", "unreserved", "samanya", "open category", "सामान्य", "பொது")),
]

_RATION = [
    ("aay", ("aay", "antyodaya", "antodaya", "अंत्योदय", "அந்தியோதயா", "அந்த்யோதயா")),
    ("phh", ("phh", "priority household", "priority card", "bpl", "pink card", "gulabi", "गुलाबी", "बीपीएल",
             "முன்னுரிமை")),
    ("apl", ("apl", "above poverty", "एपीएल")),
]

_HOUSE = [
    ("none_homeless", ("homeless", "no house", "no home", "no roof", "ghar nahi", "ghar nahin", "bina ghar", "footpath",
                       "pavement", "street mein rahta", "बेघर", "घर नहीं", "फुटपाथ", "வீடற்ற", "வீடு இல்லை",
                       "வீடில்லை")),
    ("kutcha", ("kutcha", "kuccha", "kachcha", "kaccha", "kacha", "jhopdi", "jhopri", "jhuggi", "mud house", "thatch",
                "hut", "कच्चा", "कच्चे", "झोपड़ी", "झुग्गी", "குடிசை", "மண் வீடு", "ஓலை")),
    ("pucca", ("pucca", "pakka", "pukka", "concrete", "permanent house", "brick house", "पक्का", "पक्के",
               "கான்கிரீட்", "காங்கிரீட்", "கல் வீடு")),
]

_TABLES = {"occupation": _OCCUPATION, "social_category": _SOCIAL, "ration_card_type": _RATION, "house_type": _HOUSE}
CHOICES = {f: tuple(v for v, _ in t) for f, t in _TABLES.items()}
CHOICES["occupation"] += ("other",)
ENUM_FIELDS = tuple(_TABLES)


def _has(text: str, phrase: str) -> bool:
    if phrase.startswith("(?"):
        return re.search(phrase, text) is not None
    if phrase.isascii():
        # a word start, so "retire" matches "retired" but "hut" does not match "shut"
        return re.search(r"(?<![a-z])" + re.escape(phrase.strip()) + (r"(?![a-z])" if phrase.endswith(" ") else ""),
                         text) is not None
    return phrase in text


def map_answer(field: str, answer: object) -> str | None:
    """The enum value of ``field`` that a plain answer means, or None when it is not recognisable."""
    if field not in _TABLES or not isinstance(answer, str):
        return None
    text = " ".join(answer.casefold().replace("_", " ").replace("-", " ").split())
    if not text:
        return None
    for value in CHOICES[field]:
        if text == value.replace("_", " "):
            return value
    if field == "ration_card_type" and "ration" in text.replace("राशन", "ration").replace("ரேஷன்", "ration") \
            and _NEGATION.search(text):
        return "none"
    if field == "ration_card_type" and text in ("none", "no card", "nahi", "nahin"):
        return "none"
    if field == "house_type" and "ghar" in text and "nahi" in text and "kachcha" not in text:
        return "none_homeless"
    for value, phrases in _TABLES[field]:
        if any(_has(text, p) for p in phrases):
            # "no private job" / "sarkari naukri nahi hai" is a negation of that occupation, not the occupation
            if field == "occupation" and _NEGATION.search(text) and value not in ("unemployed",):
                continue
            return value
    return None


def normalise_enums(profile: dict) -> dict:
    """Copy of ``profile`` where a free-text value of an enum field is replaced by the enum it means. Values that
    already are valid enums, or that are not understood, pass through unchanged."""
    out = dict(profile)
    for f in ENUM_FIELDS:
        v = out.get(f)
        if isinstance(v, str) and v not in CHOICES[f]:
            mapped = map_answer(f, v)
            if mapped:
                out[f] = mapped
    return out


def hint_text() -> str:
    """One line per enum for the tool description (kept short: examples only)."""
    return (
        "Map plain answers to enums, in any language: occupation street_vendor ('sabzi bechti hai', 'thela lagata hu'), "
        "artisan_craftsperson (tailor, potter, carpenter, weaver), fisherman, coir_worker, agricultural_labourer "
        "('khet mein mazdoori'), farmer ('kheti karta hu'), construction_worker ('mistri'), domestic_worker "
        "('ghar ghar kaam'), small_trader_shopkeeper ('dukan hai'), self_employed, salaried_private, govt_employee "
        "('sarkari naukri'), student, unemployed ('berozgar'), homemaker ('grihini'), retired, other; "
        "social_category sc/st/obc/ews/general ('anusuchit jati' is sc); ration_card_type aay ('antyodaya'), phh "
        "(BPL / priority card), apl, none; house_type pucca ('pakka'), kutcha ('kachcha', 'jhopdi'), none_homeless "
        "('ghar nahi').")
