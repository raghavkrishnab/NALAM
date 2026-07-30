"""Optional LLM layer.

NALAM never depends on an LLM to decide eligibility - that stays in rules.py so
results are deterministic, explainable and auditable. The model is only used to
phrase replies more naturally in the chat panel.

Today this talks to a local Ollama server. Swapping in another provider means
implementing `generate()` and nothing else.
"""

from __future__ import annotations

import os

import requests

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("NALAM_OLLAMA_MODEL", "qwen2.5:7b-instruct")
REQUEST_TIMEOUT = float(os.environ.get("NALAM_LLM_TIMEOUT", "20"))

SYSTEM_PROMPT = """You are NALAM, a warm and practical assistant that helps Tamil Nadu \
residents find government welfare schemes.

Hard rules you must never break:
- Only discuss schemes that appear in the CONTEXT block given to you. Never invent \
a scheme name, benefit amount, eligibility rule, website or office address.
- Never state that someone is eligible or ineligible. The rules engine decides that. \
You only explain and encourage.
- If the context does not answer the question, say so plainly and suggest what \
detail the person could provide.
- Reply in the same language the user wrote in. If they wrote Tamil, reply in Tamil.
- Keep replies under 90 words. Be concrete. No bullet-point walls, no jargon.
"""


def is_available() -> bool:
    """True when an Ollama server is reachable and has at least one model pulled."""
    try:
        response = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=2)
        response.raise_for_status()
        return bool(response.json().get("models"))
    except Exception:
        return False


def available_models() -> list[str]:
    try:
        response = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=2)
        response.raise_for_status()
        return [m["name"] for m in response.json().get("models", [])]
    except Exception:
        return []


def _pick_model() -> str | None:
    models = available_models()
    if not models:
        return None
    if OLLAMA_MODEL in models:
        return OLLAMA_MODEL
    # Tolerate tag drift: "qwen2.5:7b-instruct" configured, "qwen2.5:7b" pulled.
    stem = OLLAMA_MODEL.split(":")[0]
    for name in models:
        if name.startswith(stem):
            return name
    return models[0]


def generate(user_message: str, context: str, history: list[dict] | None = None) -> str | None:
    """Ask the local model for a reply. Returns None if anything goes wrong.

    A None return is normal, not exceptional - the caller falls back to the
    scripted rules-based reply, so the app works identically without Ollama.
    """
    model = _pick_model()
    if not model:
        return None

    messages = [{"role": "system", "content": f"{SYSTEM_PROMPT}\n\nCONTEXT:\n{context}"}]
    for turn in (history or [])[-6:]:
        messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": user_message})

    try:
        response = requests.post(
            f"{OLLAMA_HOST}/api/chat",
            json={
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": 0.3, "num_predict": 220},
            },
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        reply = response.json().get("message", {}).get("content", "").strip()
        return reply or None
    except Exception:
        return None


def status() -> dict:
    models = available_models()
    return {
        "available": bool(models),
        "host": OLLAMA_HOST,
        "configured_model": OLLAMA_MODEL,
        "active_model": _pick_model(),
        "installed_models": models,
    }
