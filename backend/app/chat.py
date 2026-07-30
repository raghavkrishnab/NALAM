"""Conversational scheme finder.

The chat is a slot-filling loop over the same Profile the form uses: each user
message is mined for whatever details it contains, and NALAM asks about the
single most valuable missing field next. Once enough is known, it hands off to
the rules engine.

The reply wording is upgraded by Ollama when it is running, but the questions,
the extraction and the eligibility decisions are all deterministic - pull the
plug on Ollama and the conversation still works.
"""

from __future__ import annotations

import re

from . import llm
from .models import ChatRequest, ChatResponse, Profile
from .rules import infer_from_text, match_profile

# Tamil digits map onto ASCII so "௨௫" parses as 25.
TAMIL_DIGITS = str.maketrans("௦௧௨௩௪௫௬௭௮௯", "0123456789")

TN_DISTRICTS = [
    "ariyalur", "chengalpattu", "chennai", "coimbatore", "cuddalore", "dharmapuri",
    "dindigul", "erode", "kallakurichi", "kanchipuram", "kanyakumari", "karur",
    "krishnagiri", "madurai", "mayiladuthurai", "nagapattinam", "namakkal",
    "nilgiris", "perambalur", "pudukkottai", "ramanathapuram", "ranipet",
    "salem", "sivaganga", "tenkasi", "thanjavur", "theni", "thoothukudi",
    "tiruchirappalli", "trichy", "tirunelveli", "tirupathur", "tiruppur",
    "tiruvallur", "tiruvannamalai", "tiruvarur", "vellore", "viluppuram",
    "virudhunagar",
]

DISTRICT_TA = {
    "சென்னை": "Chennai", "கோயம்புத்தூர்": "Coimbatore", "மதுரை": "Madurai",
    "திருச்சி": "Trichy", "திருச்சிராப்பள்ளி": "Tiruchirappalli", "சேலம்": "Salem",
    "திருநெல்வேலி": "Tirunelveli", "வேலூர்": "Vellore", "ஈரோடு": "Erode",
    "தஞ்சாவூர்": "Thanjavur", "திருப்பூர்": "Tiruppur", "தூத்துக்குடி": "Thoothukudi",
    "நாகர்கோவில்": "Kanyakumari", "கடலூர்": "Cuddalore", "விழுப்புரம்": "Viluppuram",
}

OCCUPATION_WORDS = {
    "farmer": ["farmer", "farming", "agriculture", "cultivat", "விவசாய", "உழவ", "பயிர்"],
    "fisherman": ["fisherman", "fisher", "fishing", "மீனவ", "மீன்பிடி"],
    "construction_worker": ["construction", "mason", "building work", "கட்டுமான", "கொத்தன"],
    "daily_wage_labourer": ["coolie", "daily wage", "labour", "labor", "கூலி", "நாட்கூலி"],
    "street_vendor": ["street vendor", "hawker", "petty shop", "தெருவோர", "சிறு கடை"],
    "auto_driver": ["auto driver", "auto", "taxi", "cab driver", "ஆட்டோ", "டாக்சி"],
    "weaver": ["weaver", "handloom", "நெசவ", "கைத்தறி"],
    "tailor": ["tailor", "stitch", "தையல்"],
    "domestic_worker": ["housemaid", "domestic work", "வீட்டு வேலை"],
    "small_business": ["shop owner", "business", "தொழில்", "கடை"],
    "student": ["student", "studying", "college", "school", "மாணவ", "படிக்", "கல்லூரி"],
    "unemployed": ["unemployed", "no job", "jobless", "வேலையில்லை", "வேலை இல்ல"],
    "homemaker": ["housewife", "homemaker", "இல்லத்தரசி"],
    "salaried": ["salaried", "office job", "private job", "ஊழிய"],
}

CATEGORY_WORDS = {
    "SC": ["scheduled caste", " sc ", "adi dravidar", "பட்டியல் சாதி", "ஆதிதிராவிடர்"],
    "ST": ["scheduled tribe", " st ", "tribal", "பட்டியல் பழங்குடி", "பழங்குடி"],
    "MBC": ["most backward", " mbc ", "மிகப் பிற்படுத்த"],
    "BC": ["backward class", " bc ", "பிற்படுத்த"],
    "DNC": ["denotified", " dnc ", "சீர்மரபின"],
    "OC": ["open category", " oc ", "forward caste"],
}

