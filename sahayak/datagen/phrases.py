"""Language templates for dummy users: how each fact is said in en / hi / hinglish / ta.

Kept deliberately simple and literal. Use the optional LLM paraphrase step in
run.py for more natural, varied wording.
"""
from __future__ import annotations

LANGS = ["en", "hi", "hinglish", "ta"]

RELATIONS = {
    #             en                  hi                 hinglish        ta              gender
    "self":        ("me",              "मेरे",             "Mere",          "என்னை",         None),
    "mother":      ("my mother",       "मेरी माँ",         "Meri maa",      "என் அம்மா",     "female"),
    "father":      ("my father",       "मेरे पिताजी",      "Mere papa",     "என் அப்பா",     "male"),
    "grandmother": ("my grandmother",  "मेरी दादी",        "Meri dadi",     "என் பாட்டி",    "female"),
    "grandfather": ("my grandfather",  "मेरे दादाजी",      "Mere dadaji",   "என் தாத்தா",    "male"),
    "wife":        ("my wife",         "मेरी पत्नी",       "Meri wife",     "என் மனைவி",     "female"),
}

INTRO = {
    "en": lambda rel: "About me:" if rel == "self" else f"About {RELATIONS[rel][0]}:",
    "hi": lambda rel: "मेरे बारे में:" if rel == "self" else f"{RELATIONS[rel][1]} के बारे में:",
    "hinglish": lambda rel: "Mere baare mein:" if rel == "self" else f"{RELATIONS[rel][2]} ke baare mein:",
    "ta": lambda rel: "என்னைப் பற்றி:" if rel == "self" else f"{RELATIONS[rel][3]} பற்றி:",
}

ASKS = {
    "en": {"self": ["What government schemes can I get?", "Which schemes am I eligible for?",
                    "Is there any government help for me?"],
           "other": ["What government schemes can they get?", "Which schemes are they eligible for?",
                     "Is there any government scheme for them?"]},
    "hi": {"self": ["मुझे कौन सी सरकारी योजनाएं मिल सकती हैं?", "क्या मेरे लिए कोई सरकारी योजना है?"],
           "other": ["उन्हें कौन सी सरकारी योजनाएं मिल सकती हैं?", "क्या उनके लिए कोई सरकारी योजना है?"]},
    "hinglish": {"self": ["Mere liye kaunsi sarkari yojana hai?", "Mujhe kaunsi schemes mil sakti hain?"],
                 "other": ["Unke liye kaunsi sarkari yojana hai?", "Unko kaunsi schemes mil sakti hain?"]},
    "ta": {"self": ["எனக்கு என்ன அரசு திட்டங்கள் கிடைக்கும்?", "எனக்கு ஏதாவது அரசு உதவி உண்டா?"],
           "other": ["அவருக்கு என்ன அரசு திட்டங்கள் கிடைக்கும்?", "அவருக்கு ஏதாவது அரசு திட்டம் உண்டா?"]},
}

DONT_KNOW = {"en": "I'm not sure about that.", "hi": "इसके बारे में पता नहीं।",
             "hinglish": "Iske baare mein pata nahi.", "ta": "அது எனக்கு தெரியாது."}
NOTHING_MORE = {"en": "That's all I know.", "hi": "बस इतना ही पता है।",
                "hinglish": "Bas itna hi pata hai.", "ta": "எனக்கு தெரிந்தது இவ்வளவுதான்."}
END = {".": {"en": ".", "hi": "।", "hinglish": ".", "ta": "."}}


def _yn(lang, value, yes, no):
    return yes[lang] if value else no[lang]


