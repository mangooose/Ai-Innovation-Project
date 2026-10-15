import json, os, sys, urllib.request, time
# Usage: python3 run.py letter.txt zai-org/GLM-5.3 out.json   (needs TRUSTEDTOKENS_API_KEY outside the Claude cloud env)
letter = open(sys.argv[1]).read()
SYSTEM = """You explain German doctor's letters (Arztbriefe) to elderly patients in plain, warm, simple English (short sentences, max ~15 words, no jargon unless explained).
Rules:
- Use ONLY facts in the letter. Never invent dates, doses, phone numbers or advice. Copy every date, dose and number exactly.
- If the letter does not say something (e.g. consequences, exact appointment date), say so explicitly and set source to "general" or "not_in_letter".
- This is not medical advice; tell the patient to ask their doctor before changing anything.
Return ONLY JSON with this shape:
{
 "worry": {"level": "calm|act_soon|urgent", "headline": str, "reason": str},
 "about_one_sentence": str,
 "todos": [{"action": str, "detail": str, "when": str, "then": str|null, "source": "letter"}],
 "if_not": {"source": "letter|general", "points": [str]},
 "summary_paragraphs": [str],
 "medicines": [{"name": str, "dose": str, "form": str, "morning": num, "midday": num, "evening": num, "night": num, "note": str|null}],
 "jargon": [{"term": str, "plain": str}],
 "details_1to1": [{"section": str, "original": str, "plain": str}],
 "faq": [{"q": str, "a": str, "source": "letter|general"}],
 "contacts": [{"who": str, "phone": str, "hours": str|null}]
}"""
body = {"model": sys.argv[2], "temperature": 0.1, "max_tokens": 12000, "stream": True, "reasoning_effort": "low",
        "messages": [{"role":"system","content":SYSTEM},{"role":"user","content":"Letter:\n\n"+letter}]}
req = urllib.request.Request("https://api.trustedtokens.eu/v1/chat/completions", data=json.dumps(body).encode(), headers={"content-type":"application/json", **({"authorization":"Bearer "+os.environ["TRUSTEDTOKENS_API_KEY"]} if os.environ.get("TRUSTEDTOKENS_API_KEY") else {})})
t=time.time()
c=""; usage=None
with urllib.request.urlopen(req, timeout=600) as resp:
    for line in resp:
        line=line.decode().strip()
        if not line.startswith("data:"): continue
        d=line[5:].strip()
        if d=="[DONE]": break
        j=json.loads(d)
        usage=j.get("usage") or usage
        if j.get("choices"): c+=j["choices"][0].get("delta",{}).get("content") or ""
r={"usage":usage}
open(sys.argv[3]+".raw","w").write(c)
c = c.strip().removeprefix("```json").removesuffix("```").strip()
out = json.loads(c)
json.dump(out, open(sys.argv[3],"w"), ensure_ascii=False, indent=1)
print("ok", round(time.time()-t,1), "s", r.get("usage"))
