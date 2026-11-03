import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import sqlite3
import re
from pathlib import Path
from decimal import Decimal, InvalidOperation

db_path = Path(__file__).resolve().parents[1] / "data" / "finn.db"
con = sqlite3.connect(str(db_path))
cur = con.cursor()

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
ANNUAL_SCOPE_RE = re.compile(r"\b(full\s*year|financial\s*year|fiscal\s*year|for\s+the\s+year|for\s+FY\s*['’]?\d{2,4}|full-year|annual(?:ly)?)\b", re.I)
QUARTER_SCOPE_RE = re.compile(r"\b(Q[1-4]|first\s+quarter|second\s+quarter|third\s+quarter|fourth\s+quarter|quarter\s+ended)\b", re.I)

GUIDE_RE = re.compile(r"\b(guid(?:e|ed|ance)|expect(?:s|ed)?|outlook|target|forecast|aim(?:s|ed)?)\b", re.I)
ACTUAL_RE = re.compile(r"\b(reported|recorded|delivered|achieved|stood at|was|were|grew|declined|increased|decreased|actual(?:ly)?)\b", re.I)

def parse_metric_value(sentence: str, metric: str, metric_match: re.Match[str]) -> tuple[str, Decimal] | None:
    if metric == "revenue":
        prefix = sentence[:metric_match.start()].strip()
        if SEGMENT_PREFIX.search(prefix):
            return None
        if re.search(r"%\s+(?:of\s+)?(?:total\s+|our\s+)?revenue\b", sentence, re.I):
            if re.match(r"\s+was\s+(?:a\s+standout\s+at\s+)?\d+[\d.]*%", sentence[metric_match.end():], re.I):
                return None

    tail = sentence[metric_match.end():]
    clause_break = re.search(r"(?:,\s*(?:while|whereas|but|although|where|accounts?\s+for|reflecting|offset\s+by)|;\s*)", tail, re.I)
    if clause_break:
        tail = tail[:clause_break.start()]

    if metric in MONETARY_METRICS:
        monetary_re = re.compile(
            r"(?:(?P<curr>₹|\$|INR|Rs\.?)\s*)?(?P<num>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>crore(?:s)?|cr\.?|million|billion|lakh(?:s)?|mn|bn|₹|INR|Rs\.?)?",
            re.I
        )
        matches = []
        for m in monetary_re.finditer(tail[:150]):
            curr = m.group("curr")
            unit_str = m.group("unit")
            num_str = m.group("num")
            if num_str and (curr or (unit_str and unit_str.lower() not in {"%", "percent", "bps"})):
                matches.append((m, curr, unit_str, num_str))
        if not matches:
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

def extract_facts(text: str, doc_period: str | None) -> list[dict]:
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if len(s.strip()) >= 20]
    facts = []
    for sentence in sentences:
        kind = "guided" if GUIDE_RE.search(sentence) else "actual" if ACTUAL_RE.search(sentence) else None
        if not kind:
            continue
        
        # Check scope / measurement basis
        is_annual = bool(ANNUAL_SCOPE_RE.search(sentence)) and not bool(QUARTER_SCOPE_RE.search(sentence))
        scope = "annual" if is_annual else "quarterly"

        period = doc_period
        for metric, pattern in METRICS.items():
            match = re.search(pattern, sentence, re.I)
            if not match:
                continue
            if metric == "revenue" and re.match(r"\s+growth\b", sentence[match.end():], re.I):
                continue
            if metric == "EBITDA" and re.match(r"\s+margin\b", sentence[match.end():], re.I):
                continue
            parsed = parse_metric_value(sentence, metric, match)
            if parsed:
                unit, value = parsed
                facts.append({
                    "kind": kind,
                    "period": period,
                    "metric": metric,
                    "unit": unit,
                    "value": value,
                    "scope": scope,
                    "excerpt": sentence,
                })
    return facts

for comp_name in ["Infosys", "ICICI Bank", "Bharti Airtel"]:
    c_row = cur.execute('SELECT id FROM companies WHERE name LIKE ?', (f'%{comp_name}%',)).fetchone()
    if not c_row:
        continue
    comp_id = c_row[0]
    docs = cur.execute('SELECT id, title, fiscal_period FROM research_documents WHERE company_id=? AND document_type="earnings_transcript" ORDER BY fiscal_period DESC', (comp_id,)).fetchall()
    print(f"\n=======================================================")
    print(f"Company: {comp_name} (transcripts: {len(docs)})")
    
    # Group facts by period
    facts_by_period = {}
    for doc_id, title, period in docs:
        chunks = cur.execute('SELECT page_number, text FROM research_chunks WHERE document_id=? ORDER BY page_number ASC', (doc_id,)).fetchall()
        for p_num, text in chunks:
            for f in extract_facts(text, period):
                f['page'] = p_num
                f['doc_title'] = title
                facts_by_period.setdefault(period, []).append(f)
                
    for period, facts in sorted(facts_by_period.items(), reverse=True):
        print(f"\n--- Period: {period} ---")
        for m_name in METRICS:
            # Find guided and actual
            # For quarterly review:
            # - Actual must be quarterly
            # - Guided for ratio metrics (margins): quarterly or annual margin target applies
            # - Guided for volume/growth (revenue growth, revenue): must match quarterly scope!
            guided = next((f for f in facts if f["metric"] == m_name and f["kind"] == "guided" and (f["scope"] == "quarterly" or m_name in {"operating margin", "EBITDA margin"})), None)
            actual = next((f for f in facts if f["metric"] == m_name and f["kind"] == "actual" and f["scope"] == "quarterly"), None)
            
            if guided or actual:
                same_unit = guided and actual and guided["unit"] == actual["unit"]
                variance = actual["value"] - guided["value"] if same_unit else None
                status = "Unavailable"
                if same_unit:
                    status = "Met" if variance == 0 else "Not determinable"
                print(f"  Metric: {m_name}")
                print(f"    Guided: {guided['value'] if guided else None} {guided['unit'] if guided else ''} (p.{guided['page'] if guided else '-'})")
                print(f"    Actual: {actual['value'] if actual else None} {actual['unit'] if actual else ''} (p.{actual['page'] if actual else '-'})")
                print(f"    Variance: {variance} | Status: {status}")
                if guided: print(f"      [Guided Excerpt]: {guided['excerpt'][:80]}...")
                if actual: print(f"      [Actual Excerpt]: {actual['excerpt'][:80]}...")