# Field name -> the question NALAM asks when that field is the next gap.
QUESTIONS = {
    "age": {
        "en": "How old are you? Many pension and scholarship schemes turn on age.",
        "ta": "உங்கள் வயது என்ன? பல ஓய்வூதிய மற்றும் உதவித்தொகைத் திட்டங்கள் வயதைப் பொறுத்தது.",
    },
    "gender": {
        "en": "Are you male or female? Tamil Nadu runs several women-only schemes.",
        "ta": "நீங்கள் ஆணா பெண்ணா? தமிழ்நாட்டில் பெண்களுக்கு மட்டுமான பல திட்டங்கள் உள்ளன.",
    },
    "annual_income": {
        "en": "Roughly what is your family's total income in a year? An approximate figure is fine.",
        "ta": "உங்கள் குடும்பத்தின் ஆண்டு மொத்த வருமானம் தோராயமாக எவ்வளவு? தோராயமான எண் போதும்.",
    },
    "district": {
        "en": "Which district do you live in?",
        "ta": "நீங்கள் எந்த மாவட்டத்தில் வசிக்கிறீர்கள்?",
    },
    "occupation": {
        "en": "What work do you do? For example farming, daily wage work, a small shop, or studying.",
        "ta": "நீங்கள் என்ன வேலை செய்கிறீர்கள்? உதாரணமாக விவசாயம், நாட்கூலி, சிறு கடை அல்லது படிப்பு.",
    },
    "social_category": {
        "en": "Which community do you belong to - SC, ST, BC, MBC or OC? Some schemes are reserved.",
        "ta": "நீங்கள் எந்தச் சமூகத்தைச் சேர்ந்தவர் - SC, ST, BC, MBC அல்லது OC? சில திட்டங்கள் ஒதுக்கப்பட்டவை.",
    },
}

GREETING = {
    "en": "Vanakkam! I am NALAM. Tell me what you need help with - money for treatment, "
          "a house, your child's education, farming, a pension, anything. You can type or "
          "speak, in Tamil or English.",
    "ta": "வணக்கம்! நான் நலம். உங்களுக்கு என்ன உதவி தேவை என்று சொல்லுங்கள் - சிகிச்சைக்கான பணம், "
          "வீடு, குழந்தையின் கல்வி, விவசாயம், ஓய்வூதியம், எதுவாக இருந்தாலும். தமிழிலோ ஆங்கிலத்திலோ "
          "தட்டச்சு செய்யலாம் அல்லது பேசலாம்.",
}

STARTER_SUGGESTIONS = {
    "en": [
        "I need help paying for my father's heart surgery",
        "I am a farmer and lost my crop to floods",
        "My husband passed away and I have no income",
        "I want a scholarship for my daughter's college",
    ],
    "ta": [
        "என் தந்தையின் இதய அறுவை சிகிச்சைக்கு உதவி தேவை",
        "நான் ஒரு விவசாயி, வெள்ளத்தில் பயிரை இழந்தேன்",
        "என் கணவர் இறந்துவிட்டார், வருமானம் இல்லை",
        "என் மகளின் கல்லூரிக்கு உதவித்தொகை வேண்டும்",
    ],
}


def _normalise(text: str) -> str:
    return f" {text.translate(TAMIL_DIGITS).lower().strip()} "


def extract_age(text: str) -> int | None:
    patterns = [
        r"(\d{1,3})\s*(?:years?\s*old|yrs?\s*old|year old|வயது)",
        r"(?:age|aged|வயசு)\s*(?:is|:)?\s*(\d{1,3})",
        r"\bi am\s+(\d{1,3})\b",
    ]
    for pattern in patterns:
        found = re.search(pattern, text)
        if found:
            age = int(found.group(1))
            if 1 <= age <= 120:
                return age
    return None


def extract_income(text: str) -> int | None:
    """Parse income, handling lakh/thousand suffixes and monthly-to-annual conversion."""
    monthly = bool(re.search(r"per month|a month|monthly|/month|மாத|மாசம்", text))

    lakh = re.search(r"(\d+(?:\.\d+)?)\s*(?:lakh|lakhs|lac|லட்ச)", text)
    if lakh:
        amount = int(float(lakh.group(1)) * 100000)
        return amount * 12 if monthly else amount

    thousand = re.search(r"(\d+(?:\.\d+)?)\s*(?:thousand|k\b|ஆயிர)", text)
    if thousand:
        amount = int(float(thousand.group(1)) * 1000)
        return amount * 12 if monthly else amount

    plain = re.search(r"(?:rs\.?|rupees|₹|ரூ\.?)\s*([\d,]+)", text)
    if not plain:
        plain = re.search(r"([\d,]{4,9})\s*(?:rupees|rs|ரூபாய்)", text)
    if not plain and re.search(r"income|salary|earn|வருமான|சம்பள", text):
        plain = re.search(r"\b([\d,]{4,9})\b", text)

    if plain:
        amount = int(plain.group(1).replace(",", ""))
        if amount <= 0:
            return None
        return amount * 12 if monthly else amount

    return None


def extract_district(text: str) -> str | None:
    for tamil, english in DISTRICT_TA.items():
        if tamil in text:
            return english
    for district in TN_DISTRICTS:
        if re.search(rf"\b{re.escape(district)}\b", text):
            return district.title()
    return None


