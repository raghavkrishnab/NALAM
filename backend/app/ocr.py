"""Tamil and English document OCR for form auto-fill.

Reads an uploaded Aadhaar card, income certificate, ration card or disability
certificate and pulls out the handful of fields the eligibility engine cares
about: name, age or date of birth, income, district, and disability percentage.

EasyOCR is the primary engine because it genuinely supports Tamil script.
Tesseract is accepted as a lighter fallback if it happens to be installed.
Neither being present is fine - the endpoint just reports itself unavailable.
"""

from __future__ import annotations

import re
import threading

_reader = None
_reader_lock = threading.Lock()
_load_error: str | None = None
# Which language set the EasyOCR reader actually managed to load, and whether
# that set includes Tamil. Reported through /api/health so the UI can tell the
# truth instead of implying Tamil OCR works when it does not.
_reader_languages: list[str] = []

# Tried best-first. EasyOCR 1.7.2 ships a Tamil recognition checkpoint whose
# output layer (143 classes) does not match the model it builds (127 classes),
# so both Tamil configurations currently raise on load and we end up on English.
# The chain means a future easyocr release that fixes this starts working with
# no code change, and Tamil documents still go to Tesseract when it is present.
LANGUAGE_CHAIN = [["ta", "en"], ["ta"], ["en"]]

DOCUMENT_SIGNATURES = {
    "aadhaar": ["aadhaar", "aadhar", "unique identification", "uidai", "ஆதார்"],
    "income_certificate": ["income certificate", "annual income", "வருமானச் சான்று", "வருமான"],
    "ration_card": ["ration", "family card", "fair price", "ரேஷன்", "குடும்ப அட்டை"],
    "disability_certificate": ["disability", "udid", "differently abled", "மாற்றுத்திறன், ஊனம்"],
    "community_certificate": ["community certificate", "caste certificate", "சாதிச் சான்று", "இனச் சான்று"],
    "land_record": ["chitta", "adangal", "patta", "survey number", "சிட்டா", "அடங்கல்", "பட்டா"],
}

TN_DISTRICTS = [
    "Ariyalur", "Chengalpattu", "Chennai", "Coimbatore", "Cuddalore", "Dharmapuri",
    "Dindigul", "Erode", "Kallakurichi", "Kanchipuram", "Kanyakumari", "Karur",
    "Krishnagiri", "Madurai", "Mayiladuthurai", "Nagapattinam", "Namakkal",
    "Nilgiris", "Perambalur", "Pudukkottai", "Ramanathapuram", "Ranipet", "Salem",
    "Sivaganga", "Tenkasi", "Thanjavur", "Theni", "Thoothukudi", "Tiruchirappalli",
    "Tirunelveli", "Tirupathur", "Tiruppur", "Tiruvallur", "Tiruvannamalai",
    "Tiruvarur", "Vellore", "Viluppuram", "Virudhunagar",
]


def is_installed() -> bool:
    try:
        import easyocr  # noqa: F401

        return True
    except ImportError:
        pass
    try:
        import pytesseract  # noqa: F401

        return True
    except ImportError:
        return False


def _tesseract_ready() -> bool:
    """True when pytesseract is importable AND the Tesseract binary has Tamil."""
    try:
        import pytesseract
    except ImportError:
        return False
    try:
        return "tam" in set(pytesseract.get_languages(config=""))
    except Exception:
        return False


def _engine_name() -> str:
    """Pick an engine, preferring whichever can actually read Tamil.

    Tesseract wins when it has the Tamil traineddata, because EasyOCR's Tamil
    model is currently unloadable and would silently give us English-only OCR.
    """
    if _tesseract_ready():
        return "tesseract"
    try:
        import easyocr  # noqa: F401

        return "easyocr"
    except ImportError:
        pass
    try:
        import pytesseract  # noqa: F401

        return "tesseract"
    except ImportError:
        return "none"


