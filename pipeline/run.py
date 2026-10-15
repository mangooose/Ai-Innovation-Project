"""Turns a German doctor's letter into the JSON the MediKlar app shows.

Usage:
    python3 run.py letter.txt zai-org/GLM-5.3 out.json [--lang en|de] [--repairs N]

Needs TRUSTEDTOKENS_API_KEY outside the Claude cloud environment.

Steps
1. Clean the letter text (drop empty PDF bullet lines like "o") without changing any content.
2. Ask the model for strict JSON, using only facts from the letter.
3. Pull the JSON out of the reply, even if the model wrapped it in text or code fences.
4. Run check.py. If it finds problems, send them back to the model and ask for a fixed
   version (up to --repairs times, default 2).
5. Save the result. Exit code 1 if problems remain, so a bad result is never mistaken for a good one.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

from check import check

API_URL = os.environ.get("TRUSTEDTOKENS_URL", "https://api.trustedtokens.eu/v1/chat/completions")

LANG = {
    "en": "plain, warm, simple English",
    "de": "einfachem, warmem Deutsch (Leichte Sprache)",
}

SYSTEM = """You explain German doctor's letters (Arztbriefe) to elderly patients in {lang}.
Use short sentences (about 15 words at most). Avoid medical words; if you must use one, explain it.

Rules:
- Use ONLY facts in the letter. Never invent dates, doses, amounts, phone numbers or advice.
- Copy every date, dose, amount and phone number exactly as written in the letter.
- Medicines: use the DISCHARGE list ("Medikation Entlassung"), not the admission list.
  List every discharge medicine. The schedule "a – b – c – d" means morning – midday – evening – night;
  copy those four numbers exactly. Put stop dates (e.g. "bis 05/2023") and notes such as
  "vor den Mahlzeiten" in "note".
- "bis einschließlich 05/2023" means up to and including May 2023, i.e. until the end of May 2023.
- If the letter does not say something (warning signs, exact appointment date, what a medicine is for),
  say so. Use source "general" for general knowledge and "not_in_letter" when the letter is silent.
- If you explain what a medicine is for and the letter does not say it, start the note with "Usually:".
- worry.level: "calm" if the letter reports success / no complications; "act_soon" if it asks for
  prompt action; "urgent" only if the letter itself says something is urgent.
- todos: the concrete things the letter asks the patient to do, most important first.
- details_1to1: one entry per important part of the letter. "original" must be copied word for word
  from the letter (you may shorten with "…"). Include diagnoses, the procedure, results, and follow-up.
- contacts: every phone number in the letter that a patient might call, with who it belongs to.
- This is not medical advice; tell the patient to ask their doctor before changing anything.

Return ONLY one JSON object, no other text, with exactly this shape:
{{
 "worry": {{"level": "calm|act_soon|urgent", "headline": str, "reason": str}},
 "about_one_sentence": str,
 "todos": [{{"action": str, "detail": str, "when": str, "then": str|null, "source": "letter|general"}}],
 "if_not": {{"source": "letter|general|not_in_letter", "points": [str]}},
 "summary_paragraphs": [str],
 "medicines": [{{"name": str, "dose": str, "form": str, "morning": num, "midday": num, "evening": num, "night": num, "note": str|null}}],
 "jargon": [{{"term": str, "plain": str}}],
 "details_1to1": [{{"section": str, "original": str, "plain": str}}],
 "faq": [{{"q": str, "a": str, "source": "letter|general|not_in_letter"}}],
 "contacts": [{{"who": str, "phone": str, "hours": str|null}}]
}}"""

REPAIR = """An automatic check compared your JSON with the letter and found these problems:
{issues}

