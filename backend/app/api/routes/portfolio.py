from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select
from app.domain.models import AlertRule, Company, Instrument, Portfolio, PortfolioHolding
from app.services.eod_triggers import latest_signal

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
        market_data.refresh_many(session, [instrument for _, _, instrument in rows])
        rules = {r.category: r for r in session.scalars(select(AlertRule))}
        vol_t = rules["Price move"].threshold if "Price move" in rules and rules["Price move"].enabled else None
        move_t = rules["Price change"].threshold if "Price change" in rules and rules["Price change"].enabled else None
        for holding, company, instrument in rows:
            item = _payload(holding, company, instrument)
            quote = market_data.quote(session, instrument)
            item["market_data"] = quote
            item["price"] = quote["close"]
            item["change"] = quote["change_percent"]
            item["positive"] = quote["change_percent"] >= 0 if quote["change_percent"] is not None else None
            signal = latest_signal(session, instrument)
            item["volume_multiple"] = signal["volume_multiple"] if signal else None
            item["signal_date"] = signal["trading_date"].isoformat() if signal else None
            vm, mv = item["volume_multiple"], item["change"]
            item["triggered"] = bool((vol_t and vm is not None and vm >= vol_t) or (move_t and mv is not None and abs(mv) >= move_t))
            holdings.append(item)
        return {"id": portfolio.id, "name": portfolio.name, "is_demo": portfolio.is_demo, "holdings": holdings,
                "summary": {"companies_tracked": len(holdings), "portfolio_value": None, "daily_change_value": None,
                            "daily_change_percent": None, "valuation_status": "unavailable",
                            "valuation_note": "Position quantities are not configured; live prices are shown per share."},
                "thresholds": {"volume_multiple": vol_t, "move_pct": move_t},
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
