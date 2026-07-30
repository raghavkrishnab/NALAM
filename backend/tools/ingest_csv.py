"""Convert the TN welfare scheme CSV into NALAM's structured catalogue.

The source CSV carries authoritative, source-linked scheme records, but its
eligibility column is free prose ("Age 18-65; Annual income < Rs 72000") and its
scheme_id column is not actually unique. This script:

  1. resolves duplicate ids and near-duplicate scheme names,
  2. parses the prose eligibility into machine-checkable rules,
  3. normalises ~46 ad-hoc category labels down to a usable taxonomy,
  4. layers on Tamil translations from data/translations_ta.json,

and writes data/schemes_master.json, which is what the API serves.

Run from the backend directory:
    python tools/ingest_csv.py "path\\to\\schemes.csv"
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
DATA = BACKEND / "data"

# ---------------------------------------------------------------------------
# Category normalisation: the CSV uses 46 free-form labels for what are really
# about a dozen concerns. Longest keys are matched first.
# ---------------------------------------------------------------------------
CATEGORY_MAP = {
    "social security pension": ["social", "elderly"],
    "social security": ["social"],
    "education / scholarship": ["education"],
    "education/nutrition": ["education", "health"],
    "education / technology": ["education"],
    "education / social justice": ["education"],
    "higher education / international": ["education"],
    "education welfare": ["education"],
    "sports scholarship": ["education"],
    "sports promotion": ["education"],
    "education": ["education"],
    "marriage assistance": ["women", "social"],
    "labour welfare": ["employment"],
    "girl child welfare": ["women", "education"],
    "women welfare": ["women"],
    "maternity": ["women", "health"],
    "agriculture finance": ["agriculture"],
    "agricultural relief & subsidy": ["agriculture"],
    "agricultural subsidy": ["agriculture"],
    "agriculture development": ["agriculture"],
    "agricultural livelihood": ["agriculture"],
    "housing & land rights": ["housing"],
    "rural housing welfare": ["housing"],
    "housing": ["housing"],
    "livelihood assistance": ["employment"],
    "livelihood / rural development": ["employment"],
    "livelihood": ["employment"],
    "food security": ["utility", "social"],
    "ex-servicemen welfare": ["social"],
    "skill development": ["education", "employment"],
    "social justice": ["social"],
    "transport welfare": ["utility"],
    "transport / education welfare": ["utility", "education"],
    "renewable energy subsidy": ["utility", "agriculture"],
    "social welfare / employment": ["employment", "social"],
    "urban welfare": ["housing"],
    "youth recognition": ["education"],
    "preventive healthcare": ["health"],
    "specialized healthcare": ["health"],
    "health insurance": ["health"],
    "emergency care": ["health"],
    "eye care": ["health"],
    "healthcare": ["health"],
    "mobility & rehabilitation": ["disability"],
    "religious pilgrimage assistance": ["social"],
    "entrepreneurship welfare": ["business"],
}

# Words stripped before comparing two scheme names for sameness.
NAME_NOISE = re.compile(
    r"\b(scheme|schemes|thittam|thittham|programme|program|assistance|"
    r"tamil\s*nadu|tn|government|govt|for|of|the|and|a|an)\b",
    re.IGNORECASE,
)


def normalise_name(name: str) -> str:
    """Reduce a scheme name to a comparison key: drop parentheticals and filler."""
    text = re.sub(r"\([^)]*\)", " ", name)
    text = NAME_NOISE.sub(" ", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    return " ".join(sorted(set(text.split())))


def names_match(a: str, b: str) -> bool:
    """True when two names describe the same scheme.

    Uses token containment rather than equality so "Free House Site Patta" and
    "Free House Site Patta Scheme for the landless" collapse together, while
    "Girl Child Protection" and "Widow Remarriage" stay separate.
    """
    tokens_a, tokens_b = set(a.split()), set(b.split())
    if not tokens_a or not tokens_b:
        return False
    if tokens_a == tokens_b:
        return True

    smaller, larger = sorted((tokens_a, tokens_b), key=len)

    # Full containment catches the common "short official name vs long
    # descriptive name" pair - "Ulema Pension" inside "Ulema and Other Mosque
    # Workers Pension". Two tokens is the floor; single-word names are too
    # ambiguous to merge on.
    if len(smaller) >= 2 and smaller <= larger:
        return True

    # Otherwise demand a substantial overlap, so longer names that merely share
    # a few generic words stay apart.
    overlap = len(smaller & larger)
    return overlap >= 3 and overlap / len(smaller) >= 0.85


# ---------------------------------------------------------------------------
# Eligibility prose -> structured rules
# ---------------------------------------------------------------------------
def parse_money(text: str) -> int | None:
    """Read Rs 72000, Rs 2.5 Lakhs, Rs 2,50,000, Rs 8 Lakhs/yr."""
    lakh = re.search(r"(?:₹|rs\.?)?\s*(\d+(?:\.\d+)?)\s*lakh", text, re.IGNORECASE)
    if lakh:
        return int(float(lakh.group(1)) * 100_000)
    plain = re.search(r"(?:₹|rs\.?)\s*([\d,]{4,12})", text, re.IGNORECASE)
    if plain:
        digits = plain.group(1).replace(",", "")
        if digits.isdigit():
            return int(digits)
    return None


def parse_age(text: str) -> dict | None:
    lowered = text.lower()

    ranged = re.search(r"age[ds]?\s*(?:between\s*)?(\d{1,2})\s*(?:-|to|and)\s*(\d{1,2})", lowered)
    if ranged:
        return {"min": int(ranged.group(1)), "max": int(ranged.group(2))}
    ranged = re.search(r"\b(\d{1,2})\s*(?:-|to)\s*(\d{1,2})\s*years?\b", lowered)
    if ranged:
        return {"min": int(ranged.group(1)), "max": int(ranged.group(2))}

    rule: dict = {}
    lower_bound = re.search(
        r"(?:age|aged|minimum age|min age)[^.;]{0,20}?(\d{1,2})\s*(?:years?)?\s*(?:and\s*)?(?:or\s*)?above|"
        r"aged\s*(\d{1,2})\s*(?:and|or)\s*above|"
        r"above\s*(?:age\s*)?(\d{1,2})",
        lowered,
    )
    if lower_bound:
        value = next(g for g in lower_bound.groups() if g)
        rule["min"] = int(value)

    upper_bound = re.search(r"(?:age\s*)?max(?:imum)?\s*(?:age\s*)?(\d{1,2})|under\s*(\d{1,2})\s*years?", lowered)
    if upper_bound:
        value = next(g for g in upper_bound.groups() if g)
        rule["max"] = int(value)

    return rule or None


def parse_disability(text: str) -> int | None:
    found = re.search(r"(\d{2,3})\s*%", text)
    if found:
        value = int(found.group(1))
        if 1 <= value <= 100:
            return value
    return None


GENDER_PATTERNS = [
    (["girl", "girls", "women", "woman", "widow", "widows", "bride", "female",
      "fisherwomen", "mother", "wives", "wife", "magalir", "maternity", "pregnant"], "female"),
    (["boys", "boy", "puthalvan", "pudhalvan", "groom", "male student"], "male"),
]

OCCUPATION_PATTERNS = [
    (["farmer", "farmers", "agricultural labour", "agricultural worker", "cultivating",
      "kuruvai", "paccs", "chitta holder", "agricultural land"], "farmer"),
    (["fisherman", "fishermen", "fisherwomen", "marine fisher"], "fisherman"),
    (["construction worker", "construction workers"], "construction_worker"),
    (["manual worker", "manual workers", "unorganized", "unorganised"], "daily_wage_labourer"),
    (["driving licence", "driving license", "drivers welfare", "commercial driver"], "auto_driver"),
    (["student", "students", "studying", "pupil"], "student"),
    (["entrepreneur", "entrepreneurs", "enterprise"], "small_business"),
    (["unemployed", "unemployment"], "unemployed"),
]

FLAG_PATTERNS = [
    (["bpl", "below poverty", "destitute", "living in poverty", "poor"], "is_low_income"),
    (["widow", "widows"], "is_widow"),
    (["deserted"], "is_deserted_wife"),
    (["unmarried female", "unmarried women"], "is_unmarried"),
    (["disability", "differently abled", "disabled", "intellectual disability",
      "muscular dystrophy", "locomotor"], "is_disabled"),
    (["pregnant", "maternity", "deliveries"], "is_pregnant"),
    (["student", "students", "studying", "class 6", "class 11", "class 12",
      "post-matric", "post matric", "college", "school"], "is_student"),
    (["rural", "village panchayat", "thatched", "hut"], "is_rural"),
    (["orphan"], "is_orphan"),
    (["govt schools", "government schools", "government and aided", "govt/aided",
      "govt or aided", "aided schools"], "govt_school_educated"),
    (["ex-servicemen", "veteran", "military"], "is_ex_serviceman"),
    (["transgender", "transpersons"], "is_transgender"),
    (["registered with employment exchange", "employment exchange"], "is_unemployed"),
]

EXCLUSION_PATTERNS = [
    (["must not own any land", "not own any land"], "owns_land"),
    (["must not own any house", "should not own house", "not own any house or house site"], "owns_pucca_house"),
    (["not receiving other pension", "not receiving any other military pension",
      "not receiving any other pension"], "receives_other_pension"),
]

SOCIAL_PATTERNS = [
    (["sc/st", "sc / st", "scheduled caste", "scheduled tribe"], ["SC", "ST"]),
    (["bc/mbc/dnt", "bc, mbc and dnt", "bc/mbc/dnc", "bc, mbc", "bc/mbc"], ["BC", "MBC", "DNC"]),
]


def parse_eligibility(row: dict) -> dict:
    """Derive structured rules from the eligibility, beneficiary and description text."""
    blob = " ".join(
        [row.get("eligibility", ""), row.get("beneficiary", ""), row.get("description", "")]
    )
    lowered = blob.lower()

    rules: dict = {"residency": "TN"}

    age = parse_age(row.get("eligibility", ""))
    if age:
        rules["age"] = age

    income = parse_money(row.get("eligibility", ""))
    if income and re.search(r"income", row.get("eligibility", ""), re.IGNORECASE):
        rules["annual_income_max"] = income

    for words, gender in GENDER_PATTERNS:
        if any(re.search(rf"\b{re.escape(w)}\b", lowered) for w in words):
            rules["gender"] = [gender]
            break

    occupations = []
    for words, occupation in OCCUPATION_PATTERNS:
        if any(w in lowered for w in words):
            occupations.append(occupation)
    if occupations:
        rules["occupation"] = sorted(set(occupations))

    for words, categories in SOCIAL_PATTERNS:
        if any(w in lowered for w in words):
            rules["social_category"] = categories
            break

    if "disability" in lowered or "differently abled" in lowered:
        percent = parse_disability(row.get("eligibility", ""))
        if percent:
            rules["disability_percent_min"] = percent

    required = []
    for words, flag in FLAG_PATTERNS:
        if any(w in lowered for w in words):
            required.append(flag)
    if required:
        rules["flags_required"] = sorted(set(required))

    excluded = []
    for words, flag in EXCLUSION_PATTERNS:
        if any(w in lowered for w in words):
            excluded.append(flag)
    if excluded:
        rules["flags_excluded"] = sorted(set(excluded))

    return rules


def map_categories(raw: str) -> list[str]:
    key = (raw or "").strip().lower()
    if key in CATEGORY_MAP:
        return CATEGORY_MAP[key]
    for label, mapped in sorted(CATEGORY_MAP.items(), key=lambda kv: -len(kv[0])):
        if label in key:
            return mapped
    return ["social"]


def split_documents(raw: str) -> list[str]:
    parts = re.split(r"[;,]", raw or "")
    return [p.strip() for p in parts if p.strip()]


def richness(row: dict) -> int:
    """How much information a row carries - used to pick a winner among duplicates."""
    return sum(len(row.get(field, "") or "") for field in
               ("eligibility", "description", "required_documents", "benefit_type", "official_source"))


def merge_rows(rows: list[dict]) -> dict:
    """Keep the richest row, but backfill any field it left blank from its siblings."""
    ordered = sorted(rows, key=richness, reverse=True)
    winner = dict(ordered[0])
    for other in ordered[1:]:
        for key, value in other.items():
            if not (winner.get(key) or "").strip() and (value or "").strip():
                winner[key] = value
    return winner


def deduplicate(rows: list[dict]) -> tuple[list[dict], list[str]]:
    """Collapse rows describing the same scheme, regardless of what their ids say."""
    notes: list[str] = []
    buckets: list[dict] = []  # {"key": str, "rows": [...]}

    for row in rows:
        key = normalise_name(row["scheme_name"])
        placed = False
        for bucket in buckets:
            if names_match(bucket["key"], key):
                bucket["rows"].append(row)
                placed = True
                break
        if not placed:
            buckets.append({"key": key, "rows": [row]})

    merged = []
    for bucket in buckets:
        if len(bucket["rows"]) > 1:
            names = " | ".join(sorted({r["scheme_name"] for r in bucket["rows"]}))
            notes.append(f"merged {len(bucket['rows'])} rows -> {names}")
        merged.append(merge_rows(bucket["rows"]))

    # Reassign ids so collisions between genuinely different schemes disappear.
    seen: dict[str, int] = {}
    for row in merged:
        base = row["scheme_id"].strip() or "TN-GEN"
        if base in seen:
            seen[base] += 1
            new_id = f"{base}-{seen[base]}"
            notes.append(f"id collision: {base} reused by '{row['scheme_name']}' -> {new_id}")
            row["scheme_id"] = new_id
        else:
            seen[base] = 0

    return merged, notes


def priority_for(row: dict, rules: dict) -> int:
    """Rank broad, high-value schemes above narrow ones as a starting point."""
    score = 78
    categories = map_categories(row.get("category", ""))
    if "health" in categories:
        score += 8
    if "social" in categories or "housing" in categories:
        score += 5
    if "education" in categories:
        score += 4
    # Universal schemes matter to more people.
    if len(rules) <= 2:
        score += 4
    # Very narrow schemes should not crowd the top of the list.
    if rules.get("disability_percent_min", 0) >= 75:
        score -= 6
    if "is_orphan" in rules.get("flags_required", []):
        score -= 4
    return max(60, min(96, score))


def build_keywords(row: dict, categories: list[str]) -> list[str]:
    text = " ".join([row.get("scheme_name", ""), row.get("description", ""),
                     row.get("beneficiary", ""), row.get("category", "")]).lower()
    words = re.findall(r"[a-z]{4,}", text)
    stop = {
        "scheme", "schemes", "tamil", "nadu", "government", "govt", "assistance",
        "thittam", "chief", "minister", "ministers", "with", "from", "that", "this",
        "under", "through", "which", "their", "them", "have", "been", "will", "must",
        "ninaivu", "ammaiyar", "programme", "program", "welfare", "financial",
    }
    seen: list[str] = []
    for word in words:
        if word not in stop and word not in seen:
            seen.append(word)
    return (seen[:18] + categories)


def convert(row: dict, translations: dict) -> dict:
    scheme_id = row["scheme_id"].strip()
    categories = map_categories(row.get("category", ""))
    rules = parse_eligibility(row)
    tamil = translations.get(scheme_id, {})

    name_en = row["scheme_name"].strip()
    description_en = (row.get("description") or "").strip() or name_en
    benefit_en = (row.get("benefit_type") or "").strip() or "See scheme details"
    department_en = (row.get("department") or "Government of Tamil Nadu").strip()

    documents_en = split_documents(row.get("required_documents", "")) or ["Aadhaar card"]
    documents_ta = tamil.get("documents") or []

    return {
        "id": scheme_id,
        "level": "state",
        "source_id": row["scheme_id"].strip(),
        "name": {"en": name_en, "ta": tamil.get("name") or name_en},
        "department": {"en": department_en, "ta": tamil.get("department") or department_en},
        "categories": categories,
        "raw_category": (row.get("category") or "").strip(),
        "beneficiary": (row.get("beneficiary") or "").strip(),
        "summary": {"en": description_en, "ta": tamil.get("summary") or description_en},
        "benefit": {"en": benefit_en, "ta": tamil.get("benefit") or benefit_en},
        "eligibility_text": {
            "en": (row.get("eligibility") or "").strip(),
            "ta": tamil.get("eligibility_text") or (row.get("eligibility") or "").strip(),
        },
        "eligibility": rules,
        "documents": [
            {"en": doc, "ta": documents_ta[i] if i < len(documents_ta) else doc}
            for i, doc in enumerate(documents_en)
        ],
        "apply": {
            "mode": (row.get("application_mode") or "Offline").strip(),
            "url": (row.get("application_link") or row.get("official_website") or "").strip(),
            "office": {
                "en": (row.get("application_mode") or "Contact your Taluk office").strip(),
                "ta": tamil.get("office") or (row.get("application_mode") or "").strip(),
            },
        },
        "official_website": (row.get("official_website") or "").strip(),
        "official_source": (row.get("official_source") or "").strip(),
        "status": (row.get("status") or "Active").strip(),
        "last_verified": (row.get("last_verified") or "").strip(),
        "keywords": build_keywords(row, categories),
        "priority": priority_for(row, rules),
        "translated": bool(tamil),
    }


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    source = Path(sys.argv[1])
    if not source.exists():
        print(f"CSV not found: {source}")
        return 1

    with source.open(encoding="utf-8-sig", newline="") as handle:
        rows = [r for r in csv.DictReader(handle) if (r.get("scheme_name") or "").strip()]

    translations_path = DATA / "translations_ta.json"
    translations = {}
    if translations_path.exists():
        translations = json.loads(translations_path.read_text(encoding="utf-8"))

    merged, notes = deduplicate(rows)
    schemes = [convert(row, translations) for row in merged]
    schemes.sort(key=lambda s: -s["priority"])

    output = DATA / "schemes_master.json"
    output.write_text(json.dumps(schemes, ensure_ascii=False, indent=2), encoding="utf-8")

    translated = sum(1 for s in schemes if s["translated"])
    with_age = sum(1 for s in schemes if "age" in s["eligibility"])
    with_income = sum(1 for s in schemes if "annual_income_max" in s["eligibility"])
    with_gender = sum(1 for s in schemes if "gender" in s["eligibility"])
    with_flags = sum(1 for s in schemes if s["eligibility"].get("flags_required"))

    print(f"read      {len(rows)} CSV rows")
    print(f"merged    {len(rows) - len(merged)} duplicate rows away")
    print(f"wrote     {len(schemes)} schemes -> {output}")
    print(f"rules     age={with_age}  income={with_income}  gender={with_gender}  flags={with_flags}")
    print(f"tamil     {translated}/{len(schemes)} translated")
    if notes:
        print("\nduplicate / id resolution log:")
        for note in notes:
            print(f"  - {note}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
