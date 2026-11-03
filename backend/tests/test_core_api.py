from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.services.market_data import MarketDataService
from app.services.announcement_ingestion import AnnouncementIngestionService, classify
from app.services.research_documents import ResearchDocumentService
from datetime import datetime, timedelta, timezone


class DeterministicProvider:
    """45 daily sessions per ticker. RELIANCE ends on a 2.4× volume day (+1.8%); DIXON on a −6% day."""

    def __init__(self) -> None:
        self.calls = 0

    def bars(self, symbol: str) -> list[dict]:
        today = datetime.now(timezone.utc)
        out = []
        for offset in range(44, -1, -1):
            volume, close = 1000, 100.0
            if offset == 0:
                close = 101.0
                if symbol.startswith("RELIANCE"):
                    volume, close = 2400, 101.8
                if symbol.startswith("DIXON"):
                    close = 94.0
            out.append({"date": today - timedelta(days=offset), "open": 100.0, "high": 102.0, "low": 98.0, "close": close, "volume": volume})
        return out

    def fetch_history(self, symbol: str, period: str = "5d") -> list[dict]:
        self.calls += 1
        return self.bars(symbol)

    def fetch_many(self, symbols: list[str], period: str = "3mo") -> dict[str, list[dict]]:
        self.calls += 1
        return {s: self.bars(s) for s in symbols}


class EmptyProvider:
    def fetch_history(self, symbol: str, period: str = "5d") -> list[dict]:
        return []


def test_seeded_core_workflow(tmp_path) -> None:
    app = create_app(Settings(database_url=f"sqlite:///{(tmp_path / 'core.db').as_posix()}", frontend_origin="http://localhost:3000"))
    provider = DeterministicProvider()
    app.state.market_data = MarketDataService(provider)
    with TestClient(app) as client:
        portfolio = client.get("/api/v1/portfolio")
        assert portfolio.status_code == 200
        body = portfolio.json()
        assert body["summary"]["companies_tracked"] == 18
        assert len({h["sector"] for h in body["holdings"]}) >= 12
        assert abs(sum(h["weight"] for h in body["holdings"]) - 100) < 0.01
        reliance = next(h for h in body["holdings"] if h["symbol"] == "RELIANCE")
        assert reliance["price"] == 101.8 and reliance["volume_multiple"] == 2.4 and reliance["triggered"] is True
        assert body["summary"]["portfolio_value"] is None
        assert provider.calls == 1  # one batched request for all 18 tickers
        cached = client.get("/api/v1/portfolio").json()
        assert cached["holdings"][0]["market_data"]["status"] == "cached"
        assert provider.calls == 1

        # No fabricated events: the digest is built only from real triggers (here: the two synthetic moves).
        digest = client.get("/api/v1/digest").json()
        assert digest["is_demo"] is False
        symbols = {item["symbol"] for item in digest["items"]}
        assert symbols == {"RELIANCE", "DIXON"}
        rel = next(i for i in digest["items"] if i["symbol"] == "RELIANCE")
        assert rel["type"] == "Price move" and rel["enrichment"]["volume_multiple"] == 2.4
        assert "2.4×" in rel["title"]
        event_id = rel["id"]
        detail = client.get(f"/api/v1/events/{event_id}")
        assert detail.status_code == 200 and detail.json()["is_read"] is True
        assert client.get(f"/api/v1/alerts/{event_id}").status_code == 200
        assert client.patch(f"/api/v1/events/{event_id}", params={"is_saved": True}).json()["is_saved"] is True

        # Thresholds re-filter instantly: volume 2.5× hides RELIANCE (2.4×); move 7% hides DIXON (−6%).
        rules = {r["category"]: r for r in client.get("/api/v1/alert-rules").json()["items"]}
        client.patch(f"/api/v1/alert-rules/{rules['Price move']['id']}", params={"threshold": 2.5})
        assert {i["symbol"] for i in client.get("/api/v1/digest").json()["items"]} == {"DIXON"}
        client.patch(f"/api/v1/alert-rules/{rules['Price change']['id']}", params={"threshold": 7})
        assert client.get("/api/v1/digest").json()["count"] == 0
        client.patch(f"/api/v1/alert-rules/{rules['Price move']['id']}", params={"threshold": 2.0})
        assert {i["symbol"] for i in client.get("/api/v1/digest").json()["items"]} == {"RELIANCE"}

        search = client.get("/api/v1/companies", params={"q": "Bharti"})
        company = search.json()["items"][0]
        info = client.get(f"/api/v1/companies/{company['id']}")
        assert info.status_code == 200
        assert info.json()["metrics"] == []  # no sample figures are seeded any more
        history = client.get(f"/api/v1/companies/{company['id']}/prices?period=1mo")
        assert history.status_code == 200 and history.json()["items"][-1]["volume"] == 1000

        assert client.put("/api/v1/portfolio/holdings/ITC", params={"enabled": False}).status_code == 200
        assert client.get("/api/v1/portfolio").json()["summary"]["companies_tracked"] == 17
        assert client.get("/api/v1/events/not-a-real-alert").status_code == 404


def test_holdings_edits_survive_restart(tmp_path) -> None:
    url = f"sqlite:///{(tmp_path / 'restart.db').as_posix()}"
    for expected in (18, 17):
        app = create_app(Settings(database_url=url))
        app.state.market_data = MarketDataService(DeterministicProvider())
        with TestClient(app) as client:
            assert client.get("/api/v1/portfolio").json()["summary"]["companies_tracked"] == expected
            client.put("/api/v1/portfolio/holdings/ITC", params={"enabled": False})


