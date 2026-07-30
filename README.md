# NALAM · Tamil Nadu Welfare Scheme Navigator

NALAM helps Tamil Nadu residents find the government welfare schemes they actually
qualify for. Describe your situation by typing, speaking, chatting, or uploading a
document, and NALAM checks it against **94 schemes** — then shows you exactly which
conditions you meet, which you fail, and which still need confirming.

Fully bilingual (English / தமிழ்). Every AI feature runs locally and free.

---

## Why the eligibility engine is not an LLM

Eligibility decisions are made by a deterministic rules engine in
[`backend/app/rules.py`](backend/app/rules.py), never by a language model. Each
condition resolves to one of three states:

| State | Meaning | Shown as |
|---|---|---|
| `pass` | The profile definitely satisfies it | ✓ Met |
| `fail` | The profile definitely violates it | ✕ Not met |
| `unknown` | The citizen has not told us enough to decide | ? Need to confirm |

That third state is the important one. A missing income figure must never be
reported as "you do not qualify" — it is reported as "we still need to check
this". Schemes with no failures and no unknowns are **eligible**; unknowns but no
failures are **likely**; any hard failure is **not eligible**.

This makes results reproducible, auditable, and explainable line by line. The
optional LLM only rephrases chat replies — it cannot change a verdict.

## Ranking

Qualifying for a scheme and *wanting* it are different things. A low-income widow
qualifies for ~30 schemes; only one of them is why she opened the app. Scores blend
four signals:

- **priority** — how broadly useful the scheme is
- **intent** — does it match the need described in the citizen's own words (strongest signal)
- **relevance** — scheme keywords hit in their text
- **specificity** — conditions matched beyond mere residency

Intent detection runs on Tamil and English text, so "இதய அறுவை சிகிச்சை" and
"heart surgery" both pull health schemes to the top.

---

## Quick start

Two terminals. Backend first.

**1. Backend** (port 8000)

```bash
cd backend && pip install -r requirements.txt && python -m uvicorn app.main:app --reload --port 8000
```

**2. Frontend** (port 5173)

```bash
cd frontend && npm install && npm run dev
```

Open <http://localhost:5173>. Vite proxies `/api` to the backend, so everything
stays same-origin — no CORS setup needed.

If port 8000 or 5173 is already taken, run the backend elsewhere and point the
proxy at it:

```bash
cd backend && python -m uvicorn app.main:app --port 8001
```

```bash
cd frontend && VITE_API_TARGET=http://127.0.0.1:8001 npm run dev
```

Vite picks the next free port for itself automatically and prints it. On Windows,
a killed server can leave an orphaned listening socket that holds its port until
reboot — `Get-NetTCPConnection -LocalPort 8000` showing a listener whose PID no
longer exists is that, and moving ports is the quickest way around it.

### Deploying

See [`deploy/DEPLOYMENT.md`](deploy/DEPLOYMENT.md). Frontend on Vercel, backend
on Hugging Face Spaces, both free.

The split is not a preference. Vercel serverless functions cap at 250 MB
unzipped, and `torch` alone is 494 MB while the Whisper weights are another
~460 MB with no persistent disk to cache them — and Tesseract is a system binary
that cannot be pip installed at all. Spaces runs a real container, so
`apt install tesseract-ocr-tam` works and the model can be baked into the image.

### Optional AI extras

The app is fully usable without these. Voice and OCR report themselves as
unavailable until installed, and the footer shows live capability status.

```bash
cd backend && pip install -r requirements-ai.txt
```

| Extra | Package | What it adds |
|---|---|---|
| Voice → text | `faster-whisper` | Tamil + English speech, auto-detects code-mixing, offline |
| Document OCR | `easyocr` | Reads Tamil + English documents to auto-fill the form |

Both are free, unlimited and run on your own machine. Set
`NALAM_WHISPER_MODEL=medium` for better Tamil accuracy if you have the VRAM.

