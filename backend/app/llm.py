"""Optional LLM layer.

NALAM never depends on an LLM to decide eligibility - that stays in rules.py so
results are deterministic, explainable and auditable. The model is only used to
phrase replies more naturally in the chat panel. If no provider is reachable,
the scripted rules-based reply is used and the app behaves identically.

Two providers are supported:

    ollama      - a local server. Free, offline, private, no key, no rate limit.
    openrouter  - a hosted router with free models. Needs an API key and
                  internet, and sends the conversation to a third party.

`auto` prefers Ollama when it is running, because keeping a citizen's situation
on their own machine is the better default for a welfare app.

Note that OpenRouter cannot replace Whisper: it serves chat completions, not
speech to text. Voice input stays local either way.
"""

from __future__ import annotations

import os

import requests

PROVIDER = os.environ.get("NALAM_LLM_PROVIDER", "auto").lower()

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("NALAM_OLLAMA_MODEL", "qwen2.5:7b-instruct")

OPENROUTER_URL = "https://openrouter.ai/api/v1"
# Free models come and go, and their exact slugs change. Override with
# NALAM_OPENROUTER_MODEL; browse current free options at
# https://openrouter.ai/models?q=free (they carry a ":free" suffix).
OPENROUTER_MODEL = os.environ.get(
    "NALAM_OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free"
)

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


def _api_key() -> str:
    """Read the OpenRouter key from the environment.

    Deliberately only ever read from the environment, never from a file in the
    repo, so a key cannot be committed by accident. The value is never logged
    or returned by any status endpoint.
    """
    return os.environ.get("OPENROUTER_API_KEY", "").strip()


# --------------------------------------------------------------------- ollama
def _ollama_models() -> list[str]:
    try:
        response = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=2)
        response.raise_for_status()
        return [m["name"] for m in response.json().get("models", [])]
    except Exception:
        return []


def _ollama_pick_model() -> str | None:
    models = _ollama_models()
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


def _ollama_generate(messages: list[dict]) -> str | None:
    model = _ollama_pick_model()
    if not model:
        return None
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
        return response.json().get("message", {}).get("content", "").strip() or None
    except Exception:
        return None


# ----------------------------------------------------------------- openrouter
def _openrouter_generate(messages: list[dict]) -> str | None:
    key = _api_key()
    if not key:
        return None
    try:
        response = requests.post(
            f"{OPENROUTER_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                # OpenRouter uses these for its public leaderboard; harmless.
                "HTTP-Referer": "http://localhost:5173",
                "X-Title": "NALAM Scheme Navigator",
            },
            json={
                "model": OPENROUTER_MODEL,
                "messages": messages,
                "temperature": 0.3,
                "max_tokens": 300,
            },
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        choices = response.json().get("choices") or []
        if not choices:
            return None
        return (choices[0].get("message", {}).get("content") or "").strip() or None
    except Exception:
        return None


# -------------------------------------------------------------------- routing
def active_provider() -> str | None:
    """Which provider would handle a request right now, if any."""
    if PROVIDER == "none":
        return None
    if PROVIDER == "ollama":
        return "ollama" if _ollama_pick_model() else None
    if PROVIDER == "openrouter":
        return "openrouter" if _api_key() else None

    # auto: local first, hosted as fallback.
    if _ollama_pick_model():
        return "ollama"
    if _api_key():
        return "openrouter"
    return None


def is_available() -> bool:
    return active_provider() is not None


def generate(user_message: str, context: str, history: list[dict] | None = None) -> str | None:
    """Ask the configured provider for a reply. Returns None if anything fails.

    A None return is normal, not exceptional - the caller falls back to the
    scripted rules-based reply, so the app works without any LLM at all.
    """
    provider = active_provider()
    if not provider:
        return None

    messages = [{"role": "system", "content": f"{SYSTEM_PROMPT}\n\nCONTEXT:\n{context}"}]
    for turn in (history or [])[-6:]:
        messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": user_message})

    if provider == "ollama":
        return _ollama_generate(messages)
    if provider == "openrouter":
        return _openrouter_generate(messages)
    return None


def status() -> dict:
    provider = active_provider()
    ollama_models = _ollama_models()
    return {
        "available": provider is not None,
        "provider": provider,
        "configured_provider": PROVIDER,
        "active_model": (
            _ollama_pick_model()
            if provider == "ollama"
            else OPENROUTER_MODEL
            if provider == "openrouter"
            else None
        ),
        "ollama": {
            "host": OLLAMA_HOST,
            "reachable": bool(ollama_models),
            "installed_models": ollama_models,
        },
        # Only ever whether a key exists - never the key itself.
        "openrouter": {
            "api_key_present": bool(_api_key()),
            "model": OPENROUTER_MODEL,
        },
    }
