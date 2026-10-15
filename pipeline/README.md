# Letter explainer pipeline (Trusted Tokens)

Turns a German doctor's letter into the JSON the MediKlar app shows.

- `run.py` sends the letter to Trusted Tokens (`zai-org/GLM-5.3`, OpenAI-compatible, streaming, `reasoning_effort: low`) with a strict "only facts from the letter" prompt, and saves JSON.
- `check.py` flags any number or date in the output that is not in the letter.
- `sample_output_cardiology.json` is the real GLM-5.3 output for `sample_letter_cardiology.txt` (about 67 s, ~7.4k tokens). Claude Opus fact-checked it against the letter: all dates, doses and phone numbers match.

```
python3 run.py sample_letter_cardiology.txt zai-org/GLM-5.3 out.json
python3 check.py sample_letter_cardiology.txt out.json
```

Notes
- Opus is not available on this Trusted Tokens key (`claude-opus-5-5` is refused); GLM-5.3 is the strongest model offered.
- Non-streaming large requests returned 502 from the gateway; streaming fixed it.
- Set `TRUSTEDTOKENS_API_KEY` when running outside the Claude cloud environment. Never commit the key.
