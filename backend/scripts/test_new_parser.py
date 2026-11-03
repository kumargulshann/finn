import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import re
from decimal import Decimal, InvalidOperation

MONETARY_METRICS = {"revenue", "EBITDA", "PAT", "ARPU", "cash flow from operations"}
RATIO_METRICS = {"revenue growth", "operating margin", "EBITDA margin"}

SEGMENT_REVENUE_PREFIX = re.compile(r"\b(AI|cloud|digital|third\s*party|b2b|retail|mobility|segment|product|service|airtel\s+money|subsidiary)\s*$", re.I)
REVENUE_SHARE_RE = re.compile(r"\b\d+[\d.]*%\s+(?:of\s+(?:total\s+|our\s+)?revenue|revenue\s+share)\b", re.I)

# Direct value pattern after metric
VALUE_RE = re.compile(r"(?P<curr>₹|\$|INR|Rs\.?)?\s*(?P<num>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>%|percent|bps|basis points|₹|INR|Rs\.?|crore(?:s)?|cr\.?|million|billion|lakh(?:s)?|mn|bn)?", re.I)

def parse_metric_value(sentence: str, metric: str, metric_match: re.Match[str]) -> tuple[str, Decimal] | None:
    # 1. Segment revenue check
    if metric == "revenue":
        prefix = sentence[:metric_match.start()].strip()
        if SEGMENT_REVENUE_PREFIX.search(prefix):
            return None
        if REVENUE_SHARE_RE.search(sentence):
            # If the entire sentence is about a share of revenue, ensure we don't pick the share %
            pass

    # 2. Extract tail after metric, cutting off at clause boundaries that introduce different subjects
    tail = sentence[metric_match.end():]
    # Clause boundary truncation
    clause_break = re.search(r"(?:,\s*(?:while|whereas|but|although|where|accounts?\s+for|reflecting|offset\s+by)|;\s*|\.\s*)", tail, re.I)
    if clause_break:
        tail = tail[:clause_break.start()]

    # If monetary metric (PAT, revenue, EBITDA, cash flow, ARPU):
    if metric in MONETARY_METRICS:
        # We need a monetary amount.
        # Notice in "Profit after tax grew by 20.1% year-on-year to ₹14,843 crore":
        # There may be a growth % in between! We must look specifically for the monetary value, NOT the %!
        # Search for currency or monetary units
        monetary_re = re.compile(
            r"(?:(?P<curr>₹|\$|INR|Rs\.?)\s*)?(?P<num>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>crore(?:s)?|cr\.?|million|billion|lakh(?:s)?|mn|bn|₹|INR|Rs\.?)",
            re.I
        )
        # Also handle bare currency symbol prefix like ₹14,843 or $5,145
        matches = list(monetary_re.finditer(tail[:150]))
        if not matches:
            # Check preceding text: e.g. "Rs. 58,500 crore of revenue"
            pre_tail = sentence[max(0, metric_match.start() - 60):metric_match.start()]
            matches = list(monetary_re.finditer(pre_tail))
        if not matches:
            return None
        # Choose the first matching monetary amount
        m = matches[0]
        raw_num = m.group("num").replace(",", "")
        try:
            val = Decimal(raw_num)
        except InvalidOperation:
            return None
        raw_unit = (m.group("unit") or m.group("curr") or "").lower().replace(".", "").strip()
        if raw_unit in {"crore", "crores", "cr"}: unit = "INR crore"
        elif raw_unit in {"₹", "inr", "rs"}: unit = "INR"
        elif raw_unit in {"million", "mn"}: unit = "million"
        elif raw_unit in {"billion", "bn"}: unit = "billion"
        elif raw_unit in {"lakh", "lakhs"}: unit = "lakh"
        elif raw_unit in {"$", "usd"}: unit = "USD"
        else: unit = raw_unit.upper()
        return unit, val

    # If ratio metric (operating margin, EBITDA margin, revenue growth):
    if metric in RATIO_METRICS:
        # MUST have % or bps!
        ratio_re = re.compile(
            r"(?P<num>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>%|percent|bps|basis points)",
            re.I
        )
        # Direct proximity check:
        # In "operating margin guidance remains at 20% to 22%" -> 20%
        # In "Operating margin was stable at 21%." -> 21%
        # In "Our revenue growth for Q2 was 1.5% YoY" -> 1.5%
        # In "revenue grew 0.6% sequentially and 1.7% year-on-year" -> if YoY, 1.7%, else 0.6%
        matches = list(ratio_re.finditer(tail[:120]))
        if not matches:
            # Check preceding text: e.g. "1.5% revenue growth"
            pre_tail = sentence[max(0, metric_match.start() - 40):metric_match.start()]
            matches = list(ratio_re.finditer(pre_tail))
        if not matches:
            return None
        
        # For revenue growth, if both YoY and sequential exist, prefer YoY
        selected_m = matches[0]
        if metric == "revenue growth" and len(matches) > 1:
            for cand in matches:
                surrounding = tail[cand.start():cand.end() + 30].lower()
                if "year-on-year" in surrounding or "yoy" in surrounding or "y-on-y" in surrounding:
                    selected_m = cand
                    break

        raw_num = selected_m.group("num").replace(",", "")
        try:
            val = Decimal(raw_num)
        except InvalidOperation:
            return None
        raw_unit = selected_m.group("unit").lower().strip()
        unit = "bps" if "bps" in raw_unit or "basis" in raw_unit else "%"
        return unit, val

    return None

test_cases = [
    ("Profit after tax grew by 20.1% year-on-year to ₹14,843 crore in Q2-2027", "PAT"),
    ("Profit after tax grew by 15.9% year-on-year to ₹14,805 crore in Q1-2027", "PAT"),
    ("Our consolidated revenue was Rs.58,500 Crores, growing at about 5.7%", "revenue"),
    ("AI revenue was a standout at 10.5% of our revenue, growing at 29%", "revenue"),
    ("Our AI services revenue was 8.2% of overall revenue in Q1.", "revenue"),
    ("Q2 revenues were $5,145 mn, an increase of 1.2% sequentially", "revenue"),
    ("Our revenue growth for Q2 was 1.5% YoY and 1.2% sequentially in constant currency terms.", "revenue growth"),
    ("Our revenue grew 0.6% sequentially and 1.7% year-on-year in constant currency terms.", "revenue growth"),
    ("Revenue growth was below our expectations, while AI first revenue now accounts for 10.5% of our total revenue", "revenue growth"),
    ("Our operating margin guidance remains at 20% to 22%", "operating margin"),
    ("Operating margin was stable at 21%.", "operating margin"),
    ("Q2 operating margins were at 21%, decline of 0.1% sequentially.", "operating margin"),
    ("Our operating margin was 21.1%.", "operating margin"),
    ("Our consolidated EBITDAaL was at Rs.29,800 Crores, this is a growth of 4.2%", "EBITDA"),
]

for s, metric in test_cases:
    m = re.search(re.escape(metric) if metric in s.lower() else r"(?:revenue|operating margin|profit after tax|ebitda)", s, re.I)
    res = parse_metric_value(s, metric, m)
    print(f"\nMetric: {metric}")
    print(f"Sentence: {s}")
    print(f"Parsed: {res}")

