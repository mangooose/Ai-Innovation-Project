# Klartext prototype server: serves web/index.html and fills it with Claude (via Trusted Tokens).
#   TRUSTEDTOKENS_API_KEY=... python3 server/app.py      then open http://localhost:8000
# Env: KLARTEXT_MODEL (default claude-opus-5-5), TRUSTEDTOKENS_BASE_URL, PORT, KLARTEXT_FAKE=1 (no LLM, returns the fixture).
import hashlib, io, json, os, re, subprocess, sys, tempfile, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
from prompt import ICONS_CONTACT, ICONS_TODO, chat_system_prompt, system_prompt  # noqa: E402

BASE_URL = os.environ.get("TRUSTEDTOKENS_BASE_URL", "https://api.trustedtokens.eu/v1").rstrip("/")
MODEL = os.environ.get("KLARTEXT_MODEL", "claude-opus-5-5")
FAKE = os.environ.get("KLARTEXT_FAKE") == "1"
MAX_PDF = 15 * 1024 * 1024
LETTERS = {}  # id -> {"text", "en", "de", "warnings"}; memory only, never written to disk


class ApiError(Exception):
    def __init__(self, status, code, detail=""):
        super().__init__(detail or code)
        self.status, self.code, self.detail = status, code, detail


# ---------- PDF -> text ----------
def pdf_text(data):
    try:
        from pypdf import PdfReader
        text = "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(data)).pages)
    except ImportError:
        with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
            f.write(data); f.flush()
            text = subprocess.run(["pdftotext", "-layout", f.name, "-"], capture_output=True, text=True, timeout=60).stdout
    except Exception as e:
        raise ApiError(422, "no_text", f"could not read PDF: {e}")
    text = re.sub(r"[ \t]+\n", "\n", text).strip()
    if len(re.sub(r"\s", "", text)) < 200:  # a scan or photo inside a PDF: no text layer, and no OCR yet
        raise ApiError(422, "no_text", "PDF has no text layer")
    return text


