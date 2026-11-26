"""Quick-reply phrase table: profile field -> language -> answer options.

Languages: en, hi (Devanagari), hinglish (Hindi in Latin script), ta (Tamil).
Fields without an entry (age, annual_income, monthly_pension, ...) are numeric or free text: no chips.
"""
from __future__ import annotations

PHRASES: dict[str, dict[str, list[str]]] = {
    "bpl": {
        "en": ["Yes, we have a BPL card", "No BPL card", "Not sure"],
        "hi": ["हाँ, बीपीएल कार्ड है", "बीपीएल कार्ड नहीं है", "पता नहीं"],
        "hinglish": ["Haan, BPL card hai", "BPL card nahi hai", "Pata nahi"],
        "ta": ["ஆம், பிபிஎல் அட்டை உள்ளது", "பிபிஎல் அட்டை இல்லை", "தெரியாது"],
    },
    "has_bank_account": {
        "en": ["Yes, I have a bank account", "No bank account"],
        "hi": ["हाँ, बैंक खाता है", "बैंक खाता नहीं है"],
        "hinglish": ["Haan, bank account hai", "Bank account nahi hai"],
        "ta": ["ஆம், வங்கிக் கணக்கு உள்ளது", "வங்கிக் கணக்கு இல்லை"],
    },
    "ever_income_tax_payer": {
        "en": ["Yes, I have paid income tax", "No, never paid income tax"],
        "hi": ["हाँ, कभी इनकम टैक्स भरा है", "नहीं, कभी इनकम टैक्स नहीं भरा"],
        "hinglish": ["Haan, kabhi income tax bhara hai", "Nahi, kabhi income tax nahi bhara"],
        "ta": ["ஆம், வருமான வரி கட்டியிருக்கிறேன்", "இல்லை, ஒருபோதும் கட்டியதில்லை"],
    },
    "income_tax_payer_last_year": {
        "en": ["Yes, paid income tax last year", "No, didn't pay last year"],
        "hi": ["हाँ, पिछले साल इनकम टैक्स भरा", "नहीं, पिछले साल नहीं भरा"],
        "hinglish": ["Haan, pichhle saal income tax bhara", "Nahi, pichhle saal nahi bhara"],
        "ta": ["ஆம், கடந்த ஆண்டு கட்டினேன்", "இல்லை, கடந்த ஆண்டு கட்டவில்லை"],
    },
    "owns_cultivable_land": {
        "en": ["Yes, we own farmland", "No farmland"],
        "hi": ["हाँ, खेती की जमीन है", "खेती की जमीन नहीं है"],
        "hinglish": ["Haan, kheti ki zameen hai", "Kheti ki zameen nahi hai"],
        "ta": ["ஆம், விவசாய நிலம் உள்ளது", "விவசாய நிலம் இல்லை"],
    },
    "household_has_lpg": {
        "en": ["Yes, we have an LPG connection", "No LPG connection"],
        "hi": ["हाँ, एलपीजी कनेक्शन है", "एलपीजी कनेक्शन नहीं है"],
        "hinglish": ["Haan, LPG connection hai", "LPG connection nahi hai"],
        "ta": ["ஆம், எல்பிஜி இணைப்பு உள்ளது", "எல்பிஜி இணைப்பு இல்லை"],
    },
    "pregnant_or_lactating": {
        "en": ["Yes, pregnant or breastfeeding", "No"],
        "hi": ["हाँ, गर्भवती हैं या स्तनपान कराती हैं", "नहीं"],
        "hinglish": ["Haan, pregnant hain ya doodh pilati hain", "Nahi"],
        "ta": ["ஆம், கர்ப்பமாக உள்ளேன் அல்லது பாலூட்டுகிறேன்", "இல்லை"],
    },
    "is_govt_employee": {
        "en": ["Yes, a government employee", "No, not a government employee"],
        "hi": ["हाँ, सरकारी कर्मचारी हैं", "नहीं, सरकारी कर्मचारी नहीं हैं"],
        "hinglish": ["Haan, sarkari karamchari hain", "Nahi, sarkari karamchari nahi hain"],
        "ta": ["ஆம், அரசு ஊழியர்", "இல்லை, அரசு ஊழியர் அல்ல"],
    },
    "marital_status": {
        "en": ["Single", "Married", "Widowed", "Divorced"],
        "hi": ["अविवाहित", "विवाहित", "विधवा/विधुर", "तलाकशुदा"],
        "hinglish": ["Unmarried", "Shaadishuda", "Vidhwa/Vidhur", "Talaakshuda"],
        "ta": ["திருமணமாகவில்லை", "திருமணமானவர்", "விதவை/மனைவியை இழந்தவர்", "விவாகரத்து ஆனவர்"],
    },
    "gender": {
        "en": ["Male", "Female", "Other"],
        "hi": ["पुरुष", "महिला", "अन्य"],
        "hinglish": ["Purush", "Mahila", "Other"],
        "ta": ["ஆண்", "பெண்", "மற்றவர்"],
    },
}

SESSION_LIMIT = {
    "en": "This conversation has reached its limit. Please start a new chat to continue.",
    "hi": "यह बातचीत अपनी सीमा तक पहुँच गई है। कृपया जारी रखने के लिए नई चैट शुरू करें।",
    "hinglish": "Yeh baatcheet apni seema tak pahunch gayi hai. Kripya aage badhne ke liye nayi chat shuru karein.",
    "ta": "இந்த உரையாடல் அதன் வரம்பை எட்டிவிட்டது. தொடர புதிய அரட்டையைத் தொடங்குங்கள்.",
}
