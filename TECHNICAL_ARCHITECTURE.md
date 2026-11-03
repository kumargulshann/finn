# FINN - Technical Architecture

## Purpose and constraints

This document turns the agreed MVP into an implementation-ready architecture for a mobile-first FINN prototype. The system is a single product with two user paths:

- **Push:** ingest selected market and company events, apply deterministic alert rules, and serve a ranked digest with evidence.
- **Pull:** retrieve company-specific source evidence, compute validated metrics, and produce a concise, cited analysis through an LLM adapter.

The architecture uses Next.js, TypeScript, Tailwind CSS, FastAPI, and SQLite. It favors one deployable backend with clear modules over microservices. It does not include order execution or personalized buy/sell recommendations.

## System overview

```text
 Yahoo Finance      NSE/BSE sources       Company IR / Screener links
      |                    |                         |
      +--------------------+-------------------------+
                           v
                 FastAPI source adapters
                           |
             Normalize / classify / extract
                           |
           +---------------+------------------+
           |                                  |
     SQLite + document store          Deterministic services
     facts, sources, events             metrics, rules, rank
           |                                  |
           +---------- Retrieval + LLM --------+
                           |
                     FastAPI JSON API
                           |
              Next.js / TypeScript / Tailwind
                 mobile-first responsive PWA
```

### Runtime boundaries

- The **Next.js app** renders the experience and calls only the FINN API. It does not call market providers or the LLM directly.
- The **FastAPI app** owns business logic, provider integrations, validation, and database access.
- **SQLite** stores normalized and queryable metadata. Original PDFs and extracted text live in a local document directory (or mounted persistent storage); rows store their relative storage key and source URL. Do not store large binary documents as SQLite blobs.
- **LLM provider** receives only the minimum retrieved evidence required for the requested answer. It has no direct database or provider credentials.

## Recommended repository structure

```text
finn/
├── frontend/
│   ├── app/
│   │   ├── (main)/today/page.tsx
│   │   ├── companies/[companyId]/page.tsx
│   │   ├── events/[eventId]/page.tsx
│   │   ├── research/page.tsx
│   │   ├── settings/page.tsx
│   │   ├── layout.tsx
│   │   └── globals.css
│   ├── components/
│   │   ├── digest/
│   │   ├── events/
│   │   ├── research/
│   │   └── ui/
│   ├── lib/
│   │   ├── api.ts
│   │   ├── schemas.ts
│   │   └── formatters.ts
│   ├── public/
│   ├── tailwind.config.ts
│   └── package.json
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── api/
│   │   │   ├── deps.py
│   │   │   └── routes/
│   │   │       ├── health.py
│   │   │       ├── companies.py
│   │   │       ├── portfolio.py
│   │   │       ├── events.py
│   │   │       ├── alerts.py
│   │   │       ├── research.py
│   │   │       └── admin_refresh.py
│   │   ├── domain/
│   │   │   ├── models.py
│   │   │   ├── enums.py
│   │   │   └── errors.py
│   │   ├── schemas/              # Pydantic request/response models
│   │   ├── db/
│   │   │   ├── session.py
│   │   │   ├── repositories/
│   │   │   └── migrations/       # Alembic
│   │   ├── integrations/
│   │   │   ├── stocks/{base.py,yahoo.py}
│   │   │   ├── announcements/{base.py,exchange.py}
│   │   │   ├── documents/{base.py,web.py,pdf.py}
│   │   │   └── llm/{base.py,provider.py}
│   │   ├── services/
│   │   │   ├── ingestion.py
│   │   │   ├── normalization.py
│   │   │   ├── announcement_classifier.py
│   │   │   ├── fact_extraction.py
│   │   │   ├── calculations.py
│   │   │   ├── alert_engine.py
│   │   │   ├── digest.py
│   │   │   ├── retrieval.py
│   │   │   └── research.py
│   │   └── tasks/
│   │       └── refresh.py
│   ├── data/
│   │   ├── finn.db
│   │   └── documents/            # ignored by git; persistent volume in deployment
│   ├── tests/
│   ├── alembic.ini
│   └── pyproject.toml
├── scripts/
│   ├── seed_demo.py
│   └── refresh_sources.py
├── .env.example
├── .gitignore
├── docker-compose.yml            # optional local/deployment convenience
└── README.md
```

Keep each integration behind a small interface and each route thin. Routes validate requests, call a service, and serialize a response; provider-specific parsing stays in `integrations/`. A single backend process is sufficient for the initial demo.

## Database design