# ---------- LLM ----------
def llm(system, user, max_tokens):
    body = {"model": MODEL, "max_tokens": max_tokens, "stream": True,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    headers = {"content-type": "application/json"}
    if os.environ.get("TRUSTEDTOKENS_API_KEY"):
        headers["authorization"] = "Bearer " + os.environ["TRUSTEDTOKENS_API_KEY"]
    req = urllib.request.Request(BASE_URL + "/chat/completions", data=json.dumps(body).encode(), headers=headers)
    out = ""
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:  # streaming: large non-streaming requests 502 on the gateway
            for line in resp:
                line = line.decode().strip()
                if not line.startswith("data:"):
                    continue
                d = line[5:].strip()
                if d == "[DONE]":
                    break
                j = json.loads(d)
                if j.get("error"):
                    raise ApiError(502, "llm_error", json.dumps(j["error"])[:500])
                if j.get("choices"):
                    out += j["choices"][0].get("delta", {}).get("content") or ""
    except urllib.error.HTTPError as e:
        raise ApiError(502, "llm_error", f"{e.code}: {e.read().decode(errors='replace')[:500]}")
    except urllib.error.URLError as e:
        raise ApiError(502, "llm_error", str(e.reason))
    return parse_json(out)


def parse_json(s):
    s = s.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    a, b = s.find("{"), s.rfind("}")
    try:
        return json.loads(s[a:b + 1])
    except Exception:
        raise ApiError(502, "llm_bad_json", s[:300])


# ---------- clean-up and checks ----------
def _norm(s):
    return re.sub(r"\s+", " ", s or "").strip().lower()


def _str(v):
    return v.strip() if isinstance(v, str) else ""


def _opt(v):
    v = _str(v)
    return v or None


def _dose(v):
    if isinstance(v, (int, float)):
        return int(v) if float(v).is_integer() else v
    v = _str(v)
    return 0 if v in ("", "0", "-") else v


def normalize(d, letter):
    """Coerce the model's JSON into exactly the shape the UI expects, and drop quotes not found in the letter."""
    L = _norm(letter)
    in_letter = lambda q: bool(q) and _norm(q) in L
    out = {"patient_salutation": _opt(d.get("patient_salutation"))}
    w = d.get("worry") or {}
    out["worry"] = {"level": w.get("level") if w.get("level") in ("calm", "act_soon", "urgent") else "calm",
                    "headline": _str(w.get("headline")), "reason": _str(w.get("reason"))}
    out["about"] = _str(d.get("about") or d.get("about_one_sentence"))
    todos = []
    for t in (d.get("todos") or [])[:3]:
        f = t.get("if_not") or {}
        todos.append({"icon": t.get("icon") if t.get("icon") in ICONS_TODO else "cal",
                      "short": _str(t.get("short") or t.get("action")), "long": _str(t.get("long") or t.get("action")),
                      "sub": _opt(t.get("sub")), "when": _str(t.get("when")), "why": _str(t.get("why") or t.get("detail")),
                      "warn": _opt(t.get("warn")), "phone": _opt(t.get("phone")),
                      "if_not": {"source": "letter" if f.get("source") == "letter" else "general",
                                 "points": [_str(p) for p in (f.get("points") or []) if _str(p)]}})
    out["todos"] = todos
    out["medicines"] = [{"name": _str(m.get("name")), "form": _str(m.get("form")), "purpose": _str(m.get("purpose")),
                         **{k: _dose(m.get(k)) for k in ("morning", "midday", "evening", "night")}, "flag": _opt(m.get("flag"))}
                        for m in (d.get("medicines") or []) if _str(m.get("name"))]
    jargon = {}
    for k, v in (d.get("jargon") or {}).items():
        k = re.sub(r"[^a-z0-9]", "", str(k).lower())
        if k and isinstance(v, dict):
            jargon[k] = {"word": _str(v.get("word")), "also": _str(v.get("also")), "plain": _str(v.get("plain")), "more": _str(v.get("more"))}
    out["jargon"] = jargon
    out["summary_paragraphs"] = [_str(p) for p in (d.get("summary_paragraphs") or []) if _str(p)]
    details = {}
    for sec in ("reason", "diagnoses", "procedures", "tests", "next"):
        s = (d.get("details") or {}).get(sec) or {}
        rows = [{"original": _str(r.get("original")) if in_letter(_str(r.get("original"))) else "", "plain": _str(r.get("plain"))}
                for r in (s.get("rows") or []) if _str(r.get("plain"))]
        orig = _str(s.get("original"))
        details[sec] = {"plain": None if rows else _opt(s.get("plain")), "rows": rows, "original": orig if in_letter(orig) else ""}
    out["details"] = details
    out["faq"] = [{"q": _str(f.get("q")), "a": _str(f.get("a")), "source": "letter" if f.get("source") == "letter" else "general"}
                  for f in (d.get("faq") or []) if _str(f.get("q"))][:5]
    out["contacts"] = [{"icon": c.get("icon") if c.get("icon") in ICONS_CONTACT else "phone", "role": _str(c.get("role") or c.get("who")),
                        "detail": _str(c.get("detail") or c.get("hours")), "phone": _str(c.get("phone"))}
                       for c in (d.get("contacts") or []) if _str(c.get("phone"))][:3]
    out["chips"] = [_str(c) for c in (d.get("chips") or []) if _str(c)][:4]
    return out


def number_warnings(data, letter):
    """Same idea as pipeline/check.py: any number in the output that is not in the letter."""
    nl = lambda s: re.sub(r"\s", "", s).replace(",", ".")
    L = nl(letter)
    text = json.dumps(data, ensure_ascii=False)
    nums = set(re.findall(r"\d+(?:[.,]\d+)*(?:/\d+)?", text))
    return sorted(n for n in nums if nl(n) not in L)


# ---------- endpoints ----------
def explain(pdf):
    if not pdf.startswith(b"%PDF"):
        raise ApiError(415, "pdf_only")
    lid = hashlib.sha256(pdf).hexdigest()[:16]
    if lid in LETTERS:
        return {"id": lid, **{k: LETTERS[lid][k] for k in ("en", "de", "warnings")}}
    text = pdf_text(pdf)
    t = time.time()
    if FAKE:
        fx = json.loads((ROOT / "server" / "fixtures" / "cardiology.json").read_text())
        res = {"en": fx["en"], "de": fx["de"]}
    else:
        with ThreadPoolExecutor(2) as ex:
            futs = {lang: ex.submit(llm, system_prompt(lang), "Letter:\n\n" + text, 16000) for lang in ("en", "de")}
            res = {lang: f.result() for lang, f in futs.items()}
    res = {lang: normalize(v, text) for lang, v in res.items()}
    warnings = {lang: number_warnings(v, text) for lang, v in res.items()}
    print(f"explain {lid}: {round(time.time() - t, 1)} s, numbers not in letter: {warnings}", flush=True)
    LETTERS[lid] = {"text": text, **res, "warnings": warnings}
    return {"id": lid, **res, "warnings": warnings}


def ask(body):
    letter = LETTERS.get(body.get("id") or "")
    if not letter:
        raise ApiError(404, "unknown_letter")
    lang = "de" if body.get("lang") == "de" else "en"
    q = _str(body.get("question"))[:1000]
    if not q:
        raise ApiError(400, "empty")
    if FAKE:
        return {"answer": "(Test mode, no AI.) Your letter is about your heart treatment.", "source": "letter"}
    hist = "".join(f"Earlier question: {_str(h.get('q'))}\nEarlier answer: {_str(h.get('a'))}\n\n"
                   for h in (body.get("history") or [])[-6:] if isinstance(h, dict))
    r = llm(chat_system_prompt(lang, letter["text"]), hist + "Question: " + q, 1500)
    src = r.get("source") if r.get("source") in ("letter", "general", "not_in_letter") else "general"
    return {"answer": _str(r.get("answer")), "source": src}


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, body, ctype="application/json"):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("content-type", ctype)
        self.send_header("content-length", str(len(body)))
        self.send_header("cache-control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            return self._send(200, (ROOT / "web" / "index.html").read_bytes(), "text/html; charset=utf-8")
        if path == "/api/health":
            return self._send(200, {"ok": True, "model": MODEL, "fake": FAKE})
        self._send(404, {"error": "not_found"})

    def do_POST(self):
        try:
            n = int(self.headers.get("content-length") or 0)
            if n > MAX_PDF:
                raise ApiError(413, "too_big")
            raw = self.rfile.read(n)
            if self.path == "/api/explain":
                return self._send(200, explain(raw))
            if self.path == "/api/ask":
                return self._send(200, ask(json.loads(raw or b"{}")))
            self._send(404, {"error": "not_found"})
        except ApiError as e:
            print(f"{self.path}: {e.code} {e.detail}", file=sys.stderr, flush=True)
            self._send(e.status, {"error": e.code})
        except Exception as e:
            print(f"{self.path}: {e!r}", file=sys.stderr, flush=True)
            self._send(500, {"error": "server"})

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print(f"Klartext on http://localhost:{port}  model={MODEL}{'  FAKE MODE' if FAKE else ''}", flush=True)
    ThreadingHTTPServer(("", port), Handler).serve_forever()
