"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { AlertCard } from "@/components/alert-card";
import { Icon } from "@/components/icons";
import { Change, CompanyMark, EmptyState, PageHeading, Panel, SectionTitle, SmallButton } from "@/components/ui";
import { getDigest, getPortfolio, toAlert, toHolding, updateAlert, type ApiAlert, type PortfolioResponse } from "@/lib/api";

type AlertFilter = "All updates" | "Results" | "Order wins" | "Acquisitions" | "Management changes" | "Fundraising" | "Regulatory updates" | "Corporate actions" | "Earnings" | "Corporate action" | "Price move";

const filters: AlertFilter[] = ["All updates", "Results", "Order wins", "Acquisitions", "Management changes", "Fundraising", "Regulatory updates", "Corporate actions", "Earnings", "Corporate action", "Price move"];

export default function TodayPage() {
  const [filter, setFilter] = useState<AlertFilter>("All updates");
  const [period, setPeriod] = useState("24 hours");
  const [showAllHoldings, setShowAllHoldings] = useState(false);
  const [portfolio, setPortfolio] = useState<PortfolioResponse | null>(null);
  const [digest, setDigest] = useState<ApiAlert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");
  const liveHoldings = useMemo(() => portfolio?.holdings ?? [], [portfolio]);
  const holdings = useMemo(() => liveHoldings.map(toHolding), [liveHoldings]);
  const portfolioValue = portfolio?.summary?.portfolio_value == null ? "Unavailable" : "INR " + (portfolio.summary.portfolio_value / 10000000).toFixed(2) + " Cr";
  const dailyPnl = portfolio?.summary?.daily_change_value == null ? "Unavailable" : "INR " + portfolio.summary.daily_change_value.toLocaleString("en-IN");
  const periodAlerts = digest;
  useEffect(() => {
    let alive = true;
    Promise.all([getPortfolio(), getDigest(period)]).then(([p, d]) => { if (alive) { setPortfolio(p); setDigest(d.items); } }).catch((reason: unknown) => { if (alive) setError(reason instanceof Error ? reason.message : "Could not load Today data."); }).finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [period]);
  const visibleAlerts = useMemo(
    () => (filter === "All updates" ? periodAlerts : periodAlerts.filter((alert) => alert.type === filter)),
    [filter, periodAlerts],
  );

  async function toggleSaved(id: string, saved: boolean) {
    try { await updateAlert(id, { is_saved: !saved }); setDigest((items) => items.map((item) => item.id === id ? { ...item, is_saved: !saved } : item)); setActionError(""); }
    catch (reason) { setActionError(reason instanceof Error ? reason.message : "Could not save alert."); }
  }

  return (
    <div>
      <PageHeading
        eyebrow="Tuesday, November 3, 2026"
        title="Good morning, Sam"
        description="Here's what's moving across your portfolio today."
        action={<div className="flex items-center gap-2"><span className="hidden items-center gap-2 rounded-lg border border-white/[0.08] bg-[#11161d] px-3 py-2 text-[10px] text-[#98a1ad] sm:flex"><span className="size-1.5 rounded-full bg-[#e1b163]" />DEMO DATA</span><SmallButton icon="calendar" onClick={() => { setLoading(true); setPeriod(period === "24 hours" ? "7 days" : "24 hours"); }}>{period}</SmallButton></div>}
      />

      <div className="mb-5 grid grid-cols-2 gap-3 xl:grid-cols-4">
        <Panel className="relative overflow-hidden p-4 sm:p-5">
          <div className="flex items-center justify-between"><p className="text-[10px] font-medium text-[#8a94a0]">Portfolio value</p><Icon className="text-[#66727e]" name="wallet" size={16} /></div>
          <div className="mt-3 flex items-end justify-between gap-2"><p className="text-[22px] font-semibold tracking-[-0.04em] text-[#f0f3f5] sm:text-[26px]">{portfolioValue}</p></div>
          <div className="mt-2 text-[10px] text-[#707a86]">No share quantities configured</div>
        </Panel>
        <Panel className="p-4 sm:p-5">
          <div className="flex items-center justify-between"><p className="text-[10px] font-medium text-[#8a94a0]">Today&apos;s P&amp;L</p><Icon className="text-[#66727e]" name="trend" size={16} /></div>
          <p className="mt-3 text-[22px] font-semibold tracking-[-0.04em] text-[#f0f3f5] sm:text-[26px]">{dailyPnl}</p>
          <div className="mt-2 text-[10px] text-[#707a86]">Per-share changes shown below</div>
        </Panel>
        <Panel className="p-4 sm:p-5">
          <div className="flex items-center justify-between"><p className="text-[10px] font-medium text-[#8a94a0]">Companies tracked</p><Icon className="text-[#66727e]" name="briefcase" size={16} /></div>
          <p className="mt-3 text-[22px] font-semibold tracking-[-0.04em] text-[#f0f3f5] sm:text-[26px]">{portfolio?.summary?.companies_tracked ?? "—"}<span className="ml-1.5 text-[13px] font-medium text-[#87919d]">companies</span></p>
          <div className="mt-2 flex items-center gap-2"><span className="text-[10px] text-[#8a94a0]">Across</span><span className="text-[10px] text-[#c2c9d1]">{new Set(holdings.map((holding) => holding.sector)).size} sectors</span></div>
        </Panel>
        <Panel className="p-4 sm:p-5">
          <div className="flex items-center justify-between"><p className="text-[10px] font-medium text-[#8a94a0]">Needs your attention</p><Icon className="text-[#d1a760]" name="bell" size={16} /></div>
          <p className="mt-3 text-[22px] font-semibold tracking-[-0.04em] text-[#f0f3f5] sm:text-[26px]">{loading ? "…" : String(periodAlerts.length).padStart(2, "0")}<span className="ml-1.5 text-[13px] font-medium text-[#87919d]">updates</span></p>
          <div className="mt-2 flex items-center gap-2"><span className="size-1.5 rounded-full bg-[#dcaa5e]" /><span className="text-[10px] text-[#c7a76d]">{periodAlerts.filter((a) => a.impact === "High").length} high impact</span></div>
        </Panel>
      </div>

      <Panel className="mb-6 flex items-center gap-0 overflow-x-auto px-4 py-3 sm:px-5">
        <span className="mr-5 shrink-0 text-[9px] font-semibold uppercase tracking-[0.14em] text-[#67717e]">Market pulse · live NSE holdings</span>
        {liveHoldings.slice(0, 4).map((item) => (
          <div className="min-w-[155px] flex-1 border-l border-white/[0.065] px-4 first:border-0 first:pl-0 sm:min-w-[190px]" key={item.symbol}>
            <p className="text-[9px] font-medium tracking-[0.05em] text-[#7f8996]">{item.symbol}</p>
            <div className="mt-1 flex items-center gap-2"><span className="text-[12px] font-semibold tabular-nums text-[#dfe3e8]">{item.price === null ? "Unavailable" : "INR " + item.price.toLocaleString("en-IN")}</span>{item.change === null ? <span className="text-[10px] text-[#78828e]">Unavailable</span> : <Change positive={item.positive ?? false} value={(item.change >= 0 ? "+" : "−") + Math.abs(item.change).toFixed(2) + "%"} />}</div>
          </div>
        ))}
        <span className="ml-2 hidden shrink-0 text-[9px] text-[#626c77] xl:block">{portfolio?.market_data_source ?? "Yahoo Finance"} · {portfolio?.latest_available_as_of ? new Date(portfolio.latest_available_as_of).toLocaleString() : "No quote timestamp"}{liveHoldings.some((item) => item.market_data?.status === "stale") ? " · Some quotes are stale" : ""}</span>
      </Panel>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.55fr)_minmax(300px,0.85fr)]">
        <Panel className="overflow-hidden">
          <div className="flex flex-wrap items-start justify-between gap-4 px-4 pt-5 sm:px-5">
            <div><p className="text-[11px] text-[#828c98]">Portfolio performance</p><div className="mt-1.5 flex items-baseline gap-2"><p className="text-[22px] font-semibold tracking-[-0.035em] text-[#edf0f3]">{portfolioValue}</p></div><p className="mt-1 text-[10px] text-[#69737f]">Portfolio valuation requires position quantities.</p></div>
          </div>
          <div className="m-4 rounded-lg border border-white/[0.06] bg-black/10 p-4 text-[10px] leading-5 text-[#78838f] sm:m-5">No portfolio value history is available because the demo portfolio contains illustrative weights but no share quantities. Current real daily prices are shown in Market pulse and Top movers.</div>
        </Panel>

        <Panel className="p-4 sm:p-5">
          <SectionTitle title="Top movers" detail="today" action={<SmallButton icon="arrowRight" className="min-h-8 px-2" onClick={() => setShowAllHoldings(true)}>Portfolio</SmallButton>} />
          {error && <p role="alert" className="mb-3 rounded-lg border border-[#673d3d] bg-[#2b191a] p-3 text-[10px] text-[#f1aaaa]">{error}</p>}
          {loading && <p className="py-6 text-center text-[10px] text-[#85909c]">Loading portfolio…</p>}
          {!loading && !error && holdings.length === 0 && <EmptyState icon="briefcase" title="No portfolio holdings" description="Add companies in Settings to build your portfolio." />}
          <div className="space-y-1">
            {holdings.slice(0, showAllHoldings ? holdings.length : 5).map((holding) => (
              <Link className="flex items-center gap-3 rounded-xl px-2 py-2.5 transition hover:bg-white/[0.035]" href="/research" key={holding.id}>
                <CompanyMark color={holding.color} initials={holding.initials} size="sm" />
                <div className="min-w-0 flex-1"><p className="truncate text-[11px] font-medium text-[#d7dce2]">{holding.name}</p><p className="mt-0.5 text-[9px] text-[#727c88]">{holding.symbol} · INR {holding.price}</p></div>
                
                <span className={`w-[68px] text-right text-[10px] font-medium ${holding.change === "Unavailable" ? "text-[#78828e]" : holding.positive ? "text-[#73cdab]" : "text-[#e48a8a]"}`}>{holding.change}</span>
              </Link>
            ))}
          </div>
          <button className="mt-2 w-full border-t border-white/[0.06] pt-3 text-[10px] font-medium text-[#82908d] transition hover:text-[#b5d9ca]" onClick={() => setShowAllHoldings(!showAllHoldings)} type="button">{showAllHoldings ? "Show top movers" : "View all " + holdings.length + " holdings"}</button>
        </Panel>
      </div>

      <section className="mt-8">
        <SectionTitle title="What matters today" detail="Ranked by relevance" action={<Link className="hidden items-center gap-1 text-[10px] font-medium text-[#80cdb0] transition hover:text-[#a4e4ca] sm:flex" href="/research">Open research workspace <Icon name="arrowRight" size={13} /></Link>} />
        <Panel className="overflow-hidden">
          <div className="flex flex-col gap-3 border-b border-white/[0.06] px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-5">
            <div className="flex gap-1 overflow-x-auto">
              {filters.map((item) => <button className={`shrink-0 rounded-md px-2.5 py-1.5 text-[10px] font-medium transition ${filter === item ? "bg-white/[0.09] text-[#e8ebef]" : "text-[#77818d] hover:bg-white/[0.04] hover:text-[#cbd1d8]"}`} key={item} onClick={() => setFilter(item)} type="button">{item}</button>)}
            </div>
            <div className="flex items-center gap-2 text-[9px] text-[#69737f]"><Icon name="clock" size={13} /><span>Showing {period.toLowerCase()}</span><button aria-label="Change time period" className="grid size-7 place-items-center rounded-md border border-white/[0.07] text-[#8a94a0] hover:bg-white/[0.05]" onClick={() => { setLoading(true); setPeriod(period === "24 hours" ? "7 days" : "24 hours"); }} type="button"><Icon name="filter" size={14} /></button></div>
          </div>
          {loading && <p className="py-8 text-center text-[10px] text-[#85909c]">Loading your digest…</p>}
          {error && <p role="alert" className="m-4 rounded-lg border border-[#673d3d] bg-[#2b191a] p-3 text-[10px] text-[#f1aaaa]">{error}</p>}
          {actionError && <p role="alert" className="m-4 rounded-lg border border-[#673d3d] bg-[#2b191a] p-3 text-[10px] text-[#f1aaaa]">{actionError}</p>}
          {!loading && !error && visibleAlerts.length > 0 ? visibleAlerts.map((item) => <AlertCard alert={toAlert(item)} key={item.id} onToggleSave={() => void toggleSaved(item.id, item.is_saved)} saved={item.is_saved} />) : !loading && !error ? <EmptyState icon="bell" title="No updates in this category" description="Try another filter to see the latest portfolio activity." /> : null}
          <div className="border-t border-white/[0.055] px-5 py-3 text-[9px] text-[#646e7a]">Exchange filings are labelled EXCHANGE; illustrative records are labelled SAMPLE. Verify every filing at its linked source.</div>
        </Panel>
      </section>
      <div className="mt-5 flex items-center gap-2 text-[9px] text-[#5f6975]"><Icon name="shield" size={12} />FINN is an information tool. Always verify material information against the original source.</div>
    </div>
  );
}
