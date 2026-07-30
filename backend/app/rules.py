"""Deterministic eligibility engine.

Every scheme is evaluated condition by condition. Each condition returns one of
three states rather than a plain boolean:

    pass    - the profile definitely satisfies it
    fail    - the profile definitely violates it
    unknown - the citizen has not told us enough to decide

That third state matters. A missing income figure should never be reported as
"you do not qualify" - it should be reported as "we still need to check this".
Schemes with no failures and no unknowns are `eligible`; schemes with unknowns
but no failures are `likely`; anything with a hard failure is `not_eligible`.
"""

from __future__ import annotations

import re

from .models import Profile, RuleCheck, SchemeMatch
from .schemes import load_schemes, localise

PASS, FAIL, UNKNOWN = "pass", "fail", "unknown"

# Human-readable labels for every occupation and flag we understand, so the
# explainer can say "Occupation: Farmer" rather than "occupation: farmer".
OCCUPATION_LABELS = {
    "farmer": {"en": "Farmer", "ta": "விவசாயி"},
    "agricultural_labourer": {"en": "Agricultural labourer", "ta": "விவசாயக் கூலித் தொழிலாளி"},
    "daily_wage_labourer": {"en": "Daily wage labourer", "ta": "நாட்கூலித் தொழிலாளி"},
    "construction_worker": {"en": "Construction worker", "ta": "கட்டுமானத் தொழிலாளி"},
    "street_vendor": {"en": "Street vendor", "ta": "தெருவோர வியாபாரி"},
    "small_business": {"en": "Small business owner", "ta": "சிறு தொழில் உரிமையாளர்"},
    "auto_driver": {"en": "Auto / taxi driver", "ta": "ஆட்டோ / டாக்சி ஓட்டுநர்"},
    "domestic_worker": {"en": "Domestic worker", "ta": "வீட்டுப் பணியாளர்"},
    "fisherman": {"en": "Fisherman", "ta": "மீனவர்"},
    "weaver": {"en": "Weaver", "ta": "நெசவாளர்"},
    "tailor": {"en": "Tailor", "ta": "தையல்காரர்"},
    "artisan": {"en": "Artisan / craftsperson", "ta": "கைவினைஞர்"},
    "carpenter": {"en": "Carpenter", "ta": "தச்சர்"},
    "blacksmith": {"en": "Blacksmith", "ta": "கொல்லர்"},
    "potter": {"en": "Potter", "ta": "குயவர்"},
    "salaried": {"en": "Salaried employee", "ta": "ஊதியம் பெறும் பணியாளர்"},
    "student": {"en": "Student", "ta": "மாணவர்"},
    "unemployed": {"en": "Unemployed", "ta": "வேலையில்லாதவர்"},
    "homemaker": {"en": "Homemaker", "ta": "இல்லத்தரசி"},
    "other": {"en": "Other", "ta": "மற்றவை"},
}

FLAG_LABELS = {
    "is_widow": {"en": "Widow", "ta": "விதவை"},
    "is_deserted_wife": {"en": "Deserted by husband", "ta": "கணவரால் கைவிடப்பட்டவர்"},
    "is_unmarried": {"en": "Unmarried", "ta": "திருமணமாகாதவர்"},
    "is_disabled": {"en": "Person with disability", "ta": "மாற்றுத்திறனாளி"},
    "is_pregnant": {"en": "Pregnant or nursing mother", "ta": "கர்ப்பிணி அல்லது பாலூட்டும் தாய்"},
    "is_student": {"en": "Currently studying", "ta": "தற்போது படிக்கிறார்"},
    "is_graduate": {"en": "Degree or diploma holder", "ta": "பட்டம் / டிப்ளமோ பெற்றவர்"},
    "govt_school_educated": {"en": "Studied in a government school", "ta": "அரசுப் பள்ளியில் படித்தவர்"},
    "is_rural": {"en": "Lives in a rural area", "ta": "கிராமப்புறத்தில் வசிக்கிறார்"},
    "is_unemployed": {"en": "Currently unemployed", "ta": "தற்போது வேலையில்லை"},
    "owns_land": {"en": "Owns agricultural land", "ta": "விவசாய நிலம் உள்ளது"},
    "owns_house": {"en": "Owns a house", "ta": "சொந்த வீடு உள்ளது"},
    "owns_pucca_house": {"en": "Owns a permanent (pucca) house", "ta": "நிரந்தர வீடு உள்ளது"},
    "needs_housing": {"en": "Needs housing support", "ta": "வீட்டுவசதி உதவி தேவை"},
    "has_lpg_connection": {"en": "Already has an LPG connection", "ta": "ஏற்கனவே எரிவாயு இணைப்பு உள்ளது"},
    "has_bank_account": {"en": "Already has a bank account", "ta": "ஏற்கனவே வங்கிக் கணக்கு உள்ளது"},
    "has_girl_child_under_10": {"en": "Has a girl child under 10", "ta": "10 வயதுக்குட்பட்ட பெண் குழந்தை உள்ளது"},
    "breadwinner_died": {"en": "Family breadwinner has died", "ta": "குடும்பத்தின் வருமானம் ஈட்டியவர் இறந்துவிட்டார்"},
    "govt_employee": {"en": "Government employee", "ta": "அரசு ஊழியர்"},
    "income_tax_payer": {"en": "Pays income tax", "ta": "வருமான வரி செலுத்துபவர்"},
}

