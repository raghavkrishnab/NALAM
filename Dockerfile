# NALAM backend image, built for Hugging Face Spaces (Docker SDK).
#
# Spaces route traffic to port 7860 by default, which is why the server binds
# there rather than 8000.

FROM python:3.11-slim

# tesseract-ocr-tam is the whole reason this runs in Docker rather than on a
# serverless platform: Tamil OCR needs a system binary that cannot be pip
# installed. ffmpeg lets faster-whisper decode whatever audio format the
# browser's MediaRecorder produced.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-tam \
        tesseract-ocr-eng \
        ffmpeg \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Spaces run as a non-root user, and anything the app writes at runtime must
# live somewhere that user owns.
RUN useradd -m -u 1000 nalam
ENV HOME=/home/nalam \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/home/nalam/.cache/huggingface \
    XDG_CACHE_HOME=/home/nalam/.cache

WORKDIR /app

COPY backend/requirements-deploy.txt ./requirements-deploy.txt
RUN pip install --no-cache-dir -r requirements-deploy.txt

COPY backend/ /app/backend/

# Bake the Whisper weights into the image. Downloading them on the first request
# instead would make that request time out, and Spaces restart often enough that
# it would keep happening.
ENV NALAM_WHISPER_MODEL=small \
    NALAM_WHISPER_DEVICE=cpu \
    NALAM_WHISPER_COMPUTE=int8
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8')" \
    && chown -R nalam:nalam /home/nalam

RUN chown -R nalam:nalam /app
USER nalam

ENV PYTHONPATH=/app/backend \
    PORT=7860
EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -fsS http://127.0.0.1:7860/api/health || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860", "--app-dir", "/app/backend"]