def test_unavailable_ticker_never_uses_seed_price(tmp_path) -> None:
    app = create_app(Settings(database_url=f"sqlite:///{(tmp_path / 'unavailable.db').as_posix()}", frontend_origin="http://localhost:3000"))
    app.state.market_data = MarketDataService(EmptyProvider())
    with TestClient(app) as client:
        result = client.get("/api/v1/portfolio").json()
        first = result["holdings"][0]
        assert first["market_data"]["status"] == "unavailable"
        assert first["price"] is None
        assert first["change"] is None
        assert first["market_data"]["error"]


class FixedAnnouncementProvider:
    def __init__(self, rows):
        self.rows = rows

    def fetch(self, instruments, start, end):
        return self.rows, []


def test_announcement_classification_and_live_ingestion_flow(tmp_path) -> None:
    expected = {
        "Quarterly financial results approved": "Results",
        "Company receives a large work order": "Order wins",
        "Acquisition of a strategic business": "Acquisitions",
        "Appointment of managing director": "Management changes",
        "Qualified institutions placement QIP": "Fundraising",
        "SEBI penalty and regulatory order": "Regulatory updates",
        "Board recommends dividend and record date": "Corporate actions",
    }
    assert {title: classify(title, "") [0] for title in expected} == expected

    app = create_app(Settings(database_url=f"sqlite:///{(tmp_path / 'announcements.db').as_posix()}", frontend_origin="http://localhost:3000"))
    now = datetime.now(timezone.utc)
    rows = [{"symbol": "BHARTIARTL", "exchange": ex, "external_id": f"unique-earnings-{ex}", "title": "Unaudited financial results for quarter ended September", "summary": "Quarterly results filed with the exchange.", "published_at": now, "source_url": f"https://example.test/{ex}.pdf", "source_name": f"{ex} filing"} for ex in ("NSE", "BSE")]
    app.state.announcement_ingestion = AnnouncementIngestionService(FixedAnnouncementProvider(rows))
    app.state.market_data = MarketDataService(DeterministicProvider())
    with TestClient(app) as client:
        first = client.post("/api/v1/announcements/refresh", params={"days": 2, "limit": 10})
        assert first.status_code == 200
        assert first.json()["fetched"] == 2
        assert first.json()["inserted"] == 1
        assert first.json()["duplicates"] == 1

        second = client.post("/api/v1/announcements/refresh", params={"days": 2, "limit": 10}).json()
        assert second["inserted"] == 0
        assert second["duplicates"] == 2

        live = client.get("/api/v1/announcements", params={"exchange": "NSE", "symbol": "BHARTIARTL"}).json()
        assert live["count"] == 1
        assert live["items"][0]["is_demo"] is False
        assert live["items"][0]["source_exchange"] == "NSE"

        digest = client.get("/api/v1/digest").json()
        announcement = next(item for item in digest["items"] if item["source_exchange"] == "NSE")
        assert announcement["type"] == "Results"
        assert announcement["source"] == "https://example.test/NSE.pdf"
        assert announcement["published_at"]
        assert announcement["why"]
        assert announcement["is_demo"] is False
        detail = client.get(f"/api/v1/events/{announcement['id']}").json()
        assert detail["source_exchange"] == "NSE"
        assert detail["is_demo"] is False


class FixedResearchProvider:
    def __init__(self, pdf: bytes):
        self.pdf = pdf

    def catalog(self, symbol: str, include_transcripts: bool = True, transcripts_per_company: int = 1):
        if symbol != "ASIANPAINT":
            return [], []
        common = {"fiscal_period": "FY 2025-26", "published_at": datetime.now(timezone.utc), "source_name": "NSE", "source_url": "https://nse.example/report.pdf"}
        return [
            {**common, "source_key": "annual:2025:2026", "title": "Annual Report FY 2025-26", "document_type": "annual_report"},
            {**common, "source_key": "transcript:q4fy26", "title": "Earnings Call Transcript Q4 FY26", "document_type": "earnings_transcript"},
        ], []

    def download_pdf(self, url: str) -> bytes:
        return self.pdf


def test_research_document_ingestion_retrieval_and_evidence_gap(tmp_path) -> None:
    import pymupdf

    pdf = pymupdf.open()
    page = pdf.new_page()
    page.insert_textbox(pymupdf.Rect(40, 40, 550, 400), "Revenue grew 14% to INR 100 crore. Management expects revenue growth to continue and targets an EBITDA margin of 20%. The company expanded manufacturing capacity. Cash flow from operations was INR 15 crore; net debt declined.")
    pdf_bytes = pdf.tobytes()
    pdf.close()

    app = create_app(Settings(database_url=f"sqlite:///{(tmp_path / 'research.db').as_posix()}", frontend_origin="http://localhost:3000"))
    app.state.research_documents = ResearchDocumentService(FixedResearchProvider(pdf_bytes))
    with TestClient(app) as client:
        refreshed = client.post("/api/v1/research/documents/refresh", params={"limit": 5}).json()
        assert refreshed["indexed"] == 2
        assert refreshed["companies"] == ["ASIANPAINT", "BAJFINANCE", "BHARTIARTL", "DIXON", "HDFCBANK"]
        same = client.post("/api/v1/research/documents/refresh", params={"limit": 5}).json()
        assert same["unchanged"] == 2

        company = client.get("/api/v1/companies", params={"q": "Asian Paints"}).json()["items"][0]
        listed = client.get(f"/api/v1/companies/{company['id']}/research/documents").json()
        assert listed["count"] == 2
        assert {item["document_type"] for item in listed["items"]} == {"annual_report", "earnings_transcript"}

        answer = client.post("/api/v1/research/answer", json={"company_id": company["id"], "question": "What guidance did management give on growth?", "lens": "management guidance"}).json()
        assert answer["citations"]
        assert answer["citations"][0]["page"] == 1
        assert "#page=1" in answer["citations"][0]["source_url"]
        assert any("expects" in item.lower() for item in answer["management_guidance"])
        assert any("revenue" in item.lower() for item in answer["financial_metrics"])
        assert answer["is_demo"] is False

        missing = client.post("/api/v1/research/answer", json={"company_id": client.get("/api/v1/companies", params={"q": "Infosys"}).json()["items"][0]["id"], "question": "What is disclosed?", "lens": "cash flow"}).json()
        assert missing["citations"] == []
        assert "no indexed" in missing["evidence_gap"].lower()