def get_reader():
    """Build the EasyOCR reader once, walking down the language chain.

    Models download on first call. GPU is attempted first and CPU is always kept
    as a fallback, since GPU init fails on plenty of driver combinations.
    """
    global _reader, _load_error, _reader_languages

    if _reader is not None:
        return _reader
    if _load_error is not None:
        raise RuntimeError(_load_error)

    with _reader_lock:
        if _reader is not None:
            return _reader

        import easyocr

        failures = []
        for languages in LANGUAGE_CHAIN:
            for use_gpu in (True, False):
                try:
                    _reader = easyocr.Reader(languages, gpu=use_gpu, verbose=False)
                    _reader_languages = languages
                    return _reader
                except Exception as exc:
                    failures.append(f"{languages} gpu={use_gpu}: {str(exc)[:90]}")

        _load_error = "Could not initialise EasyOCR. Tried " + " | ".join(failures)
        raise RuntimeError(_load_error)


def _read_with_tesseract(image_bytes: bytes) -> str:
    import io

    import pytesseract
    from PIL import Image

    image = Image.open(io.BytesIO(image_bytes))
    return pytesseract.image_to_string(image, lang="tam+eng")


def extract_text(image_bytes: bytes) -> tuple[str, str]:
    engine = _engine_name()
    if engine == "easyocr":
        reader = get_reader()
        lines = reader.readtext(image_bytes, detail=0, paragraph=True)
        return "\n".join(lines), f"easyocr:{'+'.join(_reader_languages)}"
    if engine == "tesseract":
        return _read_with_tesseract(image_bytes), "tesseract:tam+eng"
    raise RuntimeError("No OCR engine installed. Run: pip install -r requirements-ai.txt")


def detect_document_type(text: str) -> str:
    lowered = text.lower()
    for doc_type, markers in DOCUMENT_SIGNATURES.items():
        if any(marker in lowered for marker in markers):
            return doc_type
    return "unknown"


# A label and its value often land on separate lines, because OCR engines
# reflow a two-column certificate layout into reading order. Any extractor that
# insists on "Label: value" on one line will miss most real documents.
FIELD_LABELS = {
    "name": ["name", "பெயர்"],
    "age": ["age", "வயது"],
    "annual_income": ["annual income", "yearly income", "income", "வருமானம்"],
    "district": ["district", "மாவட்டம்"],
    "disability_percent": ["disability", "ஊனம்"],
}

# Lines carrying these words describe somebody else, so the value beside them is
# not the applicant's name.
OTHER_PERSON = re.compile(r"father|husband|mother|guardian|spouse|தந்தை|கணவர்|தாய்", re.IGNORECASE)


def _lines(text: str) -> list[str]:
    return [line.strip().strip(":-").strip() for line in text.splitlines() if line.strip()]


def _label_values(text: str, labels: list[str], skip_other_person: bool = False) -> list[str]:
    """Collect candidate values for a label, from same-line and next-line layouts."""
    lines = _lines(text)
    values: list[str] = []

    for index, line in enumerate(lines):
        lowered = line.lower()
        for label in labels:
            if label not in lowered:
                continue
            if skip_other_person and OTHER_PERSON.search(line):
                continue

            # "Income : Rs 48000" - value follows the label on the same line.
            after = re.split(re.escape(label), lowered, maxsplit=1, flags=re.IGNORECASE)[-1]
            tail = line[len(line) - len(after):].strip(" :-\t")
            if tail and not any(other in tail.lower() for other in labels):
                values.append(tail)

            # "Income" then the value on the following line.
            if index + 1 < len(lines):
                nxt = lines[index + 1]
                if not any(
                    other_label in nxt.lower()
                    for group in FIELD_LABELS.values()
                    for other_label in group
                ):
                    values.append(nxt)
            break

    return [v for v in values if v]


def _extract_name(text: str) -> tuple[str, float] | None:
    for candidate in _label_values(text, FIELD_LABELS["name"], skip_other_person=True):
        cleaned = re.sub(r"[^A-Za-z஀-௿. ]", " ", candidate).strip(" .")
        cleaned = re.sub(r"\s{2,}", " ", cleaned)
        # A name should be words, not a stray number or a one-letter fragment.
        if len(cleaned) >= 3 and not cleaned.isdigit() and len(cleaned.split()) <= 5:
            return cleaned, 0.75

    honorific = re.search(
        r"(?:thiru|tmt|selvi|mr|mrs|ms)\.?\s+([A-Za-z஀-௿][A-Za-z஀-௿ .]{2,40})",
        text,
        re.IGNORECASE,
    )
    if honorific:
        name = honorific.group(1).strip(" .")
        if len(name) >= 3:
            return name, 0.7
    return None