Use SQLAlchemy 2.x (or SQLModel if a smaller model layer is preferred) with Alembic migrations. Store timestamps in UTC ISO-8601 form. Store money/financial values as numeric values plus currency/unit metadata; do not encode formatted strings in the database. Treat NSE/BSE as part of the instrument identity because a ticker can be exchange-specific.

### Entity relationships

```text
Company 1---* Instrument
Company 1---* Source
Company 1---* Announcement
Company 1---* Document 1---* DocumentChunk
Company 1---* FinancialFact
Company 1---* GuidanceStatement
Portfolio 1---* PortfolioCompany *---1 Company
AlertRule 1---* AlertEvent *---0..1 Announcement / PricePoint
ResearchRun 1---* ResearchEvidence *---1 Source / DocumentChunk / FinancialFact
```

### Tables and key fields

| Table | Important fields | Purpose / constraints |
|---|---|---|
| `companies` | `id` UUID/text PK, `name`, `sector`, `industry`, `created_at`, `updated_at` | Canonical issuer record. Unique normalized name where possible. |
| `instruments` | `id`, `company_id` FK, `exchange` (`NSE`/`BSE`), `symbol`, `provider_symbol`, `currency`, `is_primary` | Exchange-specific symbol mapping. Unique (`exchange`, `symbol`). Provider symbol may be `SYMBOL.NS` or `.BO`. |
| `portfolios` | `id`, `name`, `is_demo`, timestamps | MVP may have one seeded portfolio. |
| `portfolio_companies` | `portfolio_id` FK, `company_id` FK, `added_at`, `sort_order` | Composite PK (`portfolio_id`, `company_id`). Supports 15-20 demo companies. |
| `sources` | `id`, `company_id` nullable FK, `source_type`, `publisher`, `canonical_url`, `title`, `published_at`, `retrieved_at`, `content_hash`, `status`, `is_demo` | Provenance catalog shared by events, documents, and research. Deduplicate by canonical URL + content hash when available. |
| `price_points` | `id`, `instrument_id` FK, `observed_at`, `interval`, `open`, `high`, `low`, `close`, `volume`, `currency`, `source_id` FK, `is_demo` | End-of-day market history. Unique (`instrument_id`, `observed_at`, `interval`, `source_id`). |
| `announcements` | `id`, `company_id` FK, `instrument_id` nullable FK, `source_id` FK, `category`, `headline`, `summary`, `published_at`, `importance`, `raw_text_key`, `fingerprint`, `is_demo` | Normalized exchange/company event. `fingerprint` supports deduplication. Category maps to reference taxonomy, with `other` fallback. |
| `documents` | `id`, `company_id` FK, `source_id` FK, `document_type` (`annual_report`, `transcript`, etc.), `fiscal_year`, `period_label`, `storage_key`, `mime_type`, `content_hash`, `ingested_at`, `parse_status`, `is_demo` | Original document metadata. Files stay outside SQLite. |
| `document_chunks` | `id`, `document_id` FK, `chunk_index`, `page_start`, `page_end`, `text`, `section`, `token_count` | Searchable extracted text with enough location information to cite the source. Index `document_id`, `section`; consider SQLite FTS5 for lexical search. |
| `financial_facts` | `id`, `company_id` FK, `source_id` FK, `metric`, `period_type`, `period_start`, `period_end`, `value`, `unit`, `currency`, `reported_label`, `extraction_method`, `confidence`, `is_demo` | Normalized numeric values with provenance. Unique key should include company, metric, period, and source. |
| `guidance_statements` | `id`, `company_id` FK, `source_id` FK, `metric`, `target_period`, `guidance_low`, `guidance_high`, `unit`, `currency`, `statement_text`, `published_at`, `confidence` | Explicit management guidance extracted for the worked example. Preserve the source wording and don't infer absent numeric targets. |
| `alert_rules` | `id`, `name`, `rule_type`, `config_json`, `enabled`, `created_at`, `updated_at` | MVP configuration for price/volume thresholds or announcement categories. JSON keeps rule config simple; validate by rule type. |
| `alert_events` | `id`, `rule_id` nullable FK, `company_id` FK, `announcement_id` nullable FK, `price_point_id` nullable FK, `event_type`, `title`, `reason`, `severity`, `occurred_at`, `dedupe_key`, `status`, `is_demo` | Materialized push item and explanation. Unique `dedupe_key`; status may be `unread`, `read`, `saved`, `dismissed`. |
| `research_runs` | `id`, `company_id` FK, `question`, `lens`, `answer_json`, `model_provider`, `model_name`, `prompt_version`, `created_at`, `status`, `error_code` | Stores a bounded analysis run for history/debugging. Avoid storing secrets or unnecessary user-identifying data. |
| `research_evidence` | `id`, `research_run_id` FK, `source_id` FK, `document_chunk_id` nullable FK, `financial_fact_id` nullable FK, `claim_key`, `excerpt`, `page_or_section`, `rank` | Explicit evidence links from answer claims to source records. |
| `ingestion_runs` | `id`, `integration`, `started_at`, `finished_at`, `status`, `records_seen`, `records_written`, `error_summary` | Supports last-updated state and debugging without requiring a monitoring platform. |

