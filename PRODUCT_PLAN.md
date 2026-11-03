# FINN - Product Plan

## Product thesis

**FINN helps an investor know what changed, why it matters, and where the evidence is - then lets them go deeper on demand.** Its edge is not another stream of financial content. It is a calm, explainable layer that turns a manageable slice of market events and company documents into decisions about what deserves attention.

## Target user and job

### Primary user

A public-markets investor or analyst at a lean investment firm who tracks a concentrated portfolio and cannot read every price move, filing, result, annual report, and concall transcript every day.

### Core job

“Help me stay on top of my companies without missing a material change, and make it quick to investigate the company behind that change.”

## Product principles

1. **Attention is scarce:** rank and filter; do not produce a news firehose.
2. **Explain the event, not just its label:** every push answers what happened, why it may matter, and what to inspect next.
3. **Evidence is part of the answer:** give dates, periods, primary-source links, and excerpts for researched claims.
4. **Investor remains in control:** preferences and thresholds are visible; no trade execution or unqualified recommendations.
5. **Make uncertainty visible:** distinguish verified facts, model interpretation, demo data, stale data, and missing evidence.
6. **Start narrow, demonstrate depth:** a small number of well-crafted flows is better than many hollow features.

## MVP: “The morning brief + one-tap research”

Build a responsive mobile-first PWA with a **Today** feed and a **Research** entry point. The central demo loop is:

1. Open Today and scan a ranked digest for the demo portfolio.
2. Tap a results or material-announcement card to see impact context and source.
3. Ask FINN to analyze that company, or choose a focused lens.
4. Review evidence-backed findings and open the source document.

### Push surface

- **Today digest:** 3-5 ranked items, last 24 hours by default, with a period filter and a compact “why it matters” summary.
- **Alert detail:** company, event category, event time, relevant numbers/context, significance explanation, source link, freshness label, and a clear demo/live status.
- **One configurable trigger:** demonstrate at least one unusual price/volume rule and/or selected announcement category. Let the user edit the threshold and enable/disable it. A simple in-product explanation of the trigger is essential.
- **Event types to polish:** quarterly results (Revenue, EBITDA, PAT, PAT margin; YoY and QoQ comparison) and one material corporate announcement such as management change. Other types can be summarized with a short headline and source link.

### Pull surface

- **Company search:** portfolio and a handful of ad-hoc companies, with exchange/ticker disambiguation.
- **Lens menu:** MVP priority is business/financial snapshot, trajectory, and narrative-versus-numbers. Implement the guidance-versus-actual worked example if source data can be assembled for one showcase company; otherwise show the actual evidence gap explicitly and include it as the next extension.
- **Grounded answer:** short executive takeaway, key facts, period labels, evidence excerpts/source links, and a “what is missing” section when appropriate.
- **Follow-up:** allow one conversational follow-up on the same company and source set. Avoid a general-purpose chatbot detached from the investor task.

### Suggested information architecture

- **Today:** ranked digest, date range, alert cards, freshness indicators.
- **Alert detail:** facts, FINN interpretation, evidence/source, related research action.
- **Research:** company/ticker search, research lenses, latest saved analyses.
- **Company view:** compact business summary, recent events, fundamentals/transcript sources.
- **Settings:** portfolio, announcement categories, alert threshold(s), data/demo status.

## Demo story (3-4 minutes)

1. Start on Today with 15-20-company portfolio and show only a few high-signal items rather than a dense feed.
2. Open a quarterly-results alert; point out labeled Revenue/EBITDA/PAT/PAT margin and YoY/QoQ context.
3. Open its source, then tap “Research this company.”
4. Show a concise Pull response with source periods, evidence and a clearly bounded takeaway.
5. Switch to the guidance-versus-actual example or an explicit evidence gap, then show the ad-hoc company search to prove the engine generalizes beyond the watchlist.
6. Briefly adjust an alert rule and explain the event that would trigger it.

## Prioritization

| Priority | Capability | Why it matters |
|---|---|---|
| P0 | Mobile Today feed with ranked, sourced digest | Demonstrates FINN's primary Push value |
| P0 | Event detail with “what / why / source / freshness” | Builds trust and makes the push actionable |
| P0 | Company/ticker search and a focused Pull analysis | Completes the core Push-to-Pull loop |
| P0 | Clearly labeled demo data and robust empty/error states | Keeps the prototype honest and usable |
| P1 | Results normalization and YoY/QoQ display | Makes the financial workflow concrete |
| P1 | Editable alert threshold/category and deduplication | Demonstrates triggered Push rather than only a static digest |
| P1 | Grounded document snippets with links | Makes AI output auditable |
| P1 | Four-quarter guidance-versus-actual example for one showcase company | High differentiation explicitly highlighted by the brief |
| P2 | More announcement categories, more lenses, richer history | Extend after a clean demo loop exists |
| P2 | Scheduled delivery, login, custom portfolio import, notifications | Production-oriented follow-ons, not required for the core prototype |

## Product success criteria for the prototype

- A first-time viewer can describe Push and Pull after one minute without a walkthrough.
- The morning digest feels curated and every sample card answers why it is present.
- One card can be traced from summary to primary source in one tap.
- A Pull answer supports its numeric claims with a source/period, or labels them unavailable.
- A company outside the portfolio can be looked up without a code change.
- The mobile layout is readable and the core loop works from a deployed link.

## Scope guardrails

- Curate one compelling end-to-end example for complex filings rather than build a universal PDF intelligence platform.
- Start with one provider per data type behind adapters; don't spend the challenge building generalized ETL.
- Keep the source corpus and model context small and inspectable.
- Use deterministic code for thresholds, ratios, period comparisons, and ranking inputs; use the LLM for classification/explanation where useful.
- Do not claim real-time or comprehensive coverage without operational evidence.