**Verified on this machine (Ryzen 5 8645HS / RTX 3050 6GB):**

| Check | Result |
|---|---|
| Whisper transcription | ✅ Word-perfect on a 25s English clip, 4.3s on CPU |
| OCR field extraction | ✅ Pulled name, age, income, district from an income certificate |
| Whisper on GPU | ⚠️ Falls back to CPU — see below |
| Tamil document OCR | ❌ Blocked by an EasyOCR bug — see below |

#### GPU is not used out of the box

`pip install easyocr` pulls the **CPU-only** torch wheel (`2.13.0+cpu`), and
ctranslate2 needs the CUDA runtime DLLs that a plain pip install does not
provide. `ctranslate2` will still *report* a CUDA device — but the model only
fails when it runs its first inference, and `model.transcribe()` returns a lazy
generator, so a broken GPU setup looks healthy until a real user speaks.

`transcribe.py` therefore verifies each device with a throwaway inference before
accepting it, and falls back to CPU automatically. `/api/health` reports the
device that actually loaded, not the one we hoped for. CPU is entirely usable —
4.3s for a 25-second clip.

For real GPU acceleration, install the CUDA torch build and the cuBLAS/cuDNN
runtime:

```bash
pip install --force-reinstall torch --index-url https://download.pytorch.org/whl/cu124
```

#### Tamil document OCR needs Tesseract

**EasyOCR 1.7.2's Tamil model is broken upstream.** Its Tamil checkpoint has a
143-class output layer while the model easyocr builds has 127, so loading raises
a `size mismatch` error. Both `['ta','en']` and `['ta']` fail; only `['en']`
loads. This is an EasyOCR packaging bug, not a NALAM one.

`ocr.py` walks a language chain (`ta+en` → `ta` → `en`) and reports what it
actually got, so `/api/health` returns `tamil_supported: false` rather than
implying Tamil OCR works. A future easyocr release starts working with no code
change.

**Tesseract is the fix, and NALAM prefers it automatically once Tamil is
present.** It is also far faster — 0.4s versus 12.7s for the same document.

1. Install the binary:

```bash
winget install --id UB-Mannheim.TesseractOCR
```

2. Add the Tamil pack. The winget build ships only `eng`, and `tessdata` under
   `Program Files` needs admin — so point `TESSDATA_PREFIX` at a writable copy
   instead:

```bash
mkdir -p "$LOCALAPPDATA/NALAM/tessdata" && cp "/c/Program Files/Tesseract-OCR/tessdata/"*.traineddata "$LOCALAPPDATA/NALAM/tessdata/" && curl -sSL -o "$LOCALAPPDATA/NALAM/tessdata/tam.traineddata" https://github.com/tesseract-ocr/tessdata_best/raw/main/tam.traineddata
```

```bash
setx TESSDATA_PREFIX "%LOCALAPPDATA%\NALAM\tessdata"
```

3. `pip install pytesseract`, then restart your terminal and the backend.

Verify with `/api/health`: `engine` becomes `tesseract` and `tamil_supported`
turns `true`. If it stays false, the `tamil_note` field says exactly which step
is missing.

The Windows installer does not add Tesseract to PATH, so `ocr.py` searches
`TESSERACT_CMD`, then PATH, then the standard `Program Files` locations. It only
switches away from EasyOCR when `tam` is genuinely installed, and it asks
Tesseract for just the languages that exist rather than erroring on `tam+eng`.

Verified on a Tamil income certificate — extracts name (`லட்சுமி தேவி`), age,
income, and district, mapping `மதுரை` to `Madurai` so it matches the form's
district list. Tesseract emits zero-width joiners through Tamil output, which are
stripped before field matching.

Accuracy note: Tamil OCR is much weaker on photographed certificates than on flat
scans. A square-on, well-lit image makes a large difference.

**Voice input handles Tamil regardless** — this limitation was document OCR only.