### SQLite indexes and practical rules

- Index `price_points(instrument_id, observed_at DESC)`, `announcements(company_id, published_at DESC)`, `financial_facts(company_id, metric, period_end)`, and `alert_events(occurred_at DESC, status)`.
- Use unique constraints for instrument identifiers, dedupe keys, and source-aware facts/events.
- Enable foreign keys and use transactions for each ingestion batch. Keep write batches short; SQLite permits many readers but only one writer at a time.
- Set a `busy_timeout`; use WAL mode for local concurrent reads. Do not run multiple independent API replicas against one SQLite file.
- Use `config_json` only for small validated rule settings, not as a replacement for queryable event or financial data.
- A migration to Postgres later should replace the persistence adapter and schema migration target, not require a rewrite of services.

## API design

Base path: `/api/v1`. JSON request/response bodies use snake_case. Times are UTC ISO-8601. Amounts include `value`, `currency`, and/or `unit`; every event and research claim includes source references when available. Generate OpenAPI from FastAPI and keep matching TypeScript types/schemas in the frontend (generated types are preferable once endpoints stabilize).

### Read endpoints

| Method and path | Purpose | Key query/body |
|---|---|---|
| `GET /health` | Liveness only | Returns `status`; no secret or provider detail. |
| `GET /api/v1/status` | Product data status | Source freshness, demo/live mode, latest ingestion outcome. |
| `GET /api/v1/portfolio` | Demo portfolio and summary | Optional `portfolio_id`; returns companies and latest available data timestamps. |
| `GET /api/v1/digest` | Ranked Push feed | `portfolio_id`, `from`, `to`, `limit`; default `to=now`, `from=now-24h`. |
| `GET /api/v1/companies` | Search portfolio and ad-hoc companies | `q`, optional `exchange`, `limit`; return canonical company plus matching instrument(s). |
| `GET /api/v1/companies/{company_id}` | Company overview | Company metadata, instruments, recent events, source availability. |
| `GET /api/v1/companies/{company_id}/prices` | Price history | `from`, `to`, `interval=1d`; include source and demo flag. |
| `GET /api/v1/companies/{company_id}/announcements` | Company events | `from`, `to`, `category`, `limit`. |
| `GET /api/v1/companies/{company_id}/documents` | Available reports/transcripts | `document_type`, `fiscal_year`. |
| `GET /api/v1/events/{event_id}` | Alert detail | Returns why it triggered, event facts, source links, freshness, status. |
| `GET /api/v1/companies/{company_id}/facts` | Normalized financial facts | `metrics`, `period_type`, `limit`; values carry period and units. |
| `GET /api/v1/companies/{company_id}/guidance` | Guidance history | `metric`, `target_period`; include source statement and confidence. |

### Write/action endpoints

| Method and path | Purpose | Request / behavior |
|---|---|---|
| `PATCH /api/v1/events/{event_id}` | Update event state | `{ "status": "read" }`, `saved`, or `dismissed`. |
| `GET /api/v1/alert-rules` | List demo alert rules | Include supported rule types and validated current config. |
| `POST /api/v1/alert-rules` | Create a rule | `rule_type`, `name`, scoped company/category list, thresholds/config. |
| `PATCH /api/v1/alert-rules/{rule_id}` | Edit or enable/disable | Validate config against `rule_type`. |
| `DELETE /api/v1/alert-rules/{rule_id}` | Remove a rule | Soft-disable if events should retain their rule association. |
| `POST /api/v1/research` | Run a Pull analysis | `{ company_id, lens, question?, period?, include_guidance? }`. Returns typed answer and evidence. |
| `GET /api/v1/research/{run_id}` | Retrieve prior analysis | Returns stored answer, model metadata, and citations. |
| `POST /api/v1/admin/refresh` | Refresh selected sources | Restricted to local/demo admin or protected by an admin token; accepts source types and company IDs. |

### Response conventions

