"""Shared language detection and localized stock messages (agent, server, datagen all use this).

Languages: en, hi (Devanagari), hinglish (Hindi in Latin script), ta (Tamil).
"""
from __future__ import annotations

import re
from typing import Iterable

DEVANAGARI = re.compile("[ऀ-ॿ]")
TAMIL = re.compile("[஀-௿]")
_WORDS = re.compile(r"[a-z]+")

# Common Hindi words written in Latin script. One hit in a message marks it as Hinglish.
HINGLISH_WORDS = frozenset(
    "hai hain hoon hu mera meri mere ke ki ka ko se nahi nahin kya saal umar haan aur mein bhi kuch "
    "chahiye yojana pata kaise kitna ghar paise batao bataiye".split())
# Superset used to check that a *Hinglish answer* really is Hinglish (see datagen/grader.py:script_ok).
HINGLISH_MARKERS = HINGLISH_WORDS | frozenset(
    "aap aapko aapki aapka aapke aapse hum humein ye yeh wo woh liye lekin magar sakta sakti sakte milega milegi "
    "milenge hisaab jaankari karein kijiye kijie batayein bataiye abhi toh jaise isliye apna apni apne unhe "
    "unko unka unki unke koi hota hoti hote hua hui hue".split())

_RANK = {"en": 0, "hinglish": 1, "hi": 2, "ta": 2}


def detect_language(text: str) -> str:
    """'hi' (Devanagari), 'ta' (Tamil), 'hinglish' (Latin script with common Hindi words), else 'en'."""
    if DEVANAGARI.search(text):
        return "hi"
    if TAMIL.search(text):
        return "ta"
    if HINGLISH_WORDS.intersection(_WORDS.findall(text.lower())):
        return "hinglish"
    return "en"


def has_letters(text: str) -> bool:
    return any(ch.isalpha() for ch in text)


def upgrade_language(current: str, detected: str) -> str:
    """Sticky language: a later short English reply ("female", "yes") never downgrades the session."""
    if detected == "en" or _RANK[detected] < _RANK[current]:
        return current
    return detected


def detect_session_language(messages: Iterable[dict]) -> str:
    """Language of a conversation: the strongest non-English language the user has written in so far."""
    lang = "en"
    for m in messages:
        if m.get("role") == "user" and isinstance(m.get("content"), str) and has_letters(m["content"]):
            lang = upgrade_language(lang, detect_language(m["content"]))
    return lang


MAX_STEPS_MESSAGES = {
    "en": "Sorry, I couldn't finish that. Please try asking again more simply.",
    "hi": "माफ़ कीजिए, मैं इसे पूरा नहीं कर सका। कृपया अपना सवाल थोड़ा सरल तरीके से दोबारा पूछिए।",
    "hinglish": "Maaf kijiye, main ise poora nahi kar paya. Kripya apna sawaal thoda aasaan tareeke se dobara poochhiye.",
    "ta": "மன்னிக்கவும், என்னால் இதை முடிக்க முடியவில்லை. தயவுசெய்து உங்கள் கேள்வியை எளிமையாக மீண்டும் கேளுங்கள்.",
}

EMPTY_ANSWER_MESSAGES = {
    "en": "Sorry, I couldn't prepare an answer just now. Please try again in a moment.",
    "hi": "माफ़ कीजिए, अभी मैं जवाब तैयार नहीं कर सका। कृपया कुछ देर बाद फिर से कोशिश कीजिए।",
    "hinglish": "Maaf kijiye, abhi main jawab taiyaar nahi kar paya. Kripya thodi der baad dobara koshish kijiye.",
    "ta": "மன்னிக்கவும், இப்போது பதில் தயாரிக்க முடியவில்லை. சிறிது நேரம் கழித்து மீண்டும் முயற்சிக்கவும்.",
}

