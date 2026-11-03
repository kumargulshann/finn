# FINN - Implementation Roadmap

## Delivery strategy

Build a narrow, working vertical slice from the Today feed through an alert detail into sourced Pull research. Use a compact, credible company universe and label any fixtures. Add breadth only after that path works on a phone. The challenge favors a deployed prototype that runs over an ambitious incomplete system.

## Recommended stack

### Prototype stack

- **Frontend:** Next.js + React + TypeScript, responsive PWA, Tailwind CSS, and a small component set. Use accessible semantic controls and prioritize 360-430px layouts.
- **Backend/API:** Python FastAPI. It fits market-data and document processing libraries and provides typed request/response contracts with Pydantic.
- **Persistence:** SQLite for the challenge prototype (portfolio, alert rules, events, source metadata, extracted facts, saved analyses); keep repository boundaries clean so it can move to PostgreSQL.
- **Scheduling:** a simple in-process scheduler or explicit “refresh demo data” action for the demo; use a durable job queue only if deployment requires recurring jobs.
- **AI:** provider-neutral adapter to the selected LLM. Use structured output for summaries/classification, short source-bounded prompts, and record model/provider/version for reproducibility.
- **Data inputs:** adapters for Yahoo Finance end-of-day prices/volume, exchange filings/announcements for the three showcase stocks, and annual reports/concall transcripts from Screener.in or investor-relations pages. Preserve canonical source URLs and timestamps.
- **Hosting:** one straightforward deployment for the web app and API (or frontend + API together if convenient). Keep secrets in environment configuration; provide a seeded offline/demo mode.
- **Observability:** structured logs and request IDs; capture ingestion timestamps, source errors, model errors, and answer citations. Avoid collecting unnecessary investor data.

### Why this stack

It offers a fast iteration loop, a clear boundary between UI, deterministic financial logic, ingestion, and LLM interpretation, and minimal deployment complexity. A PWA meets the brief's mobile-first requirement without a separate native build. Python is a practical fit for finance/data and document tooling. The provider/model choice stays swappable, matching the brief's flexibility.

### Architecture sketch

```text
Market / exchange / company documents
                |
         Source adapters
                |
 Normalize + classify + extract facts ----> source/evidence store
                |                                  |
       Alert rules + digest ranking          Pull retrieval
                |                                  |
          FINN API (FastAPI; deterministic calculations + LLM explanation)
                                  |
                   Next.js mobile-first PWA
```

Keep separate modules for `market_data`, `announcements`, `documents`, `facts`, `alerts`, `research`, and `api`. Avoid microservices for the prototype.

## Step-by-step build plan

### Phase 0 - Lock the demo slice

- Choose 15-20 portfolio names across sectors/sizes and 3-5 ad-hoc names.
- Choose three showcase companies for exchange filings as the brief recommends; for one, assemble enough quarterly results and guidance to support the four-quarter worked example if feasible.
- Read the companion reference document and use its announcement categories and plain-English terms in the product.
- Decide what is live retrieval versus curated fixture. Mark fixture data in both UI and underlying records.
- Write a 3-minute demo script and keep scope attached to it.

**Exit:** named demo companies, a chosen results/announcement example, source links, and an explicit live/demo data map.

### Phase 1 - Define contracts and seed data

- Define normalized schemas for Company, PricePoint, Announcement, Filing, FinancialFact, GuidanceStatement, AlertRule, AlertEvent, Source, and ResearchAnswer.
- Standardize ticker/exchange identifiers, units, fiscal periods, timestamps, and source metadata.
- Create seeded example data with historical dates and reproducible expected outputs.
- Define API contracts for portfolio/digest, event detail, company search, research lens, rule settings, and health/data status.

**Exit:** a seeded backend can serve coherent data for the scripted demo, with source and freshness metadata on every record.

### Phase 2 - Build mobile product shell

- Implement Today, Alert Detail, Research, Company View, and Settings.
- Establish visual hierarchy for urgency, source/freshness, period labels and mobile tap targets.
- Add skeleton, empty, error, stale-data, and demo-data states.
- Add navigation from a Push card to the matching Pull company analysis.

**Exit:** the complete workflow works on seeded data at phone and desktop widths.