def extract_gender(text: str) -> str | None:
    if re.search(r"\b(?:i am a |i'm a )?(?:woman|female|lady|girl|wife|mother|widow)\b|பெண்|மனைவி|தாய்|விதவை", text):
        return "female"
    if re.search(r"\b(?:i am a |i'm a )?(?:man|male|boy|husband|father)\b|ஆண்|கணவ|தந்தை", text):
        return "male"
    return None


def extract_occupation(text: str) -> str | None:
    for occupation, words in OCCUPATION_WORDS.items():
        if any(word in text for word in words):
            return occupation
    return None


def extract_social_category(text: str) -> str | None:
    for category, words in CATEGORY_WORDS.items():
        if any(word in text for word in words):
            return category
    return None


def extract_disability_percent(text: str) -> int | None:
    found = re.search(r"(\d{1,3})\s*(?:%|percent|சதவீத)", text)
    if found:
        value = int(found.group(1))
        if 1 <= value <= 100:
            return value
    return None


def update_profile(profile: Profile, message: str) -> Profile:
    """Fold everything we can read out of one message into the profile."""
    text = _normalise(message)
    updated = profile.model_copy(deep=True)

    updated.issue_text = f"{updated.issue_text} {message}".strip()

    if updated.age is None:
        updated.age = extract_age(text)
    if updated.annual_income is None:
        updated.annual_income = extract_income(text)
    if not updated.district:
        updated.district = extract_district(text) or ""
    if updated.gender is None:
        updated.gender = extract_gender(text)
    if not updated.occupation:
        updated.occupation = extract_occupation(text)
    if updated.social_category is None:
        updated.social_category = extract_social_category(text)
    if updated.disability_percent is None:
        updated.disability_percent = extract_disability_percent(text)

    if re.search(r"\bwidow\b|husband (?:died|passed|expired)|விதவை|கணவர் இறந்த", text):
        updated.marital_status = "widowed"

    return infer_from_text(updated)


def missing_fields(profile: Profile) -> list[str]:
    gaps = []
    if profile.age is None:
        gaps.append("age")
    if profile.gender is None:
        gaps.append("gender")
    if profile.annual_income is None:
        gaps.append("annual_income")
    if not profile.district:
        gaps.append("district")
    if not profile.occupation:
        gaps.append("occupation")
    if profile.social_category is None:
        gaps.append("social_category")
    return gaps


def _context_for_llm(profile: Profile, language: str) -> str:
    result = match_profile(profile, language)
    lines = ["Schemes the rules engine matched for this person:"]
    for match in (result["eligible"] + result["likely"])[:6]:
        lines.append(f"- {match.name}: {match.summary} Benefit: {match.benefit}")
    if len(lines) == 1:
        lines.append("- (none yet - not enough detail)")
    lines.append("")
    lines.append(
        "Known about the person: "
        f"age={profile.age}, gender={profile.gender}, district={profile.district or 'unknown'}, "
        f"annual_income={profile.annual_income}, occupation={profile.occupation or 'unknown'}, "
        f"community={profile.social_category or 'unknown'}, situation flags={profile.flags or 'none'}"
    )
    return "\n".join(lines)


def handle_chat(request: ChatRequest) -> ChatResponse:
    language = request.language
    profile = update_profile(request.profile, request.message)
    profile.language = language

    gaps = missing_fields(profile)
    # Two or fewer gaps means the match will already be meaningful.
    ready = len(gaps) <= 2

    result = match_profile(profile, language)
    eligible, likely = result["eligible"], result["likely"]

    if ready or not gaps:
        count = len(eligible) + len(likely)
        top = (eligible + likely)[:3]
        names = ", ".join(m.name for m in top) if top else ""
        if language == "ta":
            fallback = (
                f"நீங்கள் சொன்னதன் அடிப்படையில் {count} திட்டங்கள் பொருந்துகின்றன. "
                + (f"முக்கியமானவை: {names}. " if names else "")
                + "முழு பட்டியலையும் தகுதி விவரங்களையும் காண 'திட்டங்களைக் காட்டு' என்பதைத் தட்டவும்."
            )
        else:
            fallback = (
                f"Based on what you have told me, {count} schemes look relevant. "
                + (f"The strongest are: {names}. " if names else "")
                + "Tap 'Show my schemes' to see the full list with the exact eligibility checks."
            )
        suggestions = []
    else:
        next_field = gaps[0]
        fallback = QUESTIONS[next_field][language]
        if len(profile.issue_text.split()) > 3:
            prefix = (
                "புரிந்தது. " if language == "ta" else "Got it. "
            )
            fallback = prefix + fallback
        suggestions = []

    # Let the model rephrase, but never let it decide anything.
    source = "rules"
    reply = fallback
    if llm.is_available():
        polished = llm.generate(
            user_message=request.message,
            context=_context_for_llm(profile, language),
            history=[t.model_dump() for t in request.history],
        )
        if polished:
            reply, source = polished, "ollama"

    return ChatResponse(
        reply=reply,
        profile=profile,
        missing_fields=gaps,
        ready_to_match=ready,
        suggestions=suggestions,
        source=source,
    )
