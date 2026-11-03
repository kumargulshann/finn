"""Conservative, extractive guidance-to-actual comparison from indexed filings."""
from __future__ import annotations

import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import ResearchChunk, ResearchDocument
from app.integrations.documents.nse_provider import NSEResearchDocumentProvider

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

SEGMENT_PREFIX = re.compile(
    r"\b(AI|cloud|digital|third\s*party|b2b|retail|mobility|segment|product|service|airtel\s+money|subsidiary)\s*$",
    re.I,
)
PAT_RATIO_REF = re.compile(
    r"\b(?:%\s+of|percentage\s+of|as\s+a\s+multiple\s+of|relative\s+to)\s+(?:net\s+profit|PAT|profit\s+after\s+tax)\b",
    re.I,
)
SEGMENT_GROWTH_RE = re.compile(
    r"\b(digital\s+business(?:es)?|retail|enterprise|b2b|mobility|cloud|ai|fintech|subsidiary)\s+.*?\brevenue\s+growth\b",
    re.I,
)
ANNUAL_SCOPE_RE = re.compile(
    r"\b(full\s*year|financial\s*year|fiscal\s*year|for\s+the\s+year|for\s+FY\s*['’]?\d{2,4}|full-year|annual(?:ly)?)\b",
    re.I,
)
QUARTER_SCOPE_RE = re.compile(
    r"\b(Q[1-4]|first\s+quarter|second\s+quarter|third\s+quarter|fourth\s+quarter|quarter\s+ended)\b",
    re.I,
)

PERIOD_RE = re.compile(r"\bQ([1-4])\s*(?:of\s*|-)?\s*FY\s*['’]?\s*(20\d{2}|\d{2})\b", re.I)
GUIDE_RE = re.compile(r"\b(guid(?:e|ed|ance)|expect(?:s|ed)?|outlook|target|forecast|aim(?:s|ed)?)\b", re.I)
ACTUAL_RE = re.compile(r"\b(reported|recorded|delivered|achieved|stood at|was|were|grew|declined|increased|decreased|actual(?:ly)?)\b", re.I)


def _period(text: str, fallback: str | None) -> str | None:
    m = PERIOD_RE.search(text)
    if m:
        return f"Q{m.group(1)} FY{m.group(2)[-2:]}"
    m2 = re.search(r"\bQ([1-4])\s*[-/]?\s*(20\d{2})\b", text, re.I)
    if m2:
        return f"Q{m2.group(1)} FY{int(m2.group(2)) % 100:02d}"
    if fallback:
        fm = PERIOD_RE.search(fallback)
        if fm:
            return f"Q{fm.group(1)} FY{fm.group(2)[-2:]}"
    return None