SOCIAL_LABELS = {
    "SC": {"en": "Scheduled Caste", "ta": "பட்டியல் சாதி"},
    "ST": {"en": "Scheduled Tribe", "ta": "பட்டியல் பழங்குடி"},
    "BC": {"en": "Backward Class", "ta": "பிற்படுத்தப்பட்டோர்"},
    "MBC": {"en": "Most Backward Class", "ta": "மிகப் பிற்படுத்தப்பட்டோர்"},
    "DNC": {"en": "Denotified Community", "ta": "சீர்மரபினர்"},
    "OC": {"en": "Other Community", "ta": "பிற சமூகம்"},
}

GENDER_LABELS = {
    "female": {"en": "Female", "ta": "பெண்"},
    "male": {"en": "Male", "ta": "ஆண்"},
    "other": {"en": "Other", "ta": "மற்றவை"},
}

# Phrases that let us infer situation flags straight from free text, so a user
# who types "my husband passed away last year" gets widow schemes without
# having to hunt for the checkbox.
TEXT_FLAG_HINTS: dict[str, list[str]] = {
    "is_widow": ["widow", "husband died", "husband passed", "lost my husband", "விதவை", "கணவர் இறந்த"],
    "is_disabled": ["disabled", "disability", "handicap", "blind", "deaf", "wheelchair", "மாற்றுத்திறனாளி", "ஊனம்", "பார்வையற்ற"],
    "is_pregnant": ["pregnant", "pregnancy", "expecting", "delivery", "கர்ப்ப", "கருவுற்ற", "பிரசவ"],
    "is_student": ["student", "college", "school", "studying", "study", "மாணவ", "கல்லூரி", "பள்ளி", "படிக்"],
    "is_unemployed": ["unemployed", "no job", "lost my job", "jobless", "வேலையில்லை", "வேலை இல்ல"],
    "needs_housing": ["no house", "homeless", "hut", "need a house", "shelter", "வீடு இல்ல", "குடிசை", "வீடு தேவை"],
    "is_rural": ["village", "rural", "கிராமம்", "கிராமத்தில்"],
    "owns_land": ["my land", "acres", "farm land", "நிலம்", "ஏக்கர்"],
    "breadwinner_died": ["breadwinner died", "father died", "father passed", "தந்தை இறந்த", "வருமானம் ஈட்டியவர் இறந்த"],
}

OCCUPATION_HINTS: dict[str, list[str]] = {
    "farmer": ["farmer", "farming", "agriculture", "crop", "விவசாய", "பயிர்", "உழவ"],
    "fisherman": ["fisherman", "fishing", "மீனவ", "மீன்பிடி"],
    "construction_worker": ["construction", "mason", "கட்டுமான", "கொத்தன"],
    "street_vendor": ["street vendor", "hawker", "petty shop", "தெருவோர", "சிறு கடை"],
    "weaver": ["weaver", "handloom", "நெசவ", "கைத்தறி"],
    "auto_driver": ["auto driver", "taxi", "cab", "ஆட்டோ", "டாக்சி"],
    "tailor": ["tailor", "stitching", "தையல்"],
}