def fact_phrase(field: str, value, lang: str, gender: str | None = None) -> str | None:
    """How a dummy user states one fact. Returns None for facts with no phrasing."""
    if field == "age":
        return {"en": f"age {value}", "hi": f"उम्र {value} साल", "hinglish": f"umar {value} saal",
                "ta": f"வயது {value}"}[lang]
    if field == "gender":
        f = value == "female"
        return {"en": "a woman" if f else "a man", "hi": "महिला" if f else "पुरुष",
                "hinglish": "aurat" if f else "aadmi", "ta": "பெண்" if f else "ஆண்"}[lang]
    if field == "marital_status":
        f = gender == "female"
        table = {
            "widowed": {"en": "widow" if f else "widower", "hi": "विधवा" if f else "विधुर",
                        "hinglish": "vidhwa" if f else "vidhur", "ta": "விதவை" if f else "மனைவியை இழந்தவர்"},
            "married": {"en": "married", "hi": "शादीशुदा", "hinglish": "shaadishuda", "ta": "திருமணமானவர்"},
            "single": {"en": "unmarried", "hi": "अविवाहित", "hinglish": "shaadi nahi hui", "ta": "திருமணமாகாதவர்"},
            "divorced": {"en": "divorced", "hi": "तलाकशुदा", "hinglish": "divorced", "ta": "விவாகரத்து ஆனவர்"},
        }
        return table.get(value, {}).get(lang)
    if field == "state":
        return {"en": f"we live in {value}", "hi": f"हम {value} में रहते हैं",
                "hinglish": f"hum {value} mein rehte hain", "ta": f"நாங்கள் {value}-இல் வசிக்கிறோம்"}[lang]
    if field == "bpl":
        return _yn(lang, value,
                   {"en": "we have a BPL card", "hi": "बीपीएल कार्ड है", "hinglish": "BPL card hai", "ta": "BPL அட்டை உள்ளது"},
                   {"en": "we don't have a BPL card", "hi": "बीपीएल कार्ड नहीं है", "hinglish": "BPL card nahi hai",
                    "ta": "BPL அட்டை இல்லை"})
    if field == "annual_income":
        return {"en": f"family income is about Rs {value:,} a year", "hi": f"सालाना आय लगभग {value} रुपये",
                "hinglish": f"saal ki income lagbhag {value} rupaye", "ta": f"ஆண்டு வருமானம் சுமார் {value} ரூபாய்"}[lang]
    if field == "has_bank_account":
        return _yn(lang, value,
                   {"en": "has a bank account", "hi": "बैंक खाता है", "hinglish": "bank account hai", "ta": "வங்கி கணக்கு உள்ளது"},
                   {"en": "no bank account", "hi": "बैंक खाता नहीं है", "hinglish": "bank account nahi hai",
                    "ta": "வங்கி கணக்கு இல்லை"})
    if field == "ever_income_tax_payer":
        return _yn(lang, value,
                   {"en": "has paid income tax at some point", "hi": "पहले कभी इनकम टैक्स भरा है",
                    "hinglish": "pehle kabhi income tax bhara hai", "ta": "முன்பு வருமான வரி கட்டியிருக்கிறோம்"},
                   {"en": "has never paid income tax", "hi": "कभी इनकम टैक्स नहीं भरा", "hinglish": "kabhi income tax nahi bhara",
                    "ta": "வருமான வரி கட்டியதில்லை"})
    if field == "income_tax_payer_last_year":
        return _yn(lang, value,
                   {"en": "paid income tax last year", "hi": "पिछले साल इनकम टैक्स भरा था",
                    "hinglish": "pichhle saal income tax bhara tha", "ta": "கடந்த ஆண்டு வருமான வரி கட்டினோம்"},
                   {"en": "did not pay income tax last year", "hi": "पिछले साल इनकम टैक्स नहीं भरा",
                    "hinglish": "pichhle saal income tax nahi bhara", "ta": "கடந்த ஆண்டு வருமான வரி கட்டவில்லை"})
    if field == "owns_cultivable_land":
        return _yn(lang, value,
                   {"en": "owns farmland", "hi": "खेती की जमीन है", "hinglish": "kheti ki zameen hai", "ta": "விவசாய நிலம் உள்ளது"},
                   {"en": "no farmland", "hi": "खेती की जमीन नहीं है", "hinglish": "kheti ki zameen nahi hai",
                    "ta": "விவசாய நிலம் இல்லை"})
    if field == "is_govt_employee":  # also states in_regular_govt_employment (kept equal in profiles)
        return _yn(lang, value,
                   {"en": "has a government job", "hi": "सरकारी नौकरी है", "hinglish": "sarkari naukri hai", "ta": "அரசு வேலை உள்ளது"},
                   {"en": "never had a government job", "hi": "कभी सरकारी नौकरी नहीं की", "hinglish": "kabhi sarkari naukri nahi ki",
                    "ta": "அரசு வேலை செய்ததில்லை"})
    if field == "monthly_pension":
        if not value:
            return {"en": "gets no pension", "hi": "कोई पेंशन नहीं मिलती", "hinglish": "koi pension nahi milti",
                    "ta": "ஓய்வூதியம் இல்லை"}[lang]
        return {"en": f"gets a pension of Rs {value:,} a month", "hi": f"{value} रुपये महीना पेंशन मिलती है",
                "hinglish": f"{value} rupaye mahina pension milti hai", "ta": f"மாதம் {value} ரூபாய் ஓய்வூதியம்"}[lang]
    if field == "household_has_lpg":
        return _yn(lang, value,
                   {"en": "we already have an LPG connection", "hi": "घर में गैस कनेक्शन है", "hinglish": "ghar mein gas connection hai",
                    "ta": "வீட்டில் கேஸ் இணைப்பு உள்ளது"},
                   {"en": "no LPG connection at home", "hi": "घर में गैस कनेक्शन नहीं है", "hinglish": "ghar mein gas connection nahi hai",
                    "ta": "வீட்டில் கேஸ் இணைப்பு இல்லை"})
    if field == "pregnant_or_lactating":
        return _yn(lang, value,
                   {"en": "is pregnant", "hi": "गर्भवती हैं", "hinglish": "pregnant hai", "ta": "கர்ப்பமாக இருக்கிறார்"},
                   {"en": "not pregnant or breastfeeding", "hi": "गर्भवती नहीं हैं", "hinglish": "pregnant nahi hai",
                    "ta": "கர்ப்பமாக இல்லை"})
    if field == "children":
        if not value:
            return {"en": "no children", "hi": "कोई बच्चा नहीं", "hinglish": "koi bachcha nahi", "ta": "குழந்தைகள் இல்லை"}[lang]
        parts = []
        for c in value:
            girl = c["gender"] == "female"
            parts.append({"en": f"a {c['age']}-year-old {'daughter' if girl else 'son'}",
                          "hi": f"{c['age']} साल {'की बेटी' if girl else 'का बेटा'}",
                          "hinglish": f"{c['age']} saal {'ki beti' if girl else 'ka beta'}",
                          "ta": f"{c['age']} வயது {'மகள்' if girl else 'மகன்'}"}[lang])
        joiner = {"en": " and ", "hi": " और ", "hinglish": " aur ", "ta": " மற்றும் "}[lang]
        return {"en": "children: ", "hi": "बच्चे: ", "hinglish": "bachche: ", "ta": "குழந்தைகள்: "}[lang] + joiner.join(parts)
    return None
