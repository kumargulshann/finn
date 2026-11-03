# Covering email

**To:** assessment@enam.com
**Subject:** ENAM - IIT screening - 2027

---

Hello ENAM team,

Here is my submission for the FINN build challenge.

- **Try it on your phone:** https://finn-c0t0.onrender.com (the free host sleeps when idle, so the first load can take up to a minute)
- **Offline demo:** `demo/finn-demo.html` in the repo. It's one HTML file with a real data snapshot, for when the free server is asleep.
- **Repository:** https://github.com/kumargulshann/finn
- **AI build history:** https://github.com/kumargulshann/finn/tree/main/build-history. This holds six sessions across Antigravity, Codex and Claude Code, including the attempts I threw away.

## What I built

FINN is a mobile-first web app with two tabs that match the two modes.

**Today (Push).** The app watches an 18-stock portfolio across 13 sectors, from Reliance down to Kaynes, using live NSE filings and end-of-day prices. For the window you choose (24h, 7d or 30d) it shows only what is material. Items are ranked by event type, how big the surprise is, portfolio weight and recency. Routine filings (call notices, dividends, newspaper ads) are counted and collapsed, and NSE/BSE duplicates merge.
- **Results:** FINN opens the results PDF and gives the first cut you asked for: Revenue, EBITDA, PBT and PAT against last quarter and the same quarter last year, with the page it was read from.
- **Management changes:** it pulls the person's profile as disclosed in the filing, again with the page.
- **Triggers:** you set them in Settings (volume ≥ N× its 20-day average, or a daily move ≥ X%). Each triggered alert says whether the company filed anything that session, so you see at once whether the move has a disclosed catalyst.

**Research (Pull).** Pick any NSE ticker, not just the demo set. FINN fetches the company's annual reports and concall transcripts from NSE, indexes them page by page, and answers through six lenses. Every claim cites a page (`…pdf#page=27`), and each answer states whether the evidence is sufficient. **Guidance vs Actual** is the worked example from the brief: four quarters of what management guided against what they reported, with a source for each figure. Try Infosys.

## Key decisions and trade-offs

1. **Extractive, not generative, on the Pull side.** The brief's one hard rule is "ground it in primary sources". My first attempt used an LLM and produced plausible filings and bios that did not exist (see build history, session 1). So answers are assembled from retrieved passages (BM25 over page chunks, plus rule-based metric and guidance extraction), and every sentence traces to a page.
   - **Cost:** zero model spend at runtime.
   - **Trade-off:** answers read like evidence briefs, not fluent analyst prose, and cross-document synthesis is shallow.
2. **"Unavailable" beats a fake number.** The portfolio is defined by weights, not share counts, so rupee P&L shows as *Unavailable* rather than an invented figure. Scanned PDFs are flagged as unreadable, and a company with no indexed filings returns *Insufficient evidence* instead of an answer.
3. **Deterministic prioritisation.** A scored rank with stated reasons is something an analyst can audit and tune; a model's opinion of "important" is not.
4. **A results table I can defend.** Each column is matched to its period by the header date (companies order the columns differently), then checked against an accounting identity: revenue + other income = total income. In live data this caught a misread that would have shown L&T at −46% YoY instead of the real +15.8%. Where a filing can't be verified (banks, a few unusual layouts), the card says so and links to the filing. That covered 8 of 13 non-bank results in the last month.
5. **Responsive web, one container.** A link you open on a phone beats a TestFlight invite. Next.js and FastAPI ship as one Docker image with a pre-indexed SQLite snapshot, so the demo works even when NSE rate-limits cloud IPs.

## What I left out, and the gaps I know about

- **No LLM in the loop yet.** There is an `integrations/llm` slot, but it is not wired up, so there is no chat-style prose.
- **Profiles only come from the filing.** When a disclosure has no profile, FINN names the person and offers a LinkedIn search link. I didn't scrape LinkedIn (it breaks their terms); a licensed people-data API is the production answer.
- **Results parsing covers the standard table only.** Banks and NBFCs and some layouts fall back to "see filing".
- **Push is in-app.** Triggers recompute on end-of-day data when Today loads, and filings refresh every 4 hours on the server. There are no phone notifications yet.
- **BSE's public feed returns 403s to scripts, and there is no OCR for scanned reports.**

## Where I would take it next

1. **Model routing for Pull.** A cheap Flash-class model extracts metrics and guidance per page, cached by document hash. A strong model writes only the final narrative-vs-numbers answer, constrained to the cited chunks so grounding survives.
2. **Notifications.** A web-push or WhatsApp digest of the top three items after market close, built on the same ranking.
3. **A management credibility score.** Track guided-versus-delivered over many quarters, so the Guidance vs Actual table becomes a running signal.
4. **Retrieval quality.** Hybrid BM25 plus embeddings, OCR for scanned PDFs, and a contracted exchange feed.

Thanks for the thoughtful brief. I enjoyed it.

Gulshan Kumar