def _label(table: dict, key: str, language: str) -> str:
    entry = table.get(key)
    if not entry:
        return key.replace("_", " ").title()
    return entry.get(language) or entry.get("en") or key


def _money(amount: int, language: str) -> str:
    formatted = f"{amount:,}"
    return f"Rs {formatted}" if language == "en" else f"ரூ.{formatted}"


def infer_from_text(profile: Profile) -> Profile:
    """Enrich a profile with flags and occupation implied by its free text.

    Returns a copy; the caller's profile is left untouched. We only ever add
    information here - anything the user explicitly set always wins.
    """
    text = (profile.issue_text or "").lower()
    if not text:
        return profile

    enriched = profile.model_copy(deep=True)
    flags = set(enriched.flags)

    for flag, hints in TEXT_FLAG_HINTS.items():
        if any(hint in text for hint in hints):
            flags.add(flag)

    if enriched.marital_status == "widowed":
        flags.add("is_widow")
    if enriched.marital_status == "separated":
        flags.add("is_deserted_wife")
    if enriched.marital_status == "single" and (enriched.age or 0) >= 50:
        flags.add("is_unmarried")
    if enriched.occupation == "student":
        flags.add("is_student")
    if enriched.occupation == "unemployed":
        flags.add("is_unemployed")
    if (enriched.disability_percent or 0) >= 40:
        flags.add("is_disabled")

    enriched.flags = sorted(flags)

    if not enriched.occupation:
        for occupation, hints in OCCUPATION_HINTS.items():
            if any(hint in text for hint in hints):
                enriched.occupation = occupation
                break

    return enriched


def _check_residency(scheme: dict, profile: Profile, language: str) -> RuleCheck | None:
    required = scheme["eligibility"].get("residency")
    if not required:
        return None

    if required == "TN":
        label = {"en": "Must be a Tamil Nadu resident", "ta": "தமிழ்நாட்டில் வசிப்பவராக இருக்க வேண்டும்"}
        if profile.district:
            detail = {
                "en": f"You listed {profile.district}, which is in Tamil Nadu.",
                "ta": f"நீங்கள் {profile.district} எனக் குறிப்பிட்டுள்ளீர்கள், இது தமிழ்நாட்டில் உள்ளது.",
            }
            status = PASS
        else:
            detail = {
                "en": "Tell us your district so we can confirm this.",
                "ta": "இதை உறுதிப்படுத்த உங்கள் மாவட்டத்தைத் தெரிவிக்கவும்.",
            }
            status = UNKNOWN
    else:
        label = {"en": "Must be an Indian citizen", "ta": "இந்தியக் குடிமகனாக இருக்க வேண்டும்"}
        detail = {"en": "Open to all Indian citizens.", "ta": "அனைத்து இந்தியக் குடிமக்களுக்கும் திறந்திருக்கிறது."}
        status = PASS

    return RuleCheck(
        rule="residency",
        label=localise(label, language),
        status=status,
        detail=localise(detail, language),
    )


def _check_age(scheme: dict, profile: Profile, language: str) -> RuleCheck | None:
    age_rule = scheme["eligibility"].get("age")
    if not age_rule:
        return None

    low, high = age_rule.get("min"), age_rule.get("max")
    if low is not None and high is not None:
        label = {"en": f"Age must be between {low} and {high}", "ta": f"வயது {low} முதல் {high} வரை இருக்க வேண்டும்"}
    elif low is not None:
        label = {"en": f"Age must be {low} or above", "ta": f"வயது {low} அல்லது அதற்கு மேல் இருக்க வேண்டும்"}
    else:
        label = {"en": f"Age must be {high} or below", "ta": f"வயது {high} அல்லது அதற்கு கீழ் இருக்க வேண்டும்"}

    if profile.age is None:
        detail = {"en": "Enter your age to check this.", "ta": "இதைச் சரிபார்க்க உங்கள் வயதை உள்ளிடவும்."}
        status = UNKNOWN
    elif low is not None and profile.age < low:
        detail = {
            "en": f"You are {profile.age}, which is below the minimum of {low}.",
            "ta": f"உங்கள் வயது {profile.age}, குறைந்தபட்ச வயது {low} ஐ விட குறைவு.",
        }
        status = FAIL
    elif high is not None and profile.age > high:
        detail = {
            "en": f"You are {profile.age}, which is above the maximum of {high}.",
            "ta": f"உங்கள் வயது {profile.age}, அதிகபட்ச வயது {high} ஐ விட அதிகம்.",
        }
        status = FAIL
    else:
        detail = {"en": f"You are {profile.age} - within range.", "ta": f"உங்கள் வயது {profile.age} - வரம்பிற்குள் உள்ளது."}
        status = PASS

    return RuleCheck(rule="age", label=localise(label, language), status=status, detail=localise(detail, language))