def test_guidance_vs_actual_two_companies_with_citations(tmp_path) -> None:
    import pymupdf

    class QuarterlyProvider:
        def __init__(self):
            self.pdfs = {}
        def catalog(self, symbol, include_transcripts=True, transcripts_per_company=1):
            if symbol not in {"ASIANPAINT", "BHARTIARTL"}:
                return [], []
            records = []
            for quarter in range(1, 5):
                period = f"Q{quarter} FY26"
                guidance = f"For {period}, management guided revenue of INR {100 + quarter} crore."
                actual = f"For {period}, the company reported revenue was INR {102 + quarter} crore."
                pdf = pymupdf.open(); page = pdf.new_page(); page.insert_textbox(pymupdf.Rect(40, 40, 550, 400), guidance + " " + actual)
                self.pdfs[f"https://example.test/{symbol}-{period}.pdf"] = pdf.tobytes(); pdf.close()
                records.append({"source_key": f"{symbol}:{period}", "title": f"{symbol} Transcript {period}", "document_type": "earnings_transcript", "fiscal_period": period, "published_at": datetime.now(timezone.utc), "source_name": "Test filings", "source_url": f"https://example.test/{symbol}-{period}.pdf"})
            return records[:transcripts_per_company], []
        def download_pdf(self, url): return self.pdfs[url]

    app = create_app(Settings(database_url=f"sqlite:///{(tmp_path / 'guidance.db').as_posix()}", frontend_origin="http://localhost:3000"))
    app.state.research_documents = ResearchDocumentService(QuarterlyProvider())
    with TestClient(app) as client:
        refreshed = client.post("/api/v1/research/documents/refresh", params={"symbols": "ASIANPAINT,BHARTIARTL", "transcripts_per_company": 4}).json()
        assert refreshed["indexed"] == 8
        for symbol in ("ASIANPAINT", "BHARTIARTL"):
            company = next(x for x in client.get("/api/v1/companies").json()["items"] if x["symbol"] == symbol)
            response = client.post("/api/v1/research/guidance-vs-actual", json={"company_id": company["id"]})
            assert response.status_code == 200
            comparison = response.json()
            assert len(comparison["quarters"]) == 4
            revenue = next(item for item in comparison["quarters"][0]["metrics"] if item["metric"] == "revenue")
            assert revenue["guided_value"] is not None and revenue["actual_value"] is not None
            assert revenue["variance"] == "2"
            assert revenue["met_guidance"] == "Not determinable"
            assert revenue["guided_source"]["page"] == 1
            assert "#page=1" in revenue["actual_source"]["source_url"]


def test_fiscal_period_extraction_from_metadata_title_and_pdf(tmp_path) -> None:
    import pymupdf
    from app.integrations.documents.nse_provider import NSEResearchDocumentProvider

    # 1. Direct unit verification of extraction rules
    ext = NSEResearchDocumentProvider.extract_fiscal_period
    # Announcement metadata variations
    assert ext(text="financial results for the quarter and six months ended September 30, 2026") == "Q2 FY27"
    assert ext(text="financial results for the quarter ended June 30, 2026") == "Q1 FY27"
    assert ext(text="financial results for the quarter and financial year ended March 31, 2026") == "Q4 FY26"
    assert ext(text="results for the period ended September 30, 2026") == "Q2 FY27"
    assert ext(text="Results for Q1 FY26") == "Q1 FY26"
    assert ext(text="Q2-2027 conference call") == "Q2 FY27"

    # Title variations
    assert ext(title="HDFC Bank Limited Q2 FY27 Earnings Conference Call") == "Q2 FY27"
    assert ext(title="Q4 FY26 Media Conference Call") == "Q4 FY26"

    # Filename with publication date
    assert ext(filename="Infosys_27042026203405_Transcript_April232026_Q4.pdf", published_at=datetime(2026, 4, 27)) == "Q4 FY26"

    # PDF text variations
    assert ext(pdf_text="joining Infosys' Second Quarter Financial Results", published_at=datetime(2026, 10, 28)) == "Q2 FY27"
    assert ext(pdf_text="Bharti Airtel Limited Q1 ended June 30, 2026 Earnings Webinar") == "Q1 FY27"
    assert ext(pdf_text="We have had a strong performance in Q3.", published_at=datetime(2026, 1, 19)) == "Q3 FY26"

    # 2. Ingestion pipeline where catalog has fiscal_period=None, extracted from PDF text
    class UnlabeledTranscriptProvider:
        def __init__(self):
            self.pdfs = {}
            for q, month, name in [(1, "June 30, 2026", "First Quarter"), (2, "September 30, 2026", "Second Quarter")]:
                period = f"Q{q} FY27"
                pdf = pymupdf.open()
                page = pdf.new_page()
                page.insert_textbox(
                    pymupdf.Rect(40, 40, 550, 400),
                    f"Welcome to the {name} earnings conference call for period ended {month}. "
                    f"Management expects operating margin of 20%. "
                    f"Operating margin was 21%."
                )
                url = f"https://example.test/transcript-{q}.pdf"
                self.pdfs[url] = pdf.tobytes()
                pdf.close()

        def catalog(self, symbol, include_transcripts=True, transcripts_per_company=1):
            if symbol != "INFY":
                return [], []
            return [
                {
                    "source_key": "transcript:unlabeled:1",
                    "title": "INFY Earnings Call Transcript · 28 Jul 2026",
                    "document_type": "earnings_transcript",
                    "fiscal_period": None,  # Intentionally None, should be extracted from PDF
                    "published_at": datetime(2026, 7, 28, tzinfo=timezone.utc),
                    "source_name": "NSE",
                    "source_url": "https://example.test/transcript-1.pdf",
                },
                {
                    "source_key": "transcript:unlabeled:2",
                    "title": "INFY Earnings Call Transcript · 28 Oct 2026",
                    "document_type": "earnings_transcript",
                    "fiscal_period": None,  # Intentionally None, should be extracted from PDF
                    "published_at": datetime(2026, 10, 28, tzinfo=timezone.utc),
                    "source_name": "NSE",
                    "source_url": "https://example.test/transcript-2.pdf",
                },
            ][:transcripts_per_company], []

        def download_pdf(self, url):
            return self.pdfs[url]

    app = create_app(Settings(database_url=f"sqlite:///{(tmp_path / 'unlabeled.db').as_posix()}", frontend_origin="http://localhost:3000"))
    app.state.research_documents = ResearchDocumentService(UnlabeledTranscriptProvider())
    with TestClient(app) as client:
        refreshed = client.post("/api/v1/research/documents/refresh", params={"symbols": "INFY", "transcripts_per_company": 2}).json()
        assert refreshed["indexed"] == 2

        company = next(x for x in client.get("/api/v1/companies").json()["items"] if x["symbol"] == "INFY")
        docs = client.get(f"/api/v1/companies/{company['id']}/research/documents").json()["items"]
        transcripts = [d for d in docs if d["document_type"] == "earnings_transcript"]
        assert len(transcripts) == 2
        periods = {t["fiscal_period"] for t in transcripts}
        assert periods == {"Q1 FY27", "Q2 FY27"}

        guidance = client.post("/api/v1/research/guidance-vs-actual", json={"company_id": company["id"]}).json()
        assert len(guidance["quarters"]) == 2
        assert {q["period"] for q in guidance["quarters"]} == {"Q1 FY27", "Q2 FY27"}
        for q in guidance["quarters"]:
            op_margin = next(m for m in q["metrics"] if m["metric"] == "operating margin")
            assert op_margin["guided_value"] == "20"
            assert op_margin["actual_value"] == "21"
            assert op_margin["variance"] == "1"
            assert op_margin["met_guidance"] == "Not determinable"
            assert op_margin["guided_source"] is not None
            assert op_margin["actual_source"] is not None