- A digest item contains `event_id`, `company`, `occurred_at`, `category`, `title`, `summary`, `why_it_matters`, `severity`, `source_refs[]`, `data_mode`, and `freshness`.
- A source reference contains `source_id`, `title`, `url`, `publisher`, `published_at`, `retrieved_at`, and optional `page_or_section`.
- A research result contains `run_id`, `company`, `lens`, `takeaway`, `findings[]`, `evidence[]`, `caveats[]`, `missing_information[]`, `model`, and `created_at`.
- Validation errors use FastAPI's standard 422 response. Domain errors return a stable `{ code, message, request_id }` envelope. Provider outages should produce a clear 503 or stale-data response, not a fabricated success.
- Use pagination only where history needs it. For this prototype, bounded `limit` and date filters are enough.

## Integration design

All integrations implement small interfaces and return normalized internal records. Store the original provider/source identifier and link so normalization never destroys provenance.

### 1. Stock data

**Adapter:** `StockDataProvider` with `fetch_eod(instrument, start, end)` and optional `fetch_quote(instrument)`.

- Start with Yahoo Finance end-of-day OHLCV as guided by the brief; map an NSE symbol to the appropriate provider symbol, commonly `.NS`, and BSE to `.BO` where available.
- Store provider symbol mapping in `instruments`, not in business logic.
- Normalize timestamps, exchange sessions, currency, missing values, split/adjustment semantics, and volume. Expose end-of-day data as end-of-day; do not label it live.
- Apply per-company caching and rate-conscious refresh. Persist `source_id` and `retrieved_at`.
- Keep the provider behind an adapter: availability and terms can change, and a fallback/fixture provider should obey the same interface.
- MVP scope is historical/EOD prices for the portfolio; no streaming quotes.

### 2. Corporate announcements and filings

**Adapter:** `AnnouncementProvider.fetch(company, from, to)` returning source URL, exchange, published time, headline, document link, and raw content where accessible.

- Cover three showcase companies first, as the brief suggests.
- Prefer exchange-origin records/links. A user-visible source link remains useful even when full PDF download or parsing is unavailable.
- Classify to the companion reference taxonomy using deterministic mappings for obvious labels, with an LLM fallback only for ambiguous text. Preserve both the raw label and normalized category.
- Build a stable fingerprint from company, publish time, normalized title, and source link; dedupe repeated exchange/company reposts.
- Store the original document/response and source metadata. Record access/parse failures and keep a clear unsupported/unavailable state.
- Do not bypass access controls or imply comprehensive exchange coverage.

### 3. Financial documents

**Adapter:** `DocumentCatalogProvider` resolves annual report and concall transcript URLs from Screener.in or issuer investor-relations pages. `DocumentProcessor` downloads only where permitted, extracts text, and chunks it.

- Prioritize one showcase company and a small number of annual reports/transcripts over broad crawling.
- Extract text from text PDFs first; retain page numbers. OCR and complex scanned-PDF processing are out of MVP unless essential to the demo.
- Store original files on persistent local storage and chunks/metadata in SQLite. Compute content hashes to avoid duplicate processing.
- Extract financial facts and management guidance into structured records with source/page/section and confidence. Keep the literal excerpt alongside normalized values.
- A failed parse or missing document must be represented as unavailable. Research can cite a link even when no parsed text exists.

### 4. LLM provider

**Interface:** `LLMProvider.generate_structured(prompt, schema, model_options)` and optional `classify(text, allowed_categories)`.

- Configure provider/model by environment variables; never expose API credentials to the browser or commit them.
- Use strict response schemas for announcement classification and research findings. Validate outputs through Pydantic; retry once on schema failure, then return a controlled error.
- Pass only retrieved excerpts/facts, with explicit source IDs and periods. Tell the model to use no outside knowledge for company-specific factual claims and to report missing evidence.
- Require every factual finding to cite one or more provided evidence IDs. Reject or downgrade uncited numeric claims; calculations come from deterministic Python services.
- Keep prompts versioned (`prompt_version`) and record provider/model identifiers for reproducibility. Avoid storing chain-of-thought; persist user-visible answer, evidence, caveats, and minimal diagnostics.
- Use deterministic templates or fixture responses in offline demo mode. Model unavailability should not block the Push feed.

## Push and Pull data flows

### Push ingestion and digest

1. A manual refresh action or scheduled task calls the selected provider adapters.
2. Adapters normalize and persist prices, announcements, source metadata, facts, and ingestion results.
3. The alert engine evaluates configured rules using deterministic thresholds, computes a stable dedupe key, and materializes qualifying `alert_events`.
4. The digest service filters by portfolio/date, deduplicates, ranks using explainable features (category importance, recency, configured trigger), and returns a bounded feed.
5. The UI displays the reason, source, freshness, and demo/live status.

### Pull research

