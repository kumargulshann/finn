from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import func, select

from app.domain.models import Announcement, Company, Instrument

router = APIRouter(tags=["announcements"])


@router.post("/announcements/refresh")
def refresh_announcements(request: Request, days: int = Query(7, ge=1, le=30), limit: int = Query(25, ge=1, le=30)) -> dict:
    """Pull the configured NSE/BSE universe into SQLite. Suitable for a scheduler or manual refresh."""
    with request.app.state.session_factory() as session:
        try:
            return request.app.state.announcement_ingestion.refresh(session, days=days, limit=limit)
        except Exception as exc:
            session.rollback()
            raise HTTPException(status_code=502, detail=f"Announcement refresh failed: {exc}") from exc


@router.get("/announcements")
def list_announcements(request: Request, exchange: str | None = None, symbol: str | None = None, limit: int = Query(50, ge=1, le=100)) -> dict:
    with request.app.state.session_factory() as session:
        query = select(Announcement, Company, Instrument).join(Company, Announcement.company_id == Company.id).join(Instrument, Instrument.company_id == Company.id).where(Instrument.exchange == "NSE")
        if exchange:
            query = query.where(Announcement.source_exchange == exchange.upper())
        if symbol:
            query = query.where(Instrument.symbol == symbol.upper())
        rows = session.execute(query.order_by(Announcement.published_at.desc()).limit(limit)).all()
        items = [{"id": event.slug, "symbol": instrument.symbol, "company": company.name, "category": event.category, "headline": event.title, "summary": event.summary, "published_at": event.published_at.isoformat(), "why_it_matters": event.why_it_matters, "priority": event.severity, "source_exchange": event.source_exchange, "source_name": event.source_name, "source_url": event.source_url, "is_demo": event.is_demo} for event, company, instrument in rows]
        counts = dict(session.execute(select(Announcement.source_exchange, func.count(Announcement.id)).group_by(Announcement.source_exchange)).all())
        return {"items": items, "count": len(items), "counts_by_source": counts}
