# Deploying NALAM

Frontend on **Vercel**, backend on **Hugging Face Spaces**. Both free.

## Why two platforms

Vercel serverless functions cap at 250 MB unzipped. NALAM's AI extras do not fit
and never will:

| Dependency | Size | Fits on Vercel? |
|---|---|---|
| `torch` (EasyOCR) | 494 MB | No, twice the limit on its own |
| Whisper `small` weights | ~460 MB | No, and there is no persistent disk to cache them |
| Tesseract | system binary | No, `apt install` is not available |
| `fastapi` + `pydantic` | 5 MB | Yes |

So Vercel can host the rules engine, but not voice or OCR. Hugging Face Spaces
runs a real Docker container, which means `apt install tesseract-ocr-tam` works
and the Whisper weights can be baked into the image.

The deployed image drops EasyOCR and torch entirely (see
`backend/requirements-deploy.txt`). Tesseract reads Tamil properly and is about
thirty times faster on these documents, so the ~510 MB buys nothing.

---

## Step 1 — Backend on Hugging Face Spaces

**1. Create the Space**

Go to <https://huggingface.co/new-space>:

- **Owner**: your username
- **Space name**: `nalam`
- **License**: your choice
- **SDK**: **Docker** → **Blank**
- **Hardware**: CPU basic (free)
- **Visibility**: Public

**2. Push this repository to it**

```bash
git remote add space https://huggingface.co/spaces/YOUR_USERNAME/nalam
```

```bash
git push space main
```

When prompted, the username is your HF username and the *password* is an access
token from <https://huggingface.co/settings/tokens> with **write** permission.
A token is not a password — do not reuse your account password here.

**3. Keep the Space metadata**

A Docker Space needs YAML frontmatter at the very top of its `README.md`.
Pushing this repo overwrites the one HF generated, so add this block to the top
of `README.md` **in the Space** (not in the GitHub repo) if the build does not
start:

```yaml
---
title: NALAM Backend
emoji: 🏛️
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---
```

**4. Wait for the build**

Roughly 8–15 minutes on the first build: it installs Tesseract with the Tamil
pack and bakes in the Whisper weights. Watch the **Logs** tab.

**5. Verify**

```bash
curl https://YOUR_USERNAME-nalam.hf.space/api/health
```

Expect `schemes_loaded: 94`, `document_ocr.engine: "tesseract"`,
`document_ocr.tamil_supported: true`, and `voice_transcription.installed: true`.

That URL is your API base. Note it down.

---

## Step 2 — Frontend on Vercel

**1. Import the repository**

Go to <https://vercel.com/new>, import `raghavkrishnab/NALAM`, and leave the
build settings alone — `vercel.json` already sets the build command and output
directory.

**2. Set the API URL before deploying**

Under **Environment Variables**, add:

| Name | Value |
|---|---|
| `VITE_API_BASE_URL` | `https://YOUR_USERNAME-nalam.hf.space/api` |

This is baked in at build time, so it must be set **before** the first build.
If you add it afterwards, redeploy.

**3. Deploy**

---

## Step 3 — Allow the frontend origin

Any `*.vercel.app` domain is already allowed, including preview deployments, so
the default setup needs nothing here.

Only if you attach a **custom domain**, add a Space variable under
Settings → Variables and secrets:

| Name | Value |
|---|---|
| `NALAM_CORS_ORIGINS` | `https://your-custom-domain.com` |

Comma-separate multiple origins. The Space restarts automatically.

---

## Verifying the whole thing

Open the Vercel URL and check:

1. The hero shows **94 schemes checked** — the frontend is reaching the API.
2. **Try an example** returns matches with eligibility explanations.
3. The footer shows **Voice: Active** and **Document OCR: Active**.
4. Switch to **தமிழ்** — scheme names and explanations change language.
5. Record a voice note and confirm it transcribes.

If the hero shows a dash instead of 94, the frontend cannot reach the backend.
Open the browser console: a CORS error means Step 3, a 404 means
`VITE_API_BASE_URL` is missing the `/api` suffix.

---

## Things that will surprise you

**Free Spaces sleep after ~48 hours idle.** The first request after that pays a
cold start of a minute or more while the container boots. Before a demo, load
the URL once to wake it.

**Whisper on free CPU is slower than your laptop.** Expect roughly 10–20 seconds
for a 30-second clip on 2 shared vCPUs, against ~4 seconds locally. Set
`NALAM_WHISPER_MODEL=tiny` as a Space variable if that is too slow — accuracy on
Tamil drops noticeably, so test before committing to it.

**The browser will not grant microphone access over plain HTTP.** Vercel and
Spaces are both HTTPS, so this is fine in production, but any custom setup must
be HTTPS too.

**Rebuilding re-downloads the Whisper weights.** That is what makes the first
build slow. Later builds reuse Docker layer caching unless
`requirements-deploy.txt` changes.

---

## Local development is unchanged

None of this affects running locally. With `VITE_API_BASE_URL` unset, the
frontend falls back to the relative `/api` path and Vite proxies it to your
local backend exactly as before.
