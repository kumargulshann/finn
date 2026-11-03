import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import re
from decimal import Decimal, InvalidOperation

METRICS = {
    "revenue": r"(?:total\s+revenue|consolidated\s+revenue|net\s+sales|total\s+income|\brevenues?\b)",
    "EBITDA": r"(?:consolidated\s+EBITDA|EBITDAaL|EBITDA|earnings before interest,? taxes,? depreciation and amorti[sz]ation)",
    "EBITDA margin": r"(?:EBITDA\s+margin|EBITDAaL\s+margin|EBITDA\s+as\s+a\s+percentage)",
    "operating margin": r"(?:operating\s+margins?|EBIT\s+margin)",
    "PAT": r"(?:profit\s+after\s+tax|net\s+profit|\bPAT\b)",
    "revenue growth": r"(?:revenue\s+growth|sales\s+growth|revenues?\s+grew|growth\s+in\s+revenues?)",
    "ARPU": r"\bARPU\b",
    "cash flow from operations": r"(?:cash flow from operations|operating cash flow)",
}

MONETARY_METRICS = {"revenue", "EBITDA", "PAT", "ARPU", "cash flow from operations"}
RATIO_METRICS = {"revenue growth", "operating margin", "EBITDA margin"}

SEGMENT_PREFIX = re.compile(r"\b(AI|cloud|digital|third\s*party|b2b|retail|mobility|segment|product|service|airtel\s+money|subsidiary)\s*$", re.I)
REVENUE_SHARE_RE = re.compile(r"\b\d+[\d.]*%\s+(?:of\s+(?:total\s+|our\s+)?revenue|revenue\s+share)\b", re.I)

# Direct value pattern after metric
VALUE_RE = re.compile(r"(?P<curr>₹|\$|INR|Rs\.?)?\s*(?P<num>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>%|percent|bps|basis points|₹|INR|Rs\.?|crore(?:s)?|cr\.?|million|billion|lakh(?:s)?|mn|bn)?", re.I)

def parse_metric_value(sentence: str, metric: str, metric_match: re.Match[str]) -> tuple[str, Decimal] | None:
    # 1. Segment revenue exclusion
    if metric == "revenue":
        prefix = sentence[:metric_match.start()].strip()
        if SEGMENT_PREFIX.search(prefix):
            return None
        # Exclude phrases like "as a percentage of revenue" or "% of revenue"
        if re.search(r"%\s+(?:of\s+)?(?:total\s+|our\s+)?revenue\b", sentence, re.I):
            # If the metric match itself is followed by "% of", skip
            if re.match(r"\s+was\s+(?:a\s+standout\s+at\s+)?\d+[\d.]*%", sentence[metric_match.end():], re.I):
                return None

    # 2. Extract tail after metric, cutting off at clause boundaries that introduce different subjects
    # Do NOT cut at abbreviations like "Rs." or "dt." or "U.S."
    tail = sentence[metric_match.end():]
    clause_break = re.search(r"(?:,\s*(?:while|whereas|but|although|where|accounts?\s+for|reflecting|offset\s+by)|;\s*)", tail, re.I)
    if clause_break:
        tail = tail[:clause_break.start()]

    # If monetary metric (PAT, revenue, EBITDA, cash flow, ARPU):
    if metric in MONETARY_METRICS:
        # Search for monetary amount: Rs./INR/$/₹ with numbers and crore/million/billion/etc.
        monetary_re = re.compile(
            r"(?:(?P<curr>₹|\$|INR|Rs\.?)\s*)?(?P<num>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>crore(?:s)?|cr\.?|million|billion|lakh(?:s)?|mn|bn|₹|INR|Rs\.?)?",
            re.I
        )
        matches = []
        for m in monetary_re.finditer(tail[:150]):
            curr = m.group("curr")
            unit_str = m.group("unit")
            num_str = m.group("num")
            # Must have either a currency symbol or a monetary unit (crore, million, etc.)
            if num_str and (curr or (unit_str and unit_str.lower() not in {"%", "percent", "bps"})):
                matches.append((m, curr, unit_str, num_str))
        
        if not matches:
            # Check preceding text: e.g. "Rs. 58,500 crore of revenue"
            pre_tail = sentence[max(0, metric_match.start() - 60):metric_match.start()]
            for m in monetary_re.finditer(pre_tail):
                curr = m.group("curr")
                unit_str = m.group("unit")
                num_str = m.group("num")
                if num_str and (curr or unit_str):
                    matches.append((m, curr, unit_str, num_str))
        
        if not matches:
            return None
        
        m, curr, raw_unit, raw_num = matches[0]
        try:
            val = Decimal(raw_num.replace(",", ""))
        except InvalidOperation:
            return None
        
        unit_check = (raw_unit or curr or "").lower().replace(".", "").strip()
        if unit_check in {"crore", "crores", "cr"}: unit = "INR crore"
        elif unit_check in {"₹", "inr", "rs"}: unit = "INR"
        elif unit_check in {"million", "mn"}: unit = "million"
        elif unit_check in {"billion", "bn"}: unit = "billion"
        elif unit_check in {"lakh", "lakhs"}: unit = "lakh"
        elif unit_check in {"$", "usd"}: unit = "USD"
        else: unit = unit_check.upper()
        return unit, val

    # If ratio metric (operating margin, EBITDA margin, revenue growth):
    if metric in RATIO_METRICS:
        ratio_re = re.compile(
            r"(?P<num>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>%|percent|bps|basis points)",
            re.I
        )
        matches = list(ratio_re.finditer(tail[:120]))
        if not matches:
            pre_tail = sentence[max(0, metric_match.start() - 40):metric_match.start()]
            matches = list(ratio_re.finditer(pre_tail))
        if not matches:
            return None
        
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
    m = re.search(METRICS[metric], s, re.I)
    res = parse_metric_value(s, metric, m) if m else None
    print(f"\nMetric: {metric}")
    print(f"Sentence: {s}")
    print(f"Parsed: {res}")