def test_guidance_actual_accuracy_and_false_positive_rejection(tmp_path) -> None:
    """Verifies that Guidance vs Actual extraction rejects false positives, enforces units, and pairs same measurement basis."""
    import pymupdf
    from app.services.guidance_actual import _extract

    # 1. Direct unit verification on common false-positive sentences:
    # A) Segment revenue / share must NOT be extracted as company revenue
    facts_ai = _extract("AI revenue was a standout at 10.5% of our revenue, growing at 29%.", "Q2 FY27")
    assert not any(f["metric"] == "revenue" for f in facts_ai)

    facts_segment = _extract("Our AI services revenue was 8.2% of overall revenue in Q1.", "Q1 FY27")
    assert not any(f["metric"] == "revenue" for f in facts_segment)

    # B) Prepositional / ratio reference must NOT be extracted as PAT
    facts_fcf = _extract("Free cash flow generation was strong at $928 mn at 113% of net profit.", "Q2 FY27")
    assert not any(f["metric"] == "PAT" for f in facts_fcf)

    # C) Segment revenue growth must NOT be extracted as company revenue growth
    facts_seg_growth = _extract("Our digital businesses delivered another quarter of solid performance with revenue growth of nearly 6% sequentially.", "Q1 FY27")
    assert not any(f["metric"] == "revenue growth" for f in facts_seg_growth)

    # D) Clause-jumping numbers must NOT be bound to revenue growth
    facts_clause = _extract("Revenue growth was below our expectations, while AI first revenue now accounts for 10.5% of our total revenue.", "Q2 FY27")
    assert not any(f["metric"] == "revenue growth" for f in facts_clause)

    # E) Monetary extraction for PAT should skip the growth percentage and extract the monetary value
    facts_pat = _extract("Profit after tax grew by 20.1% year-on-year to ₹14,843 crore in Q2-2027.", "Q2 FY27")
    pat_fact = next(f for f in facts_pat if f["metric"] == "PAT")
    assert pat_fact["unit"] == "INR crore"
    assert pat_fact["value"] == 14843

    # F) YoY revenue growth preference
    facts_rev_growth = _extract("Our revenue growth for Q2 was 1.5% YoY and 1.2% sequentially in constant currency terms.", "Q2 FY27")
    growth_fact = next(f for f in facts_rev_growth if f["metric"] == "revenue growth")
    assert growth_fact["unit"] == "%"
    assert growth_fact["value"] == 1.5

    # 2. Integration test: End-to-end Guidance vs Actual with scope & page verification
    class AccurateTranscriptProvider:
        def __init__(self):
            pdf = pymupdf.open()
            # Page 1: Title
            p1 = pdf.new_page()
            p1.insert_textbox(pymupdf.Rect(40, 40, 550, 400), "Infosys Limited Q2 FY27 Earnings Conference Call October 28, 2026")
            # Page 2: Management guidance
            p2 = pdf.new_page()
            p2.insert_textbox(pymupdf.Rect(40, 40, 550, 400), "Our operating margin guidance remains at 20% to 22%. We are revising our full year revenue growth guidance to 1% to 2%.")
            # Page 3: Actual results
            p3 = pdf.new_page()
            p3.insert_textbox(pymupdf.Rect(40, 40, 550, 400), "Q2 revenues were $5,145 mn. Operating margin was stable at 21%. Our revenue growth for Q2 was 1.5% YoY.")
            self.pdf_bytes = pdf.tobytes()
            pdf.close()

        def catalog(self, symbol, include_transcripts=True, transcripts_per_company=1):
            if symbol != "INFY":
                return [], []
            return [
                {
                    "source_key": "transcript:acc:q2",
                    "title": "INFY Earnings Call Transcript · 28 Oct 2026",
                    "document_type": "earnings_transcript",
                    "fiscal_period": "Q2 FY27",
                    "published_at": datetime(2026, 10, 28, tzinfo=timezone.utc),
                    "source_name": "NSE",
                    "source_url": "https://example.test/infy-q2.pdf",
                }
            ], []

        def download_pdf(self, url):
            return self.pdf_bytes

    app = create_app(Settings(database_url=f"sqlite:///{(tmp_path / 'accurate.db').as_posix()}", frontend_origin="http://localhost:3000"))
    app.state.research_documents = ResearchDocumentService(AccurateTranscriptProvider())
    with TestClient(app) as client:
        refreshed = client.post("/api/v1/research/documents/refresh", params={"symbols": "INFY", "transcripts_per_company": 1}).json()
        assert refreshed["indexed"] == 1

        company = next(x for x in client.get("/api/v1/companies").json()["items"] if x["symbol"] == "INFY")
        guidance = client.post("/api/v1/research/guidance-vs-actual", json={"company_id": company["id"]}).json()
        assert len(guidance["quarters"]) == 1
        q2 = guidance["quarters"][0]

        # Operating margin: guided 20% on page 2, actual 21% on page 3, variance 1%
        op_margin = next(m for m in q2["metrics"] if m["metric"] == "operating margin")
        assert op_margin["guided_value"] == "20"
        assert op_margin["actual_value"] == "21"
        assert op_margin["variance"] == "1"
        assert op_margin["met_guidance"] == "Not determinable"
        assert op_margin["guided_source"]["page"] == 2
        assert "infy-q2.pdf#page=2" in op_margin["guided_source"]["source_url"]
        assert op_margin["actual_source"]["page"] == 3
        assert "infy-q2.pdf#page=3" in op_margin["actual_source"]["source_url"]

        # Revenue growth:
        # Full year guidance (1% to 2%) must NOT pair with quarterly actual growth (1.5%) because measurement bases differ!
        rev_growth = next(m for m in q2["metrics"] if m["metric"] == "revenue growth")
        assert rev_growth["guided_value"] is None  # Unpaired because guidance was full-year annual, not quarterly
        assert rev_growth["actual_value"] == "1.5"
        assert rev_growth["variance"] is None
        assert rev_growth["met_guidance"] == "Unavailable"
        assert rev_growth["actual_source"]["page"] == 3

        # Revenue:
        rev = next(m for m in q2["metrics"] if m["metric"] == "revenue")
        assert rev["guided_value"] is None
        assert rev["actual_value"] == "5145"
        assert rev["unit"] == "million"
        assert rev["variance"] is None
        assert rev["met_guidance"] == "Unavailable"
        assert rev["actual_source"]["page"] == 3