def _check_income(scheme: dict, profile: Profile, language: str) -> RuleCheck | None:
    ceiling = scheme["eligibility"].get("annual_income_max")
    if ceiling is None:
        return None

    label = {
        "en": f"Annual family income must not exceed {_money(ceiling, 'en')}",
        "ta": f"ஆண்டு குடும்ப வருமானம் {_money(ceiling, 'ta')} ஐ மிகக் கூடாது",
    }

    if profile.annual_income is None:
        detail = {
            "en": "Enter your annual income to check this.",
            "ta": "இதைச் சரிபார்க்க உங்கள் ஆண்டு வருமானத்தை உள்ளிடவும்.",
        }
        status = UNKNOWN
    elif profile.annual_income > ceiling:
        detail = {
            "en": f"Your income of {_money(profile.annual_income, 'en')} is above the {_money(ceiling, 'en')} limit.",
            "ta": f"உங்கள் வருமானம் {_money(profile.annual_income, 'ta')}, வரம்பான {_money(ceiling, 'ta')} ஐ விட அதிகம்.",
        }
        status = FAIL
    else:
        detail = {
            "en": f"Your income of {_money(profile.annual_income, 'en')} is within the {_money(ceiling, 'en')} limit.",
            "ta": f"உங்கள் வருமானம் {_money(profile.annual_income, 'ta')}, வரம்பான {_money(ceiling, 'ta')} க்குள் உள்ளது.",
        }
        status = PASS

    return RuleCheck(rule="income", label=localise(label, language), status=status, detail=localise(detail, language))


def _check_gender(scheme: dict, profile: Profile, language: str) -> RuleCheck | None:
    allowed = scheme["eligibility"].get("gender")
    if not allowed:
        return None

    names = ", ".join(_label(GENDER_LABELS, g, language) for g in allowed)
    label = {"en": f"Applicant must be {names}", "ta": f"விண்ணப்பதாரர் {names} ஆக இருக்க வேண்டும்"}

    if profile.gender is None:
        detail = {"en": "Select your gender to check this.", "ta": "இதைச் சரிபார்க்க உங்கள் பாலினத்தைத் தேர்ந்தெடுக்கவும்."}
        status = UNKNOWN
    elif profile.gender in allowed:
        detail = {"en": "Your gender matches this requirement.", "ta": "உங்கள் பாலினம் இந்தத் தேவைக்கு பொருந்துகிறது."}
        status = PASS
    else:
        detail = {
            "en": f"This scheme is restricted to {names} applicants.",
            "ta": f"இந்தத் திட்டம் {names} விண்ணப்பதாரர்களுக்கு மட்டுமே.",
        }
        status = FAIL

    return RuleCheck(rule="gender", label=localise(label, language), status=status, detail=localise(detail, language))


def _check_occupation(scheme: dict, profile: Profile, language: str) -> RuleCheck | None:
    allowed = scheme["eligibility"].get("occupation")
    if not allowed:
        return None

    names = ", ".join(_label(OCCUPATION_LABELS, o, language) for o in allowed)
    label = {"en": f"Occupation must be one of: {names}", "ta": f"தொழில் இவற்றில் ஒன்றாக இருக்க வேண்டும்: {names}"}

    if not profile.occupation:
        detail = {"en": "Tell us your occupation to check this.", "ta": "இதைச் சரிபார்க்க உங்கள் தொழிலைத் தெரிவிக்கவும்."}
        status = UNKNOWN
    elif profile.occupation in allowed:
        detail = {
            "en": f"You are a {_label(OCCUPATION_LABELS, profile.occupation, 'en')}, which qualifies.",
            "ta": f"நீங்கள் {_label(OCCUPATION_LABELS, profile.occupation, 'ta')}, இது தகுதியானது.",
        }
        status = PASS
    else:
        detail = {
            "en": f"Your occupation ({_label(OCCUPATION_LABELS, profile.occupation, 'en')}) is not covered.",
            "ta": f"உங்கள் தொழில் ({_label(OCCUPATION_LABELS, profile.occupation, 'ta')}) இதில் அடங்கவில்லை.",
        }
        status = FAIL

    return RuleCheck(rule="occupation", label=localise(label, language), status=status, detail=localise(detail, language))


