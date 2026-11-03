"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { AlertCard } from "@/components/alert-card";
import { Icon } from "@/components/icons";
import { EmptyState, PageHeading, Panel, SectionTitle } from "@/components/ui";
import { getDigest, getPortfolio, toAlert, updateAlert, type ApiAlert, type DigestResponse, type PortfolioResponse } from "@/lib/api";
import { istNow, multiple, pct, rupees } from "@/lib/format";

const PERIODS = ["24 hours", "7 days", "30 days"] as const;
type Period = (typeof PERIODS)[number];
const PERIOD_LABEL: Record<Period, string> = { "24 hours": "24h", "7 days": "7d", "30 days": "30d" };

export default function TodayPage() {
  const [period, setPeriod] = useState<Period>("24 hours");
  const [filter, setFilter] = useState("All");
  const [showRoutine, setShowRoutine] = useState(false);
  const [portfolio, setPortfolio] = useState<PortfolioResponse | null>(null);
  const [digest, setDigest] = useState<DigestResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [{ greeting, date }, setClock] = useState({ greeting: "Hello", date: "" });

  useEffect(() => {
    let alive = true;
    Promise.all([getPortfolio(), getDigest(period)])
      .then(([p, d]) => { if (alive) { setPortfolio(p); setDigest(d); setError(""); setClock(istNow()); } })
      .catch((reason: unknown) => { if (alive) setError(reason instanceof Error ? reason.message : "Could not load Today."); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [period]);

  const items = useMemo(() => digest?.items ?? [], [digest]);
  const material = useMemo(() => items.filter((a) => !a.routine), [items]);
  const routine = useMemo(() => items.filter((a) => a.routine), [items]);
  const categories = useMemo(() => ["All", ...Array.from(new Set(material.map((a) => a.type)))], [material]);
  const visible = filter === "All" ? material : material.filter((a) => a.type === filter);
  const holdings = useMemo(() => portfolio?.holdings ?? [], [portfolio]);
  const monitor = useMemo(() => [...holdings].sort((a, b) => (b.volume_multiple ?? 0) - (a.volume_multiple ?? 0)), [holdings]);
  const triggered = holdings.filter((h) => h.triggered);
  const volT = portfolio?.thresholds?.volume_multiple ?? null;
  const moveT = portfolio?.thresholds?.move_pct ?? null;
  const asOf = portfolio?.latest_available_as_of ? new Date(portfolio.latest_available_as_of).toLocaleDateString("en-IN", { day: "numeric", month: "short" }) : null;

  function choosePeriod(next: Period) { if (next !== period) { setLoading(true); setFilter("All"); setPeriod(next); } }
  async function toggleSaved(alert: ApiAlert) {
    try { await updateAlert(alert.id, { is_saved: !alert.is_saved }); setDigest((d) => d && { ...d, items: d.items.map((i) => (i.id === alert.id ? { ...i, is_saved: !alert.is_saved } : i)) }); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Could not save alert."); }
  }

  const high = material.filter((a) => a.impact === "High").length;
  const summary = loading ? "Reading filings and end-of-day data…"
    : material.length === 0 ? `Nothing material in the last ${period} across ${holdings.length} holdings.`
    : `${material.length} thing${material.length === 1 ? "" : "s"} worth your attention across ${holdings.length} holdings${routine.length ? ` · ${routine.length} routine filings tucked away` : ""}.`;

  return (
    <div>
      <PageHeading
        eyebrow={date || "Today"}
        title={greeting}
        description={summary}
        action={
          <div role="tablist" aria-label="Digest window" className="inline-flex rounded-lg border border-white/[0.09] bg-[#0d1116] p-0.5">
            {PERIODS.map((p) => (
              <button key={p} role="tab" aria-selected={period === p} onClick={() => choosePeriod(p)} type="button"
                className={`min-h-8 rounded-md px-3.5 text-[11px] font-semibold transition ${period === p ? "bg-[#1b3a30] text-[#9fe3c7]" : "text-[#7d8794] hover:text-[#d4dae1]"}`}>{PERIOD_LABEL[p]}</button>
            ))}
          </div>
        }
      />

      {error && <p role="alert" className="mb-4 rounded-lg border border-[#673d3d] bg-[#2b191a] p-3 text-[11px] text-[#f1aaaa]">{error}</p>}

      <div className="mb-5 grid grid-cols-2 gap-3 xl:grid-cols-4">
        <Stat label="Worth your attention" value={loading ? "…" : String(material.length)} note={`${high} high impact`} accent />
        <Stat label="Triggered today" value={loading ? "…" : String(triggered.length)} note={volT || moveT ? `vol ≥ ${volT ?? "–"}× or move ≥ ${moveT ?? "–"}%` : "thresholds off"} />
        <Stat label="Holdings watched" value={String(holdings.length || "—")} note={`${new Set(holdings.map((h) => h.sector)).size} sectors`} />
        <Stat label="Filtered out" value={loading ? "…" : String((digest?.filtered_by_rules ?? 0) + routine.length)} note="by your rules or as routine" />
      </div>

      <div className="grid grid-cols-[minmax(0,1fr)] gap-5 xl:grid-cols-[minmax(0,1.55fr)_minmax(300px,0.85fr)]">
        <section>
          <SectionTitle title="What matters" detail={`last ${period} · ranked`} action={<Link className="hidden items-center gap-1 text-[11px] font-medium text-[#80cdb0] hover:text-[#a4e4ca] sm:flex" href="/settings">Tune rules <Icon name="arrowRight" size={13} /></Link>} />
          <Panel className="overflow-hidden">
            {categories.length > 2 && (
              <div className="flex gap-1 overflow-x-auto border-b border-white/[0.06] px-3 py-2.5 sm:px-4">
                {categories.map((c) => (
                  <button key={c} type="button" onClick={() => setFilter(c)}
                    className={`shrink-0 rounded-md px-2.5 py-1.5 text-[11px] font-medium transition ${filter === c ? "bg-white/[0.09] text-[#e8ebef]" : "text-[#77818d] hover:bg-white/[0.04] hover:text-[#cbd1d8]"}`}>
                    {c}{c !== "All" && <span className="ml-1 text-[#5f6975]">{material.filter((a) => a.type === c).length}</span>}
                  </button>
                ))}
              </div>
            )}
            {loading && <p className="py-10 text-center text-[11px] text-[#85909c]">Reading filings and end-of-day data…</p>}
            {!loading && visible.map((item) => <AlertCard alert={toAlert(item)} key={item.id} onToggleSave={() => void toggleSaved(item)} saved={item.is_saved} />)}
            {!loading && !error && visible.length === 0 && (
              <EmptyState icon="bell" title="All quiet" description={period === "24 hours" ? "Nothing crossed your thresholds today. Try the 7d or 30d window." : "Nothing material in this window under your current rules."} />
            )}
            {!loading && routine.length > 0 && (
              <div className="border-t border-white/[0.06]">
                <button type="button" onClick={() => setShowRoutine(!showRoutine)} className="flex w-full items-center justify-between px-4 py-3 text-[11px] text-[#8a94a0] hover:bg-white/[0.02] sm:px-5">
                  <span><span className="font-semibold text-[#b8c0ca]">{routine.length} routine filings</span> · earnings-call notices, investor meets, dividends, compliance</span>
                  <Icon name={showRoutine ? "arrowUp" : "arrowDown"} size={14} />
                </button>
                {showRoutine && routine.map((item) => (
                  <Link key={item.id} href={`/events/${item.id}`} className="flex items-center gap-3 border-t border-white/[0.04] px-4 py-2.5 text-[11px] hover:bg-white/[0.02] sm:px-5">
                    <span className="w-[72px] shrink-0 font-semibold text-[#aeb7c1]">{item.symbol}</span>
                    <span className="min-w-0 flex-1 truncate text-[#86909c]">{item.title}</span>
                    <span className="shrink-0 text-[10px] text-[#5f6975]">{item.type} · {item.time}</span>
                  </Link>
                ))}
              </div>
            )}
          </Panel>
        </section>

        <aside>
          <SectionTitle title="EOD monitor" detail={asOf ? `close of ${asOf}` : "end of day"} />
          <Panel className="p-3 sm:p-4">
            <div className="mb-2 grid grid-cols-[1fr_64px_58px] gap-2 px-2 text-[9px] font-semibold uppercase tracking-[0.12em] text-[#5f6975]"><span>Holding</span><span className="text-right">Move</span><span className="text-right">Vol</span></div>
            {loading && !holdings.length && <p className="py-6 text-center text-[11px] text-[#85909c]">Loading prices…</p>}
            {monitor.map((h) => {
              const volHit = volT != null && (h.volume_multiple ?? 0) >= volT;
              const moveHit = moveT != null && h.change != null && Math.abs(h.change) >= moveT;
              return (
                <Link key={h.symbol} href={`/research?symbol=${h.symbol}`} className={`grid grid-cols-[1fr_64px_58px] items-center gap-2 rounded-lg px-2 py-2 transition hover:bg-white/[0.035] ${h.triggered ? "bg-[#1a2b25]/60" : ""}`}>
                  <span className="min-w-0"><span className="block truncate text-[12px] font-medium text-[#d7dce2]">{h.symbol}{h.triggered && <span className="ml-1.5 inline-block size-1.5 rounded-full bg-[#7fd8b4] align-middle" />}</span><span className="block truncate text-[10px] text-[#69737f]">{rupees(h.price)} · {h.sector}</span></span>
                  <span className={`text-right text-[11px] font-medium tabular-nums ${h.change == null ? "text-[#6d7783]" : h.change >= 0 ? "text-[#73cdab]" : "text-[#e48a8a]"} ${moveHit ? "underline decoration-dotted underline-offset-4" : ""}`}>{pct(h.change, 2)}</span>
                  <span className="flex items-center justify-end gap-1.5">
                    <span className="hidden h-1 w-6 overflow-hidden rounded-full bg-white/[0.06] sm:block"><span className={`block h-full rounded-full ${volHit ? "bg-[#7fd8b4]" : "bg-[#4a5562]"}`} style={{ width: `${Math.min(100, ((h.volume_multiple ?? 0) / Math.max(volT ?? 2, 1) / 1.5) * 100)}%` }} /></span>
                    <span className={`text-[11px] tabular-nums ${volHit ? "font-semibold text-[#9fe3c7]" : "text-[#8a94a0]"}`}>{multiple(h.volume_multiple)}</span>
                  </span>
                </Link>
              );
            })}
            <p className="mt-3 border-t border-white/[0.06] px-2 pt-3 text-[10px] leading-4 text-[#646e7a]">Vol = session volume ÷ 20-day average. Highlighted rows crossed your thresholds. {portfolio?.market_data_source ?? "Yahoo Finance"}.</p>
          </Panel>
        </aside>
      </div>
      <div className="mt-6 flex items-center gap-2 text-[10px] text-[#5f6975]"><Icon name="shield" size={12} />Everything here is read from NSE filings and end-of-day prices. Tap any item for the source.</div>
    </div>
  );
}

function Stat({ label, value, note, accent = false }: { label: string; value: string; note: string; accent?: boolean }) {
  return (
    <Panel className="p-4">
      <p className="text-[10px] font-medium text-[#8a94a0]">{label}</p>
      <p className={`mt-2 text-[26px] font-semibold tracking-[-0.04em] tabular-nums ${accent ? "text-[#9fe3c7]" : "text-[#f0f3f5]"}`}>{value}</p>
      <p className="mt-1 truncate text-[10px] text-[#707a86]">{note}</p>
    </Panel>
  );
}