> **On Amazon Transcribe / Textract:** neither is a fit here. Transcribe's free
> tier is 60 min/month for 12 months only, then bills per minute. **Textract does
> not support Tamil at all** — only English, Spanish, French, German, Italian and
> Portuguese — so it physically cannot read a Tamil income certificate. Whisper
> and EasyOCR are free forever and both handle Tamil.

### Optional LLM (Ollama or OpenRouter)

The LLM is strictly a presentation layer — it rewords chat replies and can never
change an eligibility verdict. See [`backend/app/llm.py`](backend/app/llm.py).
With no provider configured, chat uses its scripted rules-based replies and the
app behaves identically.

**Option A — Ollama (local, recommended).** Free forever, offline, private, no
key, no rate limit.

```bash
ollama pull qwen2.5:7b-instruct
```

**Option B — OpenRouter (hosted, has free models).** Needs an API key and
internet.

1. Get a key at <https://openrouter.ai/keys>
2. Pick a free model at <https://openrouter.ai/models?q=free> (they end in `:free`)
3. Set it in your shell — **never commit a key to the repo**:

```bash
setx OPENROUTER_API_KEY "your-key-here"
```

Then restart the terminal and the backend. Verify with `GET /api/health`, which
reports `openrouter.api_key_present` — it never returns the key itself.

`NALAM_LLM_PROVIDER` controls routing: `auto` (default) prefers Ollama when it is
running and falls back to OpenRouter if a key is set; `ollama`, `openrouter`, or
`none` force the choice. Local-first is the default deliberately — a citizen's
situation is sensitive, and Ollama keeps it on the machine.

> **OpenRouter cannot do speech-to-text.** It serves chat completions, not audio
> transcription, so it is not an alternative to Whisper. Voice input stays local
> regardless of which LLM provider you choose.
>
> Free OpenRouter models are rate-limited and typically log or train on requests.
> For a live demo, Ollama is the safer bet: no quota to exhaust, no network to drop.

---

## Features

- **Form mode** — structured intake with 19 situation flags
- **Chat mode** — slot-filling conversation; extracts age, gender, district, income,
  occupation and community from free text in either language. Handles
  "4000 per month" → ₹48,000/year and Tamil numerals.
- **Voice input** — record and transcribe, sent as `auto` language because TN speech
  is heavily code-mixed and forcing a language degrades accuracy
- **Document auto-fill** — OCR an Aadhaar card or income certificate; never
  overwrites a field the user already typed
- **Eligibility explainer** — every condition, with the actual numbers compared
- **PDF checklist** — via the browser's own print-to-PDF, the only approach that
  renders Tamil correctly without embedding a Tamil font into a PDF library.
  Failed schemes are hidden from the printout.

---

## Data

| File | Contents |
|---|---|
| `backend/data/source_tn_schemes.csv` | The official source export (87 rows), vendored unchanged |
| `backend/data/schemes_master.json` | 69 state schemes, generated from the CSV |
| `backend/data/translations_ta.json` | Tamil overlay, keyed by `scheme_id` |
| `backend/data/schemes_central.json` | 25 Government of India schemes, hand-curated |

Tamil lives in a separate overlay so the CSV can be re-exported and re-ingested
without losing translations.

### Regenerating from the CSV

```bash
cd backend && python tools/ingest_csv.py data/source_tn_schemes.csv
```

The ingestion does real work, because the source CSV needs it:

- **Parses prose eligibility into rules.** `"Age 18-65; Annual income < ₹72000"`
  becomes checkable structure. Currently derives age bounds for 16 schemes, income
  ceilings for 10, gender for 22, and situation flags for 43.
