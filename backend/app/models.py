"""Request and response shapes for the NALAM API."""

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

Language = Literal["en", "ta"]
CheckStatus = Literal["pass", "fail", "unknown"]
MatchStatus = Literal["eligible", "likely", "not_eligible"]


class Profile(BaseModel):
    """Everything the citizen tells us about their situation."""

    name: str = ""
    district: str = ""
    age: Optional[int] = None
    gender: Optional[Literal["male", "female", "other"]] = None
    marital_status: Optional[
        Literal["single", "married", "widowed", "separated"]
    ] = None
    annual_income: Optional[int] = None
    family_size: Optional[int] = None
    occupation: Optional[str] = None
    social_category: Optional[Literal["SC", "ST", "BC", "MBC", "DNC", "OC"]] = None
    disability_percent: Optional[int] = None
    # Free-form situation flags the user ticked, e.g. "is_widow", "is_rural".
    flags: list[str] = Field(default_factory=list)
    # What they typed or said in their own words.
    issue_text: str = ""
    language: Language = "en"

    @field_validator(
        "age", "annual_income", "family_size", "disability_percent",
        "gender", "marital_status", "occupation", "social_category",
        mode="before",
    )
    @classmethod
    def blank_to_none(cls, value):
        """Treat an empty or whitespace-only field as "not answered".

        HTML inputs submit "" for untouched fields, and an unanswered question
        means unknown - not invalid. Coercing here keeps every client honest
        without each one having to strip blanks itself.
        """
        if isinstance(value, str) and not value.strip():
            return None
        return value


class RuleCheck(BaseModel):
    """One eligibility condition, and how the profile fared against it."""

    rule: str
    label: str
    status: CheckStatus
    detail: str


class SchemeMatch(BaseModel):
    id: str
    name: str
    department: str
    level: str
    categories: list[str]
    summary: str
    benefit: str
    documents: list[str]
    apply_mode: str
    apply_url: str
    apply_office: str
    score: int
    status: MatchStatus
    checks: list[RuleCheck]
    passed_count: int
    failed_count: int
    unknown_count: int


class MatchResponse(BaseModel):
    profile_name: str
    language: Language
    total_evaluated: int
    eligible: list[SchemeMatch]
    likely: list[SchemeMatch]
    not_eligible: list[SchemeMatch]
    summary_text: str
    ai_note: Optional[str] = None


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatTurn] = Field(default_factory=list)
    profile: Profile = Field(default_factory=Profile)
    language: Language = "en"


class ChatResponse(BaseModel):
    reply: str
    profile: Profile
    # Fields NALAM still needs before it can match confidently.
    missing_fields: list[str] = Field(default_factory=list)
    ready_to_match: bool = False
    suggestions: list[str] = Field(default_factory=list)
    source: Literal["rules", "ollama"] = "rules"


class TranscriptionResponse(BaseModel):
    text: str
    detected_language: str
    duration_seconds: float
    model: str


class OcrField(BaseModel):
    field: str
    value: str
    confidence: float


class OcrResponse(BaseModel):
    raw_text: str
    fields: list[OcrField]
    detected_document: str
    engine: str
