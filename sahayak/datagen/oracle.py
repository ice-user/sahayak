"""A stand-in 'teacher' that needs no API: it reads the dummy user's known facts
directly and replies with fixed templates.

Use it ONLY to test the pipeline (`--teacher oracle`). Its answers are
repetitive templates, so don't train on its output; the real teacher is the
large model behind the API.
"""
from __future__ import annotations

import json
from types import SimpleNamespace as NS

from .simuser import SimUser

ASK = {"en": "To check this, please tell me: {f}?", "hi": "जांच के लिए कृपया बताइए: {f}?",
       "hinglish": "Check karne ke liye bataiye: {f}?", "ta": "சரிபார்க்க தயவுசெய்து சொல்லுங்கள்: {f}?"}
YES = {"en": "Based on what you told me, you can get: {s}. Carry your Aadhaar card and apply at the local office.",
       "hi": "आपकी दी गई जानकारी के आधार पर ये योजनाएं मिल सकती हैं: {s}। आधार कार्ड लेकर नजदीकी कार्यालय में आवेदन करें।",
       "hinglish": "Aapki di hui jaankari ke hisaab se ye schemes mil sakti hain: {s}. Aadhaar card lekar office mein apply karein.",
       "ta": "நீங்கள் கொடுத்த தகவலின் படி இந்த திட்டங்கள் கிடைக்கலாம்: {s}. ஆதார் அட்டையுடன் அருகிலுள்ள அலுவலகத்தில் விண்ணப்பிக்கவும்."}
NONE = {"en": "Based on what you told me, I couldn't find a scheme you qualify for right now. You can also check myscheme.gov.in.",
        "hi": "आपकी दी गई जानकारी के आधार पर अभी कोई योजना नहीं मिली। आप myscheme.gov.in पर भी देख सकते हैं।",
        "hinglish": "Aapki di hui jaankari ke hisaab se abhi koi scheme nahi mili. Aap myscheme.gov.in par bhi dekh sakte hain.",
        "ta": "நீங்கள் கொடுத்த தகவலின் படி இப்போது பொருந்தும் திட்டம் எதுவும் கிடைக்கவில்லை. myscheme.gov.in தளத்திலும் பார்க்கலாம்."}


class OracleClient:
    def __init__(self, sim: SimUser):
        self.sim = sim
        self.n = 0
        self.asked = 0
        self.chat = NS(completions=NS(create=self._create))

    def _msg(self, content="", tool_calls=None):
        return NS(choices=[NS(message=NS(content=content, tool_calls=tool_calls))], usage=NS(total_tokens=0))

    def _create(self, messages, **_):
        last = messages[-1]
        lang = self.sim.s.lang
        if last["role"] == "user":
            self.n += 1
            known = {k: v for k, v in self.sim.s.profile.items()
                     if k in self.sim.revealed and k not in self.sim.dont_know}
            args = json.dumps({"profile": known}, ensure_ascii=False)
            return self._msg(tool_calls=[NS(id=f"call{self.n}", function=NS(name="check_eligibility", arguments=args))])

        result = json.loads(last["content"])
        ask = [f for r in result.get("need_info", []) for f in r["missing_fields"]]
        ask = [("children" if f.startswith("children") else f) for f in ask]
        ask = [f for f in dict.fromkeys(ask) if f not in self.sim.dont_know and f not in self.sim.revealed][:3]
        if ask and not self.sim.said_nothing_more and self.asked < 2:
            self.asked += 1
            return self._msg(ASK[lang].format(f=", ".join(f.replace("_", " ") for f in ask)))
        names = [r["scheme_name"] for r in result.get("eligible", [])]
        if lang in ("hi", "ta"):  # English names go in brackets inside a Hindi/Tamil sentence, as the system prompt asks
            names = [f"({n})" for n in names]
        return self._msg(YES[lang].format(s="; ".join(names)) if names else NONE[lang])
