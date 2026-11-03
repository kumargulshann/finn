from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import func, select
from app.domain.models import Announcement, Company, FinancialMetric, Instrument, Portfolio, PortfolioHolding, ResearchDocument
from app.services.company_discovery import search_companies_service

router = APIRouter(tags=["companies"])


@router.get("/companies")
def search_companies(request: Request, q: str = "", exchange: str = "NSE", limit: int = 20) -> dict:
    with request.app.state.session_factory() as session:
        return search_companies_service(session, q=q, exchange=exchange, limit=limit)


@router.get("/companies/{company_id}")
def company_info(company_id: int, request: Request) -> dict:
    with request.app.state.session_factory() as session:
        company = session.get(Company, company_id)
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")
        instruments = session.scalars(select(Instrument).where(Instrument.company_id == company.id)).all()
        metrics = session.scalars(select(FinancialMetric).where(FinancialMetric.company_id == company.id).order_by(FinancialMetric.id)).all()
        announcements = session.scalars(select(Announcement).where(Announcement.company_id == company.id).order_by(Announcement.published_at.desc())).all()
        portfolio = session.scalar(select(Portfolio).limit(1))
        holding = session.get(PortfolioHolding, (portfolio.id, company.id)) if portfolio else None
        instrument = next((item for item in instruments if item.exchange == "NSE"), instruments[0] if instruments else None)
        quote = request.app.state.market_data.quote(session, instrument) if instrument else None

        doc_count = session.scalar(
            select(func.count(ResearchDocument.id)).where(
                ResearchDocument.company_id == company.id, ResearchDocument.is_demo.is_(False)
            )
        ) or 0
        is_demo_company = bool(metrics and any(m.is_demo for m in metrics))
        source_status = (
            f"{doc_count} official filing(s) indexed"
            if doc_count > 0
            else ("sample demo data loaded" if is_demo_company else "no documents indexed yet")
        )

        return {
            "id": company.id,
            "name": company.name,
            "sector": company.sector,
            "instruments": [{"symbol": i.symbol, "exchange": i.exchange} for i in instruments],
            "market_data": quote,
            "in_portfolio": holding is not None,
            "weight": holding.weight if holding else None,
            "metrics": [{"metric": m.metric, "value": m.value, "unit": m.unit, "period": m.period, "is_demo": m.is_demo} for m in metrics],
            "announcements": [{"id": a.slug, "title": a.title, "summary": a.summary, "category": a.category, "published_at": a.published_at.isoformat(), "source_name": a.source_name, "source_url": a.source_url, "is_demo": a.is_demo} for a in announcements],
            "source_status": source_status,
            "is_demo": is_demo_company,
        }


@router.get("/companies/{company_id}/prices")
def company_prices(company_id: int, request: Request, period: str = "1y") -> dict:
    with request.app.state.session_factory() as session:
        company = session.get(Company, company_id)
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")
        instrument = session.scalar(select(Instrument).where(Instrument.company_id == company.id, Instrument.exchange == "NSE"))
        if not instrument:
            return {"symbol": None, "status": "unavailable", "items": [], "error": "No NSE instrument is configured."}
        return request.app.state.market_data.history(session, instrument, period)
