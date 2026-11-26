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
