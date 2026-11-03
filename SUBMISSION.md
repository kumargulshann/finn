# Covering email

**To:** assessment@enam.com
**Subject:** ENAM - IIT screening - 2027

---

Hello ENAM team,

Here is my submission for the FINN build challenge.

- **Try it on your phone:** {{LIVE_URL}} (the free host sleeps when idle, so the first load can take up to a minute)
- **Repository:** https://github.com/kumargulshann/finn
- **AI build history:** https://github.com/kumargulshann/finn/tree/main/build-history. This holds six sessions across Antigravity, Codex and Claude Code, including the attempts I threw away.

## What I built

FINN is a mobile-first web app with two tabs that match the two modes.

**Today (Push).** A digest of every filing across the portfolio for a window you choose (24h, 7d or 30d). It is ranked by a transparent score: event type, financial magnitude, portfolio weight and unusual price/volume. Each card says why it ranks where it does. Routine items sink, and duplicate NSE/BSE filings collapse into one. Results filings show the headline numbers with YoY change. Triggers are user-set in Settings: a volume-spike multiple and per-category toggles. Changing them re-filters the digest immediately. For example, raising volume from 2.0× to 2.5× drops the Reliance 2.4× alert.

**Research (Pull).** Pick any NSE ticker, not just the demo set. FINN fetches the company's annual reports and concall transcripts from NSE, indexes them page by page, and answers through six lenses. Every claim cites a page (`…pdf#page=27`), and each answer states whether the evidence is sufficient. **Guidance vs Actual** is the worked example from the brief: four quarters of what management guided against what they reported, with a source for each figure. Try Infosys.

## Key decisions and trade-offs

1. **Extractive, not generative, on the Pull side.** The brief's one hard rule is "ground it in primary sources". My first attempt used an LLM and produced plausible filings and bios that did not exist (see build history, session 1). So answers are assembled from retrieved passages (BM25 over page chunks, plus rule-based metric and guidance extraction), and every sentence traces to a page.
   - **Cost:** zero model spend at runtime.
   - **Trade-off:** answers read like evidence briefs, not fluent analyst prose, and cross-document synthesis is shallow.
2. **"Unavailable" beats a fake number.** The portfolio is defined by weights, not share counts, so rupee P&L shows as *Unavailable* rather than an invented figure. Scanned PDFs are flagged as unreadable, and a company with no indexed filings returns *Insufficient evidence* instead of an answer.
3. **Deterministic prioritisation.** A scored rank with stated reasons is something an analyst can audit and tune; a model's opinion of "important" is not.
4. **Responsive web, one container.** A link you open on a phone beats a TestFlight invite. Next.js and FastAPI ship as one Docker image with a pre-indexed SQLite snapshot, so the demo works even when NSE rate-limits cloud IPs.

## What I left out, and the gaps I know about

- **No LLM in the loop yet.** There is an `integrations/llm` slot, but it is not wired up, so there is no chat-style prose.
- **No bios on management changes.** Scraping LinkedIn breaks its terms. I would use a licensed people-data API instead.
- **Results cards show YoY only.** QoQ is not computed yet.
- **No price-move (±X%) trigger.** Only the volume multiple is configurable.
- **Push is evaluated when the app loads.** There is no background scheduler and no real phone notification.
- **The portfolio is 8 holdings plus 2 watchlist names,** below the 15–20 the brief asks for. I kept it small so every seeded item could be checked by hand; it is a one-line list in `seed.py`.
- **BSE's public feed returns 403s to scripts, and there is no OCR for scanned reports.**

## Where I would take it next

1. **Model routing for Pull.** A cheap Flash-class model extracts metrics and guidance per page, cached by document hash. A strong model writes only the final narrative-vs-numbers answer, constrained to the cited chunks so grounding survives.
2. **Real Push.** An end-of-day job after market close, with a web push or WhatsApp digest of the top three items.
3. **A management credibility score.** Track guided-versus-delivered over many quarters, so the Guidance vs Actual table becomes a running signal.
4. **Retrieval quality.** Hybrid BM25 plus embeddings, OCR for scanned PDFs, and a contracted exchange feed.

Thanks for the thoughtful brief. I enjoyed it.

Gulshan Kumar
