"""Public exchange announcement feeds used by the prototype ingestion job."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx

IST = ZoneInfo("Asia/Kolkata")
NSE_PAGE = "https://www.nseindia.com/companies-listing/corporate-filings-announcements"
NSE_API = "https://www.nseindia.com/api/corporate-announcements"
BSE_API = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"


class ExchangeAnnouncementProvider:
    """Fetch normalized raw announcements from the public NSE and BSE web feeds."""

    def __init__(self, timeout_seconds: float = 15) -> None:
        self.timeout_seconds = timeout_seconds

    def fetch(self, instruments: list[dict[str, Any]], start: date, end: date) -> tuple[list[dict[str, Any]], list[str]]:
        jobs: dict[Any, str] = {}
        errors: list[str] = []
        with ThreadPoolExecutor(max_workers=8) as pool:
            for instrument in instruments:
                jobs[pool.submit(self._fetch_nse, instrument, start, end)] = f"NSE {instrument['symbol']}"
                if instrument.get("bse_scrip_code"):
                    jobs[pool.submit(self._fetch_bse, instrument, start, end)] = f"BSE {instrument['symbol']}"
            raw: list[dict[str, Any]] = []
            for future in as_completed(jobs):
                try:
                    raw.extend(future.result())
                except Exception as exc:  # A single symbol/feed should not discard successful rows.
                    status = getattr(getattr(exc, "response", None), "status_code", None)
                    label = jobs[future]
                    errors.append(f"{label}: upstream HTTP {status}" if status else f"{label}: {str(exc).splitlines()[0][:180]}")
        return raw, errors

    def _fetch_nse(self, instrument: dict[str, Any], start: date, end: date) -> list[dict[str, Any]]:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/129 Safari/537.36", "Accept": "application/json, text/plain, */*", "Referer": NSE_PAGE}
        params = {"index": "equities", "from_date": start.strftime("%d-%m-%Y"), "to_date": end.strftime("%d-%m-%Y"), "symbol": instrument["symbol"]}
        with httpx.Client(timeout=self.timeout_seconds, headers=headers, follow_redirects=True) as client:
            client.get("https://www.nseindia.com", timeout=self.timeout_seconds)
            response = client.get(NSE_API, params=params)
            response.raise_for_status()
            data = response.json()
        if not isinstance(data, list):
            raise ValueError(f"NSE returned an unexpected response for {instrument['symbol']}.")
        return [self._normalize_nse(item, instrument) for item in data]

    def _fetch_bse(self, instrument: dict[str, Any], start: date, end: date) -> list[dict[str, Any]]:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/129 Safari/537.36", "Accept": "application/json, text/plain, */*", "Origin": "https://www.bseindia.com", "Referer": "https://www.bseindia.com/"}
        rows: list[dict[str, Any]] = []
        total = 0
        for page in range(1, 11):
            params = {"pageno": page, "strCat": "-1", "subcategory": "-1", "strPrevDate": start.strftime("%Y%m%d"), "strToDate": end.strftime("%Y%m%d"), "strSearch": "P", "strScrip": instrument["bse_scrip_code"], "strType": "C"}
            response = httpx.get(BSE_API, params=params, headers=headers, timeout=self.timeout_seconds)
            response.raise_for_status()
            data = response.json()
            if data.get("Status") is False:
                raise ValueError(f"BSE returned an error for {instrument['symbol']}: {data.get('Message', 'unknown error')}")
            page_rows = data.get("Table") or []
            rows.extend(page_rows)
            try:
                total = int((data.get("Table1") or [{}])[0].get("ROWCNT") or 0)
            except (TypeError, ValueError):
                total = 0
            if not page_rows or (total and len(rows) >= total):
                break
        return [self._normalize_bse(item, instrument) for item in rows]

    @staticmethod
    def _parse_datetime(value: Any) -> datetime:
        if isinstance(value, datetime):
            parsed = value
        else:
            text = str(value or "").strip()
            try:
                parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError:
                parsed = datetime.strptime(text, "%d-%b-%Y %H:%M:%S")
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=IST)
        return parsed.astimezone(timezone.utc)

    def _normalize_nse(self, row: dict[str, Any], instrument: dict[str, Any]) -> dict[str, Any]:
        url = row.get("attchmntFile") or ""
        return {"symbol": instrument["symbol"], "exchange": "NSE", "external_id": str(row.get("seq_id") or ""), "title": row.get("desc") or row.get("subject") or "Exchange filing", "summary": row.get("attchmntText") or row.get("desc") or "The company has filed a disclosure with NSE. Review the original filing for full details.", "published_at": self._parse_datetime(row.get("an_dt") or row.get("sort_date") or row.get("dt")), "source_url": url if url.startswith("http") else ("https://nsearchives.nseindia.com" + url if url.startswith("/") else f"{NSE_PAGE}?symbol={instrument['symbol']}"), "source_name": "NSE filing", "raw": row}

    def _normalize_bse(self, row: dict[str, Any], instrument: dict[str, Any]) -> dict[str, Any]:
        file_name = row.get("ATTACHMENTNAME") or ""
        url = ("https://www.bseindia.com/xml-data/corpfiling/AttachHis/" + file_name) if file_name else (row.get("NSURL") or f"https://www.bseindia.com/stock-share-price/{instrument['bse_scrip_code']}/")
        return {"symbol": instrument["symbol"], "exchange": "BSE", "external_id": str(row.get("NEWSID") or ""), "title": row.get("NEWSSUB") or row.get("HEADLINE") or "Exchange filing", "summary": row.get("MORE") or row.get("HEADLINE") or "The company has filed a disclosure with BSE. Review the original filing for full details.", "published_at": self._parse_datetime(row.get("NEWS_DT") or row.get("DT_TM")), "source_url": url, "source_name": "BSE filing", "raw": row}
