import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import re
from decimal import Decimal

sentence = "Profit after tax grew by 20.1% year-on-year to ₹14,843 crore in Q2-2027"
print("Sentence:", sentence)

VALUE_RE = re.compile(r"(?P<num>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>%|percent|bps|basis points|₹|INR|Rs\.?|crore(?:s)?|cr\.?|million|billion|lakh(?:s)?)?", re.I)
match = VALUE_RE.search(sentence[sentence.find("Profit after tax") + len("Profit after tax"):])
print("Current extracted:", match.group("num"), match.group("unit"))

# What we want for PAT (monetary):
MONEY_RE = re.compile(r"(?:(?:₹|INR|Rs\.?|USD|\$)\s*)?(?P<num>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>crore(?:s)?|cr\.?|million|billion|lakh(?:s)?|₹|INR|Rs\.?)", re.I)
for m in MONEY_RE.finditer(sentence):
    print("Money match:", m.group("num"), m.group("unit"))
