"""NSE listed company discovery, universe catalog, and dynamic ticker lookup."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.domain.models import Company, Instrument, Portfolio, PortfolioHolding, ResearchDocument

# Comprehensive curated registry of major NSE-listed companies across sectors
NSE_SECURITIES: list[dict[str, str]] = [
    # Existing Demo Universe
    {"symbol": "RELIANCE", "name": "Reliance Industries Limited", "sector": "Energy", "bse_code": "500325"},
    {"symbol": "HDFCBANK", "name": "HDFC Bank Limited", "sector": "Financial Services", "bse_code": "500180"},
    {"symbol": "TCS", "name": "Tata Consultancy Services Limited", "sector": "Technology", "bse_code": "532540"},
    {"symbol": "ICICIBANK", "name": "ICICI Bank Limited", "sector": "Financial Services", "bse_code": "532174"},
    {"symbol": "BHARTIARTL", "name": "Bharti Airtel Limited", "sector": "Telecom", "bse_code": "532454"},
    {"symbol": "INFY", "name": "Infosys Limited", "sector": "Technology", "bse_code": "500209"},
    {"symbol": "LT", "name": "Larsen & Toubro Limited", "sector": "Industrials", "bse_code": "500510"},
    {"symbol": "ITC", "name": "ITC Limited", "sector": "Consumer Defensive", "bse_code": "500875"},
    {"symbol": "ASIANPAINT", "name": "Asian Paints Limited", "sector": "Consumer Cyclical", "bse_code": "500820"},
    {"symbol": "MARUTI", "name": "Maruti Suzuki India Limited", "sector": "Consumer Cyclical", "bse_code": "532500"},

    # Core Extended NSE Universe (Financials)
    {"symbol": "SBIN", "name": "State Bank of India", "sector": "Financial Services", "bse_code": "500112"},
    {"symbol": "AXISBANK", "name": "Axis Bank Limited", "sector": "Financial Services", "bse_code": "532215"},
    {"symbol": "KOTAKBANK", "name": "Kotak Mahindra Bank Limited", "sector": "Financial Services", "bse_code": "500247"},
    {"symbol": "BAJFINANCE", "name": "Bajaj Finance Limited", "sector": "Financial Services", "bse_code": "500034"},
    {"symbol": "BAJAJFINSV", "name": "Bajaj Finserv Limited", "sector": "Financial Services", "bse_code": "532978"},
    {"symbol": "INDUSINDBK", "name": "IndusInd Bank Limited", "sector": "Financial Services", "bse_code": "532187"},
    {"symbol": "BANKBARODA", "name": "Bank of Baroda", "sector": "Financial Services", "bse_code": "532134"},
    {"symbol": "PNB", "name": "Punjab National Bank", "sector": "Financial Services", "bse_code": "532461"},
    {"symbol": "CANBK", "name": "Canara Bank", "sector": "Financial Services", "bse_code": "532483"},
    {"symbol": "HDFCLIFE", "name": "HDFC Life Insurance Company Limited", "sector": "Financial Services", "bse_code": "540777"},
    {"symbol": "SBILIFE", "name": "SBI Life Insurance Company Limited", "sector": "Financial Services", "bse_code": "540719"},
    {"symbol": "CHOLAFIN", "name": "Cholamandalam Investment and Finance Company Limited", "sector": "Financial Services", "bse_code": "511243"},

    # Healthcare & Pharma
    {"symbol": "SUNPHARMA", "name": "Sun Pharmaceutical Industries Limited", "sector": "Healthcare", "bse_code": "524715"},
    {"symbol": "DRREDDY", "name": "Dr. Reddy's Laboratories Limited", "sector": "Healthcare", "bse_code": "500124"},
    {"symbol": "CIPLA", "name": "Cipla Limited", "sector": "Healthcare", "bse_code": "500087"},
    {"symbol": "DIVISLAB", "name": "Divi's Laboratories Limited", "sector": "Healthcare", "bse_code": "532488"},
    {"symbol": "APOLLOHOSP", "name": "Apollo Hospitals Enterprise Limited", "sector": "Healthcare", "bse_code": "508869"},
    {"symbol": "TORNTPHARM", "name": "Torrent Pharmaceuticals Limited", "sector": "Healthcare", "bse_code": "500420"},
    {"symbol": "LUPIN", "name": "Lupin Limited", "sector": "Healthcare", "bse_code": "500257"},
    {"symbol": "BIOCON", "name": "Biocon Limited", "sector": "Healthcare", "bse_code": "532523"},

    # Consumer & Retail
    {"symbol": "HINDUNILVR", "name": "Hindustan Unilever Limited", "sector": "Consumer Defensive", "bse_code": "500696"},
    {"symbol": "NESTLEIND", "name": "Nestle India Limited", "sector": "Consumer Defensive", "bse_code": "500790"},
    {"symbol": "BRITANNIA", "name": "Britannia Industries Limited", "sector": "Consumer Defensive", "bse_code": "500825"},
    {"symbol": "TATACONSUM", "name": "Tata Consumer Products Limited", "sector": "Consumer Defensive", "bse_code": "500800"},
    {"symbol": "DABUR", "name": "Dabur India Limited", "sector": "Consumer Defensive", "bse_code": "500096"},
    {"symbol": "GODREJCP", "name": "Godrej Consumer Products Limited", "sector": "Consumer Defensive", "bse_code": "532424"},
    {"symbol": "MARICO", "name": "Marico Limited", "sector": "Consumer Defensive", "bse_code": "531642"},
    {"symbol": "COLPAL", "name": "Colgate-Palmolive (India) Limited", "sector": "Consumer Defensive", "bse_code": "500830"},
    {"symbol": "VBL", "name": "Varun Beverages Limited", "sector": "Consumer Defensive", "bse_code": "540180"},
    {"symbol": "DMART", "name": "Avenue Supermarts Limited", "sector": "Consumer Defensive", "bse_code": "540376"},
    {"symbol": "TITAN", "name": "Titan Company Limited", "sector": "Consumer Cyclical", "bse_code": "500114"},
    {"symbol": "TRENT", "name": "Trent Limited", "sector": "Consumer Cyclical", "bse_code": "500251"},
    {"symbol": "ZOMATO", "name": "Zomato Limited", "sector": "Consumer Cyclical", "bse_code": "543320"},

    # Technology
    {"symbol": "WIPRO", "name": "Wipro Limited", "sector": "Technology", "bse_code": "507685"},
    {"symbol": "HCLTECH", "name": "HCL Technologies Limited", "sector": "Technology", "bse_code": "532281"},
    {"symbol": "TECHM", "name": "Tech Mahindra Limited", "sector": "Technology", "bse_code": "532755"},
    {"symbol": "LTIM", "name": "LTIMindtree Limited", "sector": "Technology", "bse_code": "540005"},
    {"symbol": "PERSISTENT", "name": "Persistent Systems Limited", "sector": "Technology", "bse_code": "533179"},
    {"symbol": "COFORGE", "name": "Coforge Limited", "sector": "Technology", "bse_code": "532541"},
    {"symbol": "MPHASIS", "name": "Mphasis Limited", "sector": "Technology", "bse_code": "526299"},

    # Automotive
    {"symbol": "TMPV", "name": "Tata Motors Passenger Vehicles Limited", "sector": "Consumer Cyclical", "bse_code": "500570"},
    {"symbol": "TMCV", "name": "Tata Motors Limited", "sector": "Consumer Cyclical", "bse_code": "500570"},
    {"symbol": "M&M", "name": "Mahindra & Mahindra Limited", "sector": "Consumer Cyclical", "bse_code": "500520"},
    {"symbol": "BAJAJ-AUTO", "name": "Bajaj Auto Limited", "sector": "Consumer Cyclical", "bse_code": "532977"},
    {"symbol": "EICHERMOT", "name": "Eicher Motors Limited", "sector": "Consumer Cyclical", "bse_code": "505200"},
    {"symbol": "HEROMOTOCO", "name": "Hero MotoCorp Limited", "sector": "Consumer Cyclical", "bse_code": "500182"},
    {"symbol": "TVSMOTOR", "name": "TVS Motor Company Limited", "sector": "Consumer Cyclical", "bse_code": "532343"},
    {"symbol": "BOSCHLTD", "name": "Bosch Limited", "sector": "Consumer Cyclical", "bse_code": "500530"},
    {"symbol": "MOTHERSON", "name": "Samvardhana Motherson International Limited", "sector": "Consumer Cyclical", "bse_code": "517334"},

    # Industrials & Infrastructure
    {"symbol": "BEL", "name": "Bharat Electronics Limited", "sector": "Industrials", "bse_code": "500049"},
    {"symbol": "HAL", "name": "Hindustan Aeronautics Limited", "sector": "Industrials", "bse_code": "541154"},
    {"symbol": "SIEMENS", "name": "Siemens Limited", "sector": "Industrials", "bse_code": "500550"},
    {"symbol": "ABB", "name": "ABB India Limited", "sector": "Industrials", "bse_code": "500002"},
    {"symbol": "ADANIPORTS", "name": "Adani Ports and Special Economic Zone Limited", "sector": "Industrials", "bse_code": "532921"},
    {"symbol": "HAVELLS", "name": "Havells India Limited", "sector": "Industrials", "bse_code": "517354"},
    {"symbol": "POLYCAB", "name": "Polycab India Limited", "sector": "Industrials", "bse_code": "542652"},
    {"symbol": "IRCTC", "name": "Indian Railway Catering and Tourism Corporation Limited", "sector": "Consumer Cyclical", "bse_code": "542830"},

    # Energy, Utilities, Basic Materials
    {"symbol": "ADANIENT", "name": "Adani Enterprises Limited", "sector": "Energy", "bse_code": "512599"},
    {"symbol": "ONGC", "name": "Oil and Natural Gas Corporation Limited", "sector": "Energy", "bse_code": "500312"},
    {"symbol": "NTPC", "name": "NTPC Limited", "sector": "Utilities", "bse_code": "532555"},
    {"symbol": "POWERGRID", "name": "Power Grid Corporation of India Limited", "sector": "Utilities", "bse_code": "532898"},
    {"symbol": "COALINDIA", "name": "Coal India Limited", "sector": "Energy", "bse_code": "533278"},
    {"symbol": "BPCL", "name": "Bharat Petroleum Corporation Limited", "sector": "Energy", "bse_code": "500547"},
    {"symbol": "IOC", "name": "Indian Oil Corporation Limited", "sector": "Energy", "bse_code": "530965"},
    {"symbol": "GAIL", "name": "GAIL (India) Limited", "sector": "Utilities", "bse_code": "532155"},
    {"symbol": "TATASTEEL", "name": "Tata Steel Limited", "sector": "Basic Materials", "bse_code": "500470"},
    {"symbol": "JSWSTEEL", "name": "JSW Steel Limited", "sector": "Basic Materials", "bse_code": "500228"},
    {"symbol": "HINDALCO", "name": "Hindalco Industries Limited", "sector": "Basic Materials", "bse_code": "500440"},
    {"symbol": "GRASIM", "name": "Grasim Industries Limited", "sector": "Basic Materials", "bse_code": "500300"},
    {"symbol": "ULTRACEMCO", "name": "UltraTech Cement Limited", "sector": "Basic Materials", "bse_code": "532538"},
    {"symbol": "AMBUJACEM", "name": "Ambuja Cements Limited", "sector": "Basic Materials", "bse_code": "500425"},
    {"symbol": "SHREECEM", "name": "Shree Cement Limited", "sector": "Basic Materials", "bse_code": "500387"},
    {"symbol": "PIDILITIND", "name": "Pidilite Industries Limited", "sector": "Basic Materials", "bse_code": "500331"},
    {"symbol": "DLF", "name": "DLF Limited", "sector": "Real Estate", "bse_code": "532868"},
]

_LOOKUP_MAP = {entry["symbol"]: entry for entry in NSE_SECURITIES}


def search_nse_universe(query: str, limit: int = 15) -> list[dict[str, str]]:
    """Match query against known NSE companies by symbol, alias, or legal name."""
    q = query.strip().upper()
    if not q:
        return []

    # Handle common ticker aliases
    aliases = {
        "TATAMOTORS": ["TMPV", "TMCV"],
        "TATA MOTORS": ["TMPV", "TMCV"],
        "SBI": ["SBIN"],
        "STATE BANK": ["SBIN"],
        "HUL": ["HINDUNILVR"],
        "HINDUSTAN UNILEVER": ["HINDUNILVR"],
        "SUN PHARMA": ["SUNPHARMA"],
        "AXIS": ["AXISBANK"],
        "BAJAJ": ["BAJFINANCE", "BAJAJFINSV", "BAJAJ-AUTO"],
    }

    results: list[dict[str, str]] = []
    seen: set[str] = set()

    # 1. Direct alias matches
    for alias_key, symbols in aliases.items():
        if alias_key in q or q in alias_key:
            for s in symbols:
                if s in _LOOKUP_MAP and s not in seen:
                    results.append(_LOOKUP_MAP[s])
                    seen.add(s)

    # 2. Exact or prefix symbol matches
    for entry in NSE_SECURITIES:
        sym = entry["symbol"]
        if sym not in seen and (sym == q or sym.startswith(q)):
            results.append(entry)
            seen.add(sym)

    # 3. Name or substring matches
    for entry in NSE_SECURITIES:
        sym = entry["symbol"]
        name_clean = entry["name"].upper()
        if sym not in seen and (q in sym or q in name_clean or all(token in name_clean for token in q.split())):
            results.append(entry)
            seen.add(sym)

    # 4. If nothing matched and query looks like an exact ticker, try dynamic yfinance lookup
    if not results and re.match(r"^[A-Z0-9&-]{2,15}$", q):
        dynamic = lookup_external_ticker(q)
        if dynamic and dynamic["symbol"] not in seen:
            results.append(dynamic)

    return results[:limit]


def lookup_external_ticker(symbol: str) -> dict[str, str] | None:
    """Dynamically verify an uncatalogued NSE ticker via Yahoo Finance."""
    sym = symbol.strip().upper()
    try:
        import yfinance as yf
        ticker = yf.Ticker(f"{sym}.NS")
        info = getattr(ticker, "info", None)
        if not info or not isinstance(info, dict):
            return None
        short_name = info.get("shortName") or info.get("longName")
        if not short_name:
            return None
        sector = info.get("sector") or "Other"
        clean_name = " ".join(short_name.split())
        return {
            "symbol": sym,
            "name": clean_name,
            "sector": sector,
            "bse_code": "",
        }
    except Exception:
        return None


def ensure_company(
    session: Session,
    symbol: str,
    name: str | None = None,
    sector: str | None = None,
    bse_code: str | None = None,
) -> tuple[Company, Instrument]:
    """Ensure an NSE company and its instrument exist in the database; create if missing."""
    sym = symbol.strip().upper()
    instrument = session.scalar(
        select(Instrument).where(Instrument.exchange == "NSE", Instrument.symbol == sym)
    )
    if instrument:
        company = session.get(Company, instrument.company_id)
        if company:
            return company, instrument

    # Company not in DB: resolve metadata
    catalog_entry = _LOOKUP_MAP.get(sym) or lookup_external_ticker(sym)
    company_name = name or (catalog_entry["name"] if catalog_entry else f"{sym} Limited")
    company_sector = sector or (catalog_entry["sector"] if catalog_entry else "Other")
    scrip_code = bse_code or (catalog_entry.get("bse_code") if catalog_entry else None)

    # Check if company with exact name exists
    company = session.scalar(select(Company).where(Company.name == company_name))
    if not company:
        company = Company(name=company_name, sector=company_sector)
        session.add(company)
        session.flush()

    new_instrument = Instrument(
        company_id=company.id,
        exchange="NSE",
        symbol=sym,
        provider_symbol=f"{sym}.NS",
        bse_scrip_code=scrip_code,
    )
    session.add(new_instrument)
    session.commit()
    session.refresh(company)
    session.refresh(new_instrument)
    return company, new_instrument


def search_companies_service(
    session: Session,
    q: str = "",
    exchange: str = "NSE",
    limit: int = 20,
) -> dict[str, Any]:
    """Search companies combining local SQLite holdings and the extended NSE universe."""
    clean_q = q.strip()
    portfolio = session.scalar(select(Portfolio).limit(1))
    holdings = {
        h.company_id
        for h in session.scalars(select(PortfolioHolding).where(PortfolioHolding.portfolio_id == portfolio.id))
    } if portfolio else set()

    # Track returned symbols
    items: list[dict[str, Any]] = []
    seen_symbols: set[str] = set()

    # 1. Search existing DB records
    db_query = select(Company, Instrument).join(Instrument).where(Instrument.exchange == exchange.upper())
    if clean_q:
        pattern = f"%{clean_q}%"
        db_query = db_query.where(or_(Company.name.ilike(pattern), Instrument.symbol.ilike(pattern)))
    db_query = db_query.order_by(Company.name).limit(limit)

    for c, i in session.execute(db_query).all():
        seen_symbols.add(i.symbol)
        # Determine if company is demo: seeded companies with is_demo portfolio or metrics
        doc_count = session.scalar(
            select(ResearchDocument.id).where(ResearchDocument.company_id == c.id, ResearchDocument.is_demo.is_(False)).limit(1)
        )
        items.append({
            "id": c.id,
            "name": c.name,
            "symbol": i.symbol,
            "exchange": i.exchange,
            "sector": c.sector,
            "in_portfolio": c.id in holdings,
            "is_demo": c.id in holdings or (doc_count is None and c.id <= 10),
        })

    # 2. If user queried with search terms, supplement from NSE securities universe
    if clean_q:
        universe_matches = search_nse_universe(clean_q, limit=limit)
        for entry in universe_matches:
            sym = entry["symbol"]
            if sym in seen_symbols:
                continue
            # Automatically persist into database so it receives a permanent company_id
            company, instrument = ensure_company(session, sym, entry["name"], entry["sector"], entry.get("bse_code"))
            seen_symbols.add(sym)
            items.append({
                "id": company.id,
                "name": company.name,
                "symbol": instrument.symbol,
                "exchange": instrument.exchange,
                "sector": company.sector,
                "in_portfolio": False,
                "is_demo": False,
            })
            if len(items) >= limit:
                break

    return {
        "items": items[:limit],
        "is_demo": all(item["is_demo"] for item in items) if items else False,
    }

