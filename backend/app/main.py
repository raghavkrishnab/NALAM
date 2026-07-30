"""NALAM API - Tamil Nadu government scheme navigator."""

from __future__ import annotations

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from . import chat as chat_module
from . import llm, ocr, transcribe
from .models import (
    ChatRequest,
    ChatResponse,
    MatchResponse,
    OcrResponse,
    Profile,
    TranscriptionResponse,
)
from .rules import FLAG_LABELS, OCCUPATION_LABELS, SOCIAL_LABELS, match_profile
from .schemes import all_categories, load_schemes, localise

MAX_AUDIO_BYTES = 25 * 1024 * 1024
MAX_IMAGE_BYTES = 15 * 1024 * 1024

app = FastAPI(
    title="NALAM API",
    description="Government scheme navigator for Tamil Nadu - bilingual, explainable, offline-capable.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    """Capability report. The UI uses this to show which AI features are live."""
    return {
        "status": "ok",
        "schemes_loaded": len(load_schemes()),
        "capabilities": {
            "rules_engine": {"available": True, "note": "Always on - deterministic eligibility"},
            "voice_transcription": transcribe.status(),
            "document_ocr": ocr.status(),
            "llm": llm.status(),
        },
    }


@app.get("/api/schemes")
def list_schemes(language: str = "en", category: str | None = None) -> dict:
    schemes = load_schemes()
    if category:
        schemes = [s for s in schemes if category in s.get("categories", [])]

    return {
        "count": len(schemes),
        "categories": all_categories(),
        "schemes": [
            {
                "id": s["id"],
                "name": localise(s["name"], language),
                "department": localise(s["department"], language),
                "level": s["level"],
                "categories": s.get("categories", []),
                "summary": localise(s["summary"], language),
                "benefit": localise(s["benefit"], language),
                "apply_url": s["apply"]["url"],
            }
            for s in schemes
        ],
    }


@app.get("/api/options")
def form_options(language: str = "en") -> dict:
    """Localised dropdown and checkbox options, so the UI never hardcodes them."""

    def pack(table: dict) -> list[dict]:
        return [
            {"value": key, "label": entry.get(language) or entry["en"]}
            for key, entry in table.items()
        ]

    return {
        "occupations": pack(OCCUPATION_LABELS),
        "social_categories": pack(SOCIAL_LABELS),
        "situation_flags": pack(
            {k: v for k, v in FLAG_LABELS.items() if k not in {"owns_pucca_house"}}
        ),
        "categories": all_categories(),
    }


@app.post("/api/match", response_model=MatchResponse)
def match(profile: Profile) -> MatchResponse:
    language = profile.language or "en"
    result = match_profile(profile, language)

    ai_note = None
    if llm.is_available():
        ai_note = (
            f"Local model {llm.status()['active_model']} is connected and assisting the chat."
            if language == "en"
            else f"உள்ளூர் மாதிரி {llm.status()['active_model']} இணைக்கப்பட்டு உரையாடலுக்கு உதவுகிறது."
        )

    return MatchResponse(
        profile_name=result["profile_name"],
        language=language,
        total_evaluated=result["total_evaluated"],
        eligible=result["eligible"],
        likely=result["likely"],
        not_eligible=result["not_eligible"],
        summary_text=result["summary_text"],
        ai_note=ai_note,
    )


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    return chat_module.handle_chat(request)


@app.get("/api/chat/starters")
def chat_starters(language: str = "en") -> dict:
    lang = language if language in ("en", "ta") else "en"
    return {
        "greeting": chat_module.GREETING[lang],
        "suggestions": chat_module.STARTER_SUGGESTIONS[lang],
    }


@app.post("/api/transcribe", response_model=TranscriptionResponse)
async def transcribe_audio(
    audio: UploadFile = File(...),
    language: str | None = Form(None),
) -> TranscriptionResponse:
    if not transcribe.is_installed():
        raise HTTPException(
            status_code=503,
            detail="Voice transcription is not installed. Run: pip install -r requirements-ai.txt",
        )

    payload = await audio.read()
    if not payload:
        raise HTTPException(status_code=400, detail="Empty audio upload")
    if len(payload) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio file too large (max 25 MB)")

    # "auto" means let Whisper detect - best for Tamil-English code-mixing.
    whisper_language = None if language in (None, "", "auto") else language

    try:
        result = transcribe.transcribe_bytes(
            payload, filename=audio.filename or "audio.webm", language=whisper_language
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return TranscriptionResponse(**result)


@app.post("/api/ocr", response_model=OcrResponse)
async def ocr_document(document: UploadFile = File(...)) -> OcrResponse:
    if not ocr.is_installed():
        raise HTTPException(
            status_code=503,
            detail="Document OCR is not installed. Run: pip install -r requirements-ai.txt",
        )

    payload = await document.read()
    if not payload:
        raise HTTPException(status_code=400, detail="Empty document upload")
    if len(payload) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Document too large (max 15 MB)")

    try:
        result = ocr.process_image(payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return OcrResponse(**result)