# Shown when the model's answer offered schemes the rule engine did not confirm. {names} = verified schemes.
GUARD_FALLBACK_WITH_SCHEMES = {
    "en": ("I can only confirm what the official rules check found for the details you have shared. "
           "You can apply for: {names}. Please confirm the amount and documents at the official office. "
           "Tell me more about yourself (age, family, income) and I can check other schemes, "
           "or visit myscheme.gov.in or your Gram Panchayat."),
    "hi": ("आपकी बताई जानकारी पर आधिकारिक नियमों की जांच में केवल यही पुष्टि हुई है। "
           "आप इनके लिए आवेदन कर सकते हैं: {names}। राशि और दस्तावेज़ सरकारी कार्यालय में पक्का कर लें। "
           "अपने बारे में और बताइए (उम्र, परिवार, आय) तो मैं दूसरी योजनाएं जांच सकता हूँ, "
           "या myscheme.gov.in या अपनी ग्राम पंचायत पर जाइए।"),
    "hinglish": ("Aapki di hui jaankari par official rules ki jaanch mein sirf yahi confirm hua hai. "
                 "Aap inke liye apply kar sakte hain: {names}. Amount aur documents sarkari office mein confirm kar lein. "
                 "Apne baare mein aur bataiye (umar, parivaar, income) to main doosri schemes check kar sakta hoon, "
                 "ya myscheme.gov.in ya apni Gram Panchayat par jaayiye."),
    "ta": ("நீங்கள் கொடுத்த தகவலுக்கு அதிகாரப்பூர்வ விதிகளின் சரிபார்ப்பில் இவை மட்டுமே உறுதியாகியுள்ளன. "
           "நீங்கள் இவற்றுக்கு விண்ணப்பிக்கலாம்: {names}. தொகை மற்றும் ஆவணங்களை அரசு அலுவலகத்தில் உறுதிசெய்யுங்கள். "
           "உங்களைப் பற்றி மேலும் சொல்லுங்கள் (வயது, குடும்பம், வருமானம்), மற்ற திட்டங்களைச் சரிபார்க்கிறேன்; "
           "அல்லது myscheme.gov.in அல்லது உங்கள் கிராம பஞ்சாயத்தை அணுகுங்கள்."),
}
GUARD_FALLBACK_NO_SCHEMES = {
    "en": ("I couldn't confirm any scheme for you yet. Please tell me about yourself (age, gender, family, income) "
           "so I can check the official rules, or visit myscheme.gov.in or your Gram Panchayat."),
    "hi": ("मैं अभी आपके लिए किसी योजना की पुष्टि नहीं कर पाया। कृपया अपने बारे में बताइए (उम्र, लिंग, परिवार, आय) "
           "ताकि मैं आधिकारिक नियमों से जांच सकूँ, या myscheme.gov.in या अपनी ग्राम पंचायत पर जाइए।"),
    "hinglish": ("Main abhi aapke liye kisi scheme ki pushti nahi kar paya. Kripya apne baare mein bataiye "
                 "(umar, gender, parivaar, income) taaki main official rules se check kar sakoon, "
                 "ya myscheme.gov.in ya apni Gram Panchayat par jaayiye."),
    "ta": ("இப்போது உங்களுக்கான எந்தத் திட்டத்தையும் என்னால் உறுதிசெய்ய முடியவில்லை. உங்களைப் பற்றி சொல்லுங்கள் "
           "(வயது, பாலினம், குடும்பம், வருமானம்), அதிகாரப்பூர்வ விதிகளின்படி சரிபார்க்கிறேன்; "
           "அல்லது myscheme.gov.in அல்லது உங்கள் கிராம பஞ்சாயத்தை அணுகுங்கள்."),
}