def _check_social_category(scheme: dict, profile: Profile, language: str) -> RuleCheck | None:
    allowed = scheme["eligibility"].get("social_category")
    if not allowed:
        return None

    names = ", ".join(_label(SOCIAL_LABELS, c, language) for c in allowed)
    label = {"en": f"Community must be one of: {names}", "ta": f"சமூகம் இவற்றில் ஒன்றாக இருக்க வேண்டும்: {names}"}

    if not profile.social_category:
        detail = {
            "en": "Select your community to check this.",
            "ta": "இதைச் சரிபார்க்க உங்கள் சமூகத்தைத் தேர்ந்தெடுக்கவும்.",
        }
        status = UNKNOWN
    elif profile.social_category in allowed:
        detail = {"en": "Your community qualifies for this scheme.", "ta": "உங்கள் சமூகம் இந்தத் திட்டத்திற்கு தகுதியானது."}
        status = PASS
    else:
        detail = {
            "en": f"This scheme is reserved for {names} applicants.",
            "ta": f"இந்தத் திட்டம் {names} விண்ணப்பதாரர்களுக்கு ஒதுக்கப்பட்டுள்ளது.",
        }
        status = FAIL

    return RuleCheck(
        rule="social_category", label=localise(label, language), status=status, detail=localise(detail, language)
    )


def _check_disability_percent(scheme: dict, profile: Profile, language: str) -> RuleCheck | None:
    minimum = scheme["eligibility"].get("disability_percent_min")
    if minimum is None:
        return None

    label = {
        "en": f"Disability must be {minimum}% or more",
        "ta": f"ஊனம் {minimum}% அல்லது அதற்கு மேல் இருக்க வேண்டும்",
    }

    if profile.disability_percent is None:
        detail = {
            "en": "Enter the percentage on your disability certificate.",
            "ta": "உங்கள் ஊனச் சான்றிதழில் உள்ள சதவீதத்தை உள்ளிடவும்.",
        }
        status = UNKNOWN
    elif profile.disability_percent >= minimum:
        detail = {
            "en": f"Your certificate shows {profile.disability_percent}%, which meets the {minimum}% threshold.",
            "ta": f"உங்கள் சான்றிதழ் {profile.disability_percent}% காட்டுகிறது, இது {minimum}% வரம்பை பூர்த்தி செய்கிறது.",
        }
        status = PASS
    else:
        detail = {
            "en": f"Your certificate shows {profile.disability_percent}%, below the {minimum}% threshold.",
            "ta": f"உங்கள் சான்றிதழ் {profile.disability_percent}% காட்டுகிறது, {minimum}% வரம்பிற்கு கீழ் உள்ளது.",
        }
        status = FAIL

    return RuleCheck(
        rule="disability_percent", label=localise(label, language), status=status, detail=localise(detail, language)
    )