def _extract_age(text: str) -> tuple[str, float] | None:
    found = re.search(r"(?:age|வயது)\s*[:\-]?\s*(\d{1,3})", text, re.IGNORECASE)
    if found and 1 <= int(found.group(1)) <= 120:
        return found.group(1), 0.85

    for candidate in _label_values(text, FIELD_LABELS["age"]):
        digits = re.search(r"\b(\d{1,3})\b", candidate)
        if digits and 1 <= int(digits.group(1)) <= 120:
            return digits.group(1), 0.7

    # Derive age from a date of birth if one is printed.
    dob = re.search(r"(?:dob|date of birth|பிறந்த\s*தேதி)\s*[:\-]?\s*(\d{2})[/\-.](\d{2})[/\-.](\d{4})", text, re.IGNORECASE)
    if not dob:
        dob = re.search(r"\b(\d{2})[/\-.](\d{2})[/\-.](19|20)(\d{2})\b", text)
        if dob:
            from datetime import date

            year = int(dob.group(3) + dob.group(4))
            age = date.today().year - year
            if 0 < age < 120:
                return str(age), 0.6
            return None
    if dob:
        from datetime import date

        age = date.today().year - int(dob.group(3))
        if 0 < age < 120:
            return str(age), 0.75
    return None


def _extract_income(text: str) -> tuple[str, float] | None:
    patterns = [
        r"(?:annual income|yearly income|income|வருமானம்)\s*(?:is|:|\-)?\s*(?:rs\.?|₹|ரூ\.?)?\s*([\d,]{4,10})",
        r"(?:rs\.?|₹|ரூ\.?)\s*([\d,]{4,10})\s*(?:per annum|annually|/year|ஆண்டுக்கு)",
    ]
    for pattern in patterns:
        found = re.search(pattern, text, re.IGNORECASE)
        if found:
            amount = found.group(1).replace(",", "")
            if amount.isdigit() and 1000 <= int(amount) <= 100000000:
                return amount, 0.8

    for candidate in _label_values(text, FIELD_LABELS["annual_income"]):
        digits = re.search(r"([\d,]{4,10})", candidate)
        if digits:
            amount = digits.group(1).replace(",", "")
            if amount.isdigit() and 1000 <= int(amount) <= 100000000:
                return amount, 0.65
    return None


def _extract_district(text: str) -> tuple[str, float] | None:
    for district in TN_DISTRICTS:
        if re.search(rf"\b{re.escape(district)}\b", text, re.IGNORECASE):
            return district, 0.7
    return None


def _extract_disability(text: str) -> tuple[str, float] | None:
    found = re.search(r"(\d{1,3})\s*(?:%|percent|சதவீதம்)", text)
    if found and 1 <= int(found.group(1)) <= 100:
        return found.group(1), 0.75
    return None


def extract_fields(text: str) -> list[dict]:
    """Pull the fields the eligibility engine can actually use out of raw OCR text."""
    extractors = {
        "name": _extract_name,
        "age": _extract_age,
        "annual_income": _extract_income,
        "district": _extract_district,
        "disability_percent": _extract_disability,
    }

    fields = []
    for field, extractor in extractors.items():
        result = extractor(text)
        if result:
            value, confidence = result
            fields.append({"field": field, "value": value, "confidence": confidence})
    return fields


def process_image(image_bytes: bytes) -> dict:
    text, engine = extract_text(image_bytes)
    return {
        "raw_text": text,
        "fields": extract_fields(text),
        "detected_document": detect_document_type(text),
        "engine": engine,
    }


def status() -> dict:
    engine = _engine_name()
    if engine == "tesseract":
        tamil = _tesseract_ready()
    elif _reader_languages:
        tamil = "ta" in _reader_languages
    else:
        # Not loaded yet - report the optimistic case, corrected after first use.
        tamil = engine == "easyocr"

    return {
        "installed": is_installed(),
        "engine": engine,
        "loaded": _reader is not None,
        "languages": _reader_languages or None,
        "tamil_supported": tamil,
        "tamil_note": (
            None
            if tamil
            else "EasyOCR's Tamil model fails to load in easyocr 1.7.2. "
            "Install Tesseract with the 'tam' language pack for Tamil document OCR."
        ),
        "error": _load_error,
    }
