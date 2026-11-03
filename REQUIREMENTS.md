# FINN - Requirements

## Brief and product goal

FINN (Financial Investment Agent) is a mobile-first AI layer for a public-markets investment team. It should reduce the time spent monitoring prices, filings, announcements, results, and macro information by selecting what matters and explaining why. This is a working prototype: creativity, product judgment, and a convincing workflow matter more than broad coverage or production completeness.

The challenge asks for two interaction modes:

- **Push:** FINN proactively reports what changed and why the investor should care.
- **Pull:** An investor asks FINN to research or analyze a company on demand.

The backend data domain is guided by the brief; the product, interaction model, and frontend are the builder's choices.

## Core requirements from the brief

### Companies and coverage

- Provide a configurable demo portfolio of 15-20 NSE/BSE-listed companies, with a sector and size mix that makes the demo interesting.
- Include a separate ad-hoc research path for approximately 3-5 companies outside the portfolio.
- Make the research engine work for an arbitrary valid NSE/BSE ticker, not only the demo companies.
- Treat data acquisition as plumbing; spend effort on useful interpretation and product experience.

### Guided data inputs

1. **Price and volume:** end-of-day prices and volume from Yahoo Finance as the starting point; Indian tickers may use `.NS`/`.BO` symbols. BSE is also named as a valid source.
2. **Corporate announcements and filings:** NSE/BSE, for the three stocks selected for the demo. Use the companion reference's announcement categories to classify them, adapt them, or ignore them. If coverage is partial, state it.
3. **Company fundamentals:** annual reports and concall (earnings-call) transcripts, including links on Screener.in or the company's investor-relations site.

### Push behavior

- Offer two push patterns:
  - **Daily digest:** a time-windowed view of material portfolio changes. The default lookback should be the last 24 hours; allow a period filter and prioritize important events.
  - **Triggered alerts:** surface events when a threshold/rule is crossed, such as a material announcement category or an unusual move versus recent average price/volume. The threshold and meaning of “unusual” must be configurable.
- A material event must explain why it matters in clear language, with a source and the event context.
- Tailor interpretation by event type. For example, explain management changes using who departed/joined and the context from incoming filings; explain quarterly results with headline Revenue, EBITDA, PAT, and PAT margin figures plus a first-cut comparison against the same quarter a year earlier and the immediately prior quarter. Other announcement types can use a one-line summary and a reason to open the filing.
- Show only changes that merit attention; avoid turning the feed into a raw news or filing list.

### Pull behavior

Pull research is grounded in the company's annual reports and concall transcripts. Offer a menu of analytical lenses; the brief names:

- Business snapshot: what the company does, segments, and revenue mix.
- Financial snapshot: current headline numbers (revenue, margins, PAT, key ratios).
- Trajectory: multi-year direction and what is growing or compressing.
- Balance sheet: debt, leverage, working-capital cycle, and funding structure.
- Cash quality: cash flow trend and whether earnings convert into cash.
- Narrative vs. numbers: whether management commentary and financials align or diverge.
- Guidance: management's stated guidance on headline items such as growth, margins, and capex.
- Bull vs. bear: a concise case on each side.
- Worked example: compare the last four quarters with management's prior guidance and report what was promised versus delivered. This is explicitly called out as a difference-making feature.

Pull should communicate what sources and periods support a conclusion. Do not present unsupported certainty or silently fill gaps in source material.

### Experience and deliverables

- Mobile-first, working prototype. A deployed link, Expo/TestFlight build, or responsive web app is acceptable.
- A daily-investor workflow should be immediately understandable and visually polished, concise, and interactive.
- Chat, voice, copilot, dashboard, or another interaction style is open for experimentation; choose a concrete interaction that demonstrates FINN's value.
- Include the GitHub repository, a short covering email/write-up, and the coding-agent/LLM conversation record used during the build (e.g. a Codex share link).
- The write-up should cover the product built, key decisions and trade-offs, what was intentionally left out, and what would be built next.
- The brief says not to optimize for completeness; a focused prototype that runs and demonstrates its thesis is preferred to a broad broken demo.

## Expected user workflows

### 1. Check today's portfolio