### Phase 3 - Implement deterministic Push

- Build the digest query with default 24-hour window, selectable lookback, deduplication, and simple explainable ranking.
- Add one configurable rule: thresholded price/volume move or selected material category.
- Normalize result metrics and calculate YoY/QoQ comparisons in code with unit/period checks.
- Add event-specific summaries, beginning with quarterly results and one announcement class.
- Include direct source links and explain the trigger/reason on each card.

**Exit:** changing a rule or date window changes the digest in an understandable way; duplicate events do not flood the feed.

### Phase 4 - Implement grounded Pull

- Add ticker/company search across portfolio and ad-hoc names.
- Build source indexing for a deliberately small corpus of annual report/transcript materials and metadata.
- Retrieve a small set of relevant excerpts and pass them to a provider adapter with explicit instructions to cite evidence and say when absent.
- Return typed output: takeaway, findings, periods, evidence/source IDs, caveats, and missing information.
- Calculate quantitative facts and comparisons in deterministic code rather than asking the model to do arithmetic from prose.
- Implement the core snapshot/trajectory lenses; add a sourced guidance-versus-actual example for one company if the necessary material is available.

**Exit:** each numeric claim is traceable to a period/source or clearly identified as unavailable; an unsupported question gets a useful gap response.

### Phase 5 - Connect real sources selectively

- Implement the Yahoo Finance price/volume adapter and normalize NSE/BSE tickers.
- Add one reliable retrieval path for exchange announcements/filings on the three showcase stocks; retain original URL, publish time, type, and raw response/document.
- Link annual reports and transcripts from Screener.in or company IR; only extract enough content for the demo lenses.
- Add timeouts, retries/backoff, caching, and graceful “source unavailable” handling.
- Verify terms/access and do not bypass source protections. Keep fixture fallback clearly marked.

**Exit:** the demo can refresh the selected sources or explain precisely when it is showing fixture data.

### Phase 6 - Evaluation, polish, deployment, submission

- Manually verify every demo event and Pull answer against its linked source and period.
- Check result-metric math, ticker resolution, date-window boundaries, deduplication, mobile layouts and failure states.
- Review AI summaries for fabricated facts, unsupported causal claims, and unclear uncertainty.
- Deploy the prototype; test the deployed path from a phone-sized viewport and a clean browser session.
- Prepare repository setup/run instructions, a short architecture/data caveat note, the covering write-up, and the coding-agent conversation record/share link requested in the challenge.

**Exit:** a reliable deployed demo, repository, clear run instructions, and submission materials.

## Minimal evaluation checklist

- **Push:** digest order makes sense; 24-hour and broader filters work; source/freshness visible; trigger rationale and deduplication are clear.
- **Results:** revenue, EBITDA, PAT, and PAT margin display correct units and period labels; YoY and QoQ comparisons use the right base periods.
- **Pull:** company outside portfolio resolves; each factual statement has a source; the answer handles missing transcript/annual-report material honestly.
- **Guidance example:** each promise and actual is tied to a metric, quarter, and source; gaps are not quietly interpolated.
- **Product:** one-handed mobile use, readable density, obvious Push/Pull entry points, helpful empty and error states.
- **Trust:** seeded/demo versus live is unambiguous; no buy/sell instruction or implication of guaranteed coverage.

## Key decisions and trade-offs

- **Responsive PWA over native:** lower setup and distribution friction, still meets mobile-first brief; native push notifications can come later.
- **Curated source set over exchange-wide ingestion:** allows high-quality interpretation and a convincing end-to-end demo within challenge scope.
- **SQLite and one API service over distributed infrastructure:** faster build and simpler deploy; move to Postgres/jobs only when usage requires it.
- **Rules and calculations in code, explanations with LLM:** more dependable figures and alert behavior while still demonstrating useful AI.
- **Evidence-first constrained analysis over open-ended chat:** more credible financial research and easier evaluation.

## Risks to surface in the covering note

- Data coverage/freshness is limited to the selected companies and sources; name the limits.
- Any historical fixture or synthesized demo record is labeled as such.
- Retrieval may fail on a source or document; FINN should show a gap rather than fabricate a replacement.
- The prototype is an information/research aid, not a trading system or investment recommendation engine.