def test_pull_research_infosys_and_icici_bank_grounded_experience(tmp_path) -> None:
    """Verifies that PULL research answers natural-language queries with grounded claims, citations, conflict analysis, and evidence sufficiency on real DB."""
    from pathlib import Path
    from app.db.session import create_database_engine, create_session_factory
    from app.domain.models import Company
    from app.services.research_documents import ResearchDocumentService

    # Use existing seeded finn.db via absolute path
    db_path = (Path(__file__).resolve().parents[1] / "data" / "finn.db").as_posix()
    session_factory = create_session_factory(create_database_engine(f"sqlite:///{db_path}"))
    service = ResearchDocumentService()

    with session_factory() as session:
        infy = session.query(Company).filter(Company.name == "Infosys").first()
        icici = session.query(Company).filter(Company.name == "ICICI Bank").first()

        # 1. INFOSYS - Management guidance natural language query
        infy_res = service.answer(
            session=session,
            company_id=infy.id,
            question="What is management guidance on revenue growth and operating margin?",
            lens="management guidance",
        )
        assert infy_res["evidence_sufficiency"]["status"] == "sufficient"
        assert len(infy_res["key_claims"]) >= 3
        # Every claim must have a valid document title, page > 0, and #page= in source_url
        for claim in infy_res["key_claims"]:
            assert claim["document_title"]
            assert claim["page"] > 0
            assert f"#page={claim['page']}" in claim["source_url"]

        # Operating margin 20% to 22% must be found in claims
        assert any("20% to 22%" in c["claim"] for c in infy_res["key_claims"])
        # Guidance trajectory shift across quarters must be highlighted in conflicts
        assert infy_res["conflicting_info"] is not None
        assert "Trajectory shift" in infy_res["conflicting_info"]
        assert "### Executive Summary" in infy_res["answer"]
        assert "### Key Sourced Claims" in infy_res["answer"]
        assert "### Conflicting Disclosures & Trajectory Shifts" in infy_res["answer"]
        assert "### Evidence Assessment" in infy_res["answer"]

        # 2. ICICI BANK - Net Interest Margin natural language query
        icici_nim = service.answer(
            session=session,
            company_id=icici.id,
            question="What did management report about net interest margin NIM and deposit growth?",
            lens="financial performance",
        )
        assert icici_nim["evidence_sufficiency"]["status"] == "sufficient"
        assert len(icici_nim["key_claims"]) >= 3
        # Should cite Q2 FY27 NIM of 4.18%
        assert any("4.18%" in c["claim"] for c in icici_nim["key_claims"])
        # Should highlight divergence between NII expansion and NIM compression
        assert icici_nim["conflicting_info"] is not None
        assert "margin compression" in icici_nim["conflicting_info"].lower() or "divergence" in icici_nim["conflicting_info"].lower()

        # 3. ICICI BANK - Forward guidance query (Bank does not provide forward numerical guidance)
        icici_guidance = service.answer(
            session=session,
            company_id=icici.id,
            question="What guidance did management provide on credit costs or loan growth?",
            lens="management guidance",
        )
        # Must clearly state that evidence is insufficient for forward numeric targets
        assert icici_guidance["evidence_sufficiency"]["status"] == "insufficient"
        assert "does not issue forward-looking numerical quarterly guidance" in icici_guidance["evidence_gap"]
        assert "does not publish forward-looking numerical quarterly guidance" in icici_guidance["answer"]

        # 4. UNSUPPORTED QUERY - Completely absent topic
        unsupported = service.answer(
            session=session,
            company_id=infy.id,
            question="What did management announce regarding cryptocurrency trading and Bitcoin reserves?",
            lens="business overview",
        )
        assert unsupported["evidence_sufficiency"]["status"] == "insufficient"
        assert len(unsupported["key_claims"]) == 0


