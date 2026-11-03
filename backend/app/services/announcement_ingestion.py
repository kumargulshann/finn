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

from app.domain.models import Announcement, Instrument, Portfolio, PortfolioHolding
from app.integrations.announcements.exchange_provider import ExchangeAnnouncementProvider
from app.services.filing_enrichment import parse_people_pdf, parse_results_pdf, results_headline

IST = ZoneInfo("Asia/Kolkata")
CATEGORIES = ("Results", "Order wins", "Acquisitions", "Management changes", "Fundraising", "Regulatory updates",
              "Corporate actions", "Capex", "Credit rating", "Pledging", "Insider trading", "Earnings call",
              "Investor meetings", "Routine")


def _p(*patterns: str) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(x, re.I) for x in patterns)


# Ordered (category, patterns) checked against the exchange subject line first, then the body text.
# Patterns are deliberately specific: almost every filing cites "Regulation 30" and "Board of Directors",
# so neither is allowed to drive a category on its own.
SUBJECT_RULES: tuple[tuple[str, tuple[re.Pattern[str], ...]], ...] = (
    ("Routine", _p(r"newspaper", r"certificate under", r"trading window", r"loss of share", r"duplicate share", r"spurious",
                   r"compliance certificate", r"esop|esos|employee stock", r"investor complaints", r"\bxbrl\b",
                   r"business responsibility", r"\besg\b", r"related party transactions?$")),
    ("Earnings call", _p(r"con\.? ?call", r"conference call", r"earnings call", r"audio recording", r"transcript")),
    ("Investor meetings", _p(r"investor meet", r"analysts?/institutional", r"investor conference")),
    ("Results", _p(r"financial results?", r"\bresults?\b", r"integrated filing.*financial")),
    ("Acquisitions", _p(r"acquisition", r"amalgamation", r"merger", r"demerger", r"scheme of arrangement", r"joint venture", r"takeover")),
    ("Fundraising", _p(r"raising of funds", r"fund ?rais", r"rights issue", r"preferential", r"\bqip\b", r"qualified institution",
                       r"buy ?back", r"commercial paper", r"debentures?", r"allotment of securities")),
    ("Management changes", _p(r"change in (?:directorate|management|director|key managerial|kmp)", r"appointment", r"resignation",
                              r"cessation", r"re-?designation", r"retire")),
    ("Regulatory updates", _p(r"litigation", r"action\(s\) (?:taken|initiated)|orders? passed", r"penalt", r"show cause", r"insolvency",
                              r"\bnclt\b", r"\bsebi\b.*order", r"default", r"fraud")),
    ("Credit rating", _p(r"credit rating", r"\brating\b")),
    ("Pledging", _p(r"pledge", r"encumbrance")),
    ("Insider trading", _p(r"insider trading", r"\bsast\b", r"reg(?:ulation)?\.? ?7\(2\)")),
    ("Capex", _p(r"capex", r"capacity (?:addition|expansion)", r"commencement of (?:commercial )?production", r"new plant", r"expansion")),
    ("Order wins", _p(r"award of order", r"receipt of order", r"bagging", r"order win", r"letter of award|\bloa\b", r"contracts?\b", r"work order")),
    ("Corporate actions", _p(r"dividend", r"record date", r"book closure", r"bonus", r"(?:stock|share) split|sub-?division", r"postal ballot",
                             r"(?:annual|extra-?ordinary) general meeting|\bagm\b|\begm\b", r"shareholders? meeting")),
)
BODY_RULES: tuple[tuple[str, tuple[re.Pattern[str], ...]], ...] = (
    ("Earnings call", _p(r"call with (?:the )?(?:media|analysts|investors)", r"press conference", r"webcast", r"transcript of (?:the )?(?:earnings|conference|con\.?) ?call", r"(?:transcript|audio recording) of the discussion",
                         r"audio recording of (?:the )?(?:earnings|conference)", r"(?:earnings|conference) call (?:is )?scheduled")),
    ("Results", _p(r"(?:approved|considered|submitted).{0,80}financial results", r"financial results? for the (?:quarter|period|half|year)",
                   r"quarterly results", r"unaudited (?:standalone |consolidated )?financial results")),
    ("Acquisitions", _p(r"\bacqui(?:re|sition)", r"amalgamation", r"\bmerger\b", r"demerger", r"joint venture", r"stake (?:sale|purchase)")),
    ("Management changes", _p(r"\b(?:appoint(?:ed|ment)|resign(?:ed|ation)|cessation|retire(?:d|ment)?)\b.{0,80}\b(?:managing director|whole[- ]?time director|chief \w+ officer|ceo|cfo|coo|company secretary|key managerial|independent director)")),
    ("Fundraising", _p(r"rights issue", r"preferential (?:issue|allotment)", r"qualified institutions? placement", r"\bqip\b",
                       r"non[- ]convertible debentures", r"commercial paper", r"buy-?back")),
    ("Regulatory updates", _p(r"show cause notice", r"penalty of", r"(?:order|demand) (?:passed|received|issued) by", r"insolvency", r"\bnclt\b",
                              r"\bgst\b.{0,40}(?:demand|order)", r"income tax.{0,40}(?:demand|order)")),
    ("Order wins", _p(r"(?:received|secured|bagged|won) (?:an? )?(?:order|contract)", r"letter of award", r"work order")),
    ("Credit rating", _p(r"credit rating", r"\b(?:crisil|icra|care ratings|india ratings|fitch|moody)")),
    ("Capex", _p(r"capacity (?:expansion|addition)", r"capital expenditure", r"commercial production")),
    ("Corporate actions", _p(r"\bdividend\b", r"record date", r"bonus (?:issue|shares)", r"sub-?division", r"postal ballot", r"general meeting")),
)
GENERIC_SUBJECT = re.compile(r"\s*(?:general\s+)?updates?|press release|outcome of board meeting|disclosure.*|other restructuring|", re.I)
_HIGH = re.compile(r"resign|cessation|fraud|insolvency|default|penalt|show cause|downgrade|terminat|qualified opinion|\bqip\b|rights issue|acqui|merger|demerger", re.I)
_TOP_ROLE = re.compile(r"managing director|\bceo\b|\bcfo\b|chief executive|chief financial|whole[- ]?time director|chairman|chairperson", re.I)


