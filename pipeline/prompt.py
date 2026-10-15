# The prompt and JSON shape that turn a German doctor's letter into what the Klartext UI shows.
# Shared by server/app.py and run.py.

LANG_NAME = {"en": "English", "de": "German (simple, warm, 'Sie' form)"}

ICONS_TODO = ["pill", "drop", "cal", "heart", "phone", "file"]
ICONS_CONTACT = ["heart", "file", "phone"]

SCHEMA = """{
 "patient_salutation": str|null,        // how to greet the patient, e.g. "Mr Königsstein" / "Herr Königsstein"; null if unclear
 "worry": {"level": "calm|act_soon|urgent", "headline": str, "reason": str},
 "about": str,                          // "About this letter: ..." one sentence, starts with that phrase in the target language
 "todos": [                             // the 3 most important things the patient must do (fewer only if the letter has fewer)
  {"icon": "pill|drop|cal|heart|phone|file",
   "short": str,                        // max ~5 words, e.g. "Take both blood thinners"
   "long": str,                         // one sentence heading
   "sub": str|null,                     // small line under the heading: medicine names, doctor name, a practical hint
   "when": str,                         // short chip, e.g. "Every day", "Until end of May 2023", "In about 6 months"
   "why": str,                          // why, as the letter says it; say so if the letter gives no date or reason
   "warn": str|null,                    // one safety line, e.g. never stop medicines on your own; null if not needed
   "phone": str|null,                   // phone number to call for this to-do, copied exactly; null if none
   "if_not": {"source": "letter|general", "points": [str]}}  // what can happen if not done; "general" if the letter does not say
 ],
 "medicines": [{"name": str, "form": str, "purpose": str, "morning": num|str, "midday": num|str, "evening": num|str, "night": num|str, "flag": str|null}],
                                        // name with strength, e.g. "ASS 100 mg"; form e.g. "tablet", "inhaler · 2 puffs";
                                        // purpose short, e.g. "blood thinner"; flag = a short note like "Before eating" or "Until end of May 2023"
 "summary_paragraphs": [str],           // 2-4 short paragraphs. Mark hard words as [[term_id|visible words]], term_id must be a key of "jargon"
 "jargon": {"term_id": {"word": str, "also": str, "plain": str, "more": str}},
                                        // term_id lowercase a-z only; word = the term as in the letter; also = other name or translation;
                                        // plain = 1-2 simple sentences; more = extra detail from the letter or ""
 "details": {                           // 5 fixed sections. Each has EITHER "plain" (a paragraph) OR "rows", plus "original"
  "reason":     {"plain": str|null, "rows": [{"original": str, "plain": str}], "original": str},  // why the patient went to hospital
  "diagnoses":  {...same...},           // illnesses; rows: original = the diagnosis line as in the letter
  "procedures": {...same...},           // what the doctors did
  "tests":      {...same...},           // tests and results
  "next":       {...same...}            // what happens next
 },                                     // "original" = an exact quote (German) copied from the letter for that section; [[term_id|words]] allowed in plain texts
 "faq": [{"q": str, "a": str, "source": "letter|general"}],   // exactly 5 questions this patient will likely have
 "contacts": [{"icon": "heart|file|phone", "role": str, "detail": str, "phone": str}],
                                        // up to 3 people to call, most useful first. role e.g. "Your heart doctor";
                                        // detail = name, address or opening hours; phone copied exactly from the letter
 "chips": [str]                         // exactly 4 short questions the patient might ask in the chat
}"""


def system_prompt(lang):
    return f"""You explain German doctor's letters (Arztbriefe) to elderly patients in plain, warm, simple {LANG_NAME[lang]}.
Short sentences (max ~15 words), no jargon unless explained.
Rules:
- Use ONLY facts in the letter. Never invent dates, doses, phone numbers, names or advice. Copy every date, dose and number exactly.
- If the letter does not say something (consequences, exact appointment date), say so plainly and set source to "general".
- This is not medical advice. Never tell the patient to change or stop a medicine; tell them to ask their doctor first.
- All patient-facing text in {LANG_NAME[lang]}. Fields named "original" stay in German, copied word for word from the letter.
Return ONLY one JSON object (no markdown fences, no comments) with this shape:
{SCHEMA}"""


def chat_system_prompt(lang, letter):
    return f"""You answer an elderly patient's questions about their German doctor's letter, in plain, warm, simple {LANG_NAME[lang]}.
Rules:
- Answer ONLY from the letter below. Copy dates, doses and phone numbers exactly. 1-4 short sentences.
- If the letter does not answer the question, say so, do not guess, and suggest asking their doctor (name the doctor and phone number from the letter if there is one).
- General background that is not in the letter must be marked with source "general".
- Never tell the patient to change or stop a medicine. You give explanations, not medical advice.
- You may wrap the single most important fact in **double asterisks**.
Return ONLY JSON: {{"answer": str, "source": "letter|general|not_in_letter"}}

Letter:

{letter}"""