# Fallback follow-up: the facts the rule engine still needs, asked for by name. {facts} = comma-separated labels.
GUARD_FALLBACK_ASK = {
    "en": "To check the official rules for you, please tell me: {facts}?",
    "hi": "आपके लिए आधिकारिक नियम जांचने के लिए कृपया बताइए: {facts}?",
    "hinglish": "Aapke liye official rules check karne ke liye kripya bataiye: {facts}?",
    "ta": "உங்களுக்கான அதிகாரப்பூர்வ விதிகளைச் சரிபார்க்க, தயவுசெய்து சொல்லுங்கள்: {facts}?",
}
# Profile field -> label per language (a field without a label is asked for by its English label).
FIELD_LABELS = {
    "age": {"en": "your age", "hi": "आपकी उम्र", "hinglish": "aapki umar", "ta": "உங்கள் வயது"},
    "gender": {"en": "your gender", "hi": "आपका लिंग", "hinglish": "aapka gender", "ta": "உங்கள் பாலினம்"},
    "bpl": {"en": "do you have a BPL card", "hi": "क्या आपके पास बीपीएल कार्ड है", "hinglish": "kya aapke paas BPL card hai",
            "ta": "உங்களிடம் BPL அட்டை உள்ளதா"},
    "marital_status": {"en": "your marital status", "hi": "आपकी वैवाहिक स्थिति", "hinglish": "aapki marital status",
                       "ta": "உங்கள் திருமண நிலை"},
    "annual_income": {"en": "your household income per year", "hi": "परिवार की सालाना आय",
                      "hinglish": "parivaar ki saalana income", "ta": "குடும்ப ஆண்டு வருமானம்"},
    "ever_income_tax_payer": {"en": "have you ever paid income tax", "hi": "क्या आपने कभी इनकम टैक्स भरा है",
                              "hinglish": "kya aapne kabhi income tax bhara hai", "ta": "நீங்கள் எப்போதாவது வருமான வரி செலுத்தியுள்ளீர்களா"},
    "income_tax_payer_last_year": {"en": "did you pay income tax last year", "hi": "क्या आपने पिछले साल इनकम टैक्स भरा",
                                   "hinglish": "kya aapne pichhle saal income tax bhara",
                                   "ta": "கடந்த ஆண்டு வருமான வரி செலுத்தினீர்களா"},
    "has_bank_account": {"en": "do you have a bank account", "hi": "क्या आपका बैंक खाता है",
                         "hinglish": "kya aapka bank account hai", "ta": "உங்களுக்கு வங்கிக் கணக்கு உள்ளதா"},
    "owns_cultivable_land": {"en": "do you own farm land", "hi": "क्या आपके पास खेती की ज़मीन है",
                             "hinglish": "kya aapke paas kheti ki zameen hai", "ta": "உங்களுக்கு விவசாய நிலம் உள்ளதா"},
    "is_govt_employee": {"en": "are you a government employee", "hi": "क्या आप सरकारी कर्मचारी हैं",
                         "hinglish": "kya aap sarkari karmchari hain", "ta": "நீங்கள் அரசு ஊழியரா"},
    "monthly_pension": {"en": "your monthly pension, if any", "hi": "आपकी मासिक पेंशन, अगर है",
                        "hinglish": "aapki monthly pension, agar hai", "ta": "உங்கள் மாத ஓய்வூதியம், இருந்தால்"},
    "household_has_lpg": {"en": "does your home have an LPG connection", "hi": "क्या घर में गैस कनेक्शन है",
                          "hinglish": "kya ghar mein gas connection hai", "ta": "வீட்டில் எரிவாயு இணைப்பு உள்ளதா"},
    "pregnant_or_lactating": {"en": "are you pregnant or breastfeeding", "hi": "क्या आप गर्भवती या स्तनपान कराने वाली हैं",
                              "hinglish": "kya aap pregnant ya breastfeeding hain", "ta": "நீங்கள் கர்ப்பமாகவோ பாலூட்டுபவரோ"},
    "in_regular_govt_employment": {"en": "are you in regular government employment", "hi": "क्या आप नियमित सरकारी नौकरी में हैं",
                                   "hinglish": "kya aap regular sarkari naukri mein hain", "ta": "நீங்கள் நிரந்தர அரசு வேலையில் உள்ளீர்களா"},
    "children": {"en": "your children's ages and genders", "hi": "बच्चों की उम्र और लिंग",
                 "hinglish": "bachchon ki umar aur gender", "ta": "குழந்தைகளின் வயது மற்றும் பாலினம்"},
}
MAX_FALLBACK_QUESTIONS = 3


# Added to the system prompt on every turn (the agent re-detects the language each turn). Small models drift into
# Devanagari for Latin-script Hindi, so the script is spelled out.
REPLY_LANGUAGE_HINTS = {
    "en": "Reply in English. Keep scheme names in English.",
    "hi": "Reply in Hindi using Devanagari script. Keep scheme names in English.",
    "hinglish": ("Reply in Hinglish: Hindi written with Latin letters (Roman script), NOT Devanagari. "
                 "Keep scheme names in English."),
    "ta": "Reply in Tamil script (தமிழ்). Keep scheme names in English.",
}


def reply_language_hint(lang: str) -> str:
    return REPLY_LANGUAGE_HINTS.get(lang, REPLY_LANGUAGE_HINTS["en"])
