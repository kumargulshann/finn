"""NSE annual-report and earnings-call transcript catalog/download adapter."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx

NSE_HOME = "https://www.nseindia.com"
ANNUAL_REPORTS_API = f"{NSE_HOME}/api/annual-reports"
ANNOUNCEMENTS_API = f"{NSE_HOME}/api/corporate-announcements"
ANNUAL_REPORTS_PAGE = f"{NSE_HOME}/companies-listing/corporate-filings-annual-reports"
ANNOUNCEMENTS_PAGE = f"{NSE_HOME}/companies-listing/corporate-filings-announcements"
IST = ZoneInfo("Asia/Kolkata")


class NSEResearchDocumentProvider:
    def __init__(self, timeout_seconds: float = 35, max_document_bytes: int = 80_000_000) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_document_bytes = max_document_bytes

    @staticmethod
    def _headers(referer: str) -> dict[str, str]:
        return {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/129 Safari/537.36", "Accept": "application/json, text/plain, */*", "Referer": referer}

    def catalog(self, symbol: str, include_transcripts: bool = True, transcripts_per_company: int = 1) -> tuple[list[dict[str, Any]], list[str]]:
        items: list[dict[str, Any]] = []
        errors: list[str] = []
        with httpx.Client(timeout=self.timeout_seconds, follow_redirects=True, headers=self._headers(ANNUAL_REPORTS_PAGE)) as client:
            try:
                client.get(NSE_HOME)
                response = client.get(ANNUAL_REPORTS_API, params={"index": "equities", "symbol": symbol})
                response.raise_for_status()
                reports = response.json().get("data", [])
                reports = sorted(reports, key=lambda row: str(row.get("toYr", "0")), reverse=True)
                report = next((row for row in reports if str(row.get("fileName", "")).lower().endswith(".pdf")), None)
                if report:
                    year_from, year_to = report.get("fromYr"), report.get("toYr")
                    items.append({"source_key": "annual:" + str(year_from) + ":" + str(year_to), "title": f"{symbol} Annual Report FY {year_from}-{year_to}", "document_type": "annual_report", "fiscal_period": f"FY {year_from}-{year_to}", "published_at": self._parse_datetime(report.get("broadcast_dttm")), "source_url": report["fileName"], "source_name": "NSE Annual Reports", "raw": report})
                else:
                    errors.append(f"{symbol}: no PDF annual report listed by NSE")
            except Exception as exc:
                errors.append(f"{symbol}: annual report catalog: {self._message(exc)}")

            if include_transcripts:
                try:
                    end = date.today()
                    start = end - timedelta(days=500)
                    response = client.get(ANNOUNCEMENTS_API, params={"index": "equities", "from_date": start.strftime("%d-%m-%Y"), "to_date": end.strftime("%d-%m-%Y"), "symbol": symbol}, headers=self._headers(ANNOUNCEMENTS_PAGE))
                    response.raise_for_status()
                    rows = response.json()
                    matches = []
                    for row in rows if isinstance(rows, list) else []:
                        text = f"{row.get('desc', '')} {row.get('attchmntText', '')} {row.get('attchmntFile', '')}".lower()
                        if row.get("attchmntFile", "").lower().endswith(".pdf") and "transcript" in text:
                            matches.append(row)
                    matches.sort(key=lambda row: row.get("sort_date") or "", reverse=True)
                    if matches:
                        for row in matches[:transcripts_per_company]:
                            pub = self._parse_datetime(row.get("an_dt") or row.get("sort_date"))
                            fn = str(row.get("attchmntFile", ""))
                            meta_text = f"{row.get('desc', '')} {row.get('attchmntText', '')}"
                            title = f"{symbol} Earnings Call Transcript · {pub.strftime('%d %b %Y') if pub else 'Undated'}"
                            fiscal_period = self.extract_fiscal_period(text=meta_text, title=title, filename=fn, published_at=pub)
                            items.append({"source_key": "transcript:" + str(row.get("seq_id") or row.get("attchmntFile")), "title": title, "document_type": "earnings_transcript", "fiscal_period": fiscal_period, "published_at": pub, "source_url": row["attchmntFile"], "source_name": "NSE Corporate Filings", "raw": row})
                    else:
                        errors.append(f"{symbol}: no earnings-call transcript found in the selected 500-day window")
                except Exception as exc:
                    errors.append(f"{symbol}: transcript catalog: {self._message(exc)}")
        return items, errors

    def download_pdf(self, url: str) -> bytes:
        headers = self._headers(ANNUAL_REPORTS_PAGE)
        with httpx.Client(timeout=self.timeout_seconds, follow_redirects=True, headers=headers) as client:
            response = client.get(url)
            response.raise_for_status()
        if len(response.content) > self.max_document_bytes:
            raise ValueError(f"Document exceeds {self.max_document_bytes // 1_000_000} MB size limit.")
        if not response.content.startswith(b"%PDF"):
            raise ValueError("NSE attachment is not a PDF; no document text was stored.")
        return response.content

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if not value or value == "-":
            return None
        text = str(value).strip()
        for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%B-%Y %H:%M:%S", "%d-%b-%Y %H:%M"):
            try:
                return datetime.strptime(text, fmt).replace(tzinfo=IST).astimezone(timezone.utc)
            except ValueError:
                continue
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return parsed.replace(tzinfo=IST).astimezone(timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
        except ValueError:
            return None

    @staticmethod
    def extract_fiscal_period(
        text: str = "",
        title: str = "",
        filename: str = "",
        pdf_text: str = "",
        published_at: datetime | None = None,
    ) -> str | None:
        """
        Extract Indian fiscal quarter notation (e.g. 'Q1 FY26') from:
        - Announcement metadata (text, attchmntText, desc)
        - Document title
        - Attachment filename / URL
        - Early transcript text (cover page / opening remarks)
        """
        import re

        # 1. Direct Q[1-4] FY[20]XX or Q[1-4] of FY[20]XX or Q[1-4]-FY[20]XX
        period_pattern = re.compile(
            r"\bQ([1-4])\s*(?:of\s*|-)?\s*FY\s*['’]?\s*(20\d{2}|\d{2})\b",
            re.IGNORECASE,
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
            re.IGNORECASE,
        )
        for sample in [title, text, pdf_text[:5000]]:
            if not sample:
                continue
            m = date_end_pattern.search(sample)
            if not m:
                m = re.search(
                    rf"(?:ended|ending)\s+(?:on\s+)?(?:\d{{1,2}}(?:st|nd|rd|th)?\s+)?({month_pattern})\s+(?:\d{{1,2}}[,\s]+)?(20\d{{2}})",
                    sample,
                    re.IGNORECASE,
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

        # 5. Filename pattern: e.g. Transcript_April232026_Q4.pdf or HDFCBANK_..._Q1.pdf
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

        # 6. PDF early text mentioning quarter with financial results / performance
        q_results = re.search(r"\b(Q[1-4])\s*(?:financial\s*results|earnings|results|performance|conference\s*call)\b", pdf_text[:3000], re.IGNORECASE)
        if not q_results:
            q_results = re.search(r"\b(?:performance in|results for|held for)\s+(Q[1-4])\b", pdf_text[:3000], re.IGNORECASE)
        if q_results and published_at:
            quarter = q_results.group(1).upper()
            q_num = int(quarter[1])
            if q_num == 4:
                fy = published_at.year if published_at.month <= 6 else published_at.year + 1
            elif q_num == 3 and published_at.month <= 3:
                fy = published_at.year
            else:
                fy = published_at.year + 1 if published_at.month > 3 else published_at.year
            return f"{quarter} FY{fy % 100:02d}"

        return None

    @classmethod
    def _fiscal_period(cls, text: str, filename: str = "", title: str = "", published_at: datetime | None = None) -> str | None:
        return cls.extract_fiscal_period(text=text, filename=filename, title=title, published_at=published_at)

    @staticmethod
    def _message(exc: Exception) -> str:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        return f"HTTP {status}" if status else str(exc).splitlines()[0][:150]