Fix every problem using only the letter. Keep everything else the same.
Return the complete corrected JSON object only."""


def clean_letter(text):
    """Remove empty PDF list markers and repeated blank lines; keep every real line unchanged."""
    lines = [ln.rstrip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln.strip() not in {"o", "•", "▪", "-", "–"}]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip() + "\n"


def extract_json(text):
    """Find the JSON object in a model reply (handles code fences and extra text)."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fence:
        text = fence.group(1)
    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON object in the reply")
    obj, _ = json.JSONDecoder().raw_decode(text[start:])
    return obj


def call_model(model, messages, json_mode=True, attempts=3):
    """Streaming chat completion. Returns (text, usage). Retries gateway errors and timeouts."""
    body = {"model": model, "temperature": 0.1, "max_tokens": 12000, "stream": True,
            "reasoning_effort": "low", "messages": messages}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    headers = {"content-type": "application/json"}
    if os.environ.get("TRUSTEDTOKENS_API_KEY"):
        headers["authorization"] = "Bearer " + os.environ["TRUSTEDTOKENS_API_KEY"]
    for attempt in range(1, attempts + 1):
        req = urllib.request.Request(API_URL, data=json.dumps(body).encode(), headers=headers)
        try:
            text, usage = "", None
            with urllib.request.urlopen(req, timeout=600) as resp:
                for raw in resp:
                    line = raw.decode("utf-8", "replace").strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    chunk = json.loads(data)
                    usage = chunk.get("usage") or usage
                    if chunk.get("choices"):
                        text += chunk["choices"][0].get("delta", {}).get("content") or ""
            if not text.strip():
                raise ValueError("empty reply")
            return text, usage
        except urllib.error.HTTPError as e:
            if e.code == 400 and json_mode:  # gateway/model may not support response_format
                return call_model(model, messages, json_mode=False, attempts=attempts)
            if e.code < 500 and e.code != 429:
                raise
            err = e
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            err = e
        if attempt < attempts:
            wait = 5 * attempt
            print(f"  attempt {attempt} failed ({err}); retrying in {wait}s", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"model call failed after {attempts} attempts: {err}")


def explain(letter, model, lang="en", repairs=2, log=print, call=call_model):
    """Return (output_json, remaining_issues, raw_replies)."""
    cleaned = clean_letter(letter)
    messages = [{"role": "system", "content": SYSTEM.format(lang=LANG[lang])},
                {"role": "user", "content": "Letter:\n\n" + cleaned}]
    raws, out, issues = [], None, ["no output yet"]
    for round_no in range(repairs + 1):
        text, usage = call(model, messages)
        raws.append(text)
        log(f"round {round_no + 1}: reply received, usage={usage}")
        try:
            out = extract_json(text)
            issues, notes, _ = check(letter, out)
            for n in notes:
                log("  note:", n)
        except ValueError as e:
            out, issues = None, [f"reply was not valid JSON: {e}"]
        if not issues:
            log(f"round {round_no + 1}: all checks passed")
            break
        log(f"round {round_no + 1}: {len(issues)} problem(s):")
        for i in issues:
            log("  -", i)
        messages += [{"role": "assistant", "content": text},
                     {"role": "user", "content": REPAIR.format(issues="\n".join("- " + i for i in issues))}]
    return out, issues, raws


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("letter")
    ap.add_argument("model")
    ap.add_argument("out")
    ap.add_argument("--lang", choices=sorted(LANG), default="en")
    ap.add_argument("--repairs", type=int, default=2, help="max. repair rounds when checks fail")
    a = ap.parse_args()

    letter = open(a.letter, encoding="utf-8").read()
    t = time.time()
    out, issues, raws = explain(letter, a.model, a.lang, a.repairs)
    open(a.out + ".raw", "w", encoding="utf-8").write("\n\n=====\n\n".join(raws))
    if out is not None:
        json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"done in {time.time() - t:.1f}s -> {a.out}")
    if issues:
        print(f"WARNING: {len(issues)} problem(s) remain; do not show this output to a patient.")
        sys.exit(1)


if __name__ == "__main__":
    main()