Investor opens FINN on a phone, sees a short ranked digest, understands what changed and why it matters, and can open the source filing or price context. A period control can widen the window beyond 24 hours.

### 2. Inspect an alert

Investor taps a material alert, sees the company, event type, timestamp, relevant figures or threshold movement, concise explanation, data freshness, and source link. Investor can mark it read/save it or move into deeper analysis.

### 3. Tune what is important

Investor adjusts watchlist/portfolio companies, announcement types and a small set of thresholds. The product explains that these are demo rules and does not imply the system understands a personal mandate unless configured.

### 4. Research a company

Investor searches/selects a listed company (including outside the portfolio), chooses one of the analysis lenses or asks a plain-language question, receives an answer tied to annual report/transcript evidence, and can inspect sources/periods.

### 5. Compare guidance with delivery

Investor requests the worked example; FINN lays out guidance by quarter and actual results for up to the last four quarters, labels mismatches/gaps, and links to the relevant source passages.

## MVP acceptance criteria

1. A phone-sized layout works without horizontal scrolling and makes Push and Pull discoverable.
2. Seeded demo portfolio covers 15-20 plausible NSE/BSE companies across sectors and sizes; 3-5 separate ad-hoc companies are searchable.
3. Push feed contains a useful daily digest and at least two visibly distinct event types, including a results interpretation and a filing/announcement event. Each card links to its underlying source or clearly labels demo data.
4. At least one triggered rule is demonstrable (e.g. price/volume move or selected material announcement category), with editable rule threshold and an explanation of why it fired.
5. Pull supports company search and a subset of the named lenses, including one financial/trajectory analysis and the worked guidance-versus-actual example.
6. Answers show the company, period, source links and evidence snippets; missing evidence is presented as a gap, not invented as fact.
7. Data recency/source state is visible. Demo fixtures are labeled; unavailable or delayed data is not made to look live.
8. Setup and demo instructions are documented; the prototype can be run reliably from the repository.

## Technical challenges and risks

- **Indian market identifiers and source availability:** NSE/BSE codes, Yahoo suffixes, ambiguous names, access restrictions, and occasional missing data require normalization and a provider adapter.
- **Filings are unstructured:** PDFs and varied announcement formats need classification, metadata extraction, and source links; this is a major scope trap.
- **Grounded analysis:** LLM summaries can fabricate figures or confuse periods. Extract and validate facts where possible, pass source excerpts to the model, require structured output and citations, and expose missing evidence.
- **Guidance tracking:** Guidance and actuals rarely share a tidy schema. The four-quarter worked example needs a small, explicit record of what management said, the period/metric, the source passage, and actual outcome.
- **Alert quality:** Thresholds should avoid noise and duplicate alerts. Use normalized rules, a cooldown/dedup key, and clear “why now” context.
- **Financial interpretation:** Ratios, YoY/QoQ comparisons and units must be consistent. Label each period and currency/unit; do not imply investment advice or recommendations.
- **Demo credibility:** Historical fixtures are appropriate when live feeds are infeasible, but must be clearly marked and sourced. Never imply that stale/demo data is real-time.
- **Mobile-first density:** Financial context and source traceability must remain legible on a narrow screen without turning every card into a report.

## Explicit non-goals for the MVP

- Trading, order placement, portfolio optimization, or personalized buy/sell recommendations.
- Comprehensive exchange-wide real-time streaming, every company announcement, or production-grade ingestion reliability.
- Multi-user enterprise permissions, brokerage connections, custom portfolio import, or a full research terminal.
- Exhaustive coverage of all eight research lenses if it compromises a reliable Push and Pull demo.
- Autonomous investment actions. FINN informs and explains; the investor decides.

## Assumptions and decisions to confirm during implementation

- The reference document named in the challenge is the authority for announcement categories and financial terminology. Use it when shaping classifiers and UI labels; don't invent a competing taxonomy.
- A responsive web app/PWA is the fastest low-friction mobile-first deliverable unless the team has a strong reason to choose Expo.
- In the MVP, real-source links plus a compact, labeled set of curated fixtures are acceptable where retrieval or live access is unreliable.
- This plan proposes an LLM-assisted experience with deterministic calculations and rules. Model provider is intentionally swappable because the brief permits any provider.

