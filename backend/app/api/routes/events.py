import json
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select
from app.domain.models import AlertRule, Announcement, Company, Instrument, Portfolio, PortfolioHolding
from app.services.alert_engine import (
    calculate_priority_score,
    deduplicate_alerts,
    enrich_alert_reasons,
    enrichment_of,
    should_include_alert,
)
from app.services.eod_triggers import sync_triggers
from app.services.filing_enrichment import results_why

PERIOD_SECONDS = {"24 hours": 86400, "7 days": 7 * 86400, "30 days": 30 * 86400}
LOW_SIGNAL = {"Routine", "Earnings call", "Investor meetings", "Corporate actions", "Insider trading"}

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
    if minutes < 60:
        time_label = f"{minutes} min ago"
    elif minutes < 24 * 60:
        time_label = f"{minutes // 60} hr ago"
    elif minutes < 48 * 60:
        time_label = "Yesterday"
    else:
        time_label = f"{minutes // 1440} days ago"

    why, facts = enrich_alert_reasons(event, company, instrument, holding, market_data, rule)
    enrichment = enrichment_of(event)
    if enrichment.get("kind") == "results":
        why = results_why(enrichment) or why

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
        "enrichment": enrichment,
        "routine": event.category in LOW_SIGNAL or event.severity == "Low",
    }


@router.get("/digest")
@router.get("/alerts")
def get_digest(request: Request, period: str = "24 hours", category: str | None = None, limit: int = 150) -> dict:
    window = PERIOD_SECONDS.get(period, PERIOD_SECONDS["24 hours"])
    with request.app.state.session_factory() as session:
        portfolio = session.scalar(select(Portfolio).limit(1))
        holdings = {h.company_id: h for h in session.scalars(select(PortfolioHolding).where(PortfolioHolding.portfolio_id == portfolio.id))} if portfolio else {}
        tracked_instruments = session.scalars(select(Instrument).where(Instrument.exchange == "NSE", Instrument.company_id.in_(holdings))).all()

        # Triggered alerts: refresh EOD bars (batched, cached) and recompute threshold crossings.
        market = request.app.state.market_data
        market.refresh_many(session, list(tracked_instruments))
        sync_triggers(session, list(tracked_instruments))

        rules_by_category = {rule.category: rule for rule in session.scalars(select(AlertRule))}
        cutoff = datetime.now(timezone.utc).timestamp() - window
        query = (select(Announcement, Company, Instrument)
                 .join(Company, Announcement.company_id == Company.id)
                 .join(Instrument, Instrument.company_id == Company.id)
                 .where(Instrument.exchange == "NSE")
                 .order_by(Announcement.published_at.desc()).limit(600))
        out, filtered = [], 0
        quotes: dict[int, dict] = {}
        for event, company, instrument in session.execute(query).all():
            published = event.published_at if event.published_at.tzinfo else event.published_at.replace(tzinfo=timezone.utc)
            if published.timestamp() < cutoff:
                continue
            if category and event.category.lower() != category.lower():
                continue
            if portfolio and company.id not in holdings:
                continue
            included, _ = should_include_alert(event, rules_by_category)
            if not included:
                filtered += 1
                continue
            holding = holdings.get(company.id)
            if instrument.id not in quotes:
                quotes[instrument.id] = market.quote(session, instrument)
            quote = quotes[instrument.id]
            score = calculate_priority_score(event, holding, quote)
            out.append(_serialize(event, company, instrument, holding, quote, rules_by_category.get(event.category), score))

        deduped = deduplicate_alerts(out)
        deduped.sort(key=lambda item: item.get("priority_score", 0.0), reverse=True)
        items = deduped[:limit]
        return {
            "items": items,
            "count": len(items),
            "material_count": sum(1 for item in items if not item["routine"]),
            "filtered_by_rules": filtered,
            "period": period if period in PERIOD_SECONDS else "24 hours",
            "is_demo": False,
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
        if not event.is_read:
            event.is_read = True
            session.commit()
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