1. API validates the company, lens, and requested period.
2. Retrieval finds relevant document chunks, facts, guidance statements, and recent events for that company. Keep a small bounded evidence set; SQLite FTS5 or simple keyword search is enough for the first version.
3. Deterministic calculation services compute ratios, comparisons, trajectories, and guidance-versus-actual tables from normalized facts.
4. The LLM turns those validated facts and selected excerpts into a concise narrative that follows the response schema.
5. The service validates all citations against evidence IDs, persists the run and evidence links, and returns the answer.
6. If evidence is absent or conflicting, the response names the gap/conflict. It must not fill missing periods from model memory.

## Deployment and configuration

### Simplest reliable deployment

- Deploy the Next.js frontend and FastAPI backend as two processes, with one public origin where practical (`/` for Next.js and `/api` reverse-proxied to FastAPI). A single VM/container host with a reverse proxy is enough for the prototype.
- Attach a persistent volume for `finn.db` and `data/documents`. Back up both before upgrades; migrations must be applied on startup/deploy in a controlled step.
- Run one FastAPI instance when using SQLite. If the hosting platform requires multiple backend replicas or ephemeral disks, switch to a managed database before scaling rather than sharing a SQLite file over a network filesystem.
- For a local demo, Docker Compose can run frontend and backend; direct `npm run dev` and `uvicorn` instructions should also be documented.
- Use manual refresh or a single in-process scheduler for scheduled demo ingestion. Since in-process jobs run once per backend worker, do not scale workers without moving scheduling to a dedicated process.

### Environment variables

```text
FINN_ENV=development
DATABASE_URL=sqlite:///./data/finn.db
DOCUMENTS_DIR=./data/documents
FRONTEND_ORIGIN=http://localhost:3000
LLM_PROVIDER=<provider>
LLM_MODEL=<model>
LLM_API_KEY=<secret>
STOCK_DATA_MODE=provider|fixture
ANNOUNCEMENT_MODE=provider|fixture
ADMIN_REFRESH_TOKEN=<optional local/demo secret>
```

`.env.example` contains names and safe placeholders only. Production secrets belong in the hosting provider's secret store.

## Security, reliability, and trust

- Restrict CORS to the deployed frontend origin. Validate all provider URLs before fetching and reject private-network/localhost targets to reduce SSRF risk from document links.
- Apply request timeouts, bounded downloads, file-type/size checks, and retries with backoff to integrations. Do not let a provider outage stall user-facing read endpoints.
- Escape document-derived text in the UI; treat filings and transcripts as untrusted input, including against prompt injection. Retrieved text is evidence, not instructions to the model.
- Protect refresh/admin endpoints. For a single-user demo, avoid adding a full auth system unless the deployment is publicly exposed with mutable data; use a read-only demo mode or simple access gate where needed.
- Log request IDs, provider outcomes, ingestion status, and LLM failures without logging keys or full sensitive prompts.
- Present source publication and retrieval times separately. Display “demo,” “delayed,” “stale,” and “unavailable” states plainly.
- Add explicit UI and API language that FINN is a research aid; investor decisions remain with the user.

## Architecture decisions and deferred work

| Decision | MVP choice | Revisit when |
|---|---|---|
| Service topology | One modular FastAPI application | Independent scaling or team ownership needs appear |
| Database | SQLite on persistent disk, one writer process | Multi-instance writes or concurrent users require managed Postgres |
| Search | SQLite FTS5 / keyword retrieval | Larger corpus or semantic retrieval measurably improves results |
| Jobs | Manual refresh or single scheduler | Reliable recurring ingestion needs a durable queue/worker |
| Document storage | Persistent local volume | Scale/redundancy needs object storage |
| Authentication | Minimal demo access control | Multiple real users or portfolio privacy is in scope |
| Notifications | In-app feed | Native/web push is explicitly prioritized |
| Model | Provider-neutral structured generation | Evaluation identifies a clear provider-specific advantage |

## Build order from this architecture

1. Define Pydantic/TypeScript contracts and SQLite migrations for companies, instruments, sources, events, facts, rules, and research evidence.
2. Seed portfolio, company sources, and reproducible demo events; implement health/status, portfolio, digest, event detail, and search endpoints.
3. Build the mobile Today and Alert Detail screens against seeded API responses.
4. Add one stock adapter and one announcement path; verify symbol normalization, dates, deduplication, and freshness.
5. Add document catalog, extraction/chunking, and deterministic metrics; demonstrate sourced Pull research.
6. Add the LLM adapter with typed, evidence-restricted outputs and citation validation.
7. Complete the guidance-versus-actual showcase, deployment persistence, graceful failures, and demo documentation.