def _results_pdf() -> bytes:
    import pymupdf
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((40, 50), "Statement of Unaudited Consolidated Financial Results for the quarter ended 30.09.2026 (Rs in Crore)", fontsize=8)
    for x, d in ((300, "30.09.2026"), (370, "30.06.2026"), (440, "30.09.2025"), (510, "31.03.2026")):
        page.insert_text((x, 90), "Quarter ended", fontsize=7)
        page.insert_text((x, 100), d, fontsize=7)
    rows = [("Revenue from operations", 1100, 1000, 900, 3800), ("Other income", 10, 10, 10, 40), ("Total income", 1110, 1010, 910, 3840),
            ("Finance costs", 20, 20, 20, 80), ("Depreciation and amortisation expense", 30, 30, 30, 120),
            ("Profit before tax", 200, 180, 150, 700), ("Tax expense", 50, 45, 40, 180), ("Net profit for the period", 150, 135, 110, 520)]
    for i, (label, *vals) in enumerate(rows):
        y = 130 + i * 16
        page.insert_text((40, y), label, fontsize=8)
        for x, v in zip((300, 370, 440, 510), vals):
            page.insert_text((x, y), f"{v:,.2f}", fontsize=8)
    return doc.tobytes()


def _appointment_pdf() -> bytes:
    import pymupdf
    doc = pymupdf.open()
    page = doc.new_page()
    text = ("Sub: Appointment of Chief Financial Officer\n\nPursuant to Regulation 30, the Board approved the appointment of\n"
            "Ms. Anita Rao as Chief Financial Officer with effect from 1 November 2026.\n\nBrief profile:\n"
            "Ms. Anita Rao is a chartered accountant with 22 years of experience in finance.\nShe was previously CFO of an FMCG major and led its treasury and investor relations.\n"
            "She holds an MBA from IIM Ahmedabad.\n\nYours faithfully,")
    page.insert_text((40, 60), text, fontsize=9)
    return doc.tobytes()


class FakeFilingDownloader:
    def download_pdf(self, url: str) -> bytes:
        if url.endswith("results.pdf"):
            return _results_pdf()
        if url.endswith("people.pdf"):
            return _appointment_pdf()
        raise ValueError("not found")


