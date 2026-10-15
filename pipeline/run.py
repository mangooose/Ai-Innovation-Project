import json, os, sys, urllib.request, time
# Usage: python3 run.py letter.txt claude-opus-5-5 out.json   (needs TRUSTEDTOKENS_API_KEY; KLARTEXT_LANG=de for German)
letter = open(sys.argv[1]).read()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prompt import system_prompt
SYSTEM = system_prompt(os.environ.get("KLARTEXT_LANG", "en"))
body = {"model": sys.argv[2], "max_tokens": 16000, "stream": True,
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
