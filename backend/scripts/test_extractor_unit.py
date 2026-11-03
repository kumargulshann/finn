import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import re
from datetime import datetime

def extract_fiscal_period(
    text: str = "",
    title: str = "",
    filename: str = "",
    pdf_text: str = "",
    published_at: datetime = None
) -> str | None:
    """
    Extracts Indian fiscal quarter notation (e.g. 'Q1 FY26') from announcement
    metadata, titles, filenames, and PDF text.
    """
    # 1. Direct Q[1-4] FY[20]XX or Q[1-4] of FY[20]XX or Q[1-4]-FY[20]XX
    period_pattern = re.compile(
        r"\bQ([1-4])\s*(?:of\s*|-)?\s*FY\s*['’]?\s*(20\d{2}|\d{2})\b",
        re.IGNORECASE
    )
    for sample in [title, text, filename, pdf_text[:5000]]:
        if not sample:
            continue
        m = period_pattern.search(sample)
        if m:
            quarter = m.group(1)
            year = m.group(2)[-2:]
            return f"Q{quarter} FY{year}"

    # 2. Q[1-4] [20]XX (e.g. Q2-2027, Q1 2026, Q2-2026)
    q_year_pattern = re.compile(r"\bQ([1-4])\s*[-/]?\s*(20\d{2})\b", re.IGNORECASE)
    for sample in [title, text, pdf_text[:5000]]:
        if not sample:
            continue
        m = q_year_pattern.search(sample)
        if m:
            quarter = m.group(1)
            year_int = int(m.group(2))
            return f"Q{quarter} FY{year_int % 100:02d}"

    # 3. Ended / Ending [on] [Day] [Month] [Year] or [Month] [Day], [Year]
    month_pattern = r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    date_end_pattern = re.compile(
        rf"(?:quarter|half\s*year|six\s*months?|financial\s*year|period|three\s*months?|Q[1-4])"
        rf"(?:\s+(?:and|&)\s+(?:half\s*year|six\s*months?|financial\s*year|quarter))?"
        rf"\s+(?:ended|ending)\s+(?:on\s+)?(?:\d{{1,2}}(?:st|nd|rd|th)?\s+)?({month_pattern})\s+(?:\d{{1,2}}[,\s]+)?(20\d{{2}})",
        re.IGNORECASE
    )
    for sample in [title, text, pdf_text[:5000]]:
        if not sample:
            continue
        m = date_end_pattern.search(sample)
        if not m:
            m = re.search(
                rf"(?:ended|ending)\s+(?:on\s+)?(?:\d{{1,2}}(?:st|nd|rd|th)?\s+)?({month_pattern})\s+(?:\d{{1,2}}[,\s]+)?(20\d{{2}})",
                sample, re.IGNORECASE
            )
        if m:
            month_str = m.group(1).title()
            calendar_year = int(m.group(2))
            month = datetime.strptime(month_str, "%B").month
            quarter_by_end_month = {3: 4, 6: 1, 9: 2, 12: 3}
            if month in quarter_by_end_month:
                quarter = quarter_by_end_month[month]
                fiscal_year = calendar_year if month == 3 else calendar_year + 1
                return f"Q{quarter} FY{fiscal_year % 100:02d}"

    # 4. Spelled-out quarters: "First Quarter", "Second Quarter", "Third Quarter", "Fourth Quarter"
    ord_pattern = re.compile(r"\b(first|second|third|fourth|1st|2nd|3rd|4th)\s+quarter\b", re.IGNORECASE)
    ord_map = {"first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3, "fourth": 4, "4th": 4}
    for sample in [title, text, pdf_text[:5000]]:
        if not sample:
            continue
        m = ord_pattern.search(sample)
        if m:
            q_num = ord_map[m.group(1).lower()]
            ym = re.search(r"\b(?:FY\s*['’]?\s*(20\d{2}|\d{2})|financial\s+year\s+(20\d{2}))\b", sample, re.IGNORECASE)
            if ym:
                yr = (ym.group(1) or ym.group(2))[-2:]
                return f"Q{q_num} FY{yr}"
            ref_date = published_at
            if not ref_date:
                dm = re.search(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}[,\s]+(20\d{2})\b", sample, re.IGNORECASE)
                if dm:
                    ref_date = datetime.strptime(f"{dm.group(1)} {dm.group(2)}", "%B %Y")
            if ref_date:
                if q_num == 4:
                    fy = ref_date.year if ref_date.month <= 6 else ref_date.year + 1
                elif q_num == 3 and ref_date.month <= 3:
                    fy = ref_date.year
                else:
                    fy = ref_date.year + 1 if ref_date.month > 3 else ref_date.year
                return f"Q{q_num} FY{fy % 100:02d}"

    # 5. Filename check with reference date: e.g. Transcript_April232026_Q4.pdf
    fn_match = re.search(r"[_\-](Q[1-4])(?:_?(?:FY)?(\d{2,4}))?\.pdf", filename, re.IGNORECASE)
    if fn_match:
        quarter = fn_match.group(1).upper()
        if fn_match.group(2):
            return f"{quarter} FY{fn_match.group(2)[-2:]}"
        elif published_at:
            q_num = int(quarter[1])
            if q_num == 4:
                fy = published_at.year if published_at.month <= 6 else published_at.year + 1
            else:
                fy = published_at.year + 1 if published_at.month > 3 else published_at.year
            return f"{quarter} FY{fy % 100:02d}"

    # 6. In PDF text, look for "performance in Q[1-4]" or "Q[1-4] results" + date
    q_simple = re.search(r"\b(?:performance in\s+|results for\s+|in\s+)?(Q[1-4])\b", pdf_text[:3000], re.IGNORECASE)
    if q_simple and published_at:
        quarter = q_simple.group(1).upper()
        q_num = int(quarter[1])
        if q_num == 4:
            fy = published_at.year if published_at.month <= 6 else published_at.year + 1
        elif q_num == 3 and published_at.month <= 3:
            fy = published_at.year
        else:
            fy = published_at.year + 1 if published_at.month > 3 else published_at.year
        return f"{quarter} FY{fy % 100:02d}"

    return None

print("Unit test extraction:")
print("1. 'Q1 FY26':", extract_fiscal_period(text="Results for Q1 FY26"))
print("2. 'Q1 of FY 2025-26':", extract_fiscal_period(text="Earnings call for Q1 of FY 2026"))
print("3. 'ended September 30, 2026':", extract_fiscal_period(text="for the quarter and half year ended September 30, 2026"))
print("4. 'ended March 31, 2026':", extract_fiscal_period(text="financial results for the quarter and financial year ended March 31, 2026"))
print("5. 'Second Quarter' in Oct 2026:", extract_fiscal_period(pdf_text="thank you for joining Infosys' Second Quarter Financial Results.", published_at=datetime(2026, 10, 28)))
print("6. 'Third Quarter' in Jan 2026:", extract_fiscal_period(pdf_text="We have had a strong performance in Q3.", published_at=datetime(2026, 1, 19)))
print("7. 'Q4 filename in Apr 2026':", extract_fiscal_period(filename="Transcript_April232026_Q4.pdf", published_at=datetime(2026, 4, 27)))

