# MediKlar
link: https://mangooose.github.io/Ai-Innovation-Project/web/index.html
Explains German doctor's letters (Arztbriefe) in plain words for older people.

## What's here

- `web/index.html`: the whole app in one file, no build step. It really reads the uploaded letter in the browser: PDFs with pdf.js, photos and scanned PDFs with German OCR (Tesseract). From the letter's own text it shows medicines by time of day, to-dos, phone numbers, dates, the letter's sections and a glossary of medical words. Nothing leaves the device. With an API key in settings ("Aa" → AI explanation) it also explains the letter in plain words via the model, checks every number, date, phone number and medicine against the letter, and asks the model to fix mismatches. "Try with an example letter" shows the sample cardiology letter (EN/DE).
- `pipeline/`: a script that turns a letter into the structured explanation via Trusted Tokens (GLM-5.3), plus a checker that compares every number, date, phone number and medicine schedule with the letter and sends mistakes back to the model to fix. See `pipeline/README.md`.

## The app

- Upload: take a photo (opens the camera on phones) or choose a file (photo, PDF or .txt).
- A reading screen with real progress (PDF text, OCR, AI, checks), then an overview: good news or not, what the letter is about, and the 3 to-dos.
- Tiles open Medicines (by time of day), Report (plain summary and the letter side by side), Questions and Help.
- Read-aloud on every screen, text size and high contrast under "Aa", EN/DE switch in the top bar.
- Not medical advice: it only repeats what the letter says, and says so when the letter is silent.
