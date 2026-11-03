"""Portfolio, universe and alert-rule bootstrap.

`seed_demo_data` is idempotent: it creates the demo portfolio on a fresh database and upgrades an
existing one in place (adds missing holdings and rules, removes retired illustrative records).
No fabricated filings or financial figures are seeded — everything shown in the digest comes from
exchange feeds, the filing PDFs, or end-of-day market data.
"""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.domain.models import AlertRule, Announcement, Company, FinancialMetric, Instrument, Portfolio, PortfolioHolding

# 18 holdings across sectors and market-cap tiers (large, mid and small caps). Weights sum to 100.
COMPANIES = [
    ("Reliance Industries", "RELIANCE", "Energy", 11.0, "500325"),
    ("HDFC Bank", "HDFCBANK", "Banks", 8.5, "500180"),
    ("ICICI Bank", "ICICIBANK", "Banks", 7.5, "532174"),
    ("Tata Consultancy Services", "TCS", "IT services", 7.0, "532540"),
    ("Infosys", "INFY", "IT services", 6.5, "500209"),
    ("Bharti Airtel", "BHARTIARTL", "Telecom", 6.5, "532454"),
    ("Larsen & Toubro", "LT", "Capital goods", 6.0, "500510"),
    ("ITC", "ITC", "FMCG", 5.5, "500875"),
    ("Bajaj Finance", "BAJFINANCE", "NBFC", 5.5, "500034"),
    ("Sun Pharmaceutical Industries", "SUNPHARMA", "Pharma", 5.0, "524715"),
    ("Maruti Suzuki India", "MARUTI", "Automobiles", 5.0, "532500"),
    ("Asian Paints", "ASIANPAINT", "Consumer durables", 4.0, "500820"),
    ("NTPC", "NTPC", "Power", 4.0, "532555"),
    ("UltraTech Cement", "ULTRACEMCO", "Cement", 4.0, "532538"),
    ("Titan Company", "TITAN", "Consumer durables", 4.0, "500114"),
    ("Dixon Technologies", "DIXON", "Electronics mfg", 3.5, "540699"),
    ("Persistent Systems", "PERSISTENT", "IT services", 3.5, "533179"),
    ("Kaynes Technology India", "KAYNES", "Electronics mfg", 3.0, "543664"),
]
BSE_CODES = {symbol: code for _, symbol, _, _, code in COMPANIES}

# (rule name, category, threshold). Categories follow the reference taxonomy.
ALERT_RULES: list[tuple[str, str, float | None]] = [
    ("Results", "Results", None),
    ("M&A", "Acquisitions", None),
    ("Fund raising", "Fundraising", None),
    ("Management changes", "Management changes", None),
    ("Litigation & regulatory", "Regulatory updates", None),
    ("Order wins & press releases", "Order wins", None),
    ("Capex", "Capex", None),
    ("Credit rating", "Credit rating", None),
    ("Promoter pledging", "Pledging", None),
    ("Insider trading", "Insider trading", None),
    ("Dividends, bonus & splits", "Corporate actions", None),
    ("Earnings call notices", "Earnings call", None),
    ("Investor meetings", "Investor meetings", None),
    ("Routine filings", "Routine", None),
    ("Unusual volume", "Price move", 2.0),        # volume ≥ N × 20-day average
    ("Large daily price move", "Price change", 4.0),  # |daily move| ≥ N %
]
RETIRED_RULE_CATEGORIES = ("Earnings", "Corporate action", "Macro")
# Bump when COMPANIES changes; holdings are synced once per version so user edits in Settings survive restarts.
PORTFOLIO_NAME = "FINN demo portfolio · v2"


def seed_demo_data(session: Session) -> None:
    portfolio = session.scalar(select(Portfolio).limit(1))
    if portfolio is None:
        portfolio = Portfolio(name=PORTFOLIO_NAME, is_demo=True)
        session.add(portfolio)
        session.flush()
        sync_holdings = True
    else:
        sync_holdings = portfolio.name != PORTFOLIO_NAME
        portfolio.name = PORTFOLIO_NAME

    for order, (name, symbol, sector, weight, bse_code) in enumerate(COMPANIES):
        instrument = session.scalar(select(Instrument).where(Instrument.exchange == "NSE", Instrument.symbol == symbol))
        if instrument is None:
            company = session.scalar(select(Company).where(Company.name == name))
            if company is None:
                company = Company(name=name, sector=sector)
                session.add(company)
                session.flush()
            instrument = Instrument(company_id=company.id, exchange="NSE", symbol=symbol, provider_symbol=f"{symbol}.NS", bse_scrip_code=bse_code)
            session.add(instrument)
            session.flush()
        company = session.get(Company, instrument.company_id)
        company.sector = sector
        instrument.bse_scrip_code = instrument.bse_scrip_code or bse_code
        holding = session.get(PortfolioHolding, (portfolio.id, company.id))
        if not sync_holdings:
            continue
        if holding is None:
            session.add(PortfolioHolding(portfolio_id=portfolio.id, company_id=company.id, weight=weight, sort_order=order))
        else:
            holding.weight, holding.sort_order = weight, order

    # Retire illustrative content from earlier builds: hand-written events and sample metrics.
    session.execute(delete(Announcement).where(Announcement.is_demo.is_(True)))
    session.execute(delete(FinancialMetric).where(FinancialMetric.is_demo.is_(True)))
    session.execute(delete(AlertRule).where(AlertRule.category.in_(RETIRED_RULE_CATEGORIES)))

    existing = {rule.category: rule for rule in session.scalars(select(AlertRule))}
    for name, category, threshold in ALERT_RULES:
        rule = existing.get(category)
        if rule is None:
            session.add(AlertRule(name=name, category=category, enabled=True, threshold=threshold))
        else:
            rule.name = name
            if threshold is not None and rule.threshold is None:
                rule.threshold = threshold
    session.commit()