def _check_flags(scheme: dict, profile: Profile, language: str) -> list[RuleCheck]:
    """Required and disqualifying situation flags.

    A required flag the user did not tick is `unknown`, not `fail` - they may
    simply not have reached that checkbox. A disqualifying flag they *did* tick
    is a hard `fail`, because that is a positive statement about their situation.
    """
    checks: list[RuleCheck] = []
    held = set(profile.flags)

    for flag in scheme["eligibility"].get("flags_required", []):
        name = _label(FLAG_LABELS, flag, language)
        label = {"en": f"Must be: {name}", "ta": f"இதுவாக இருக்க வேண்டும்: {name}"}
        if flag in held:
            detail = {"en": "You indicated this applies to you.", "ta": "இது உங்களுக்குப் பொருந்தும் எனக் குறிப்பிட்டுள்ளீர்கள்."}
            status = PASS
        else:
            detail = {
                "en": f"Confirm whether this applies: {name.lower()}.",
                "ta": f"இது பொருந்துமா என உறுதிப்படுத்தவும்: {name}.",
            }
            status = UNKNOWN
        checks.append(
            RuleCheck(
                rule=f"flag:{flag}", label=localise(label, language), status=status, detail=localise(detail, language)
            )
        )

    for flag in scheme["eligibility"].get("flags_excluded", []):
        name = _label(FLAG_LABELS, flag, language)
        label = {"en": f"Must NOT be: {name}", "ta": f"இதுவாக இருக்கக் கூடாது: {name}"}
        if flag in held:
            detail = {
                "en": f"You indicated: {name.lower()} - this disqualifies you.",
                "ta": f"நீங்கள் குறிப்பிட்டது: {name} - இது உங்களைத் தகுதியிழக்கச் செய்கிறது.",
            }
            status = FAIL
        else:
            detail = {"en": "This does not apply to you.", "ta": "இது உங்களுக்குப் பொருந்தாது."}
            status = PASS
        checks.append(
            RuleCheck(
                rule=f"not_flag:{flag}",
                label=localise(label, language),
                status=status,
                detail=localise(detail, language),
            )
        )

    return checks


# What the citizen is actually asking for, inferred from their own words. This
# is the strongest ranking signal we have: someone who says "heart surgery"
# wants health schemes, not a free LPG connection they also happen to qualify for.
INTENT_KEYWORDS: dict[str, list[str]] = {
    "health": [
        "health", "hospital", "surgery", "operation", "treatment", "medical", "medicine",
        "doctor", "illness", "disease", "cancer", "heart", "kidney", "dialysis", "accident",
        "injury", "sick", "pain", "மருத்துவ", "மருத்துவமனை", "அறுவை", "சிகிச்சை", "நோய்",
        "இதய", "சிறுநீரக", "புற்றுநோய்", "விபத்து", "மருந்து",
    ],
    "education": [
        "school", "college", "student", "study", "studying", "education", "scholarship",
        "fees", "tuition", "degree", "exam", "book", "laptop", "hostel", "பள்ளி", "கல்லூரி",
        "மாணவ", "கல்வி", "உதவித்தொகை", "கட்டணம்", "படிப்பு", "பட்டம்", "புத்தக",
    ],
    "agriculture": [
        "farm", "farmer", "farming", "agriculture", "crop", "paddy", "land", "seed",
        "irrigation", "tractor", "harvest", "drought", "flood", "cattle", "cow", "goat",
        "விவசாய", "வேளாண்", "பயிர்", "நிலம்", "விதை", "நீர்ப்பாசன", "அறுவடை", "வறட்சி",
        "வெள்ளம்", "மாடு", "ஆடு", "உழவ", "நெல்",
    ],
    "housing": [
        "house", "home", "housing", "shelter", "roof", "hut", "homeless", "rent", "patta",
        "site", "வீடு", "வீட்டுவசதி", "குடிசை", "தங்குமிட", "மனை", "பட்டா", "கூரை",
    ],
    "employment": [
        "job", "work", "employment", "unemployed", "wage", "salary", "livelihood",
        "jobless", "labour", "labor", "coolie", "வேலை", "கூலி", "ஊதிய", "வாழ்வாதார",
        "வேலையில்லை", "தொழிலாளி",
    ],
    "business": [
        "business", "shop", "loan", "entrepreneur", "startup", "vendor", "trade",
        "capital", "subsidy", "தொழில்", "கடை", "கடன்", "தொழில்முனைவ", "வியாபார", "மானிய",
    ],
    "women": [
        "woman", "women", "girl", "daughter", "wife", "mother", "widow", "pregnant",
        "maternity", "marriage", "பெண்", "மகள்", "மனைவி", "தாய்", "விதவை", "கர்ப்ப",
        "மகப்பேறு", "திருமண", "மகளிர்",
    ],
    "disability": [
        "disability", "disabled", "handicap", "blind", "deaf", "wheelchair", "tricycle",
        "ஊனம்", "மாற்றுத்திறனாளி", "பார்வையற்ற", "செவித்திறன்", "முச்சக்கர",
    ],
    "elderly": [
        "old", "elderly", "senior", "pension", "aged", "retire", "முதியோர்", "ஓய்வூதிய",
        "வயதான", "மூத்த",
    ],
    "utility": [
        "ration", "rice", "food", "gas", "lpg", "cylinder", "electricity", "current",
        "bus", "travel", "ரேஷன்", "அரிசி", "உணவு", "எரிவாயு", "சிலிண்டர்", "மின்சார",
        "பேருந்து", "பயண",
    ],
    "social": [
        "pension", "destitute", "support", "death", "died", "orphan", "ஓய்வூதிய",
        "ஆதரவற்ற", "இறந்த", "அனாதை",
    ],
}