- **Deduplicates properly.** The file is named `..._Deduplicated.csv` but is not:
  11 `scheme_id` values are reused across 22 rows. Worse, they collide in two
  different ways — 6 are the same scheme twice (second row richer), but 5 are
  *different* schemes sharing an ID (`TN-SW-006` is both Girl Child Protection
  **and** Widow Remarriage Assistance; `TN-ED-004` is both Illam Thedi Kalvi
  **and** Naan Mudhalvan). Merging on ID would silently delete real schemes, so
  matching is done on normalised names instead, with colliding IDs reassigned.
  There is further cross-ID duplication an ID check misses entirely
  (`TN-WEL-003` "Free House Site Patta" vs `TN-SS-007` "Free House Site Patta
  Scheme"). Net: 87 rows → 69 distinct schemes.
- **Normalises categories.** 46 free-form labels collapse to 12 usable ones.
- **Merges the Tamil overlay.**

### Known data caveats

- The three `Chief Minister's Girl Child Protection Scheme` rows (umbrella,
  Scheme I, Scheme II) are merged into one entry. Scheme I and II differ in
  deposit amount by number of girl children; the merged card loses that
  distinction. Split them in the CSV if the difference matters to you.
- Structured rules are derived from prose, so a scheme with unusual phrasing may
  end up with fewer machine-checkable conditions than it really has. Its
  original eligibility text is always preserved in `eligibility_text` and shown
  in the UI.
- Scheme data reflects the source export's `last_verified` date. **Always confirm
  on the official site before applying** — NALAM surfaces `official_source` for
  exactly this reason.

---

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Capability report — drives the live status footer |
| `GET /api/schemes?language=` | Full localised catalogue |
| `GET /api/options?language=` | Localised dropdown and checkbox options |
| `POST /api/match` | Run the rules engine over a profile |
| `POST /api/chat` | Conversational slot filling |
| `POST /api/transcribe` | Audio → text (Whisper) |
| `POST /api/ocr` | Image → fields (EasyOCR) |

Interactive docs at <http://localhost:8000/docs>.

---

## Layout

```
backend/
  app/
    main.py        FastAPI routes
    rules.py       eligibility engine + intent detection
    chat.py        slot-filling conversation
    schemes.py     catalogue loader
    llm.py         Ollama adapter (optional)
    transcribe.py  faster-whisper (optional)
    ocr.py         EasyOCR (optional)
    models.py      request/response schemas
  data/            source CSV, generated catalogue, Tamil overlay
  tools/
    ingest_csv.py  CSV → structured catalogue
frontend/
  src/
    App.jsx        shell, language state, tabs
    i18n.js        every user-visible string, EN + TA
    styles.css     civic design system + print stylesheet
    components/    SchemeForm, ResultsPanel, ChatPanel, BrowsePanel, VoiceInput
legacy/            original static prototype, kept for reference
```

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `NALAM_WHISPER_MODEL` | `small` | `tiny`…`large-v3` |
| `NALAM_WHISPER_DEVICE` | `auto` | `cpu` / `cuda` |
| `NALAM_WHISPER_COMPUTE` | `int8` | auto-upgrades to `float16` on CUDA |
| `TESSERACT_CMD` | _(auto-detected)_ | Full path to `tesseract.exe` if not on PATH |
| `TESSDATA_PREFIX` | _(Tesseract default)_ | Folder holding `*.traineddata`, e.g. a writable Tamil copy |
| `NALAM_LLM_PROVIDER` | `auto` | `auto` / `ollama` / `openrouter` / `none` |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Ollama server |
| `NALAM_OLLAMA_MODEL` | `qwen2.5:7b-instruct` | Falls back to any pulled model |
| `OPENROUTER_API_KEY` | _(unset)_ | Read from the environment only, never logged |
| `NALAM_OPENROUTER_MODEL` | `meta-llama/llama-3.3-70b-instruct:free` | Any OpenRouter slug |
| `VITE_API_TARGET` | `http://127.0.0.1:8000` | Backend the Vite proxy points at |

---

NALAM is a guidance tool, not an official government service. Eligibility rules
change. Always verify on the official website or at your Taluk office before applying.
