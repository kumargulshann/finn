# AI build history

FINN was built across three AI coding tools over three days. Every session is exported here, including the attempts that did not ship. This index tells the story; the linked files hold the full transcripts.

| # | Date (IST) | Tool / model | What happened | Transcript |
|---|---|---|---|---|
| 1 | 1 Nov, 18:51–19:30 | Antigravity · Gemini 3.8 Flash | First attempt in `E:\Enam`. Asked for a "robust, submission-ready" build in one shot. It produced a broad app quickly, but the filing links were fabricated: every "View exchange filing" button pointed at the same made-up PDF. | [01](01-antigravity-first-attempt.md) |
| 2 | 1–2 Nov | Codex · gpt-6-luna | Fresh start in `E:\EnamCodex`. Codex audited attempt 1 and flagged that seeded filings, executive bios and research figures were presented as real primary-source data. I told it to discard that folder and build cleanly. | [02](02-codex-clean-restart.md) |
| 3 | 3 Nov, 11:45 | Antigravity | Re-planning prompt for the final build. It hit a quota error and returned nothing, so I moved the same prompt to Codex two minutes later. | [03](03-antigravity-brief-analysis.md) |
| 4 | 3 Nov, 11:47–16:09 | Codex · gpt-6-luna | **Main build of this repo.** Planning docs first (requirements, product plan, architecture; no code until those were agreed), then one vertical slice per prompt: scaffold + health check → mobile UI → core API → yfinance market data → NSE announcements pipeline → document retrieval with citations → Guidance vs Actual. | [04](04-codex-main-build.md) |
| 5 | 3 Nov, 16:22–23:45 | Antigravity · Gemini 3.8 Flash (+ Claude Opus 4.6 for harder turns) | I switched tools and opened with a written handover document. This session was review-and-harden, with "don't add new features" in nearly every prompt: fiscal-period extraction on real transcripts, metric/unit/period matching accuracy, grounded answers with conflict detection, PUSH prioritisation and thresholds, coverage outside the demo set, end-to-end testing, README. | [05](05-antigravity-hardening.md) |
| 6 | 4 Nov | Claude Code · Opus 5.5 | Packaging (single-container Docker deploy, seed snapshot, this history export, writeup), then closing the gaps the writeup admitted: an 18-stock portfolio, real EOD triggers (volume ×, daily %), a results-PDF parser giving QoQ/YoY with accounting cross-checks (it caught a misread L&T column), executive profiles extracted from filings, classification on the reference taxonomy, removal of all sample events, and fixes to mobile overflow verified with emulated-phone screenshots. | [06](06-claude-code-packaging.md) |

## How I worked with the tools

- **Plan before code.** Session 4 opens with three planning documents and an explicit "don't start coding yet". The architecture was fixed before the first file was written.
- **One vertical slice per prompt,** each ending with "test before proceeding". Each prompt names the data source, the failure behaviour ("show unavailable, not fake values") and the boundary ("keep demo data clearly labelled").
- **Treat fabrication as the main risk.** Attempt 1 failed because the model invented filings and bios, so every later prompt carries a "never invent / clearly mark evidence gaps" constraint. That is also why the research engine is extractive rather than generative.
- **Switch tools when blocked, and carry context deliberately.** When I changed tools I handed over with a written context document (top of session 5) rather than starting cold.
- **Review passes are scoped.** The hardening prompts say "Don't add new features" or "Keep the existing UI and architecture". They target accuracy, not scope.

## About these exports

They are converted from each tool's local session store (Codex `.jsonl`, Antigravity's SQLite step log, Claude Code `.jsonl`) by a small script, with these changes:

- Tool calls are collapsed into `<details>` blocks; long tool outputs are truncated.
- Encrypted reasoning blobs, account and session metadata, and injected system prompts are omitted.
- Email addresses and anything shaped like a credential are redacted.

Nothing else is edited. User prompts and assistant messages appear verbatim and in order.