def detect_intents(text: str) -> set[str]:
    """Which scheme categories the citizen's own words point at."""
    lowered = (text or "").lower()
    if not lowered.strip():
        return set()

    intents = set()
    for category, words in INTENT_KEYWORDS.items():
        for word in words:
            if word.isascii():
                if re.search(rf"\b{re.escape(word)}", lowered):
                    intents.add(category)
                    break
            elif word in lowered:
                intents.add(category)
                break
    return intents


def _intent_bonus(scheme: dict, intents: set[str]) -> int:
    """Reward category overlap with what the citizen asked for, penalise misses.

    Without this, a widow on a low income qualifies for ~30 schemes that all
    score the same, and the one she actually came for is buried among free
    bicycles and pilgrimage grants.
    """
    if not intents:
        return 0

    categories = set(scheme.get("categories", []))
    overlap = categories & intents
    if overlap:
        return min(14 + (len(overlap) - 1) * 6, 26)
    return -14


def _relevance_bonus(scheme: dict, profile: Profile) -> int:
    """Reward schemes whose keywords appear in what the citizen actually described."""
    text = f"{profile.issue_text} {profile.occupation or ''}".lower()
    if not text.strip():
        return 0

    hits = 0
    for keyword in scheme.get("keywords", []):
        keyword = keyword.lower().strip()
        if not keyword:
            continue
        # Word-boundary match for ASCII keywords; plain containment for Tamil,
        # which agglutinates and would not match on boundaries.
        if keyword.isascii():
            if re.search(rf"\b{re.escape(keyword)}\b", text):
                hits += 1
        elif keyword in text:
            hits += 1

    return min(hits * 5, 24)


def evaluate_scheme(
    scheme: dict, profile: Profile, language: str, intents: set[str] | None = None
) -> SchemeMatch:
    checks: list[RuleCheck] = []

    for builder in (
        _check_residency,
        _check_age,
        _check_income,
        _check_gender,
        _check_occupation,
        _check_social_category,
        _check_disability_percent,
    ):
        check = builder(scheme, profile, language)
        if check is not None:
            checks.append(check)

    checks.extend(_check_flags(scheme, profile, language))

    if not checks:
        checks.append(
            RuleCheck(
                rule="open",
                label=localise({"en": "Open to all applicants", "ta": "அனைத்து விண்ணப்பதாரர்களுக்கும் திறந்திருக்கிறது"}, language),
                status=PASS,
                detail=localise({"en": "This scheme has no restrictive conditions.", "ta": "இந்தத் திட்டத்திற்கு கட்டுப்படுத்தும் நிபந்தனைகள் இல்லை."}, language),
            )
        )

    passed = sum(1 for c in checks if c.status == PASS)
    failed = sum(1 for c in checks if c.status == FAIL)
    unknown = sum(1 for c in checks if c.status == UNKNOWN)

    if failed:
        status = "not_eligible"
    elif unknown:
        status = "likely"
    else:
        status = "eligible"

    # Scoring blends four signals rather than starting from priority alone,
    # which used to saturate every eligible scheme at the 99 cap and made the
    # ranking meaningless. Weights are chosen so results spread across ~45-99.
    #
    #   priority    how broadly useful the scheme is        -> 41..53
    #   intent      matches the need the citizen described  -> -14..26
    #   relevance   keywords hit in what the citizen wrote   ->  0..24
    #   specificity conditions matched beyond mere residency ->  0..12
    #
    # Intent carries the most weight because qualifying for a scheme and wanting
    # it are different things: a low-income widow qualifies for ~30 schemes, and
    # only the intent signal knows she came here about a hospital bill.
    # Specificity then separates a narrowly-targeted match (widow pension for a
    # widow) from a blanket one (free rice for every resident).
    specific_passes = sum(1 for c in checks if c.status == PASS and c.rule != "residency")

    score = scheme.get("priority", 70) * 0.55
    score += _intent_bonus(scheme, intents or set())
    score += _relevance_bonus(scheme, profile)
    score += min(specific_passes * 2, 12)

    if status == "eligible":
        score += 8
    elif status == "likely":
        score -= unknown * 2
    else:
        score -= 35 + failed * 8

    score = round(score)

    return SchemeMatch(
        id=scheme["id"],
        name=localise(scheme["name"], language),
        department=localise(scheme["department"], language),
        level=scheme["level"],
        categories=scheme.get("categories", []),
        summary=localise(scheme["summary"], language),
        benefit=localise(scheme["benefit"], language),
        documents=[localise(d, language) for d in scheme.get("documents", [])],
        apply_mode=scheme["apply"]["mode"],
        apply_url=scheme["apply"]["url"],
        apply_office=localise(scheme["apply"]["office"], language),
        score=max(0, min(99, score)),
        status=status,
        checks=checks,
        passed_count=passed,
        failed_count=failed,
        unknown_count=unknown,
    )


