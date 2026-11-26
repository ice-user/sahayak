import type { LangCode } from "../types";

type L = Record<LangCode, string>;

/** Follow-up question per missing field, in each language. */
export const QUESTIONS: Record<string, L> = {
  age: { en: "How old is the person who needs the scheme?", hi: "योजना किसके लिए चाहिए, उनकी उम्र कितनी है?", hinglish: "Scheme kiske liye chahiye, unki umar kitni hai?", ta: "திட்டம் யாருக்கு தேவை? அவர்களின் வயது என்ன?" },
  gender: { en: "Is the person a woman, a man, or other?", hi: "क्या वे महिला हैं या पुरुष?", hinglish: "Kya woh mahila hain ya purush?", ta: "அவர் பெண்ணா, ஆணா?" },
  marital_status: { en: "Are they married, single, widowed, divorced or separated?", hi: "क्या वे विवाहित, अविवाहित, विधवा या तलाकशुदा हैं?", hinglish: "Kya woh married, single, widow ya divorced hain?", ta: "திருமணமானவரா, தனியரா, விதவையா?" },
  bpl: { en: "Does the household have a BPL card?", hi: "क्या परिवार के पास बीपीएल कार्ड है?", hinglish: "Kya ghar mein BPL card hai?", ta: "குடும்பத்திடம் பிபிஎல் அட்டை உள்ளதா?" },
  has_bank_account: { en: "Do they have a bank or post office account?", hi: "क्या उनका बैंक या डाकघर में खाता है?", hinglish: "Kya unka bank ya post office account hai?", ta: "வங்கி அல்லது அஞ்சலக கணக்கு உள்ளதா?" },
  is_income_tax_payer: { en: "Does anyone in the family pay income tax?", hi: "क्या परिवार में कोई आयकर देता है?", hinglish: "Kya ghar mein koi income tax bharta hai?", ta: "குடும்பத்தில் யாராவது வருமான வரி செலுத்துகிறார்களா?" },
  ever_income_tax_payer: { en: "Have you ever paid income tax?", hi: "क्या आपने कभी आयकर दिया है?", hinglish: "Kya aapne kabhi income tax diya hai?", ta: "நீங்கள் எப்போதாவது வருமான வரி செலுத்தியிருக்கிறீர்களா?" },
  income_tax_payer_last_year: { en: "Did anyone in the family pay income tax last year?", hi: "क्या परिवार में किसी ने पिछले साल आयकर दिया?", hinglish: "Kya parivar mein kisi ne pichhle saal income tax diya?", ta: "குடும்பத்தில் யாராவது கடந்த ஆண்டு வருமான வரி செலுத்தினார்களா?" },
  owns_cultivable_land: { en: "Does the family own farmland?", hi: "क्या परिवार के पास खेती की ज़मीन है?", hinglish: "Kya parivar ke paas kheti ki zameen hai?", ta: "குடும்பத்திடம் விவசாய நிலம் உள்ளதா?" },
  is_govt_employee: { en: "Is anyone in the family a government employee or retired from government service?", hi: "क्या परिवार में कोई सरकारी कर्मचारी या सेवानिवृत्त है?", hinglish: "Kya ghar mein koi sarkari karmchari ya retired hai?", ta: "குடும்பத்தில் அரசு ஊழியர் அல்லது ஓய்வு பெற்றவர் உள்ளாரா?" },
  monthly_pension: { en: "Do they get a monthly pension? If so, roughly how much?", hi: "क्या उन्हें मासिक पेंशन मिलती है? कितनी?", hinglish: "Kya unhe monthly pension milti hai? Kitni?", ta: "மாத ஓய்வூதியம் கிடைக்கிறதா? எவ்வளவு?" },
  household_has_lpg: { en: "Does the household already have an LPG gas connection?", hi: "क्या घर में पहले से एलपीजी गैस कनेक्शन है?", hinglish: "Kya ghar mein pehle se LPG gas connection hai?", ta: "வீட்டில் ஏற்கனவே எல்பிஜி இணைப்பு உள்ளதா?" },
  pregnant_or_lactating: { en: "Is she pregnant or breastfeeding?", hi: "क्या वे गर्भवती हैं या स्तनपान करा रही हैं?", hinglish: "Kya woh pregnant hain ya breastfeeding kara rahi hain?", ta: "அவர் கர்ப்பமாக அல்லது பாலூட்டுகிறாரா?" },
  in_regular_govt_employment: { en: "Does she hold a regular government or PSU job?", hi: "क्या उनके पास सरकारी या PSU की पक्की नौकरी है?", hinglish: "Kya unke paas sarkari ya PSU ki pakki naukri hai?", ta: "அரசு அல்லது பொதுத்துறை நிரந்தர வேலை உள்ளதா?" },
  children: { en: "Do you have a daughter? How old is she?", hi: "क्या आपकी कोई बेटी है? उसकी उम्र कितनी है?", hinglish: "Kya aapki beti hai? Uski umar kitni hai?", ta: "உங்களுக்கு மகள் இருக்கிறாரா? அவள் வயது என்ன?" },
  "children.age/gender": { en: "How old is your daughter?", hi: "आपकी बेटी की उम्र कितनी है?", hinglish: "Aapki beti ki umar kitni hai?", ta: "உங்கள் மகளின் வயது என்ன?" },
};

