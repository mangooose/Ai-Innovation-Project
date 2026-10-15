# Klartext

Explains German doctor's letters (Arztbriefe) in plain words for older people.

## What's here

- `web/index.html`: the app UI as one self-contained file. Open it in a browser; no build step. All letter content is mock data (a sample cardiology discharge letter) until the backend is connected.
- `pipeline/`: a script that turns a letter into the structured explanation via Trusted Tokens (GLM-5.3), plus a checker that flags any number not found in the letter. See `pipeline/README.md`.

## The app

- Upload: take a photo (opens the camera on phones) or choose a file (photo or PDF).
- A short "One moment…" screen, then an overview: good news or not, what the letter is about, and the 3 to-dos.
- Tiles open Medicines (by time of day), Report (plain summary and the letter side by side), Questions and Help.
- Read-aloud on every screen, text size and high contrast under "Aa", EN/DE switch in the top bar.
- Not medical advice: it only repeats what the letter says, and says so when the letter is silent.
