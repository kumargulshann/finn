"""Normalize, classify, deduplicate, and persist exchange filings."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import Announcement, Instrument
from app.integrations.announcements.exchange_provider import ExchangeAnnouncementProvider

IST = ZoneInfo("Asia/Kolkata")
CATEGORIES = ("Results", "Order wins", "Acquisitions", "Management changes", "Fundraising", "Regulatory updates", "Corporate actions")
RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Results", ("financial results", "quarterly results", "annual results", "unaudited results", "audited results", "earnings results", "financial result")),
    ("Order wins", ("order received", "order win", "letter of award", "contract awarded", "work order", "purchase order", "loa received")),
    ("Acquisitions", ("acquisition", "acquire", "merger", "amalgamation", "strategic investment", "stake sale", "divestment", "demerger")),
    ("Management changes", ("appointment", "resignation", "cessation", "director", "managing director", "chief executive", "key managerial", "auditor")),
    ("Fundraising", ("fund raising", "fundraising", "rights issue", "preferential issue", "qualified institutions placement", "qip", "public issue", "private placement", "debt securities", "non convertible debenture")),
    ("Regulatory updates", ("sebi", "regulatory", "regulation 30", "show cause", "penalty", "fine imposed", "order passed", "court", "investigation", "non-compliance", "default")),
    ("Corporate actions", ("dividend", "bonus issue", "stock split", "buyback", "record date", "postal ballot", "scheme of arrangement", "shareholder meeting", "trading window", "corporate action")),
)


def classify(title: str, summary: str) -> tuple[str, str]:
    text = f"{title} {summary}".lower()
    for category, terms in RULES:
        if any(term in text for term in terms):
            return category, priority(category, text)
    return "", ""


def priority(category: str, text: str) -> str:
    high = ("fraud", "insolvency", "default", "termination", "acquisition", "merger", "resignation", "penalty", "fine", "qualified institutions placement", "qip", "rights issue", "auditor")
    if category in {"Results", "Acquisitions", "Fundraising", "Regulatory updates"} or any(term in text for term in high):
        return "High"
    if category in {"Order wins", "Management changes", "Corporate actions"}:
        return "Medium"
    return "Low"


def why_matters(category: str) -> str:
    return {
        "Results": "Results can change the earnings baseline and expectations. Compare the reported figures with prior periods and management guidance in the filing.",
        "Order wins": "New contracts can affect revenue visibility and capacity utilization. The disclosed order size, timeline, and execution terms determine materiality.",
        "Acquisitions": "A transaction can change the company’s growth profile, capital needs, and risk exposure. Consider the deal size, funding, and expected completion conditions.",
        "Management changes": "Leadership or auditor changes can affect execution and oversight. The role, reason, and transition plan in the filing provide important context.",
        "Fundraising": "New capital can support investment or strengthen the balance sheet, while also changing leverage or ownership dilution.",
        "Regulatory updates": "Regulatory or legal developments can affect operations, costs, and governance. The filing’s status and any quantified exposure matter.",
        "Corporate actions": "This event may change shareholder cash flows, share count, or voting rights. Check the dates, ratio, and eligibility terms in the filing.",
    }.get(category, "Review the exchange filing for company-specific implications.")


def extract_filing_facts(category: str, severity: str, title: str, summary: str, exchange: str) -> list[str]:
    facts = [
        f"Event category: {category}",
        f"Filing source: {exchange} Corporate Announcement Feed",
        f"Impact classification: {severity} priority",
    ]
    money_match = re.findall(
        r"(?:₹|Rs\.?|INR|USD|\$)\s*[\d,]+(?:\.\d+)?\s*(?:cr(?:ore)?s?|lakhs?|mn|bn|billion|million)?",
        f"{title} {summary}",
        re.IGNORECASE,
    )
    if money_match:
        facts.append(f"Disclosed amount: {money_match[0]}")
    pct_match = re.findall(r"[\d,]+(?:\.\d+)?\s*%", f"{title} {summary}")
    if pct_match:
        facts.append(f"Disclosed percentage: {pct_match[0]}")
    return facts


def _canonical_title(title: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", title.lower()))


def _fingerprint(company_id: int, title: str, published_at: datetime) -> str:
    local_day = published_at.astimezone(IST).date().isoformat()
    value = f"{company_id}|{local_day}|{_canonical_title(title)}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class AnnouncementIngestionService:
    def __init__(self, provider: ExchangeAnnouncementProvider | None = None) -> None:
        self.provider = provider or ExchangeAnnouncementProvider()

    def refresh(self, session: Session, days: int = 7, limit: int = 10) -> dict[str, Any]:
        end = datetime.now(IST).date()
        start = end - timedelta(days=days - 1)
        instruments = session.scalars(select(Instrument).where(Instrument.exchange == "NSE").order_by(Instrument.symbol).limit(limit)).all()
        company_by_symbol = {item.symbol: item.company_id for item in instruments}
        request_rows = [{"symbol": item.symbol, "bse_scrip_code": item.bse_scrip_code} for item in instruments]
        raw, errors = self.provider.fetch(request_rows, start, end)
        inserted = duplicates = ignored = 0
        for item in raw:
            company_id = company_by_symbol.get(item["symbol"])
            if not company_id:
                ignored += 1
                continue
            title = " ".join(str(item.get("title") or "Exchange filing").split())[:300]
            summary = " ".join(str(item.get("summary") or "Review the original exchange filing for details.").split())
            category, severity = classify(title, summary)
            if not category:
                ignored += 1
                continue
            published = item["published_at"]
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
            published = published.astimezone(timezone.utc)
            external_id = item.get("external_id") or _fingerprint(company_id, title, published)[:20]
            source_key = f"{item['exchange']}:{external_id}"
            fingerprint = _fingerprint(company_id, title, published)
            exists = session.scalar(select(Announcement.id).where((Announcement.source_key == source_key) | (Announcement.fingerprint == fingerprint)).limit(1))
            if not exists:
                candidates = session.scalars(select(Announcement).where(Announcement.company_id == company_id, Announcement.is_demo.is_(False), Announcement.category == category, Announcement.published_at >= published - timedelta(hours=24), Announcement.published_at <= published + timedelta(hours=24))).all()
                if any(SequenceMatcher(None, _canonical_title(event.title), _canonical_title(title)).ratio() >= 0.96 for event in candidates):
                    exists = True
            if exists:
                duplicates += 1
                continue
            facts = extract_filing_facts(category, severity, title, summary, item["exchange"])
            session.add(Announcement(company_id=company_id, slug=f"filing-{item['exchange'].lower()}-{external_id.lower().replace('/', '-')[:70]}", category=category, title=title, summary=summary[:5000], why_it_matters=why_matters(category), severity=severity, positive=False, published_at=published, source_name=item["source_name"], source_url=item["source_url"], source_date=published.astimezone(IST).strftime("%d %b %Y %H:%M IST"), facts_json=json.dumps(facts, ensure_ascii=False), is_demo=False, source_exchange=item["exchange"], source_key=source_key, fingerprint=fingerprint))
            session.flush()
            inserted += 1
        session.commit()
        return {"inserted": inserted, "duplicates": duplicates, "ignored": ignored, "fetched": len(raw), "errors": errors, "symbols": [item.symbol for item in instruments], "from_date": start.isoformat(), "to_date": end.isoformat(), "source": "NSE and BSE public corporate announcement feeds"}
