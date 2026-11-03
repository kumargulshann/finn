import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import re
from decimal import Decimal, InvalidOperation

PAT_RATIO_REF = re.compile(r"\b(?:%\s+of|percentage\s+of|as\s+a\s+multiple\s+of|relative\s+to)\s+(?:net\s+profit|PAT|profit\s+after\s+tax)\b", re.I)
SEGMENT_GROWTH_RE = re.compile(r"\b(digital\s+business(?:es)?|retail|enterprise|b2b|mobility|cloud|ai|fintech|subsidiary)\s+.*?\brevenue\s+growth\b", re.I)

s1 = "Free cash flow generation was strong at $928 mn at 113% of net profit."
print("s1 is PAT denominator?", bool(PAT_RATIO_REF.search(s1)))

s2 = "Our digital businesses delivered another quarter of solid performance with revenue growth of nearly 6% sequentially."
print("s2 is segment growth?", bool(SEGMENT_GROWTH_RE.search(s2)))

s3 = "Our revenue grew 0.6% sequentially and 1.7% year-on-year in constant currency terms."
# Find all growth numbers with context
GROWTH_NUMS = list(re.finditer(r"(?P<num>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>%|percent|bps)\s*(?P<ctx>sequentially|quarter-on-quarter|qoq|year-on-year|yoy|y-on-y)?", s3, re.I))
for m in GROWTH_NUMS:
    print("Growth match:", m.group("num"), m.group("unit"), m.group("ctx"))

