# Klartext

Explains German doctor's letters (Arztbriefe) in plain words for older people.

## What's here

- `web/index.html`: the app UI as one self-contained file. Served by `server/app.py`, every screen is filled from the uploaded letter by Claude. Opened directly as a file, it shows the built-in sample (a cardiology discharge letter).
- `server/app.py`: the AI prototype server (Python standard library, plus `pypdf` or `pdftotext` for reading PDFs). See "Run the AI prototype" below.
- `pipeline/`: the shared prompt (`prompt.py`), a command-line runner, and a checker that flags any number not found in the letter. See `pipeline/README.md`.

## The app

- Upload: take a photo (opens the camera on phones) or choose a file (photo or PDF).
- A short "One moment…" screen, then an overview: good news or not, what the letter is about, and the 3 to-dos.
- Tiles open Medicines (by time of day), Report (plain summary and the letter side by side), Questions and Help.
- Read-aloud on every screen, text size and high contrast under "Aa", EN/DE switch in the top bar.
- Not medical advice: it only repeats what the letter says, and says so when the letter is silent.

## Run the AI prototype

```
pip install pypdf            # or have pdftotext (poppler) installed
TRUSTEDTOKENS_API_KEY=... python3 server/app.py
# open http://localhost:8000 and choose a PDF of a doctor's letter
```

- Claude is called through Trusted Tokens' OpenAI-compatible endpoint. `KLARTEXT_MODEL` sets the model id (default `claude-opus-5-5`); if the gateway asks for a provider, use the id it lists, for example with a provider prefix.
- PDFs with a text layer only. Photos and scanned PDFs get a message; there is no OCR yet.
- One upload makes two calls in parallel (English and German), so the EN/DE switch is instant. Expect about a minute on "One moment…".
- The chat sends questions to `/api/ask`, answered only from the letter.
- Every result goes through the number check: numbers not found in the letter are printed in the server log.
- Letters and results are kept in memory only, never written to disk.
- `KLARTEXT_FAKE=1` skips the AI and returns `server/fixtures/cardiology.json` (hand-written from the sample, for UI testing without a key).
- Test letters: `pipeline/sample_letter_cardiology.txt` and `pipeline/sample_letter_orthopedics.txt` (synthetic); turn them into PDFs to upload.
