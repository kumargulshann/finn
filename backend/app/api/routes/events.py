import json
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select
from app.domain.models import AlertRule, Announcement, Company, Instrument, Portfolio, PortfolioHolding
from app.services.alert_engine import (
    calculate_priority_score,
    deduplicate_alerts,
    enrich_alert_reasons,
    should_include_alert,
)

router = APIRouter(tags=["alerts"])


def _serialize(
    event: Announcement,
    company: Company,
    instrument: Instrument,
    holding: PortfolioHolding | None = None,
    market_data: dict | None = None,
    rule: AlertRule | None = None,
    score: float | None = None,
) -> dict:
    published = event.published_at
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    minutes = max(1, int((datetime.now(timezone.utc) - published).total_seconds() / 60))
    time_label = f"{minutes} min ago" if minutes < 60 else ("Yesterday" if minutes > 720 else f"{minutes // 60} hr ago")

    why, facts = enrich_alert_reasons(event, company, instrument, holding, market_data, rule)

    return {
        "id": event.slug,
        "company_id": company.id,
        "company": company.name,
        "symbol": instrument.symbol,
        "sector": company.sector or "Other",
        "title": event.title,
        "summary": event.summary,
        "type": event.category,
        "time": time_label,
        "published_at": published.isoformat(),
        "impact": event.severity,
        "positive": event.positive,
        "initials": company.name[0],
        "color": "#5e9f87",
        "source": event.source_url,
        "sourceName": event.source_name,
        "sourceDate": event.source_date,
        "source_exchange": event.source_exchange,
        "why": why,
        "details": facts,
        "is_demo": event.is_demo,
        "is_read": event.is_read,
        "is_saved": event.is_saved,
        "portfolio_weight": holding.weight if holding else None,
        "price": market_data.get("close") if market_data else None,
        "daily_change": market_data.get("change_percent") if market_data else None,
        "market_data": market_data,
        "priority_score": score,
    }


@router.get("/digest")
@router.get("/alerts")
def get_digest(request: Request, period: str = "24 hours", category: str | None = None, limit: int = 50) -> dict:
    with request.app.state.session_factory() as session:
        portfolio = session.scalar(select(Portfolio).limit(1))
        tracked_ids = set(session.scalars(select(PortfolioHolding.company_id).where(PortfolioHolding.portfolio_id == portfolio.id))) if portfolio else set()

        rules = session.scalars(select(AlertRule)).all()
        rules_by_category = {rule.category: rule for rule in rules}

        query = select(Announcement, Company, Instrument).join(Company, Announcement.company_id == Company.id).join(Instrument, Instrument.company_id == Company.id).where(Instrument.exchange == "NSE").order_by(Announcement.published_at.desc()).limit(min(max(limit, 1), 100))
        rows = session.execute(query).all()
        out = []
        for event, company, instrument in rows:
            age_seconds = (datetime.now(timezone.utc) - (event.published_at.replace(tzinfo=timezone.utc) if event.published_at.tzinfo is None else event.published_at)).total_seconds()
            if age_seconds > (86400 if period == "24 hours" else 604800):
                continue
            if category and event.category.lower() != category.lower():
                continue
            if portfolio and company.id not in tracked_ids:
                continue

            rule = rules_by_category.get(event.category)
            # Evaluate category enablement and threshold
            included, _ = should_include_alert(event, rules_by_category)
            if not included:
                continue

            holding = session.get(PortfolioHolding, (portfolio.id, company.id)) if portfolio else None
            quote = request.app.state.market_data.quote(session, instrument)
            score = calculate_priority_score(event, holding, quote)
            out.append(_serialize(event, company, instrument, holding, quote, rule, score))

        # Deduplicate alerts
        deduped = deduplicate_alerts(out)

        # Sort by composite priority score (Financial impact, event type, market move, recency)
        deduped.sort(key=lambda item: item.get("priority_score", 0.0), reverse=True)
        result_items = deduped[:limit]

        return {
            "items": result_items,
            "count": len(result_items),
            "is_demo": all(item["is_demo"] for item in result_items) if result_items else True,
        }


@router.get("/events/{event_id}")
@router.get("/alerts/{event_id}")
def get_event(event_id: str, request: Request) -> dict:
    with request.app.state.session_factory() as session:
        row = session.execute(select(Announcement, Company, Instrument).join(Company, Announcement.company_id == Company.id).join(Instrument, Instrument.company_id == Company.id).where(Announcement.slug == event_id, Instrument.exchange == "NSE")).first()
        if not row:
            raise HTTPException(status_code=404, detail="Alert not found")
        event, company, instrument = row
        portfolio = session.scalar(select(Portfolio).limit(1))
        holding = session.get(PortfolioHolding, (portfolio.id, company.id)) if portfolio else None
        quote = request.app.state.market_data.quote(session, instrument)
        rule = session.scalar(select(AlertRule).where(AlertRule.category == event.category).limit(1))
        score = calculate_priority_score(event, holding, quote)
        return _serialize(event, company, instrument, holding, quote, rule, score)


@router.patch("/events/{event_id}")
@router.patch("/alerts/{event_id}")
def update_event(event_id: str, request: Request, is_read: bool | None = None, is_saved: bool | None = None) -> dict:
    with request.app.state.session_factory() as session:
        event = session.scalar(select(Announcement).where(Announcement.slug == event_id))
        if not event:
            raise HTTPException(status_code=404, detail="Alert not found")
        if is_read is not None:
            event.is_read = is_read
        if is_saved is not None:
            event.is_saved = is_saved
        session.commit()
        return {"id": event.slug, "is_read": event.is_read, "is_saved": event.is_saved}
