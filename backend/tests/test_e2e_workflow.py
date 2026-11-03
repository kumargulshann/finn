"""End-to-End integration test suite for FINN PUSH and PULL workflows."""
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.services.market_data import MarketDataService
from app.services.announcement_ingestion import AnnouncementIngestionService
from app.domain.models import ResearchChunk, ResearchDocument


class MockMarketDataProvider:
    def __init__(self) -> None:
        self.call_count = 0

    def fetch_history(self, symbol: str, period: str = "5d") -> list[dict]:
        self.call_count += 1
        now = datetime.now(timezone.utc)
        return [
            {
                "date": now - timedelta(days=i),
                "open": 1000.0 + i * 5,
                "high": 1020.0 + i * 5,
                "low": 995.0 + i * 5,
                "close": 1010.0 + i * 5,
                "volume": 250000 + i * 10000,
            }
            for i in range(4, -1, -1)
        ]


class MockAnnouncementProvider:
    def __init__(self, items) -> None:
        self.items = items

    def fetch(self, instruments, start, end):
        return self.items, []


def test_full_push_and_pull_e2e(tmp_path) -> None:
    """Validate full end-to-end PUSH and PULL workflows in an integrated environment."""
    db_path = (tmp_path / "finn_e2e.db").as_posix()
    app = create_app(Settings(database_url=f"sqlite:///{db_path}", frontend_origin="http://localhost:3000"))
    provider = MockMarketDataProvider()
    app.state.market_data = MarketDataService(provider)

    with TestClient(app) as client:
        # =========================================================================
        # 1. PUSH WORKFLOW
        # =========================================================================
        
        # 1.1 Portfolio summary & holdings
        portfolio_res = client.get("/api/v1/portfolio")
        assert portfolio_res.status_code == 200
        pdata = portfolio_res.json()
        assert pdata["summary"]["companies_tracked"] == 8
        assert pdata["is_demo"] is True
        assert len(pdata["holdings"]) == 8
        first_holding = pdata["holdings"][0]
        assert first_holding["price"] is not None
        assert first_holding["market_data"]["status"] in {"fresh", "cached"}
        # Truthful valuation check: no share quantities
        assert pdata["summary"]["portfolio_value"] is None

        # 1.2 Today digest & prioritization
        digest_res = client.get("/api/v1/digest?period=24%20hours")
        assert digest_res.status_code == 200
        ddata = digest_res.json()
        assert ddata["count"] == 3
        alerts = ddata["items"]
        
        # Priority check: High impact financial results must be ranked first
        assert alerts[0]["impact"] == "High"
        assert alerts[0]["type"] == "Earnings"
        assert alerts[0]["priority_score"] >= alerts[1]["priority_score"]
        assert alerts[1]["priority_score"] >= alerts[2]["priority_score"]

        # 1.3 Alert Detail & Bookmarking
        top_id = alerts[0]["id"]
        detail_res = client.get(f"/api/v1/events/{top_id}")
        assert detail_res.status_code == 200
        detail = detail_res.json()
        assert detail["why"]
        assert len(detail["details"]) >= 3
        assert detail["source"]
        assert detail["sourceName"]
        assert detail["is_saved"] is False

        # Bookmark alert
        patch_res = client.patch(f"/api/v1/events/{top_id}?is_saved=true")
        assert patch_res.status_code == 200
        assert patch_res.json()["is_saved"] is True
        assert client.get(f"/api/v1/events/{top_id}").json()["is_saved"] is True

        # 1.4 Configurable Alert Thresholds in Settings
        rules_res = client.get("/api/v1/alert-rules")
        assert rules_res.status_code == 200
        rules = rules_res.json()["items"]
        price_rule = next(r for r in rules if r["category"] == "Price move")
        assert price_rule["threshold"] == 2.0

        # Change threshold from 2.0 to 3.0 (higher than Reliance's 2.4x volume surge)
        client.patch(f"/api/v1/alert-rules/{price_rule['id']}?threshold=3.0")
        digest_higher = client.get("/api/v1/digest?period=24%20hours").json()
        assert digest_higher["count"] == 2
        assert "RELIANCE" not in [i["symbol"] for i in digest_higher["items"]]

        # Restore threshold to 1.5 -> Reliance alert re-appears
        client.patch(f"/api/v1/alert-rules/{price_rule['id']}?threshold=1.5")
        digest_restored = client.get("/api/v1/digest?period=24%20hours").json()
        assert digest_restored["count"] == 3
        assert "RELIANCE" in [i["symbol"] for i in digest_restored["items"]]

        # 1.5 Deduplication with Real Ingestion
        now = datetime.now(timezone.utc)
        duplicate_announcements = [
            {
                "symbol": "BHARTIARTL",
                "exchange": "NSE",
                "external_id": "ann-bharti-001",
                "title": "Financial results for quarter ended September",
                "summary": "Detailed audited financials submitted to exchange.",
                "published_at": now,
                "source_url": "https://nsearchives.nseindia.com/bharti1.pdf",
                "source_name": "NSE Announcement",
            },
            {
                "symbol": "BHARTIARTL",
                "exchange": "BSE",
                "external_id": "ann-bharti-bse-001",
                "title": "Financial results for quarter ended September",
                "summary": "Detailed audited financials submitted to exchange.",
                "published_at": now,
                "source_url": "https://bsearchives.bseindia.com/bharti_bse.pdf",
                "source_name": "BSE Announcement",
            },
        ]
        app.state.announcement_ingestion = AnnouncementIngestionService(MockAnnouncementProvider(duplicate_announcements))
        refresh_res = client.post("/api/v1/announcements/refresh?days=2&limit=10")
        assert refresh_res.status_code == 200
        assert refresh_res.json()["inserted"] == 1
        assert refresh_res.json()["duplicates"] == 1

        # =========================================================================
        # 2. PULL WORKFLOW
        # =========================================================================

        # 2.1 Company Search & Coverage
        # Seeded company
        infy_search = client.get("/api/v1/companies?q=INFY").json()["items"]
        assert any(c["symbol"] == "INFY" for c in infy_search)
        infy = next(c for c in infy_search if c["symbol"] == "INFY")
        assert infy["in_portfolio"] is True

        # Non-portfolio companies
        for sym, name in [("SBIN", "State Bank of India"), ("SUNPHARMA", "Sun Pharmaceutical"), ("HINDUNILVR", "Hindustan Unilever")]:
            search_items = client.get(f"/api/v1/companies?q={sym}").json()["items"]
            assert any(c["symbol"] == sym for c in search_items)
            match = next(c for c in search_items if c["symbol"] == sym)
            assert match["in_portfolio"] is False
            assert match["is_demo"] is False

        # Alias mapping
        sbi_alias = client.get("/api/v1/companies?q=SBI").json()["items"]
        assert any(c["symbol"] == "SBIN" for c in sbi_alias)
        hul_alias = client.get("/api/v1/companies?q=HUL").json()["items"]
        assert any(c["symbol"] == "HINDUNILVR" for c in hul_alias)

        # 2.2 Company Info & Market Prices
        infy_info = client.get(f"/api/v1/companies/{infy['id']}").json()
        assert infy_info["name"] == "Infosys"
        assert infy_info["market_data"]["close"] is not None
        assert infy_info["market_data"]["volume"] is not None

        infy_prices = client.get(f"/api/v1/companies/{infy['id']}/prices?period=5d").json()
        assert len(infy_prices["items"]) == 5

        # 2.3 Unindexed company handling (Zero hallucination policy)
        sbin_id = next(c["id"] for c in client.get("/api/v1/companies?q=SBIN").json()["items"] if c["symbol"] == "SBIN")
        
        # Documents count is 0
        sbin_docs = client.get(f"/api/v1/companies/{sbin_id}/research/documents").json()
        assert sbin_docs["count"] == 0

        # Research answer returns insufficient evidence, zero claims, zero citations
        sbin_ans = client.post("/api/v1/research/answer", json={
            "company_id": sbin_id,
            "question": "What is the management outlook on loan growth and credit costs?",
            "lens": "management guidance",
        }).json()
        assert sbin_ans["evidence_sufficiency"]["status"] == "insufficient"
        assert sbin_ans["citations"] == []
        assert sbin_ans["key_claims"] == []

        # Guidance vs actual returns empty comparison with explicit notice
        sbin_gva = client.post("/api/v1/research/guidance-vs-actual", json={"company_id": sbin_id}).json()
        assert sbin_gva["quarters"] == []
        assert "No indexed source documents are available." in sbin_gva["evidence_gap"]

        # 2.4 Indexing & Research Retrieval with Multi-Quarter Grounding
        # Index 4 quarters of transcripts for Infosys
        with app.state.session_factory() as session:
            quarters_data = [
                ("Q3 FY26", "INFY Q3 FY26 Transcript", 3, "Our revenue was 5.1 billion. Operating margin was 21.2%. We guide operating margin between 20% to 22%."),
                ("Q4 FY26", "INFY Q4 FY26 Transcript", 4, "Our revenue growth was 4.1%. Operating margin was 21.0%. Management guided operating margin of 20%."),
                ("Q1 FY27", "INFY Q1 FY27 Transcript", 5, "Our revenue was 5082 million. Revenue growth was 2.4%. Operating margin was 21.1%. Guidance for revenue growth is 1.5% and operating margin 20%."),
                ("Q2 FY27", "INFY Q2 FY27 Transcript", 6, "Our revenue was 5145 million. Revenue growth was 1.5%. Operating margin stood at 21.0%. Guidance for operating margin is 20%."),
            ]
            for period, title, page, text in quarters_data:
                doc = ResearchDocument(
                    company_id=infy["id"],
                    source_key=f"infy-{period.lower().replace(' ', '')}",
                    title=title,
                    document_type="earnings_transcript",
                    fiscal_period=period,
                    published_at=now,
                    source_name="NSE Announcement",
                    source_url=f"https://nsearchives.nseindia.com/{period}.pdf",
                    content_hash=f"hash-{period}",
                    page_count=35,
                    is_demo=False,
                )
                session.add(doc)
                session.flush()

                chunk = ResearchChunk(
                    document_id=doc.id,
                    page_number=page,
                    chunk_index=1,
                    text=text,
                    financial_metrics_json='["revenue", "operating margin"]',
                    guidance_json='["operating margin guidance"]',
                    business_updates_json='["strategic updates"]',
                )
                session.add(chunk)

            # Also index an ICICI Bank transcript chunk to test the banking guidance policy
            icici_company_id = next(c["id"] for c in client.get("/api/v1/companies?q=ICICI").json()["items"] if "ICICI" in c["symbol"])
            icici_doc = ResearchDocument(
                company_id=icici_company_id,
                source_key="icici-q4fy26",
                title="ICICIBANK Earnings Call Transcript · 24 Apr 2026",
                document_type="earnings_transcript",
                fiscal_period="Q4 FY26",
                published_at=now,
                source_name="NSE Announcement",
                source_url="https://nsearchives.nseindia.com/icici_q4.pdf",
                content_hash="hash-icici-q4",
                page_count=30,
                is_demo=False,
            )
            session.add(icici_doc)
            session.flush()

            icici_chunk = ResearchChunk(
                document_id=icici_doc.id,
                page_number=8,
                chunk_index=1,
                text="In terms of net interest margin and loan growth, as you know, we do not provide forward-looking numerical quarterly guidance on credit costs or NIM.",
                financial_metrics_json='["net interest margin", "credit costs"]',
                guidance_json='["no forward-looking guidance"]',
                business_updates_json='["banking operations"]',
            )
            session.add(icici_chunk)
            session.commit()

        # Re-check document count for INFY
        infy_docs_after = client.get(f"/api/v1/companies/{infy['id']}/research/documents").json()
        assert infy_docs_after["count"] == 4

        # Test Research QA across lenses
        lenses = [
            ("financial performance", "What was the operating margin trend?"),
            ("management guidance", "What is management guidance on operating margin?"),
        ]
        for lens, q in lenses:
            ans = client.post("/api/v1/research/answer", json={
                "company_id": infy["id"],
                "question": q,
                "lens": lens,
            }).json()
            assert ans["evidence_sufficiency"]["status"] in {"sufficient", "partial"}
            assert len(ans["citations"]) > 0
            assert all(c["page"] in {3, 4, 5, 6} for c in ans["citations"])
            assert all(c["source_url"].startswith("https://nsearchives.nseindia.com/") for c in ans["citations"])

        # Test Guidance vs Actual 4-quarter comparison
        infy_gva = client.post("/api/v1/research/guidance-vs-actual", json={"company_id": infy["id"]}).json()
        assert len(infy_gva["quarters"]) == 4
        periods = [q["period"] for q in infy_gva["quarters"]]
        assert periods == ["Q2 FY27", "Q1 FY27", "Q4 FY26", "Q3 FY26"]

        # Check operating margin metric across quarters
        for q_obj in infy_gva["quarters"]:
            op_metric = next(m for m in q_obj["metrics"] if m["metric"] == "operating margin")
            assert op_metric["unit"] == "%"
            assert op_metric["guided_value"] == "20"
            assert op_metric["actual_value"] is not None
            assert op_metric["variance"] is not None
            assert op_metric["guided_source"]["page"] in {3, 4, 5, 6}
            assert op_metric["actual_source"]["page"] in {3, 4, 5, 6}

        # 2.5 Banking Sector Non-Numerical Guidance Rule (ICICI Bank)
        icici_id = next(c["id"] for c in client.get("/api/v1/companies?q=ICICI").json()["items"] if "ICICI" in c["symbol"])
        icici_guidance = client.post("/api/v1/research/answer", json={
            "company_id": icici_id,
            "question": "What is management guidance on net interest margin and credit costs?",
            "lens": "management guidance",
        }).json()
        assert icici_guidance["evidence_sufficiency"]["status"] == "insufficient"
        assert "does not publish forward-looking numerical quarterly guidance" in icici_guidance["answer"]

        # =========================================================================
        # 3. SETTINGS WORKFLOW
        # =========================================================================
        # 3.1 Toggle portfolio holding
        assert client.put("/api/v1/portfolio/holdings/ASIANPAINT?enabled=true").status_code == 200
        assert client.get("/api/v1/portfolio").json()["summary"]["companies_tracked"] == 9

        assert client.put("/api/v1/portfolio/holdings/ASIANPAINT?enabled=false").status_code == 200
        assert client.get("/api/v1/portfolio").json()["summary"]["companies_tracked"] == 8

        # 3.2 Category toggle
        assert client.patch(f"/api/v1/alert-rules/{price_rule['id']}?enabled=false").status_code == 200
        assert client.patch(f"/api/v1/alert-rules/{price_rule['id']}?enabled=true").status_code == 200
