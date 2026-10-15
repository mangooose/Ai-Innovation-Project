# Letter explainer pipeline (Trusted Tokens)

Turns a German doctor's letter into the JSON the MediKlar app shows, and checks it against the letter before it can be used.

- `run.py` cleans the letter (drops empty PDF bullet lines), sends it to Trusted Tokens (`zai-org/GLM-5.3`, OpenAI-compatible, streaming, `reasoning_effort: low`) with a strict "only facts from the letter" prompt, pulls the JSON out of the reply, and runs the checker. If the checker finds problems, they are sent back to the model for a corrected version (up to 2 rounds). It exits with code 1 if problems remain, so a bad result is never saved as if it were good. Gateway errors (502/503/429, timeouts) are retried.
- `check.py` compares the output with the letter. It fails on:
  - missing fields or wrong types, values or sources;
  - any number, date or time that is not in the letter, including written dates like "23 June 2022" or "Mai 2023";
  - an amount with the wrong unit, for example "3 litres" when the letter says 1,5–2 Liter;
  - a phone number that does not match the letter digit for digit;
  - a medicine that is not on the discharge list, has the wrong strength or the wrong morning–midday–evening–night schedule, or is missing.

  It also warns when a quoted "original" phrase is not word for word in the letter.
- `test_pipeline.py` has 24 offline tests: planted mistakes the checker must catch, JSON extraction, and the retry/repair loop against a fake model server. No key or network needed.
- `sample_output_cardiology.json` is the GLM-5.3 output for `sample_letter_cardiology.txt`, corrected by hand against the letter (Oct 2026):
  - fixed the explanations of NYHA II and "maligne Hypertonie";
  - added the planned admission, the May 2022 heart attack and the other diagnoses;
  - added the hospital's main number and a "Can I drive?" answer that says the letter is silent;
  - medicine purposes the letter doesn't state now start with "Usually:".

  It passes `check.py` with no problems.

```
python3 run.py sample_letter_cardiology.txt zai-org/GLM-5.3 out.json            # English
python3 run.py sample_letter_cardiology.txt zai-org/GLM-5.3 out_de.json --lang de
python3 check.py sample_letter_cardiology.txt out.json
python3 -m unittest -v test_pipeline
```

Notes
- Opus is not available on this Trusted Tokens key (`claude-opus-5-5` is refused); GLM-5.3 is the strongest model offered.
- Non-streaming large requests returned 502 from the gateway; streaming fixed it.
- Set `TRUSTEDTOKENS_API_KEY` when running outside the Claude cloud environment. Never commit the key. `TRUSTEDTOKENS_URL` overrides the endpoint.
- The medicine check reads the standard eArztbrief layout ("Medikation Entlassung", "Code/Bezeichnung", "Dosierschema Freitext"). For letters without that list it prints a note and skips that check.
- The checker proves numbers and medicines match the letter; it cannot judge whether a plain-language explanation is medically right. A person should still read new outputs.
