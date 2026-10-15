"""Checks a MediKlar explanation (JSON) against the original doctor's letter.

Usage:  python3 check.py letter.txt out.json      (exit code 1 if problems are found)

What it checks
1. Shape: every field the app needs is there, with the right type and allowed values.
2. Numbers: every number, date, time and dose in the explanation must appear in the letter
   (as a whole number, not just as part of a longer one). Written dates such as
   "23 June 2022" or "Mai 2023" are converted and checked too.
3. Phone numbers: digits must match a phone number in the letter exactly.
4. Medicines: each medicine must be on the letter's discharge list, with the same strength
   and the same morning-midday-evening-night schedule; none may be left out.
5. Quotes (warning only): longer phrases in details_1to1[].original should be in the letter.
"""
import json
import re
import sys

LEVELS = {"calm", "act_soon", "urgent"}
SOURCES = {"letter", "general", "not_in_letter"}
SLOTS = ("morning", "midday", "evening", "night")

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7,
    "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "januar": 1, "jänner": 1, "februar": 2, "märz": 3, "maerz": 3, "mai": 5, "juni": 6,
    "juli": 7, "oktober": 10, "dezember": 12,
}
MONTH_RE = "|".join(sorted(MONTHS, key=len, reverse=True))

# Number-like tokens, longest forms first: dates, month/year, times, decimals, integers.
TOKEN_RE = re.compile(
    r"\d{1,2}\.\d{1,2}\.\d{2,4}"      # 23.06.2022
    r"|\d{1,2}/\d{4}"                  # 05/2023
    r"|\d{1,2}:\d{2}"                  # 09:00
    r"|\d+(?:[.,]\d+)?"                # 2,75  1.5  100
)


def _norm_token(t):
    if re.fullmatch(r"\d+,\d+", t):
        t = t.replace(",", ".")
    if re.fullmatch(r"\d{1,2}/\d{4}", t):           # 5/2023 -> 05/2023
        m, y = t.split("/")
        t = f"{int(m):02d}/{y}"
    if re.fullmatch(r"\d{1,2}\.\d{1,2}\.\d{4}", t):  # 1.6.2022 -> 01.06.2022
        d, m, y = t.split(".")
        t = f"{int(d):02d}.{int(m):02d}.{y}"
    return t


def tokens(text):
    return [_norm_token(t) for t in TOKEN_RE.findall(text)]


def letter_index(letter):
    toks = set(tokens(letter))
    # month/year forms of every full date, so "June 2022" can match "23.06.2022"
    for d in re.findall(r"\d{1,2}\.(\d{1,2})\.(\d{4})", letter):
        toks.add(f"{int(d[0]):02d}/{d[1]}")
    # month names written in the letter ("Mai 2022")
    for m, y in re.findall(rf"\b({MONTH_RE})\s+(\d{{4}})\b", letter, re.I):
        toks.add(f"{MONTHS[m.lower()]:02d}/{y}")
    phones = set()
    for line in letter.splitlines():
        for run in re.findall(r"\+?\d[\d\s/()-]{4,}\d", line):
            phones.add(re.sub(r"\D", "", run))
    return toks, phones


