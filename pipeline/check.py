# Flags any number/date in the AI output that does not appear in the letter (normalising . , and spaces).
import json, re, sys
letter = open(sys.argv[1]).read()
out = json.dumps(json.load(open(sys.argv[2])), ensure_ascii=False)
norm = lambda s: re.sub(r"[\s]", "", s).replace(",", ".")
L = norm(letter)
nums = set(re.findall(r"\d+(?:[.,]\d+)*(?:/\d+)?", out))
missing = sorted(n for n in nums if norm(n) not in L)
print("numbers checked:", len(nums)); print("not found in letter:", missing)
