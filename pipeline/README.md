# Letter explainer pipeline (Trusted Tokens)

Turns a German doctor's letter into the JSON the Klartext UI shows.

- `prompt.py` holds the system prompt and JSON shape, shared with `server/app.py`.
- `run.py` sends the letter to Trusted Tokens (OpenAI-compatible, streaming) with that prompt and saves JSON. `KLARTEXT_LANG=de` for German.
- `check.py` flags any number or date in the output that is not in the letter.
- `sample_output_cardiology.json` is an earlier real GLM-5.3 output, in the previous JSON shape, for `sample_letter_cardiology.txt` (about 67 s, ~7.4k tokens). Claude Opus fact-checked it against the letter: all dates, doses and phone numbers match.

```
python3 run.py sample_letter_cardiology.txt claude-opus-5-5 out.json
python3 check.py sample_letter_cardiology.txt out.json
```

Notes
- Opus is not available on this Trusted Tokens key (`claude-opus-5-5` is refused); GLM-5.3 is the strongest model offered.
- Non-streaming large requests returned 502 from the gateway; streaming fixed it.
- Set `TRUSTEDTOKENS_API_KEY` when running outside the Claude cloud environment. Never commit the key.