def classify(title: str, summary: str) -> tuple[str, str]:
    """Return (category, severity). The exchange subject line wins; body text is the fallback."""
    subject, body = title or "", summary or ""
    category = ""
    for name, patterns in SUBJECT_RULES:
        if any(p.search(subject) for p in patterns):
            category = name
            break
    if not category or GENERIC_SUBJECT.fullmatch(subject):
        for name, patterns in BODY_RULES:
            if any(p.search(body) for p in patterns):
                category = name
                break
    if not category:
        category = "Routine" if subject.strip() else ""
    return (category, priority(category, f"{subject} {body}")) if category else ("", "")


def priority(category: str, text: str) -> str:
    if category in {"Results", "Acquisitions", "Fundraising"}:
        return "High"
    if category == "Management changes":
        return "High" if _TOP_ROLE.search(text) else "Medium"
    if category in {"Regulatory updates", "Credit rating", "Pledging"}:
        return "High" if _HIGH.search(text) else "Medium"
    if category in {"Order wins", "Capex"}:
        return "Medium"
    return "Low"


def why_matters(category: str) -> str:
    return {
        "Results": "Results reset the earnings baseline. The first-cut table compares the quarter with the previous quarter and the same quarter last year.",
        "Order wins": "New contracts can affect revenue visibility and capacity utilisation. Order size relative to annual revenue and the execution timeline determine materiality.",
        "Acquisitions": "A transaction can change the company’s growth profile, capital needs and risk. Deal size, funding and completion conditions matter most.",
        "Management changes": "Leadership changes affect execution and oversight. Who is coming in, from where, and whether succession was planned all matter.",
        "Fundraising": "New capital can fund growth or repair the balance sheet, while changing leverage or diluting existing holders.",
        "Regulatory updates": "Legal or regulatory developments can affect operations, costs and governance. Look for a quantified exposure and the current status.",
        "Corporate actions": "Changes shareholder cash flows or share count. Check the record date and ratio; rarely moves the investment case.",
        "Capex": "New capacity signals management’s demand outlook and will shape future depreciation, debt and returns.",
        "Credit rating": "Rating actions move the cost of debt and signal an outside view of balance-sheet risk.",
        "Pledging": "Promoter pledges can force selling if the share price falls; rising pledges are a risk signal.",
        "Insider trading": "Insider buying or selling can signal how insiders view valuation, though trades are often routine.",
        "Earnings call": "Housekeeping for the investor call. The transcript itself is indexed for Research once it is filed.",
        "Investor meetings": "Schedule of meetings with investors; useful context, rarely market-moving on its own.",
        "Routine": "Routine compliance paperwork. Kept for completeness and collapsed by default.",
        "Price move": "An unusual end-of-day move against the stock’s own recent trading.",
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
    def __init__(self, provider: ExchangeAnnouncementProvider | None = None, pdf_downloader: Any | None = None) -> None:
        self.provider = provider or ExchangeAnnouncementProvider()
        self._pdf_downloader = pdf_downloader

    def _download(self, url: str) -> bytes:
        if self._pdf_downloader is None:
            from app.integrations.documents.nse_provider import NSEResearchDocumentProvider
            self._pdf_downloader = NSEResearchDocumentProvider()
        return self._pdf_downloader.download_pdf(url)

    def refresh(self, session: Session, days: int = 7, limit: int = 25, enrich: bool = True) -> dict[str, Any]:
        end = datetime.now(IST).date()
        start = end - timedelta(days=days - 1)
        portfolio = session.scalar(select(Portfolio).limit(1))
        query = select(Instrument).where(Instrument.exchange == "NSE")
        if portfolio:
            query = query.join(PortfolioHolding, PortfolioHolding.company_id == Instrument.company_id).where(PortfolioHolding.portfolio_id == portfolio.id).order_by(PortfolioHolding.sort_order)
        else:
            query = query.order_by(Instrument.symbol)
        instruments = session.scalars(query.limit(limit)).all()
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
        reclassified = self.reclassify(session)
        enriched = self.enrich_pending(session) if enrich else {"attempted": 0}
        return {"inserted": inserted, "duplicates": duplicates, "ignored": ignored, "fetched": len(raw), "errors": errors, "symbols": [item.symbol for item in instruments], "from_date": start.isoformat(), "to_date": end.isoformat(), "reclassified": reclassified, "enrichment": enriched, "source": "NSE and BSE public corporate announcement feeds"}

    @staticmethod
    def reclassify(session: Session) -> int:
        """Re-apply the current classifier to stored exchange filings (cheap; titles/bodies are stored)."""
        changed = 0
        for event in session.scalars(select(Announcement).where(Announcement.is_demo.is_(False), Announcement.category != "Price move")):
            category, severity = classify(event.title, event.summary)
            if category and (category != event.category or severity != event.severity):
                event.category, event.severity = category, severity
                event.why_it_matters = why_matters(category)
                changed += 1
        session.commit()
        return changed

    def enrich_pending(self, session: Session, max_items: int = 30) -> dict[str, int]:
        """Download Results / Management-change filings once and store the extracted first cut."""
        pending = session.scalars(
            select(Announcement)
            .where(Announcement.is_demo.is_(False), Announcement.category.in_(("Results", "Management changes")), Announcement.enrichment_json.is_(None), Announcement.source_url.like("%.pdf"))
            .order_by(Announcement.published_at.desc())
            .limit(max_items)
        ).all()
        stats = {"attempted": 0, "parsed": 0, "failed": 0}
        for event in pending:
            stats["attempted"] += 1
            try:
                pdf = self._download(event.source_url)
                data = parse_results_pdf(pdf) if event.category == "Results" else parse_people_pdf(pdf)
            except Exception as exc:  # network / format errors are recorded, never fabricated around
                data = {"kind": "results" if event.category == "Results" else "people", "status": "unavailable", "reason": f"Filing could not be downloaded ({str(exc)[:120]})."}
            apply_enrichment(event, data)
            stats["parsed" if data.get("status") == "parsed" else "failed"] += 1
            session.commit()
        return stats


def apply_enrichment(event: Announcement, data: dict[str, Any]) -> None:
    event.enrichment_json = json.dumps(data, ensure_ascii=False)
    if data.get("kind") == "results" and data.get("status") == "parsed":
        headline = results_headline(data)
        if headline:
            event.summary = headline
        pat = next((m for m in data["metrics"] if m["metric"] == "PAT"), None)
        if pat and pat.get("yoy_pct") is not None:
            event.positive = pat["yoy_pct"] >= 0
    elif data.get("kind") == "people" and data.get("people"):
        first = data["people"][0]
        if first.get("name"):
            role = f" ({first['role']})" if first.get("role") else ""
            action = f"{data['action'].capitalize()}: " if data.get("action") else ""
            event.summary = f"{action}{first['name']}{role}. " + (first["profile"][:220] + "…" if first.get("profile") else "No profile disclosed in the filing.")
