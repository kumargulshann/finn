"""Enrich exchange filings with numbers and people pulled from the filing PDF itself.

Two enrichers, both strictly extractive (nothing is inferred beyond the document):

* Results first-cut: reads the SEBI-format results table and returns Revenue, EBITDA (derived),
  PBT and PAT for the current quarter, the preceding quarter and the year-ago quarter, with
  QoQ / YoY change and the page the table was read from.
* Management-change profile: SEBI LODR requires a "brief profile" of an appointed director/KMP in
  the disclosure. We locate that section and return it with its page number.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

import pymupdf

NUM_RE = re.compile(r"^\(?-?(?:\d{1,3}(?:,\d{2,3})+|\d+)(?:\.\d+)?\)?$")
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
DATE_NUMERIC = re.compile(r"(\d{1,2})\s*[./-]\s*(\d{1,2})\s*[./-]\s*(\d{2,4})")
DATE_DMONY = re.compile(r"(\d{1,2})(?:st|nd|rd|th)?[\s./'’-]*([A-Za-z]{3,9})[\s.,/'’-]*(\d{2,4})")
DATE_MONDY = re.compile(r"([A-Za-z]{3,9})[\s.]*(\d{1,2})(?:st|nd|rd|th)?[\s,]*(\d{4})")


# --------------------------------------------------------------------------- helpers
def _to_number(token: str) -> float | None:
    t = token.strip()
    if not NUM_RE.match(t):
        return None
    neg = t.startswith("(") and t.endswith(")") or t.startswith("-") or t.startswith("(-")
    t = t.strip("()").replace(",", "").lstrip("-")
    try:
        value = float(t)
    except ValueError:
        return None
    return -value if neg else value


def _is_value_token(token: str) -> bool:
    """Accept money-like numbers; reject bare serial numbers such as '1', '12'."""
    t = token.strip("()-")
    if not NUM_RE.match(token.strip()):
        return False
    return "." in t or "," in t or len(t) >= 3 or t in {"0", "-"}


def _month(token: str) -> int | None:
    t = token[:3].lower()
    if t in MONTHS:
        return MONTHS[t]
    close = difflib.get_close_matches(t, MONTHS.keys(), n=1, cutoff=0.66)  # OCR slips such as "Seo" for "Sep"
    return MONTHS[close[0]] if close and len(token) <= 9 else None


def _year(y: str) -> int:
    n = int(y)
    return n + 2000 if n < 100 else n


def _parse_date(text: str) -> date | None:
    """Return the *last* quarter-end date found in text (column headers end with the date)."""
    hits: list[tuple[int, date]] = []
    for rx, order in ((DATE_NUMERIC, "dmy"), (DATE_DMONY, "dMy"), (DATE_MONDY, "Mdy")):
        for m in rx.finditer(text):
            try:
                if order == "dmy":
                    d, mo, y = int(m.group(1)), int(m.group(2)), _year(m.group(3))
                elif order == "dMy":
                    mon = _month(m.group(2))
                    if not mon:
                        continue
                    d, mo, y = int(m.group(1)), mon, _year(m.group(3))
                else:
                    mon = _month(m.group(1))
                    if not mon:
                        continue
                    d, mo, y = int(m.group(2)), mon, _year(m.group(3))
                if 2000 <= y <= 2100 and mo in (3, 6, 9, 12) and 28 <= d <= 31:
                    hits.append((m.end(), date(y, mo, d)))
            except ValueError:
                continue
    return max(hits)[1] if hits else None


def _months_between(a: date, b: date) -> int:
    return (a.year - b.year) * 12 + (a.month - b.month)


def quarter_label(d: date) -> str:
    fy = d.year + 1 if d.month > 3 else d.year
    q = {6: 1, 9: 2, 12: 3, 3: 4}[d.month]
    return f"Q{q} FY{str(fy)[-2:]}"


def _pct(cur: float | None, base: float | None) -> float | None:
    if cur is None or base is None or base == 0:
        return None
    return round((cur - base) / abs(base) * 100, 1)


# ------------------------------------------------------------------- results table
@dataclass
class _Line:
    y: float
    label: str
    values: list[tuple[float, float]]  # (x_center, value)


ROW_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "revenue": [re.compile(r"revenue\s+from\s+operations(?!.*other)"), re.compile(r"^\W*(?:\d+\W*)?(?:i+\W*)?income\s+from\s+operations")],
    "other_income": [re.compile(r"\bother\s+income")],
    "finance": [re.compile(r"finance\s+costs?"), re.compile(r"\binterest\s+(?:and\s+finance\s+)?(?:cost|expense)")],
    "depreciation": [re.compile(r"depreciation")],
    "pbt_pre_exc": [re.compile(r"(?:profit|loss).{0,25}before\s+exceptional")],
    "pbt": [re.compile(r"(?:profit|loss)[\s/()a-z]{0,25}before\s+tax(?!.*exceptional)")],
    "total_income": [re.compile(r"\btotal\s+income\b(?!.*comprehensive)")],
    "tax": [re.compile(r"^\W*(?:[ivx]+\W*|\d+\W*)?(?:total\s+)?tax\s+expenses?"), re.compile(r"^\W*(?:[ivx]+\W*|\d+\W*)?total\s+tax")],
    "pat": [re.compile(r"(?:net\s+)?(?:profit|loss)[\s/()a-z]{0,20}(?:for\s+the\s+(?:period|quarter|year)|after\s+tax)(?!.*(?:attributable|comprehensive|share\s+of))")],
}
BANK_HINTS = ("interest earned", "operating profit before provisions", "provisions (other than tax)", "net interest income")
UNIT_HINTS = (("crore", 1.0), ("cr.", 1.0), ("lakh", 0.01), ("million", 0.1), (" mn", 0.1))


def _page_lines(page: Any) -> tuple[list[_Line], list[tuple[float, float, str, int, int]]]:
    words = _merge_split_numbers(page.get_text("words"))
    # Cluster words into visual rows by vertical centre (gap-based, so rows never split on a bucket edge).
    clusters: list[list[Any]] = []
    for w in sorted(words, key=lambda w: (w[1] + w[3]) / 2):
        yc = (w[1] + w[3]) / 2
        if clusters:
            last = clusters[-1]
            mean = sum((v[1] + v[3]) / 2 for v in last) / len(last)
            if abs(yc - mean) <= 3.2:
                last.append(w)
                continue
        clusters.append([w])
    lines: list[_Line] = []
    for ws in clusters:
        key = sum((v[1] + v[3]) / 2 for v in ws) / len(ws) / 3.0
        ws = sorted(ws, key=lambda w: w[0])
        label_words, values = [], []
        for w in ws:
            if _is_value_token(w[4]) and label_words or (_is_value_token(w[4]) and w[0] > page.rect.width * 0.35):
                v = _to_number(w[4])
                if v is not None:
                    values.append(((w[0] + w[2]) / 2, v))
                    continue
            if not values:
                label_words.append(w[4])
        lines.append(_Line(y=key * 3.0, label=" ".join(label_words).lower(), values=values))
    return lines, [(w[0], w[2], w[4], w[5], w[6]) for w in words]


def _numeric_piece(text: str) -> bool:
    return bool(re.fullmatch(r"\(?-?[\d,]*\.?\d*\)?", text)) and any(ch.isdigit() for ch in text)


def _merge_split_numbers(words: list[Any]) -> list[Any]:
    """Re-join numbers a PDF split into fragments, e.g. '9' + ',953.89' or '6,141' + '9.2'."""
    seen: set[tuple[str, int, int]] = set()
    unique = []
    for w in words:  # some PDFs render the text layer twice (bold simulation) — drop exact overlaps
        key = (w[4], round(w[0] / 4), round(w[1] / 4))
        if key not in seen:
            seen.add(key)
            unique.append(w)
    ordered = sorted(unique, key=lambda w: (round((w[1] + w[3]) / 6), w[0]))
    out: list[Any] = []
    for w in ordered:
        if out:
            p = out[-1]
            same_row = abs(((p[1] + p[3]) / 2) - ((w[1] + w[3]) / 2)) < 3
            gap = w[0] - p[2]
            joinable = (re.match(r"^,\d", w[4]) and re.match(r"^\(?-?\d{1,3}$", p[4]) and 0 <= gap < 8) or \
                       (_numeric_piece(p[4]) and _numeric_piece(w[4]) and 0 <= gap < 2.2 and "." not in p[4] and not p[4].endswith(")"))
            if same_row and joinable:
                out[-1] = (p[0], min(p[1], w[1]), w[2], max(p[3], w[3]), p[4] + w[4], p[5], p[6], p[7])
                continue
        out.append(tuple(w))
    return out


def _is_year_row(values: list[tuple[float, float]]) -> bool:
    return bool(values) and all(v.is_integer() and 2000 <= v <= 2100 for _, v in values)


def _columns(lines: list[_Line]) -> list[float]:
    """Column centres from the rows that carry the most common number of values (robust to stray tokens)."""
    rows = [ln for ln in lines if len(ln.values) >= 3 and not _is_year_row(ln.values)]
    if not rows:
        return []
    counts: dict[int, int] = {}
    for ln in rows:
        counts[len(ln.values)] = counts.get(len(ln.values), 0) + 1
    n = max(counts, key=lambda k: (counts[k], k))
    full = [sorted(x for x, _ in ln.values) for ln in rows if len(ln.values) == n]
    cols: list[float] = []
    for k in range(n):
        xs = sorted(r[k] for r in full)
        x = xs[len(xs) // 2]
        if cols and x - cols[-1] < 12:
            continue
        cols.append(x)
    return cols


def _header_dates(page: Any, columns: list[float], first_value_y: float) -> dict[int, date]:
    """Map column index -> period-end date by reading each column's header band top-to-bottom.

    Handles headers split across lines ("September 30," / "2026", "30.06." / "2026").
    A title like "...ended 30th September, 2026" spans many columns' bands and is ignored because a
    column header must sit inside one band.
    """
    if not columns:
        return {}
    words = [w for w in _merge_split_numbers(page.get_text("words")) if w[3] <= first_value_y + 1 and w[1] >= first_value_y - 140]
    bounds = []
    for k, c in enumerate(columns):
        left = (columns[k - 1] + c) / 2 if k else c - (columns[1] - c) / 2 if len(columns) > 1 else c - 30
        right = (c + columns[k + 1]) / 2 if k + 1 < len(columns) else c + (c - columns[k - 1]) / 2 if k else c + 30
        bounds.append((left, right))
    found: dict[int, date] = {}
    for k, (left, right) in enumerate(bounds):
        band = [w for w in words if left - 4 <= (w[0] + w[2]) / 2 <= right + 4 and (w[2] - w[0]) < (right - left) * 1.8]
        band.sort(key=lambda w: (round((w[1] + w[3]) / 2), w[0]))
        d = _parse_date(" ".join(w[4] for w in band))
        if d:
            found[k] = d
    return found if len(found) >= 2 else {}


def _score_page(text: str) -> int:
    t = text.lower()
    if "profit" not in t or "tax" not in t:
        return 0
    score = 0
    score += 3 if "revenue from operations" in t else 0
    score += 2 if re.search(r"quarter|3 months|three months", t) else 0
    score += 1 if "consolidated" in t[:600] else 0
    score += 1 if "finance cost" in t else 0
    return score


def parse_results_pdf(pdf: bytes, max_pages: int = 40) -> dict[str, Any]:
    try:
        doc = pymupdf.open(stream=pdf, filetype="pdf")
    except Exception as exc:  # corrupt / not a PDF
        return {"kind": "results", "status": "unparsed", "reason": f"Could not open PDF ({exc.__class__.__name__})."}
    candidates = []
    for i, page in enumerate(doc):
        if i >= max_pages:
            break
        text = page.get_text()
        low = text.lower()
        if any(h in low for h in BANK_HINTS) and "revenue from operations" not in low:
            return {"kind": "results", "status": "unsupported", "reason": "Bank / NBFC results use a different statement format (interest earned, provisions); headline table not auto-parsed.", "page": i + 1}
        s = _score_page(text)
        if s >= 5:
            candidates.append((s, i))
    if not candidates:
        textless = all(len(p.get_text().strip()) < 50 for p in list(doc)[:5])
        reason = "Filing appears to be scanned (no text layer)." if textless else "No standard results table found in the filing."
        return {"kind": "results", "status": "unparsed", "reason": reason}

    # Prefer consolidated pages, then document order.
    candidates.sort(key=lambda c: (-c[0], c[1]))
    reasons = []
    for _, page_index in candidates[:5]:
        result = _parse_page(doc[page_index], page_index + 1)
        if result.get("status") == "parsed":
            return result
        reasons.append(f"p{page_index + 1}: {result.get('reason', 'unreadable')}")
    return {"kind": "results", "status": "unparsed", "reason": "Results table found but could not be read reliably (" + "; ".join(reasons[:3]) + ").", "page": candidates[0][1] + 1}


def _parse_page(page: Any, page_no: int) -> dict[str, Any]:
    lines, _ = _page_lines(page)
    columns = _columns(lines)
    if len(columns) < 3:
        return {"status": "unparsed", "reason": "fewer than 3 value columns"}
    # Header region ends at the first genuine table row (titles and year rows are not data).
    need = max(3, len(columns) - 1)
    value_lines = [ln for ln in lines if len(ln.values) >= need and not _is_year_row(ln.values)]
    first_value_y = min(ln.y for ln in value_lines) if value_lines else 0
    dates = _header_dates(page, columns, first_value_y)

    # Identify current / preceding / year-ago quarter columns from their header dates (never assumed).
    q_idx = [0, 1, 2]
    known = {i: d for i, d in dates.items() if i in q_idx}
    if len(known) < 2:
        return {"status": "unparsed", "reason": "Column period dates could not be read."}
    cur_i = max(known, key=lambda i: (known[i], -i))
    cur_d = known[cur_i]
    qoq_i = next((i for i, d in known.items() if _months_between(cur_d, d) == 3), None)
    yoy_i = next((i for i, d in known.items() if _months_between(cur_d, d) == 12), None)
    if qoq_i is None and yoy_i is None:
        return {"status": "unparsed", "reason": "Quarter columns not identifiable."}
    order_basis = "header dates"
    period = quarter_label(cur_d) if cur_d else None

    def col_of(x: float) -> int:
        return min(range(len(columns)), key=lambda k: abs(columns[k] - x))

    # Attach labels: a value line with a short/empty label inherits the previous label-only lines.
    rows: dict[str, dict[int, float]] = {}
    pending_label = ""
    for ln in lines:
        label = re.sub(r"\s+", " ", ln.label).strip()
        if not ln.values:
            pending_label = (pending_label + " " + label).strip()[-160:]
            continue
        full = label if len(re.sub(r"[^a-z]", "", label)) > 6 else (pending_label + " " + label).strip()
        pending_label = ""
        for key, patterns in ROW_PATTERNS.items():
            if key in rows:
                continue
            if any(p.search(full) for p in patterns):
                if key == "revenue" and ("gross" in full and "revenue from operations" not in full):
                    continue
                vals: dict[int, float] = {}
                for x, v in ln.values:
                    vals.setdefault(col_of(x), v)
                if cur_i in vals:
                    rows[key] = vals
                break

    rev, pat = rows.get("revenue"), rows.get("pat")
    pbt = rows.get("pbt") or rows.get("pbt_pre_exc")
    if not rev or not pat or not pbt:
        missing = [k for k, v in (("revenue", rev), ("PBT", pbt), ("PAT", pat)) if not v]
        return {"status": "unparsed", "reason": "Rows not found: " + ", ".join(missing)}

    low = page.get_text().lower()
    factor, unit_note = 1.0, "₹ crore (as reported)"
    for hint, f in UNIT_HINTS:
        if hint in low:
            factor = f
            unit_note = "₹ crore" if f == 1.0 else f"₹ crore (converted from {hint.strip(' .')})"
            break
    else:
        unit_note = "as reported (unit not stated on page)"

    # Accounting identities catch misread columns:
    #   revenue + other income = total income  (gates the whole column)
    #   PBT − tax ≈ PAT                         (gates the PAT figure only; associates / deferral items can differ)
    ti_row, oi_row, tax_row = rows.get("total_income") or {}, rows.get("other_income") or {}, rows.get("tax") or {}

    def income_ok(idx: int | None) -> bool:
        if idx is None:
            return False
        r, oi, ti = rev.get(idx), oi_row.get(idx), ti_row.get(idx)
        if r is None:
            return False
        if oi is None or ti is None:
            return False  # cannot verify → do not publish
        return abs(r + oi - ti) <= max(1.0, abs(ti) * 0.01)

    def pat_ok(idx: int | None) -> bool:
        b, t, p = (pbt or {}).get(idx), tax_row.get(idx), pat.get(idx)
        if b is None or t is None or p is None:
            return True
        return abs(b - t - p) <= max(2.0, abs(b) * 0.15)

    if not income_ok(cur_i):
        return {"status": "unparsed", "reason": "Figures could not be verified against the total-income line."}
    qoq_i = qoq_i if income_ok(qoq_i) else None
    yoy_i = yoy_i if income_ok(yoy_i) else None
    pat = {k: v for k, v in pat.items() if pat_ok(k)}
    checked = 1 + (1 if tax_row else 0)

    def get(row: dict[int, float] | None, idx: int | None) -> float | None:
        if not row or idx is None or idx not in row:
            return None
        return round(row[idx] * factor, 2)

    def ebitda(idx: int | None) -> float | None:
        base = get(rows.get("pbt_pre_exc"), idx) or get(rows.get("pbt"), idx)
        fin, dep = get(rows.get("finance"), idx), get(rows.get("depreciation"), idx)
        if base is None or fin is None or dep is None:
            return None
        oi = get(rows.get("other_income"), idx) or 0.0
        return round(base + fin + dep - oi, 2)

    metrics = []
    for name, getter in (
        ("Revenue", lambda i: get(rev, i)),
        ("EBITDA", ebitda),
        ("PBT", lambda i: get(pbt, i)),
        ("PAT", lambda i: get(pat, i)),
    ):
        cur, prev, yago = getter(cur_i), getter(qoq_i), getter(yoy_i)
        metrics.append({"metric": name, "current": cur, "previous_quarter": prev, "year_ago": yago,
                        "qoq_pct": _pct(cur, prev), "yoy_pct": _pct(cur, yago)})

    r = metrics[0]
    if not r["current"] or r["current"] <= 0 or metrics[3]["current"] is None or abs(metrics[3]["current"]) > r["current"] * 2:
        return {"status": "unparsed"}

    basis = "Consolidated" if "consolidated" in low[:800] else "Standalone"
    return {
        "kind": "results",
        "status": "parsed",
        "period": period,
        "basis": basis,
        "unit": unit_note,
        "page": page_no,
        "column_basis": order_basis,
        "cross_checks": checked,
        "ebitda_definition": "PBT before exceptional items + finance costs + depreciation − other income",
        "metrics": metrics,
    }


def results_headline(enrichment: dict[str, Any]) -> str | None:
    if enrichment.get("status") != "parsed":
        return None
    parts = []
    for m in enrichment["metrics"]:
        if m["metric"] in ("Revenue", "PAT") and m["current"] is not None:
            bits = [f"{m['metric']} ₹{m['current']:,.0f} Cr"]
            if m["yoy_pct"] is not None:
                bits.append(f"{m['yoy_pct']:+.1f}% YoY")
            if m["qoq_pct"] is not None:
                bits.append(f"{m['qoq_pct']:+.1f}% QoQ")
            parts.append(" ".join(bits[:1]) + (f" ({', '.join(bits[1:])})" if len(bits) > 1 else ""))
    label = f"{enrichment.get('period') or 'Quarter'} {enrichment.get('basis', '').lower()}".strip()
    return f"{label}: " + "; ".join(parts) if parts else None


# ------------------------------------------------------------- management profiles
PROFILE_HEAD = re.compile(r"(brief\s+profile|profile\s+of|brief\s+resume|background\s+of|experience\s+and\s+expertise|qualifications?\s+and\s+experience)", re.I)
PERSON_RE = re.compile(r"\b(Mr\.?|Ms\.?|Mrs\.?|Dr\.?|Shri|Smt\.?)[ \t]+([A-Z][A-Za-z.\-']+(?:[ \t]+(?!Mr\b|Ms\b|Mrs\b|Dr\b)[A-Z][A-Za-z.\-']+){0,3})")
ROLE_RE = re.compile(r"\b(Chief\s+[A-Z][a-z]+\s+Officer|CEO|CFO|COO|CTO|Managing\s+Director|Whole[\s-]?time\s+Director|Executive\s+Director|Independent\s+Director|Non[\s-]Executive\s+Director|Company\s+Secretary|Chairman|Chairperson|President)\b", re.I)
ACTION_RE = re.compile(r"\b(appoint(?:ed|ment)|re-?appoint(?:ed|ment)|resign(?:ed|ation)|cessation|retire(?:d|ment)|step(?:ped|s)?\s+down|elevat(?:ed|ion))\b", re.I)


def parse_people_pdf(pdf: bytes, max_pages: int = 25) -> dict[str, Any]:
    try:
        doc = pymupdf.open(stream=pdf, filetype="pdf")
    except Exception as exc:
        return {"kind": "people", "status": "unparsed", "reason": f"Could not open PDF ({exc.__class__.__name__})."}
    pages = [(i + 1, doc[i].get_text()) for i in range(min(len(doc), max_pages))]
    if all(len(t.strip()) < 50 for _, t in pages[:3]):
        return {"kind": "people", "status": "unparsed", "reason": "Filing appears to be scanned (no text layer)."}
    full = "\n".join(t for _, t in pages)
    action = ACTION_RE.search(full)
    people: list[dict[str, Any]] = []
    seen: set[str] = set()
    for page_no, text in pages:
        flat = re.sub(r"[ \t]+", " ", text)
        for m in PROFILE_HEAD.finditer(flat):
            window = flat[m.end(): m.end() + 1600]
            person = PERSON_RE.search(flat[max(0, m.start() - 200): m.end() + 400])
            name = f"{person.group(1).rstrip('.')}. {person.group(2)}".replace("Shri.", "Shri").replace("Smt..", "Smt.") if person else None
            key = (name or "") + str(page_no)
            body = re.sub(r"\s+", " ", window).strip(" :-–\n")
            # Drop SEBI form boilerplate that precedes the actual text.
            body = re.sub(r"^(?:\(?in case of (?:an )?appointment\)?\s*[;:,.-]?\s*)+", "", body, flags=re.I)
            body = re.sub(r"^(?:not applicable|n\.?a\.?)\s*[;:,.-]?\s*", "", body, flags=re.I)
            # Stop at the next numbered section / signature block.
            body = re.split(r"\s(?:\d+\.?|[a-h]\))\s+(?:Disclosure|Relationship|Date|Reason|Terms|Name|Letter)|Yours (?:faithfully|truly|sincerely)|For\s+[A-Z][A-Za-z&. ]+Limited", body)[0]
            if re.match(r"(?:not applicable|n\.?a\.?)\b", body, re.I):
                continue
            sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", body)
            profile = " ".join(sentences[:4]).strip()
            if len(profile) < 60 or re.match(r"\d+\s+(?:Disclosure|Relationship)", profile) or \
                    ("not applicable" in profile.lower() and len(profile) < 220):
                continue
            # The person is whoever the profile is about, so read the name from the profile itself.
            own = PERSON_RE.search(profile[:160])
            subject = re.match(r"([A-Z][A-Za-z.]+(?:\s+[A-Z][A-Za-z.]+){1,3})\s+(?:is|has|was|joined|holds|brings)\b", profile)
            if own:
                name = f"{own.group(1).rstrip('.')}. {own.group(2)}".replace("Shri.", "Shri").replace("Smt..", "Smt.")
            elif subject:
                name = subject.group(1)
            if name and name in seen:
                continue
            role = ROLE_RE.search(flat[max(0, m.start() - 600): m.end() + 600])
            people.append({"name": name, "role": role.group(1) if role else None, "profile": profile[:700], "page": page_no})
            seen.add(name or key)
            if len(people) >= 3:
                break
        if len(people) >= 3:
            break
    if not people:
        # Still name the person and action when stated, without inventing a bio.
        person = PERSON_RE.search(full)
        role = ROLE_RE.search(full)
        return {"kind": "people", "status": "no_profile", "action": action.group(1).lower() if action else None,
                "people": [{"name": f"{person.group(1).rstrip('.')}. {person.group(2)}", "role": role.group(1) if role else None, "profile": None, "page": None}] if person else [],
                "reason": "The filing does not include a brief profile of the person."}
    return {"kind": "people", "status": "parsed", "action": action.group(1).lower() if action else None, "people": people}


def results_why(enrichment: dict[str, Any]) -> str | None:
    """A grounded read of the parsed table — growth, margin direction, and whether profit kept pace with sales."""
    if enrichment.get("status") != "parsed":
        return None
    m = {row["metric"]: row for row in enrichment["metrics"]}
    rev, ebitda, pat = m.get("Revenue", {}), m.get("EBITDA", {}), m.get("PAT", {})
    bits: list[str] = []
    if rev.get("yoy_pct") is not None:
        q = f", {rev['qoq_pct']:+.1f}% on the previous quarter" if rev.get("qoq_pct") is not None else ""
        bits.append(f"Revenue moved {rev['yoy_pct']:+.1f}% year on year{q}.")
    if ebitda.get("current") and rev.get("current") and ebitda.get("year_ago") and rev.get("year_ago"):
        now_m = ebitda["current"] / rev["current"] * 100
        then_m = ebitda["year_ago"] / rev["year_ago"] * 100
        bps = round((now_m - then_m) * 100)
        bits.append(f"EBITDA margin {now_m:.1f}% vs {then_m:.1f}% a year ago ({bps:+d} bps).")
    if pat.get("yoy_pct") is not None and rev.get("yoy_pct") is not None:
        gap = pat["yoy_pct"] - rev["yoy_pct"]
        if gap > 5:
            bits.append("Profit grew faster than sales — operating leverage or lower costs are flowing through.")
        elif gap < -5:
            bits.append("Profit lagged sales — costs, interest, depreciation or tax absorbed the growth.")
        else:
            bits.append("Profit broadly tracked sales.")
    if not bits:
        return None
    return " ".join(bits) + f" Read from the {enrichment.get('basis', '').lower()} results table on page {enrichment.get('page')} of the filing."