def test_push_experience_prioritization_thresholds_reasons_and_deduplication(tmp_path) -> None:
    app = create_app(Settings(database_url=f"sqlite:///{(tmp_path / 'push_test.db').as_posix()}", frontend_origin="http://localhost:3000"))
    flat = DeterministicProvider()
    flat.bars = lambda symbol: [{"date": datetime.now(timezone.utc) - timedelta(days=o), "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1000} for o in range(44, -1, -1)]
    app.state.market_data = MarketDataService(flat)
    now = datetime.now(timezone.utc)
    base = {"published_at": now, "source_name": "NSE filing"}
    results_text = "Bharti Airtel Limited has submitted to the Exchange, the financial results for the quarter ended September 30, 2026."
    rows = [
        {**base, "symbol": "BHARTIARTL", "exchange": "NSE", "external_id": "r1", "title": "Outcome of Board Meeting", "summary": results_text, "source_url": "https://nse.test/results.pdf"},
        {**base, "symbol": "BHARTIARTL", "exchange": "BSE", "external_id": "r1b", "title": "Outcome of Board Meeting", "summary": results_text, "source_url": "https://bse.test/results.pdf"},
        {**base, "symbol": "TCS", "exchange": "NSE", "external_id": "m1", "title": "Change in Management", "summary": "Appointment of Ms. Anita Rao as Chief Financial Officer.", "source_url": "https://nse.test/people.pdf"},
        {**base, "symbol": "ITC", "exchange": "NSE", "external_id": "d1", "title": "Dividend", "summary": "Interim dividend and record date.", "source_url": "https://nse.test/div.pdf"},
        {**base, "symbol": "INFY", "exchange": "NSE", "external_id": "c1", "title": "Analysts/Institutional Investor Meet/Con. Call Updates", "summary": "Transcript of the earnings call held on 23 October 2026.", "source_url": "https://nse.test/call.pdf"},
        {**base, "symbol": "LT", "exchange": "NSE", "external_id": "n1", "title": "Copy of Newspaper Publication", "summary": "Newspaper publication of results.", "source_url": "https://nse.test/paper.pdf"},
    ]
    app.state.announcement_ingestion = AnnouncementIngestionService(FixedAnnouncementProvider(rows), pdf_downloader=FakeFilingDownloader())

    with TestClient(app) as client:
        refreshed = client.post("/api/v1/announcements/refresh", params={"days": 2}).json()
        assert refreshed["inserted"] == 5 and refreshed["duplicates"] == 1  # NSE/BSE copy collapsed
        assert refreshed["enrichment"] == {"attempted": 2, "parsed": 2, "failed": 0}

        digest = client.get("/api/v1/digest", params={"period": "24 hours"}).json()
        items = {i["symbol"]: i for i in digest["items"]}
        assert digest["count"] == 5 and digest["material_count"] == 2

        # Results first cut: QoQ and YoY read from the filing, page-cited, and the card leads the digest.
        results = items["BHARTIARTL"]
        assert digest["items"][0]["symbol"] == "BHARTIARTL"
        e = results["enrichment"]
        assert e["status"] == "parsed" and e["period"] == "Q2 FY27" and e["page"] == 1
        revenue = next(m for m in e["metrics"] if m["metric"] == "Revenue")
        assert (revenue["current"], revenue["previous_quarter"], revenue["year_ago"]) == (1100, 1000, 900)
        assert (revenue["qoq_pct"], revenue["yoy_pct"]) == (10.0, 22.2)
        ebitda = next(m for m in e["metrics"] if m["metric"] == "EBITDA")
        assert ebitda["current"] == 200 + 20 + 30 - 10
        assert "+22.2% YoY" in results["summary"] and "QoQ" in results["summary"]
        assert "EBITDA margin" in results["why"] and "page 1" in results["why"]

        # Management change: the incoming person and the profile come from the filing, with its page.
        people = items["TCS"]["enrichment"]
        assert people["status"] == "parsed" and people["action"] == "appointment"
        assert people["people"][0]["name"] == "Ms. Anita Rao" and "chartered accountant" in people["people"][0]["profile"]
        assert people["people"][0]["page"] == 1 and items["TCS"]["impact"] == "High"

        # Routine filings are kept but flagged so the UI collapses them.
        assert {s for s, i in items.items() if i["routine"]} == {"ITC", "INFY", "LT"}
        assert items["INFY"]["type"] == "Earnings call" and items["LT"]["type"] == "Routine"

        # Category toggles filter the digest.
        rules = {r["category"]: r for r in client.get("/api/v1/alert-rules").json()["items"]}
        client.patch(f"/api/v1/alert-rules/{rules['Results']['id']}", params={"enabled": False})
        assert "BHARTIARTL" not in {i["symbol"] for i in client.get("/api/v1/digest").json()["items"]}
        client.patch(f"/api/v1/alert-rules/{rules['Results']['id']}", params={"enabled": True})

        # A second refresh does not re-download or duplicate anything.
        again = client.post("/api/v1/announcements/refresh", params={"days": 2}).json()
        assert again["inserted"] == 0 and again["enrichment"]["attempted"] == 0


def test_company_coverage_outside_demo_portfolio(tmp_path) -> None:
    """Verify that any NSE-listed company can be discovered, searched by ticker or alias,

    and researched with strict data-availability handling (no fabricated numbers).
    Tested across 5 companies outside the demo portfolio: SBIN, TATASTEEL, HINDUNILVR, AXISBANK, WIPRO.
    """
    app = create_app(Settings(database_url=f"sqlite:///{(tmp_path / 'coverage.db').as_posix()}", frontend_origin="http://localhost:3000"))
    provider = DeterministicProvider()
    app.state.market_data = MarketDataService(provider)

    with TestClient(app) as client:
        # 1. Verify demo portfolio contains 8 companies, and none of our 5 target companies are in it
        portfolio_res = client.get("/api/v1/portfolio").json()
        portfolio_symbols = {h["symbol"] for h in portfolio_res["holdings"]}
        test_targets = [
            ("SBIN", "State Bank of India", "Financial Services"),
            ("TATASTEEL", "Tata Steel Limited", "Basic Materials"),
            ("HINDUNILVR", "Hindustan Unilever Limited", "Consumer Defensive"),
            ("AXISBANK", "Axis Bank Limited", "Financial Services"),
            ("WIPRO", "Wipro Limited", "Technology"),
        ]
        for sym, _, _ in test_targets:
            assert sym not in portfolio_symbols, f"{sym} should not be in seeded demo portfolio"

        # 2. Test Ticker & Alias Discovery for all 5 companies
        # Direct symbol searches
        for sym, expected_name, expected_sector in test_targets:
            search_res = client.get("/api/v1/companies", params={"q": sym})
            assert search_res.status_code == 200
            data = search_res.json()
            assert any(item["symbol"] == sym for item in data["items"]), f"Failed to discover {sym}"
            match = next(item for item in data["items"] if item["symbol"] == sym)
            assert match["name"] == expected_name
            assert match["sector"] == expected_sector
            assert match["in_portfolio"] is False
            assert match["is_demo"] is False
            assert isinstance(match["id"], int)

        # Alias searches: SBI -> SBIN, HUL -> HINDUNILVR, SUN PHARMA -> SUNPHARMA
        sbi_alias = client.get("/api/v1/companies", params={"q": "SBI"}).json()["items"]
        assert any(item["symbol"] == "SBIN" for item in sbi_alias)

        hul_alias = client.get("/api/v1/companies", params={"q": "HUL"}).json()["items"]
        assert any(item["symbol"] == "HINDUNILVR" for item in hul_alias)

        sun_alias = client.get("/api/v1/companies", params={"q": "SUN PHARMA"}).json()["items"]
        assert any(item["symbol"] == "SUNPHARMA" for item in sun_alias)

        # 3. Test Company Info & Truthful Data Availability for all 5 companies
        company_ids = {}
        for sym, expected_name, _ in test_targets:
            search_item = next(
                item for item in client.get("/api/v1/companies", params={"q": sym}).json()["items"]
                if item["symbol"] == sym
            )
            cid = search_item["id"]
            company_ids[sym] = cid

            info_res = client.get(f"/api/v1/companies/{cid}")
            assert info_res.status_code == 200
            info = info_res.json()
            assert info["name"] == expected_name
            assert info["in_portfolio"] is False
            assert info["is_demo"] is False
            assert info["source_status"] == "no documents indexed yet"
            assert info["instruments"][0]["symbol"] == sym
            assert info["instruments"][0]["exchange"] == "NSE"

            # Market data quote returns live/mock quote without fabricating portfolio holdings
            assert info["market_data"]["status"] in {"fresh", "cached"}
            assert info["market_data"]["close"] is not None

            # Historical prices
            prices_res = client.get(f"/api/v1/companies/{cid}/prices?period=5d")
            assert prices_res.status_code == 200
            assert 5 <= len(prices_res.json()["items"]) <= 8  # calendar week of daily bars

            # 4. Strict handling of unindexed documents (NO fabricated numbers or claims)
            docs_res = client.get(f"/api/v1/companies/{cid}/research/documents")
            assert docs_res.status_code == 200
            assert docs_res.json()["count"] == 0
            assert docs_res.json()["items"] == []

            # Research answer returns insufficient evidence, zero claims, zero citations
            answer_payload = {
                "company_id": cid,
                "question": "What is management guidance on revenue and operating margins?",
                "lens": "management guidance",
            }
            ans_res = client.post("/api/v1/research/answer", json=answer_payload)
            assert ans_res.status_code == 200
            ans_data = ans_res.json()
            assert ans_data["evidence_sufficiency"]["status"] == "insufficient"
            assert ans_data["citations"] == []
            assert ans_data["key_claims"] == []
            assert "no indexed annual reports or earnings-call transcripts" in ans_data["evidence_gap"].lower() or "no source documents" in ans_data["evidence_gap"].lower()

            # Guidance vs Actual returns empty quarters and explicit evidence gap
            gva_res = client.post("/api/v1/research/guidance-vs-actual", json={"company_id": cid})
            assert gva_res.status_code == 200
            gva_data = gva_res.json()
            assert gva_data["quarters"] == []
            assert "No indexed source documents are available." in gva_data["evidence_gap"]

        # 5. Test Research Retrieval when Documents ARE indexed for a non-portfolio company
        # We index a document for WIPRO
        wipro_id = company_ids["WIPRO"]
        with app.state.session_factory() as session:
            from app.domain.models import ResearchChunk, ResearchDocument
            wipro_doc = ResearchDocument(
                company_id=wipro_id,
                source_key="nse-wipro-q2fy26-transcript",
                title="Wipro Limited Q2 FY26 Earnings Conference Call",
                document_type="earnings_transcript",
                fiscal_period="Q2 FY26",
                published_at=datetime.now(timezone.utc),
                source_name="NSE Announcement",
                source_url="https://nsearchives.nseindia.com/wipro_q2fy26.pdf",
                content_hash="wipro-hash-123",
                page_count=18,
                is_demo=False,
            )
            session.add(wipro_doc)
            session.flush()

            chunk_text = (
                "For the second quarter, our IT services revenue was $2,660 million, showing sequential expansion. "
                "Operating margin for the quarter stood at 16.8%, expanding by 40 basis points. "
                "Regarding guidance, we expect revenue growth in the range of -1.0% to +1.0% sequentially in constant currency for Q3 FY26."
            )
            chunk = ResearchChunk(
                document_id=wipro_doc.id,
                page_number=4,
                chunk_index=1,
                text=chunk_text,
                financial_metrics_json='["revenue: $2,660 million", "operating margin: 16.8%"]',
                guidance_json='["guidance: -1.0% to +1.0%"]',
                business_updates_json='["IT services expansion"]',
            )
            session.add(chunk)
            session.commit()

        # Re-check Wipro info: source_status updates to reflect indexed filing
        wipro_info = client.get(f"/api/v1/companies/{wipro_id}").json()
        assert wipro_info["source_status"] == "1 official filing(s) indexed"

        # Re-check Wipro documents endpoint
        wipro_docs = client.get(f"/api/v1/companies/{wipro_id}/research/documents").json()
        assert wipro_docs["count"] == 1
        assert wipro_docs["items"][0]["title"] == "Wipro Limited Q2 FY26 Earnings Conference Call"
        assert wipro_docs["items"][0]["is_demo"] is False

        # Re-run research answer for Wipro: now grounds against the primary transcript passage
        wipro_answer = client.post("/api/v1/research/answer", json={
            "company_id": wipro_id,
            "question": "What did management report about operating margin and Q3 guidance?",
            "lens": "management guidance",
        }).json()
        assert wipro_answer["evidence_sufficiency"]["status"] in {"sufficient", "partial"}
        assert len(wipro_answer["citations"]) == 1
        assert wipro_answer["citations"][0]["page"] == 4
        assert wipro_answer["citations"][0]["source_url"] == "https://nsearchives.nseindia.com/wipro_q2fy26.pdf#page=4"
        assert "16.8%" in wipro_answer["answer"]

        # 6. Test Unknown / Gibberish Ticker and Invalid Company IDs
        empty_search = client.get("/api/v1/companies", params={"q": "NONEXISTENTXYZ999"}).json()
        assert len(empty_search["items"]) == 0

        not_found_info = client.get("/api/v1/companies/999999")
        assert not_found_info.status_code == 404
        assert not_found_info.json()["detail"] == "Company not found"

        not_found_docs = client.get("/api/v1/companies/999999/research/documents")
        assert not_found_docs.status_code == 404





