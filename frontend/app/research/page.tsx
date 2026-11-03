"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Icon } from "@/components/icons";
import { Badge, CompanyMark, EmptyState, PageHeading, Panel, SectionTitle } from "@/components/ui";
import { askResearch, getCompany, getCompanyPrices, getDigest, getResearchDocuments, refreshResearchDocuments, searchCompanies, getGuidanceActual, type GuidanceActual, type ApiAlert, type CompanyInfo, type CompanySearchResult, type PriceHistory, type ResearchAnswer, type ResearchDocument } from "@/lib/api";

const lenses = ["business overview", "financial performance", "balance sheet", "cash flow", "management guidance", "guidance vs actual", "bull vs bear analysis"];

export default function ResearchPage() {
  const [companies, setCompanies] = useState<CompanySearchResult[]>([]);
  const [searchResults, setSearchResults] = useState<CompanySearchResult[]>([]);
  const [company, setCompany] = useState<CompanySearchResult | null>(null);
  const [info, setInfo] = useState<CompanyInfo | null>(null);
  const [priceHistory, setPriceHistory] = useState<PriceHistory | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [events, setEvents] = useState<ApiAlert[]>([]);
  const [documents, setDocuments] = useState<ResearchDocument[]>([]);
  const [documentsLoading, setDocumentsLoading] = useState(true);
  const [documentsError, setDocumentsError] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [refreshLimit, setRefreshLimit] = useState(5);
  const [refreshMessage, setRefreshMessage] = useState("");
  const [search, setSearch] = useState("");
  const [lens, setLens] = useState(lenses[1]);
  const [question, setQuestion] = useState("What did management report about financial performance, and what should I monitor next?");
  const [researchResult, setResearchResult] = useState<ResearchAnswer | null>(null);
  const [guidanceResult, setGuidanceResult] = useState<GuidanceActual | null>(null);
  const [researchLoading, setResearchLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    Promise.all([searchCompanies(""), getDigest("30 days")]).then(([result, digest]) => {
      if (!active) return;
      setCompanies(result.items);
      const wanted = (new URLSearchParams(window.location.search).get("symbol") ?? "INFY").toUpperCase();
      setEvents(digest.items.filter((item) => !item.routine));
      const match = result.items.find((item) => item.symbol === wanted);
      if (match) setCompany(match);
      else searchCompanies(wanted).then((found) => { if (active) setCompany(found.items.find((item) => item.symbol === wanted) ?? found.items[0] ?? result.items[0] ?? null); }).catch(() => { if (active) setCompany(result.items[0] ?? null); });
    }).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Could not load research data."))
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);
  useEffect(() => {
    const query = search.trim();
    if (!query) return;
    let active = true;
    const timer = window.setTimeout(() => {
      searchCompanies(query).then((result) => { if (active) setSearchResults(result.items); })
        .catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : "Company search failed."); });
    }, 180);
    return () => { active = false; window.clearTimeout(timer); };
  }, [search]);
  useEffect(() => {
    let active = true;
    if (!company) return;
    getCompany(company.id).then((result) => { if (active) setInfo(result); })
      .catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : "Could not load company details."); });
    return () => { active = false; };
  }, [company]);
  useEffect(() => {
    let active = true;
    if (!company) return;
    getResearchDocuments(company.id).then((result) => { if (active) { setDocuments(result.items); setDocumentsError(""); } })
      .catch((reason: unknown) => { if (active) setDocumentsError(reason instanceof Error ? reason.message : "Could not load company documents."); })
      .finally(() => { if (active) setDocumentsLoading(false); });
    return () => { active = false; };
  }, [company]);
  async function loadPriceHistory() {
    if (!company) return;
    setHistoryLoading(true);
    try { setPriceHistory(await getCompanyPrices(company.id, "1mo")); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Could not load daily price history."); }
    finally { setHistoryLoading(false); }
  }
  async function refreshLibrary() {
    setRefreshing(true); setRefreshMessage(""); setDocumentsError("");
    try {
      const result = await refreshResearchDocuments(refreshLimit);
      setRefreshMessage(`Indexed ${result.indexed} new documents across ${result.companies.length} companies; ${result.unchanged} already current.`);
      if (result.errors.length) setDocumentsError(result.errors.slice(0, 3).join(" · "));
      if (company) setDocuments((await getResearchDocuments(company.id)).items);
    } catch (reason) { setDocumentsError(reason instanceof Error ? reason.message : "Document refresh failed."); }
    finally { setRefreshing(false); }
  }
  async function runResearch() {
    if (!company) return;
    setResearchLoading(true); setResearchResult(null); setGuidanceResult(null); setError("");
    try {
      if (lens === "guidance vs actual") setGuidanceResult(await getGuidanceActual(company.id));
      else setResearchResult(await askResearch(company.id, question, lens));
    }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Research request failed."); }
    finally { setResearchLoading(false); }
  }
  const matches = useMemo(() => {
    const q = search.trim().toLowerCase();
    return q ? searchResults : [];
  }, [search, searchResults]);
  return <div>
    <PageHeading eyebrow="On-demand company intelligence" title="Research workspace" description="Search annual reports and earnings-call transcripts. Answers link to source documents and page numbers." action={<div className="flex flex-wrap items-center gap-2"><select aria-label="Companies to refresh" className="h-9 rounded-lg border border-white/[0.09] bg-[#0d1117] px-2 text-[9px] text-[#bdc5ce]" onChange={(event) => setRefreshLimit(Number(event.target.value))} value={refreshLimit}><option value={5}>5 companies</option><option value={10}>10 companies</option></select><button className="inline-flex h-9 items-center gap-2 rounded-lg border border-[#355848]/40 bg-[#15271f] px-3 text-[9px] font-semibold text-[#8fd3b7] disabled:opacity-50" disabled={refreshing} onClick={() => void refreshLibrary()} type="button"><Icon name="file" size={13} />{refreshing ? "Fetching documents…" : "Refresh source library"}</button></div>} />
    {refreshMessage && <p role="status" className="mb-3 rounded-lg border border-[#315744]/50 bg-[#15271f] p-3 text-[10px] text-[#9bd6b8]">{refreshMessage}</p>}
    {error && <p role="alert" className="mb-4 rounded-lg border border-[#673d3d] bg-[#2b191a] p-3 text-[10px] text-[#f1aaaa]">{error}</p>}
    <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-5 xl:grid-cols-[minmax(0,1.5fr)_minmax(280px,0.7fr)]">
      <div className="space-y-5">
        <Panel className="p-4 sm:p-5">
          <label className="mb-2 block text-[10px] font-medium text-[#89939f]" htmlFor="company-search">Company or ticker</label>
          <div className="relative flex h-11 items-center gap-2.5 rounded-lg border border-white/[0.09] bg-[#0d1117] px-3"><Icon className="text-[#737f8c]" name="search" size={16} /><input id="company-search" className="min-w-0 flex-1 bg-transparent text-[11px] text-[#e2e6eb] outline-none" placeholder="Search NSE companies" value={search} onChange={(e) => setSearch(e.target.value)} /></div>
          {search && <div className="mt-2 overflow-hidden rounded-xl border border-white/[0.1] bg-[#171d25]">{matches.length ? matches.map((item) => <button key={item.id} onClick={() => { setCompany(item); setInfo(null); setPriceHistory(null); setSearch(""); setResearchResult(null); }} className="flex w-full items-center gap-3 px-3 py-2.5 text-left hover:bg-white/[0.05]"><CompanyMark initials={item.name[0]} color="#5e9f87" size="sm" /><span className="flex-1"><span className="block text-[11px] text-[#e0e5eb]">{item.name}</span><span className="text-[9px] text-[#76818e]">{item.symbol} · {item.sector}</span></span><span className="text-[9px] text-[#76818e]">{item.in_portfolio ? "Portfolio" : "Ad hoc"}</span></button>) : <p className="p-4 text-center text-[10px] text-[#87919d]">{loading ? "Loading companies…" : "No matching NSE companies found. Search by company name or ticker (e.g. SBIN, SUNPHARMA, HINDUNILVR)."}</p>}</div>}
          {company && <div className="mt-4 flex items-center gap-3"><CompanyMark initials={company.name[0]} color="#5e9f87" /><div><p className="text-[12px] font-semibold text-[#e2e6eb]">{company.name}</p><p className="text-[9px] text-[#76818e]">{company.symbol} · {company.sector} · {company.in_portfolio ? "In portfolio" : "Ad hoc research"}</p></div></div>}
        </Panel>
        {company && <Panel className="p-4 sm:p-5">
          <div className="flex items-center justify-between gap-3"><SectionTitle title="Indexed source documents" detail={company.symbol} /><Badge>{`${documents.length} indexed`}</Badge></div>
          {documentsLoading && <p className="text-[10px] text-[#87919d]">Loading company documents…</p>}
          {documentsError && <p role="alert" className="mb-2 rounded-lg border border-[#673d3d] bg-[#2b191a] p-2.5 text-[9px] text-[#f1aaaa]">{documentsError}</p>}
          {!documentsLoading && documents.length === 0 && <p className="text-[10px] leading-5 text-[#87919d]">No documents indexed for this company yet. Refresh the source library to fetch its latest annual report and earnings-call transcript.</p>}
          <div className="space-y-1">{documents.map((doc) => <a className="flex items-center gap-3 rounded-lg px-2 py-2.5 hover:bg-white/[0.04]" href={doc.source_url} key={doc.id} rel="noreferrer" target="_blank"><Icon className="text-[#8fd3b7]" name="file" size={15} /><span className="min-w-0 flex-1"><span className="block truncate text-[10px] text-[#d2d9e0]">{doc.title}</span><span className="text-[9px] text-[#74808c]">{doc.page_count} pages · {doc.fiscal_period ?? doc.document_type} · {doc.source_name}</span></span><Icon className="text-[#74808c]" name="external" size={13} /></a>)}</div>
        </Panel>}
        {company && <Panel className="p-4 sm:p-5">
          <SectionTitle title="Latest daily market data" detail={info?.market_data?.source ?? "Yahoo Finance"} />
          {info?.market_data?.close !== null && info?.market_data?.close !== undefined ? <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div><p className="text-[9px] text-[#77818e]">Latest close</p><p className="mt-1 text-[13px] font-semibold text-[#e0e5eb]">INR {info.market_data.close.toLocaleString("en-IN", { maximumFractionDigits: 2 })}</p></div>
            <div><p className="text-[9px] text-[#77818e]">Daily move</p><p className="mt-1 text-[13px] font-semibold text-[#e0e5eb]">{info.market_data.change_percent === null ? "Unavailable" : (info.market_data.change_percent >= 0 ? "+" : "−") + info.market_data.change_percent.toFixed(2) + "%"}</p></div>
            <div><p className="text-[9px] text-[#77818e]">Volume</p><p className="mt-1 text-[13px] font-semibold text-[#e0e5eb]">{info.market_data.volume?.toLocaleString("en-IN") ?? "Unavailable"}</p></div>
            <div><p className="text-[9px] text-[#77818e]">Market timestamp</p><p className="mt-1 text-[10px] text-[#c1c9d2]">{info.market_data.market_as_of ? new Date(info.market_data.market_as_of).toLocaleString() : "Unavailable"}</p></div>
          </div> : <p className="text-[10px] leading-5 text-[#89939f]">{info?.market_data?.error ?? (info ? "Quote unavailable for this ticker." : "Loading latest quote…")}</p>}
          {info?.market_data?.status === "stale" && <p className="mt-3 text-[9px] text-[#d0b36f]">Showing a cached quote; refresh failed. {info.market_data.error}</p>}
          <p className="mt-3 text-[9px] text-[#68737f]">Daily EOD data, retrieved {info?.market_data?.fetched_at ? new Date(info.market_data.fetched_at).toLocaleString() : "—"} · Not a real-time quote.</p>
        </Panel>}
        {company && <Panel className="p-4 sm:p-5">
          <div className="flex items-center justify-between gap-3"><SectionTitle title="Historical EOD prices" detail="Last month · OHLCV" /><button className="rounded-lg border border-white/[0.09] px-3 py-2 text-[9px] text-[#9aa4af] hover:bg-white/[0.04]" onClick={() => void loadPriceHistory()} disabled={historyLoading}>{historyLoading ? "Loading…" : priceHistory ? "Refresh" : "Load history"}</button></div>
          {priceHistory && <><p className="mb-2 text-[9px] text-[#6f7a87]">{priceHistory.source} · latest available {priceHistory.market_as_of ? new Date(priceHistory.market_as_of).toLocaleDateString() : "unavailable"}{priceHistory.status === "stale" ? " · cached / stale" : ""}</p>{priceHistory.items.slice(-5).reverse().map((bar) => <div className="grid grid-cols-4 gap-2 border-t border-white/[0.05] py-2 text-[9px] text-[#9ca6b1]" key={bar.date}><span>{bar.date}</span><span>Close {bar.close.toLocaleString("en-IN", { maximumFractionDigits: 2 })}</span><span>Vol {bar.volume?.toLocaleString("en-IN") ?? "—"}</span><span>Range {bar.low?.toFixed(2) ?? "—"}–{bar.high?.toFixed(2) ?? "—"}</span></div>)}{!priceHistory.items.length && <p className="text-[10px] text-[#89939f]">{priceHistory.error ?? "Daily history unavailable for this ticker."}</p>}</>}
        </Panel>}
        <Panel className="overflow-hidden">
          <div className="border-b border-white/[0.06] p-4 sm:p-5"><SectionTitle title="Choose a research lens" detail="Change at any time" /><div className="flex gap-2 overflow-x-auto">{lenses.map((item) => <button key={item} onClick={() => { setLens(item); setResearchResult(null); setGuidanceResult(null); }} className={"shrink-0 rounded-lg border px-3 py-2 text-[10px] capitalize " + (lens === item ? "border-[#4a7c67]/50 bg-[#1a3028] text-[#9ce0c2]" : "border-white/[0.07] text-[#89939e]")}>{item}</button>)}</div></div>
          <div className="p-4 sm:p-5">{lens === "guidance vs actual" ? <div className="mb-3 rounded-lg border border-white/[0.06] bg-white/[0.02] p-3 text-[10px] leading-5 text-[#9da8b3]">Compares explicit quarter-matched disclosures from indexed documents. Refresh up to four transcripts for {company?.symbol} <button className="ml-2 text-[#8fd3b7] underline disabled:opacity-50" disabled={refreshing || !company} onClick={() => void (async () => { if (!company) return; setRefreshing(true); setDocumentsError(""); try { const result = await refreshResearchDocuments(1, company.symbol, 4); setRefreshMessage(`Indexed ${result.indexed} new quarterly documents for ${company.symbol}; ${result.unchanged} already current.`); if (result.errors.length) setDocumentsError(result.errors.join(" · ")); setDocuments((await getResearchDocuments(company.id)).items); } catch (reason) { setDocumentsError(reason instanceof Error ? reason.message : "Quarterly refresh failed."); } finally { setRefreshing(false); } })()}>{refreshing ? "Fetching…" : "Fetch four quarters"}</button></div> : <><label htmlFor="research-question" className="mb-2 block text-[10px] text-[#89939f]">Your question</label><textarea id="research-question" className="min-h-[100px] w-full rounded-xl border border-white/[0.08] bg-[#0d1117] p-3.5 text-[11px] leading-6 text-[#d5dbe2]" value={question} onChange={(e) => setQuestion(e.target.value)} /></>}<div className="mt-3 flex items-center justify-between gap-3"><span className="text-[9px] text-[#717c88]">Figures cite indexed company documents; missing evidence is surfaced.</span><button className="min-h-10 rounded-lg bg-[#c8f0dd] px-4 text-[10px] font-semibold text-[#10231c] disabled:opacity-50" disabled={!company || (lens !== "guidance vs actual" && !question.trim()) || researchLoading} onClick={() => void runResearch()}><Icon name="spark" size={14} /> {researchLoading ? "Searching…" : lens === "guidance vs actual" ? "Compare four quarters" : "Run research"}</button></div></div>
        </Panel>
        {researchResult && <Panel className="p-4 sm:p-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <SectionTitle title="FINN research response" detail={researchResult.lens} />
            <div className="flex items-center gap-2">
              {researchResult.evidence_sufficiency && (
                <span className={"inline-flex items-center rounded-md border px-2 py-0.5 text-[9px] font-medium " + (
                  researchResult.evidence_sufficiency.status === "sufficient"
                    ? "border-[#355848]/50 bg-[#15271f] text-[#8fd3b7]"
                    : researchResult.evidence_sufficiency.status === "partial"
                    ? "border-[#655532]/50 bg-[#292419] text-[#d0b36f]"
                    : "border-[#673d3d]/60 bg-[#2b191a] text-[#f1aaaa]"
                )}>
                  {researchResult.evidence_sufficiency.status.toUpperCase()} EVIDENCE
                </span>
              )}
              <Badge>Source-backed</Badge>
            </div>
          </div>
          <div className="mb-4 whitespace-pre-line text-[11px] leading-6 text-[#c1c9d2]">{researchResult.answer}</div>
          {researchResult.conflicting_info && !researchResult.conflicting_info.toLowerCase().startsWith("no conflicting") && (
            <div className="mb-4 rounded-xl border border-[#d6b981]/30 bg-[#292419]/60 p-3.5 text-[10px] leading-5 text-[#d6b981]">
              <div className="mb-1 flex items-center gap-1.5 font-semibold uppercase tracking-wider text-[#e6cb95]">
                <Icon name="info" size={13} />
                <span>Discrepancy / Trajectory Shift Detected</span>
              </div>
              <p className="text-[#d8cfbe]">{researchResult.conflicting_info}</p>
            </div>
          )}
          {researchResult.evidence_gap && <p role="status" className="mb-4 rounded-lg border border-[#655532]/40 bg-[#292419]/55 p-3 text-[10px] leading-5 text-[#d0b36f]">Evidence gap: {researchResult.evidence_gap}</p>}
          {[["Financial metrics", researchResult.financial_metrics], ["Management guidance", researchResult.management_guidance], ["Business updates", researchResult.business_updates]].map(([heading, values]) => <section className="mb-4" key={heading as string}>{(values as string[]).length > 0 && <><h3 className="mb-1 text-[9px] font-semibold uppercase tracking-[0.12em] text-[#8fa99b]">{heading as string} · extracted source text</h3>{(values as string[]).slice(0, 5).map((value) => <p className="border-t border-white/[0.05] py-2 text-[10px] leading-5 text-[#b8c1cb]" key={value}>{value}</p>)}</>}</section>)}
          {lens === "bull vs bear analysis" && <div className="mb-4 grid gap-3 sm:grid-cols-2"><div><h3 className="mb-2 text-[9px] font-semibold uppercase text-[#8fd3b7]">Potentially supportive disclosures</h3>{researchResult.bull_evidence.map((item, index) => <p className="mb-2 rounded-lg border border-white/[0.06] p-2.5 text-[9px] leading-5 text-[#b8c1cb]" key={index}>{item.excerpt}<a className="mt-1 block text-[#8fd3b7]" href={item.source_url} rel="noreferrer" target="_blank">{item.document_title} · p. {item.page}</a></p>)}{!researchResult.bull_evidence.length && <p className="text-[9px] text-[#77818e]">No supportive passage found in the retrieved evidence.</p>}</div><div><h3 className="mb-2 text-[9px] font-semibold uppercase text-[#d6b981]">Risks or counterpoints disclosed</h3>{researchResult.bear_evidence.map((item, index) => <p className="mb-2 rounded-lg border border-white/[0.06] p-2.5 text-[9px] leading-5 text-[#b8c1cb]" key={index}>{item.excerpt}<a className="mt-1 block text-[#8fd3b7]" href={item.source_url} rel="noreferrer" target="_blank">{item.document_title} · p. {item.page}</a></p>)}{!researchResult.bear_evidence.length && <p className="text-[9px] text-[#77818e]">No risk or counterpoint passage found in the retrieved evidence.</p>}</div></div>}
          <h3 className="mb-2 text-[9px] font-semibold uppercase tracking-[0.12em] text-[#8fa99b]">Cited passages</h3>
          {researchResult.citations.length ? researchResult.citations.map((citation, index) => <blockquote className="mb-3 rounded-xl border border-white/[0.06] bg-white/[0.015] p-3" key={`${citation.document_id}-${citation.page}-${index}`}><p className="text-[10px] leading-5 text-[#c3cbd4]">{citation.excerpt}</p><a className="mt-2 inline-flex items-center gap-1 text-[9px] font-medium text-[#8fd3b7]" href={citation.source_url} rel="noreferrer" target="_blank">{citation.document_title} · page {citation.page} <Icon name="external" size={11} /></a></blockquote>) : <EmptyState icon="file" title="No supporting passage" description="No matching passage was found in the currently indexed documents. No answer was inferred." />}
        </Panel>}
        {guidanceResult && <Panel className="p-4 sm:p-5"><SectionTitle title="Guidance vs Actual" detail="Source-backed quarter comparison" />{guidanceResult.evidence_gap && <p role="status" className="my-3 rounded-lg border border-[#655532]/40 bg-[#292419]/55 p-3 text-[10px] leading-5 text-[#d0b36f]">Evidence gap: {guidanceResult.evidence_gap}</p>}{guidanceResult.quarters.map((quarter) => <section className="mb-5" key={quarter.period}><h3 className="mb-2 text-[11px] font-semibold text-[#d2dae2]">{quarter.period}</h3><div className="overflow-x-auto"><table className="w-full min-w-[640px] text-left text-[9px]"><thead className="text-[#77838f]"><tr>{["Metric", "Guided", "Actual", "Variance", "Assessment"].map((heading) => <th className="px-2 py-2" key={heading}>{heading}</th>)}</tr></thead><tbody>{quarter.metrics.map((item) => <tr className="border-t border-white/[0.06]" key={item.metric}><td className="px-2 py-2 text-[#c8d0d9]">{item.metric}</td>{([[item.guided_value, item.guided_source], [item.actual_value, item.actual_source]] as const).map(([value, source], index) => <td className="px-2 py-2 text-[#aeb8c3]" key={index}>{value === null ? "Unavailable" : <>{value} {item.unit}{source && <a className="ml-1 block text-[#8fd3b7]" href={source.source_url} rel="noreferrer" target="_blank">{source.document_title} · p. {source.page}</a>}</>}</td>)}<td className="px-2 py-2 text-[#aeb8c3]">{item.variance === null ? "Unavailable" : `${item.variance} ${item.unit}`}</td><td className="px-2 py-2 text-[#c0c8d1]">{item.met_guidance}</td></tr>)}</tbody></table></div></section>)}{!guidanceResult.quarters.length && <EmptyState icon="file" title="No comparable quarter data" description="Fetch quarterly transcripts or index source documents. FINN will not estimate missing values." />}</Panel>}
        {!researchResult && !guidanceResult && <Panel><EmptyState icon="spark" title={researchLoading ? "Searching indexed documents" : "Research, with citations"} description={researchLoading ? "Retrieving source evidence from the selected company's reports and transcripts…" : "Choose a company and lens, then run research to retrieve evidence with source links and page references."} /></Panel>}
      </div>
      <aside className="space-y-5">
        <Panel className="p-4 sm:p-5"><SectionTitle title="Recent events" detail={company?.symbol}/>{events.filter((event) => event.symbol === company?.symbol).length ? events.filter((event) => event.symbol === company?.symbol).slice(0, 5).map((event) => <Link key={event.id} href={"/events/" + event.id} className="flex items-start gap-2.5 rounded-lg px-1.5 py-2.5 hover:bg-white/[0.035]"><CompanyMark initials={event.initials} color={event.color} size="sm"/><span className="min-w-0 flex-1"><span className="block text-[10px] text-[#c7ced6]">{event.title}</span><span className="text-[9px] text-[#6e7985]">{event.type} · {event.time}</span></span></Link>) : <p className="text-[10px] text-[#87919d]">{loading ? "Loading events…" : "No material events in the last 30 days."}</p>}</Panel>
        <Panel className="p-4 sm:p-5"><SectionTitle title="Companies to explore" detail="Outside your portfolio"/>{companies.filter((item) => !item.in_portfolio).map((item) => <button key={item.id} onClick={() => { setCompany(item); setInfo(null); setPriceHistory(null); setResearchResult(null); }} className="flex w-full items-center gap-3 rounded-lg px-1.5 py-2 text-left hover:bg-white/[0.04]"><CompanyMark initials={item.name[0]} color="#5e9f87" size="sm"/><span><span className="block text-[10px] text-[#cad0d7]">{item.name}</span><span className="text-[9px] text-[#737e89]">{item.symbol} · {item.sector}</span></span></button>)}</Panel>
        <Panel className="border-[#294739]/40 bg-[#17251f] p-4 sm:p-5"><p className="text-[10px] font-semibold text-[#c6e2d5]">Source-first by design</p><p className="mt-2 text-[9px] leading-5 text-[#899b91]">Missing evidence is called out rather than filled in.</p></Panel>
      </aside>
    </div>
  </div>;
}