def match_profile(profile: Profile, language: str = "en") -> dict:
    enriched = infer_from_text(profile)
    intents = detect_intents(enriched.issue_text)
    matches = [
        evaluate_scheme(scheme, enriched, language, intents) for scheme in load_schemes()
    ]
    matches.sort(key=lambda m: -m.score)

    eligible = [m for m in matches if m.status == "eligible"]
    # Truncate before summarising so the headline count always equals the number
    # of cards actually rendered.
    likely = [m for m in matches if m.status == "likely"][:12]
    not_eligible = [m for m in matches if m.status == "not_eligible"][:8]

    return {
        "profile_name": enriched.name,
        "language": language,
        "total_evaluated": len(matches),
        "eligible": eligible,
        "likely": likely,
        "not_eligible": not_eligible,
        "summary_text": build_summary(enriched, eligible, likely, language),
        "enriched_profile": enriched,
    }


def build_summary(profile: Profile, eligible: list, likely: list, language: str) -> str:
    name = profile.name.strip()
    if language == "ta":
        greeting = f"{name}, " if name else ""
        if eligible:
            return (
                f"{greeting}உங்கள் விவரங்களின் அடிப்படையில் {len(eligible)} திட்டங்களுக்கு நீங்கள் "
                f"தகுதி பெறுகிறீர்கள், மேலும் {len(likely)} திட்டங்கள் சில கூடுதல் விவரங்களுடன் "
                f"பொருந்தக்கூடும். முதலில் உயர் பொருத்தமுள்ள திட்டங்களுக்கு விண்ணப்பிக்கவும்."
            )
        if likely:
            return (
                f"{greeting}{len(likely)} திட்டங்கள் உங்களுக்குப் பொருந்தக்கூடும். "
                f"கீழே காணப்படும் விடுபட்ட விவரங்களை நிரப்பினால் உறுதியான பட்டியலை வழங்க முடியும்."
            )
        return f"{greeting}தற்போதைய விவரங்களுடன் பொருத்தமான திட்டங்கள் எதுவும் கிடைக்கவில்லை. மேலும் விவரங்களைச் சேர்க்கவும்."

    greeting = f"{name}, " if name else ""
    if eligible:
        return (
            f"{greeting}you meet every condition for {len(eligible)} scheme"
            f"{'s' if len(eligible) != 1 else ''}, and {len(likely)} more could apply once a few "
            f"details are confirmed. Start with the highest-scoring matches below."
        )
    if likely:
        return (
            f"{greeting}{len(likely)} schemes could apply to you. Fill in the missing details "
            f"flagged below and NALAM can confirm your eligibility exactly."
        )
    return f"{greeting}no schemes matched the details provided. Add more information about your situation to widen the search."
