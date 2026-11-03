import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import AlertRule, Announcement, Company, FinancialMetric, Instrument, Portfolio, PortfolioHolding

COMPANIES = [
    ("Reliance Industries", "RELIANCE", "Energy", 12.4),
    ("HDFC Bank", "HDFCBANK", "Financials", 10.8),
    ("Tata Consultancy Services", "TCS", "Technology", 9.6),
    ("ICICI Bank", "ICICIBANK", "Financials", 8.9),
    ("Bharti Airtel", "BHARTIARTL", "Telecom", 7.7),
    ("Infosys", "INFY", "Technology", 6.4),
    ("Larsen & Toubro", "LT", "Industrials", 5.8),
    ("ITC", "ITC", "Consumer", 5.2),
    ("Asian Paints", "ASIANPAINT", "Consumer", 0),
    ("Maruti Suzuki India", "MARUTI", "Automotive", 0),
]
BSE_CODES = {"RELIANCE": "500325", "HDFCBANK": "500180", "TCS": "532540", "ICICIBANK": "532174", "BHARTIARTL": "532454", "INFY": "500209", "LT": "500510", "ITC": "500875", "ASIANPAINT": "500820", "MARUTI": "532500"}
ANNOUNCEMENT_RULES = [(f"{category} announcements", category, None) for category in ("Results", "Order wins", "Acquisitions", "Management changes", "Fundraising", "Regulatory updates", "Corporate actions")]
SAMPLE_METRICS = {
    "RELIANCE": (255000, 10.2, 17.2, 19000),
    "HDFCBANK": (76000, 10.8, 22.8, 18000),
    "TCS": (65200, 5.5, 24.5, 12500),
    "ICICIBANK": (42000, 9.5, 30.0, 12000),
    "BHARTIARTL": (41473, 12.6, 53.1, 5673),
    "INFY": (41000, 4.2, 21.0, 6800),
    "LT": (65000, 16.0, 11.2, 3800),
    "ITC": (20000, 7.0, 35.0, 5200),
    "ASIANPAINT": (8500, 5.0, 18.0, 800),
    "MARUTI": (41000, 9.4, 12.0, 3500),
}

