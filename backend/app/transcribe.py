"""Tamil and English speech to text with faster-whisper.

The model is loaded lazily on first use and then held in memory, so the first
transcription pays the load cost and every later one is fast. If faster-whisper
is not installed the endpoint reports itself unavailable instead of crashing -
the rest of NALAM keeps working.
"""

from __future__ import annotations

import os
import tempfile
import threading
import time

MODEL_SIZE = os.environ.get("NALAM_WHISPER_MODEL", "small")
# int8 keeps a 6 GB laptop GPU comfortable and is plenty accurate for speech.
COMPUTE_TYPE = os.environ.get("NALAM_WHISPER_COMPUTE", "int8")
DEVICE = os.environ.get("NALAM_WHISPER_DEVICE", "auto")

_model = None
_model_lock = threading.Lock()
_load_error: str | None = None
# Set once the model is loaded, so /api/health reports what is actually running
# rather than what we hoped to run.
_active_device: str | None = None


def is_installed() -> bool:
    try:
        import faster_whisper  # noqa: F401

        return True
    except ImportError:
        return False


def _candidate_devices() -> list[str]:
    """Devices to try, best first.

    A CUDA device being *present* does not mean it is *usable*: ctranslate2
    reports a device count from the driver, but actually loading a model also
    needs the CUDA runtime DLLs (cuBLAS, cuDNN) on the path. A machine with an
    NVIDIA GPU but no CUDA toolkit installed will happily report a device and
    then fail with "cublas64_12.dll is not found". So CUDA is only ever a
    preference, with CPU always kept as a fallback.
    """
    if DEVICE != "auto":
        return [DEVICE]

    devices = []
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() > 0:
            devices.append("cuda")
    except Exception:
        pass
    devices.append("cpu")
    return devices


def _resolve_device() -> str:
    """Best guess for reporting before the model has actually been loaded."""
    return _active_device or _candidate_devices()[0]


def _verify_device(model) -> None:
    """Run one tiny inference to prove the device really works.

    Constructing a WhisperModel on CUDA succeeds even when the CUDA runtime
    libraries are missing - ctranslate2 loads cuBLAS lazily on the first encode.
    On top of that, `model.transcribe()` returns a *generator*, so a failure
    inside it does not surface until the segments are consumed. Both together
    mean a broken GPU setup looks perfectly healthy until a real user speaks.

    So: transcribe a fraction of a second of silence and drain the generator.
    Any device problem raises here, while we can still fall back to CPU.
    """
    import numpy as np

    silence = np.zeros(4000, dtype=np.float32)  # 0.25s at 16 kHz
    segments, _ = model.transcribe(silence, language="en", beam_size=1, vad_filter=False)
    for _ in segments:
        pass


def get_model():
    """Load the Whisper model once, behind a lock so concurrent requests share it."""
    global _model, _load_error, _active_device

    if _model is not None:
        return _model
    if _load_error is not None:
        raise RuntimeError(_load_error)

    with _model_lock:
        if _model is not None:
            return _model

        from faster_whisper import WhisperModel

        failures = []
        for device in _candidate_devices():
            compute = COMPUTE_TYPE
            if device == "cuda" and compute == "int8":
                compute = "float16"
            try:
                candidate = WhisperModel(MODEL_SIZE, device=device, compute_type=compute)
                _verify_device(candidate)
                _model = candidate
                _active_device = device
                return _model
            except Exception as exc:
                failures.append(f"{device}: {exc}")

        _load_error = (
            f"Could not load Whisper model '{MODEL_SIZE}'. Tried " + "; ".join(failures)
        )
        raise RuntimeError(_load_error)


def transcribe_bytes(audio: bytes, filename: str = "audio.webm", language: str | None = None) -> dict:
    """Transcribe an uploaded audio blob.

    `language` may be "ta", "en", or None to let Whisper auto-detect - which is
    what we want for Tamil-English code-mixed speech, very common in TN.
    """
    model = get_model()

    suffix = os.path.splitext(filename)[1] or ".webm"
    handle, path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(handle, "wb") as file:
            file.write(audio)

        started = time.time()
        segments, info = model.transcribe(
            path,
            language=language,
            beam_size=5,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
        )
        text = " ".join(segment.text.strip() for segment in segments).strip()

        return {
            "text": text,
            "detected_language": info.language or (language or "unknown"),
            "duration_seconds": round(time.time() - started, 2),
            "model": f"faster-whisper:{MODEL_SIZE}:{_active_device or 'cpu'}",
        }
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def status() -> dict:
    return {
        "installed": is_installed(),
        "loaded": _model is not None,
        "model": MODEL_SIZE,
        # Before first use this is the preferred device; afterwards it is the one
        # that actually loaded, which may have fallen back to CPU.
        "device": (_active_device or _resolve_device()) if is_installed() else "n/a",
        "error": _load_error,
    }