def _parse_value(sentence: str, metric: str, metric_match: re.Match[str]) -> tuple[str, Decimal] | None:
    # 1. Segment revenue exclusion
    if metric == "revenue":
        prefix = sentence[:metric_match.start()].strip()
        if SEGMENT_PREFIX.search(prefix):
            return None
        if re.search(r"%\s+(?:of\s+)?(?:total\s+|our\s+)?revenue\b", sentence, re.I):
            if re.match(r"\s+was\s+(?:a\s+standout\s+at\s+)?\d+[\d.]*%", sentence[metric_match.end():], re.I):
                return None

    # 2. PAT reference / denominator exclusion (e.g. "free cash flow was $928 mn at 113% of net profit")
    if metric == "PAT" and PAT_RATIO_REF.search(sentence):
        return None

    # 3. Segment growth exclusion (e.g. "Our digital businesses delivered ... revenue growth of 6%")
    if metric == "revenue growth" and SEGMENT_GROWTH_RE.search(sentence):
        return None

    # 4. Extract tail after metric, cutting off at clause boundaries that introduce different subjects
    tail = sentence[metric_match.end():]
    clause_break = re.search(r"(?:,\s*(?:while|whereas|but|although|where|accounts?\s+for|reflecting|offset\s+by)|;\s*)", tail, re.I)
    if clause_break:
        tail = tail[:clause_break.start()]

    # 5. Monetary metrics: MUST have monetary unit (INR, INR crore, million, billion, etc.)
    if metric in MONETARY_METRICS:
        monetary_re = re.compile(
            r"(?:(?P<curr>₹|\$|INR|Rs\.?)\s*)?(?P<num>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>crore(?:s)?|cr\.?|million|billion|lakh(?:s)?|mn|bn|₹|INR|Rs\.?)?",
            re.I,
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

    # 6. Ratio metrics: MUST have ratio unit (%, bps)
    if metric in RATIO_METRICS:
        ratio_re = re.compile(
            r"(?P<num>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>%|percent|bps|basis points)",
            re.I,
        )
        matches = list(ratio_re.finditer(tail[:120]))
        if not matches:
            pre_tail = sentence[max(0, metric_match.start() - 40):metric_match.start()]
            matches = list(ratio_re.finditer(pre_tail))
        if not matches:
            return None

        selected_m = matches[0]
        # For revenue growth, prefer YoY over sequential if both are mentioned
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


def _extract(text: str, period_fallback: str | None) -> list[dict]:
    # Normalize soft line breaks within paragraphs to spaces so wrapped sentences aren't fragmented
    normalized = re.sub(r"(?<!\n)\n(?!\n)", " ", text)
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n{2,}", normalized) if len(s.strip()) >= 20]
    facts = []
    for sentence in sentences:
        kind = "guided" if GUIDE_RE.search(sentence) else "actual" if ACTUAL_RE.search(sentence) else None
        if not kind:
            continue
        period = _period(sentence, period_fallback)
        if not period:
            continue

        is_annual = bool(ANNUAL_SCOPE_RE.search(sentence)) and not bool(QUARTER_SCOPE_RE.search(sentence))
        scope = "annual" if is_annual else "quarterly"

        for metric, pattern in METRICS.items():
            match = re.search(pattern, sentence, re.I)
            if not match:
                continue
            if metric == "revenue" and re.match(r"\s+growth\b", sentence[match.end():], re.I):
                continue
            if metric == "EBITDA" and re.match(r"\s+margin\b", sentence[match.end():], re.I):
                continue
            parsed = _parse_value(sentence, metric, match)
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


def guidance_vs_actual(session: Session, company_id: int) -> dict:
    rows = session.execute(
        select(ResearchChunk, ResearchDocument)
        .join(ResearchDocument, ResearchChunk.document_id == ResearchDocument.id)
        .where(ResearchDocument.company_id == company_id, ResearchDocument.is_demo.is_(False))
        .order_by(ResearchDocument.published_at.desc())
    ).all()

    # Ensure any transcript document with unpopulated fiscal_period is resolved from text/title/metadata
    for _, doc in rows:
        if doc.document_type == "earnings_transcript" and not doc.fiscal_period:
            doc_chunks = [c for c, d in rows if d.id == doc.id and c.page_number <= 5]
            early_text = "\n".join(c.text for c in doc_chunks)
            detected = NSEResearchDocumentProvider.extract_fiscal_period(
                text=doc.title,
                title=doc.title,
                filename=doc.source_url,
                pdf_text=early_text,
                published_at=doc.published_at,
            )
            if detected:
                doc.fiscal_period = detected
                session.flush()

    facts = []
    available_periods = set()
    for chunk, doc in rows:
        fallback = doc.fiscal_period if doc.document_type == "earnings_transcript" else None
        for fact in _extract(chunk.text, fallback):
            fact.update({"document": doc, "page": chunk.page_number})
            facts.append(fact)
            if fact["kind"] == "actual":
                available_periods.add(fact["period"])

    # Explicit transcript fiscal-period metadata also identifies a quarter when its
    # figures cannot be extracted; show that quarter with Unavailable cells.
    for _, doc in rows:
        if doc.document_type == "earnings_transcript" and doc.fiscal_period:
            m = PERIOD_RE.search(doc.fiscal_period)
            if m:
                available_periods.add(f"Q{m.group(1)} FY{m.group(2)[-2:]}")

    periods = sorted(
        available_periods,
        key=lambda p: (int(PERIOD_RE.search(p).group(2)), int(PERIOD_RE.search(p).group(1))),
        reverse=True,
    )[:4]

    results = []
    for period in periods:
        metrics = []
        names = list(METRICS)
        for name in names:
            # Measurement basis enforcement:
            # - Actual figures must match the quarterly reporting basis.
            # - For guidance on ratio metrics (operating margin, EBITDA margin) where targets are annual bands
            #   evaluated each quarter, annual or quarterly guidance applies.
            # - For volume/growth metrics (revenue, revenue growth), annual guidance MUST NOT be paired against quarterly actuals.
            guided = next(
                (
                    f for f in facts
                    if f["period"] == period and f["metric"] == name and f["kind"] == "guided"
                    and (f["scope"] == "quarterly" or name in {"operating margin", "EBITDA margin"})
                ),
                None,
            )
            actual = next(
                (
                    f for f in facts
                    if f["period"] == period and f["metric"] == name and f["kind"] == "actual"
                    and f["scope"] == "quarterly"
                ),
                None,
            )

            same_unit = guided and actual and guided["unit"] == actual["unit"]
            variance = actual["value"] - guided["value"] if same_unit else None

            def citation(f):
                if not f:
                    return None
                doc = f["document"]
                return {
                    "excerpt": f["excerpt"],
                    "document_title": doc.title,
                    "page": f["page"],
                    "source_url": f"{doc.source_url}#page={f['page']}",
                }

            status = "Unavailable"
            if same_unit:
                # A difference from a point target is not enough to decide management's tolerance.
                status = "Not determinable" if variance != 0 else "Met"

            metrics.append({
                "metric": name,
                "unit": (guided or actual)["unit"] if (guided or actual) else None,
                "guided_value": str(guided["value"]) if guided else None,
                "actual_value": str(actual["value"]) if actual else None,
                "variance": str(variance) if variance is not None else None,
                "met_guidance": status,
                "guided_source": citation(guided),
                "actual_source": citation(actual),
            })
        results.append({"period": period, "metrics": metrics})

    gaps = []
    if not rows:
        gaps.append("No indexed source documents are available.")
    if not available_periods:
        gaps.append("No explicit quarter-matched actual results with units were found in indexed text.")
    if len(periods) < 4:
        gaps.append(f"Only {len(periods)} quarter(s) have extractable actual figures; earlier quarters are unavailable in the indexed corpus.")
    if rows and not any(f["kind"] == "guided" for f in facts):
        gaps.append("No explicit quarter-matched management guidance with a stated unit was found.")

    return {
        "company_id": company_id,
        "quarters": results,
        "evidence_gap": " ".join(gaps) if gaps else None,
        "is_demo": False,
    }
