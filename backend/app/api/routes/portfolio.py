from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select
from app.domain.models import Company, Instrument, Portfolio, PortfolioHolding

router = APIRouter(tags=["portfolio"])

def _payload(holding: PortfolioHolding, company: Company, instrument: Instrument) -> dict:
    return {"id": instrument.symbol.lower(), "company_id": company.id, "name": company.name, "symbol": instrument.symbol, "exchange": instrument.exchange, "sector": company.sector or "Other", "price": None, "change": None, "positive": None, "weight": holding.weight, "market_data": None, "is_demo": True}

@router.get("/portfolio")
def get_portfolio(request: Request) -> dict:
    with request.app.state.session_factory() as session:
        portfolio = session.scalar(select(Portfolio).limit(1))
        if not portfolio:
            return {"id": None, "name": "Demo portfolio", "is_demo": True, "holdings": []}
        rows = session.execute(select(PortfolioHolding, Company, Instrument).join(Company, Company.id == PortfolioHolding.company_id).join(Instrument, Instrument.company_id == Company.id).where(PortfolioHolding.portfolio_id == portfolio.id, Instrument.exchange == "NSE").order_by(PortfolioHolding.sort_order)).all()
        holdings = []
        market_data = request.app.state.market_data
        for holding, company, instrument in rows:
            item = _payload(holding, company, instrument)
            quote = market_data.quote(session, instrument)
            item["market_data"] = quote
            item["price"] = quote["close"]
            item["change"] = quote["change_percent"]
            item["positive"] = quote["change_percent"] >= 0 if quote["change_percent"] is not None else None
            holdings.append(item)
        return {"id": portfolio.id, "name": portfolio.name, "is_demo": portfolio.is_demo, "holdings": holdings,
                "summary": {"companies_tracked": len(holdings), "portfolio_value": None, "daily_change_value": None,
                            "daily_change_percent": None, "valuation_status": "unavailable",
                            "valuation_note": "Position quantities are not configured; live prices are shown per share."},
                "market_data_source": "Yahoo Finance (via yfinance)",
                "latest_available_as_of": max((h["market_data"]["market_as_of"] for h in holdings if h["market_data"]["market_as_of"]), default=None)}

@router.put("/portfolio/holdings/{symbol}")
def set_holding(symbol: str, request: Request, enabled: bool) -> dict:
    with request.app.state.session_factory() as session:
        portfolio = session.scalar(select(Portfolio).limit(1))
        company = session.scalar(select(Company).join(Instrument).where(Instrument.symbol == symbol.upper(), Instrument.exchange == "NSE"))
        if not portfolio or not company:
            raise HTTPException(status_code=404, detail="Company not found")
        holding = session.get(PortfolioHolding, (portfolio.id, company.id))
        if enabled and not holding:
            session.add(PortfolioHolding(portfolio_id=portfolio.id, company_id=company.id, weight=0, sort_order=99))
        elif not enabled and holding:
            session.delete(holding)
        session.commit()
        return {"symbol": symbol.upper(), "tracked": enabled}