def seed_demo_data(session: Session) -> None:
    if session.scalar(select(Portfolio.id).limit(1)):
        # Keep the local illustrative corpus deterministic across application restarts.
        for symbol, values in SAMPLE_METRICS.items():
            company = session.scalar(select(Company).join(Instrument).where(Instrument.symbol == symbol))
            if company:
                metric_values = dict(zip(("Revenue", "Revenue growth", "EBITDA margin", "PAT"), values))
                existing = {metric.metric: metric for metric in session.scalars(select(FinancialMetric).where(FinancialMetric.company_id == company.id, FinancialMetric.is_demo.is_(True)))}
                for name, value in metric_values.items():
                    if name in existing:
                        existing[name].value = value
                    else:
                        unit = "INR Cr" if name in ("Revenue", "PAT") else "% YoY" if name == "Revenue growth" else "%"
                        session.add(FinancialMetric(company_id=company.id, metric=name, value=value, unit=unit, period="Q2 FY26", is_demo=True))
        for symbol, code in BSE_CODES.items():
            instrument = session.scalar(select(Instrument).where(Instrument.exchange == "NSE", Instrument.symbol == symbol))
            if instrument and not instrument.bse_scrip_code:
                instrument.bse_scrip_code = code
        existing_rule_names = set(session.scalars(select(AlertRule.name)))
        session.add_all([AlertRule(name=name, category=category, enabled=True, threshold=threshold) for name, category, threshold in ANNOUNCEMENT_RULES if name not in existing_rule_names])
        session.commit()
        return
    portfolio = Portfolio(name="ENAM Demo Portfolio", is_demo=True)
    session.add(portfolio)
    session.flush()
    companies: dict[str, Company] = {}
    for order, (name, symbol, sector, weight) in enumerate(COMPANIES):
        company = Company(name=name, sector=sector)
        company.instruments.append(Instrument(exchange="NSE", symbol=symbol, provider_symbol=f"{symbol}.NS", bse_scrip_code=BSE_CODES[symbol]))
        session.add(company)
        session.flush()
        companies[symbol] = company
        if weight:
            session.add(PortfolioHolding(portfolio_id=portfolio.id, company_id=company.id, weight=weight, sort_order=order))
        metric_values = SAMPLE_METRICS[symbol]
        for (metric, unit), value in zip((("Revenue", "INR Cr"), ("Revenue growth", "% YoY"), ("EBITDA margin", "%"), ("PAT", "INR Cr")), metric_values):
            session.add(FinancialMetric(company_id=company.id, metric=metric, value=value, unit=unit, period="Q2 FY26", is_demo=True))
    now = datetime.now(timezone.utc)
    entries = [
        ("quarterly-results", "BHARTIARTL", "Earnings", "Q2 revenue grows 12.6%; ARPU reaches ₹257", "India mobile revenue accelerated on premiumization and subscriber mix. EBITDA margin expanded 110 bps year over year.", "The result points to continued pricing strength in the core India business. Revenue growth was ahead of the prior quarter, while margin expansion suggests operating leverage is holding up as premium plans gain mix.", "High", True, 18, "Bharti Airtel · Q2 FY26 results", "https://www.airtel.in/about-bharti/equity/results", ["Revenue: ₹41,473 Cr · +12.6% YoY", "EBITDA: ₹22,021 Cr · +14.9% YoY", "PAT: ₹5,673 Cr · +89.1% YoY*", "ARPU: ₹257 · up from ₹233 a year ago"]),
        ("management-change", "TCS", "Corporate action", "Chief Operating Officer to retire in December", "The company has named an internal successor, with a transition period planned through year end.", "The announcement creates a near-term leadership transition, but the named successor is an internal appointment. The filing does not indicate a change to strategy or financial guidance.", "Medium", False, 42, "TCS · Exchange filing", "https://www.tcs.com/investor-relations", ["Outgoing: N. Ganapathy Subramaniam, COO", "Transition: through 31 December 2026", "Successor: internal appointment announced", "Guidance impact: none disclosed in the filing"]),
        ("volume-spike", "RELIANCE", "Price move", "Trading volume runs 2.4× above its 20-day average", "Shares are up 1.8% in early trade. No corresponding material filing has been identified yet.", "The move is unusual relative to recent trading, but volume alone does not establish a catalyst. FINN has not found a matching material announcement in the selected source set.", "Medium", True, 60, "NSE · Price and volume data", "https://www.nseindia.com/get-quotes/equity?symbol=RELIANCE", ["Price move: +1.82% vs. previous close", "Volume: 2.4× the 20-day average", "Matched filing: none found in current sources", "Alert rule: volume above 2.0× average"]),
        ("hdfc-deposit", "HDFCBANK", "Earnings", "Deposit growth outpaces advances for a second quarter", "Deposits grew 15.8% year over year versus 7.9% growth in advances, continuing a recent trend.", "Faster deposit growth can ease funding pressure over time. Loan growth remains slower, so the trend is worth monitoring alongside the next reported net interest margin.", "Medium", True, 1500, "HDFC Bank · Quarterly business update", "https://www.hdfcbank.com/personal/about-us/investor-relations", ["Deposits: +15.8% YoY", "Advances: +7.9% YoY", "CASA ratio: 36.8%", "Context: second consecutive quarter of deposit outgrowth"]),
    ]
    for slug, symbol, category, title, summary, why, severity, positive, minutes, source, url, facts in entries:
        session.add(Announcement(company_id=companies[symbol].id, slug=slug, category=category, title=title, summary=summary, why_it_matters=why, severity=severity, positive=positive, published_at=now - timedelta(minutes=minutes), source_name=source, source_url=url, source_date="Sample filing · 03 Nov 2026", facts_json=json.dumps(facts, ensure_ascii=False), is_demo=True))
    rules = [("Quarterly results", "Earnings", None), ("Corporate announcements", "Corporate action", None), ("Price and volume moves", "Price move", 2.0), ("Macro and sector context", "Macro", None), *ANNOUNCEMENT_RULES]
    session.add_all([AlertRule(name=name, category=category, enabled=True, threshold=threshold) for name, category, threshold in rules])
    session.commit()