export const YES: L = { en: "Yes", hi: "हाँ", hinglish: "Haan", ta: "ஆம்" };
export const NO: L = { en: "No", hi: "नहीं", hinglish: "Nahi", ta: "இல்லை" };
export const NOT_SURE: L = { en: "Not sure", hi: "पता नहीं", hinglish: "Pata nahi", ta: "தெரியாது" };
export const BPL_YES: L = { en: "Yes, we have a BPL card", hi: "हाँ, हमारे पास बीपीएल कार्ड है", hinglish: "Haan, BPL card hai", ta: "ஆம், பிபிஎல் அட்டை உள்ளது" };
export const BPL_NO: L = { en: "No BPL card", hi: "बीपीएल कार्ड नहीं है", hinglish: "BPL card nahi hai", ta: "பிபிஎல் அட்டை இல்லை" };

export const GENDER_OPTS: L[] = [
  { en: "Woman", hi: "महिला", hinglish: "Mahila", ta: "பெண்" },
  { en: "Man", hi: "पुरुष", hinglish: "Purush", ta: "ஆண்" },
];
export const MARITAL_OPTS: L[] = [
  { en: "Widowed", hi: "विधवा", hinglish: "Widow", ta: "விதவை" },
  { en: "Married", hi: "विवाहित", hinglish: "Married", ta: "திருமணமானவர்" },
  { en: "Single", hi: "अविवाहित", hinglish: "Single", ta: "திருமணமாகாதவர்" },
];

export const TEXT = {
  askFirst: {
    en: "I can help you find schemes. To check what you qualify for I need a few facts. Who is the scheme for, and how old are they?",
    hi: "मैं योजनाएँ ढूँढने में मदद कर सकता हूँ। पात्रता जाँचने के लिए कुछ जानकारी चाहिए। योजना किसके लिए है और उनकी उम्र कितनी है?",
    hinglish: "Main schemes dhoondhne mein madad kar sakta hoon. Eligibility check karne ke liye kuch jaankari chahiye. Scheme kiske liye hai aur unki umar kitni hai?",
    ta: "திட்டங்களைக் கண்டறிய உதவுகிறேன். தகுதியைச் சரிபார்க்க சில தகவல்கள் தேவை. திட்டம் யாருக்கு? அவர்களின் வயது என்ன?",
  } as L,
  eligibleHead: {
    en: "Based on what you told me, you may get **{n}** of these:",
    hi: "आपकी जानकारी के आधार पर आप इनमें से **{n}** योजनाओं के पात्र हो सकते हैं:",
    hinglish: "Aapki jaankari ke hisaab se aap in mein se **{n}** schemes ke liye eligible ho sakte hain:",
    ta: "நீங்கள் சொன்னதன் அடிப்படையில் இவற்றில் **{n}** திட்டங்கள் உங்களுக்கு கிடைக்கலாம்:",
  } as L,
  noneYet: {
    en: "From what you have told me, I can't confirm any scheme yet.",
    hi: "अभी तक की जानकारी से मैं किसी योजना की पुष्टि नहीं कर सकता।",
    hinglish: "Abhi tak ki jaankari se main kisi scheme ki pushti nahi kar sakta.",
    ta: "இதுவரை சொன்ன தகவல்களால் எந்தத் திட்டத்தையும் உறுதி செய்ய முடியவில்லை.",
  } as L,
  needMore: {
    en: "**{n}** more may fit, but I need one more fact. {q}",
    hi: "**{n}** और योजनाएँ मिल सकती हैं, पर एक और जानकारी चाहिए। {q}",
    hinglish: "**{n}** aur schemes mil sakti hain, par ek aur jaankari chahiye. {q}",
    ta: "மேலும் **{n}** திட்டங்கள் பொருந்தலாம், ஆனால் இன்னும் ஒரு தகவல் தேவை. {q}",
  } as L,
  notEligible: {
    en: "**{n}** schemes do not fit; the reasons are in the collapsed list below.",
    hi: "**{n}** योजनाएँ लागू नहीं होतीं; कारण नीचे की सूची में हैं।",
    hinglish: "**{n}** schemes lagu nahi hotin; wajah neeche list mein hai.",
    ta: "**{n}** திட்டங்கள் பொருந்தாது; காரணங்கள் கீழே உள்ள பட்டியலில் உள்ளன.",
  } as L,
  closing: {
    en: "Amounts vary by state. Please confirm at your local office before you go.",
    hi: "राशि राज्य के अनुसार अलग हो सकती है। जाने से पहले स्थानीय कार्यालय में पुष्टि कर लें।",
    hinglish: "Amount state ke hisaab se alag ho sakta hai. Jaane se pehle local office mein confirm kar lein.",
    ta: "தொகை மாநிலத்துக்கு மாநிலம் மாறலாம். செல்லும் முன் உள்ளூர் அலுவலகத்தில் உறுதிப்படுத்துங்கள்.",
  } as L,
  errorLlm: {
    en: "The AI service did not respond. Please try again.",
    hi: "AI सेवा ने जवाब नहीं दिया। कृपया फिर कोशिश करें।",
    hinglish: "AI service ne jawab nahi diya. Kripya dobara try karein.",
    ta: "AI சேவை பதிலளிக்கவில்லை. மீண்டும் முயற்சிக்கவும்.",
  } as L,
  rateLimit: {
    en: "Too many requests from this network. Try again in about 10 minutes.",
    hi: "इस नेटवर्क से बहुत ज़्यादा अनुरोध आए हैं। लगभग 10 मिनट बाद कोशिश करें।",
    hinglish: "Is network se bahut zyada requests aaye hain. Lagbhag 10 minute baad try karein.",
    ta: "இந்த நெட்வொர்க்கிலிருந்து அதிக கோரிக்கைகள். சுமார் 10 நிமிடம் கழித்து முயற்சிக்கவும்.",
  } as L,
};