def _strings(obj, path=""):
    """Yield (path, string) for every string in the JSON."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _strings(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _strings(v, f"{path}[{i}]")
    elif isinstance(obj, str):
        yield path, obj


# ---------------------------------------------------------------- 1. shape
def check_shape(out):
    issues = []

    def need(obj, key, typ, where):
        if not isinstance(obj, dict) or key not in obj:
            issues.append(f"shape: missing '{where}{key}'")
            return None
        v = obj[key]
        if typ is not None and not isinstance(v, typ):
            issues.append(f"shape: '{where}{key}' should be {typ.__name__}")
            return None
        return v

    if not isinstance(out, dict):
        return ["shape: top level must be a JSON object"]
    w = need(out, "worry", dict, "")
    if w:
        if need(w, "level", str, "worry.") not in LEVELS:
            issues.append("shape: worry.level must be calm, act_soon or urgent")
        need(w, "headline", str, "worry.")
        need(w, "reason", str, "worry.")
    need(out, "about_one_sentence", str, "")
    for i, t in enumerate(need(out, "todos", list, "") or []):
        for k in ("action", "detail", "when"):
            need(t, k, str, f"todos[{i}].")
        if not isinstance(t, dict) or t.get("source") not in SOURCES:
            issues.append(f"shape: todos[{i}].source must be one of {sorted(SOURCES)}")
    f = need(out, "if_not", dict, "")
    if f:
        if f.get("source") not in SOURCES:
            issues.append("shape: if_not.source must be letter, general or not_in_letter")
        need(f, "points", list, "if_not.")
    sp = need(out, "summary_paragraphs", list, "")
    if sp is not None and not sp:
        issues.append("shape: summary_paragraphs is empty")
    for i, m in enumerate(need(out, "medicines", list, "") or []):
        for k in ("name", "dose", "form"):
            need(m, k, str, f"medicines[{i}].")
        for k in SLOTS:
            v = m.get(k) if isinstance(m, dict) else None
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                issues.append(f"shape: medicines[{i}].{k} must be a number")
    for i, j in enumerate(need(out, "jargon", list, "") or []):
        need(j, "term", str, f"jargon[{i}].")
        need(j, "plain", str, f"jargon[{i}].")
    for i, d in enumerate(need(out, "details_1to1", list, "") or []):
        for k in ("section", "original", "plain"):
            need(d, k, str, f"details_1to1[{i}].")
    for i, q in enumerate(need(out, "faq", list, "") or []):
        need(q, "q", str, f"faq[{i}].")
        need(q, "a", str, f"faq[{i}].")
        if not isinstance(q, dict) or q.get("source") not in SOURCES:
            issues.append(f"shape: faq[{i}].source must be one of {sorted(SOURCES)}")
    for i, c in enumerate(need(out, "contacts", list, "") or []):
        need(c, "who", str, f"contacts[{i}].")
        need(c, "phone", str, f"contacts[{i}].")
    return issues


# ---------------------------------------------------------------- 2. numbers and dates
WRITTEN_DATE_RE = rf"(?:(\d{{1,2}})\.?\s+)?\b({MONTH_RE})\b\s+(\d{{4}})"


def check_numbers(letter, out):
    toks, _ = letter_index(letter)
    issues, checked = [], 0
    for path, s in _strings(out):
        if path.startswith("contacts") and path.endswith(".phone"):
            continue  # checked separately, digit by digit
        # written dates: "23 June 2022", "June 2022", "Mai 2023"
        for day, mon, year in re.findall(WRITTEN_DATE_RE, s, re.I):
            checked += 1
            mm = MONTHS[mon.lower()]
            want = f"{int(day):02d}.{mm:02d}.{year}" if day else f"{mm:02d}/{year}"
            if want not in toks:
                issues.append(f"date not in letter: '{(day + ' ') if day else ''}{mon} {year}' at {path}")
        rest = re.sub(WRITTEN_DATE_RE, " ", s, flags=re.I)
        for t in tokens(rest):
            checked += 1
            if t not in toks:
                issues.append(f"number not in letter: '{t}' at {path}")
    return issues, checked


# ---------------------------------------------------------------- 2b. numbers with units
# A number next to a unit must appear in the letter next to the same kind of unit,
# so "3 litres" fails even though some other "3" is in the letter.
UNITS = {
    "volume": r"litres?|liters?|liter|l(?=/|\b)",
    "mass": r"mg|µg|mcg|micrograms?|mikrogramm|milligrams?|milligramm",
    "gfr": r"ml/min",
    "rate": r"/\s*min\b|beats? per minute|per minute|pro minute|schläge pro minute",
    "length": r"mm\b|millimet(?:re|er)s?",
    "months": r"months?|monate?n?",
    "weeks": r"weeks?|wochen?",
    "days": r"days?|tagen?|tage",
    "age": r"-?\s*years?[- ]old|-?jährige?[rn]?",
}
NUM = r"(\d+(?:[.,]\d+)?)"
RANGE_UNIT_RE = re.compile(
    rf"{NUM}(?:\s*(?:-|–|to|bis|and|und)\s*{NUM})?\s*(?:x\s*{NUM}\s*)?({'|'.join(f'(?:{u})' for u in UNITS.values())})",
    re.I)


def _unit_kind(u):
    for kind, pat in UNITS.items():
        if re.fullmatch(pat, u.strip(), re.I):
            return kind
    for kind, pat in UNITS.items():
        if re.match(pat, u.strip(), re.I):
            return kind
    return None


def unit_pairs(text):
    pairs = set()
    for a, b, c, u in RANGE_UNIT_RE.findall(text):
        kind = _unit_kind(u)
        for n in (a, b, c):
            if n:
                pairs.add((_norm_token(n), kind))
    return pairs


def check_units(letter, out):
    have = unit_pairs(letter)
    issues = []
    for path, s in _strings(out):
        if path.startswith("contacts"):
            continue
        for n, kind in unit_pairs(s):
            if kind and (n, kind) not in have:
                issues.append(f"amount not in letter: '{n}' with unit type '{kind}' at {path}")
    return issues


# ---------------------------------------------------------------- 3. phone numbers
def check_phones(letter, out):
    _, phones = letter_index(letter)
    issues = []
    for i, c in enumerate(out.get("contacts") or []):
        if not isinstance(c, dict):
            continue
        digits = re.sub(r"\D", "", str(c.get("phone", "")))
        if not digits:
            issues.append(f"phone missing at contacts[{i}]")
        elif digits not in phones:
            issues.append(f"phone not in letter: '{c.get('phone')}' at contacts[{i}]")
    return issues


# ---------------------------------------------------------------- 4. medicines
def letter_medicines(letter):
    """Parse the discharge medication list of a German eArztbrief.

    Returns {key: {"name", "strength", "schedule"}}, or {} if the letter has no such list.
    """
    m = re.search(r"Medikation\s+Entlassung(.*)", letter, re.S)
    text = m.group(1) if m else letter
    entries = {}
    for b in re.split(r"Code/Bezeichnung:", text)[1:]:
        lines = b.strip().splitlines()
        if not lines:
            continue
        name = lines[0].strip()
        sched = re.search(
            r"Dosierschema\s+Freitext:\s*([\d.,½]+)\s*[–-]\s*([\d.,½]+)\s*[–-]\s*([\d.,½]+)\s*[–-]\s*([\d.,½]+)", b)
        if not sched or not name:
            continue
        strength = re.search(r"(\d+(?:[.,]\d+)?)\s*(mg|µg|mcg|mikrogramm|g|ml|ie|i\.e\.)(?!\w)", name, re.I)
        entries[name.split()[0].lower()] = {
            "name": name,
            "strength": _norm_token(strength.group(1)) if strength else None,
            "schedule": tuple(float(x.replace("½", "0.5").replace(",", ".")) for x in sched.groups()),
        }
    return entries


def check_medicines(letter, out):
    want = letter_medicines(letter)
    if not want:
        return [], "no structured medication list in letter; medicine check skipped"
    issues, seen = [], set()
    fmt = lambda t: " – ".join(f"{x:g}" for x in t)
    for i, m in enumerate(out.get("medicines") or []):
        if not isinstance(m, dict):
            continue
        name = str(m.get("name", ""))
        key = next((k for k in want if re.search(rf"(?<!\w){re.escape(k)}(?!\w)", name, re.I)), None)
        if not key:
            issues.append(f"medicine not on the letter's discharge list: '{name}' at medicines[{i}]")
            continue
        seen.add(key)
        w = want[key]
        got = tuple(float(m[s]) if isinstance(m.get(s), (int, float)) and not isinstance(m.get(s), bool) else -1
                    for s in SLOTS)
        if got != w["schedule"]:
            issues.append(f"schedule wrong for {name}: output {fmt(got)}, letter {fmt(w['schedule'])}")
        if w["strength"] and w["strength"] not in tokens(name + " " + str(m.get("dose", ""))):
            issues.append(f"strength wrong for {name}: letter says {w['strength']}")
    for k, w in want.items():
        if k not in seen:
            issues.append(f"medicine left out: '{w['name']}' is on the letter's discharge list")
    return issues, None


# ---------------------------------------------------------------- 5. quotes (warning only)
def check_quotes(letter, out):
    """details_1to1[].original should be copied from the letter. The letter is a form, so the
    model may join a field label and its value; we only warn about phrases of 4+ words that
    are not in the letter."""
    flat = re.sub(r"\s+", " ", letter)
    warnings = []
    for i, d in enumerate(out.get("details_1to1") or []):
        if not isinstance(d, dict):
            continue
        for seg in re.split(r"[…,:;()]|\.\s", str(d.get("original", ""))):
            seg = re.sub(r"\s+", " ", seg).strip(" .")
            if len(seg.split()) >= 4 and seg not in flat:
                warnings.append(f"quote not word for word in letter: '{seg}' at details_1to1[{i}]")
    return warnings


def check(letter, out):
    """Return (issues, notes, stats). An empty issues list means the output passed."""
    issues = check_shape(out)
    if not isinstance(out, dict):
        return issues, [], {}
    num_issues, n = check_numbers(letter, out)
    med_issues, med_note = check_medicines(letter, out)
    issues += num_issues + check_units(letter, out) + check_phones(letter, out) + med_issues
    notes = ([med_note] if med_note else []) + check_quotes(letter, out)
    return issues, notes, {"numbers_checked": n, "medicines_in_letter": len(letter_medicines(letter))}


def main():
    if len(sys.argv) != 3:
        sys.exit("usage: python3 check.py letter.txt out.json")
    letter = open(sys.argv[1], encoding="utf-8").read()
    out = json.load(open(sys.argv[2], encoding="utf-8"))
    issues, notes, stats = check(letter, out)
    for k, v in stats.items():
        print(f"{k}: {v}")
    for n in notes:
        print("note:", n)
    if issues:
        print(f"PROBLEMS ({len(issues)}):")
        for i in issues:
            print(" -", i)
        sys.exit(1)
    print("OK: everything checked matches the letter")


if __name__ == "__main__":
    main()
