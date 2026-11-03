"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Icon } from "@/components/icons";
import { Badge, CompanyMark, EmptyState, Panel, SectionTitle, SmallButton } from "@/components/ui";
import { getAlert, updateAlert, type ApiAlert, type Enrichment } from "@/lib/api";
import { multiple, pct, rupees } from "@/lib/format";
const num = (v: number | null) => (v == null ? "—" : v.toLocaleString("en-IN", { maximumFractionDigits: v >= 1000 ? 0 : 1 }));

const pageLink = (url: string, page?: number | null) => (page ? `${url.split("#")[0]}#page=${page}` : url);

function ResultsTable({ e, source }: { e: Enrichment; source: string }) {
  if (e.status !== "parsed" || !e.metrics) {
    return <Panel className="p-5 sm:p-6"><SectionTitle title="Results first cut" detail="not available" />
      <p className="text-[12px] leading-6 text-[#9aa3ae]">{e.reason ?? "The results table could not be read from this filing."} FINN shows nothing rather than a number it could not verify. Open the filing below for the full statement.</p></Panel>;
  }
  const color = (v: number | null) => (v == null ? "text-[#6d7783]" : v >= 0 ? "text-[#7fd8b4]" : "text-[#ee9a9a]");
  return (
    <Panel className="p-5 sm:p-6">
      <SectionTitle title="Results first cut" detail={`${e.period ?? "Quarter"} · ${e.basis} · ${e.unit}`} />
      <div className="-mx-1 overflow-x-auto">
        <table className="w-full min-w-[340px] text-left text-[11px] sm:text-[12px]">
          <thead className="text-[10px] uppercase tracking-[0.1em] text-[#6f7985]"><tr><th className="px-1 py-2 font-semibold">Metric</th><th className="px-1 py-2 text-right font-semibold">Now</th><th className="px-1 py-2 text-right font-semibold">Prev Q</th><th className="px-1 py-2 text-right font-semibold">Yr ago</th><th className="px-1 py-2 text-right font-semibold">QoQ</th><th className="px-1 py-2 text-right font-semibold">YoY</th></tr></thead>
          <tbody>
            {e.metrics.map((m) => (
              <tr key={m.metric} className="border-t border-white/[0.06]">
                <td className="px-1 py-2.5 font-medium text-[#d7dde4]">{m.metric}{m.metric === "EBITDA" && <span className="ml-1 text-[10px] text-[#69737f]">derived</span>}</td>
                <td className="px-1 py-2.5 text-right tabular-nums text-[#e6eaee]">{num(m.current)}</td>
                <td className="px-1 py-2.5 text-right tabular-nums text-[#9aa3ae]">{num(m.previous_quarter)}</td>
                <td className="px-1 py-2.5 text-right tabular-nums text-[#9aa3ae]">{num(m.year_ago)}</td>
                <td className={`px-1 py-2.5 text-right font-semibold tabular-nums ${color(m.qoq_pct)}`}>{pct(m.qoq_pct)}</td>
                <td className={`px-1 py-2.5 text-right font-semibold tabular-nums ${color(m.yoy_pct)}`}>{pct(m.yoy_pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-[10px] leading-5 text-[#6f7a86]">Read from the results table on <a className="text-[#8fd3b7] underline-offset-2 hover:underline" href={pageLink(source, e.page)} target="_blank" rel="noreferrer">page {e.page} of the filing</a>; each column is matched to its period by the header date and cross-checked against the total-income line. EBITDA = {e.ebitda_definition}. A dash means the figure could not be verified.</p>
    </Panel>
  );
}

function People({ e, source }: { e: Enrichment; source: string }) {
  const people = e.people ?? [];
  return (
    <Panel className="p-5 sm:p-6">
      <SectionTitle title="Who is it?" detail={e.action ? `${e.action} · from the filing` : "from the filing"} />
      {people.length === 0 && <p className="text-[12px] leading-6 text-[#9aa3ae]">{e.reason ?? "The filing does not name the person in a readable way."}</p>}
      <div className="space-y-4">
        {people.map((p, i) => (
          <div key={`${p.name}-${i}`} className="rounded-xl border border-white/[0.07] bg-white/[0.02] p-4">
            <div className="flex flex-wrap items-center gap-2"><span className="text-[13px] font-semibold text-[#e3e7eb]">{p.name ?? "Name not stated"}</span>{p.role && <Badge>{p.role}</Badge>}</div>
            <p className="mt-2 text-[12px] leading-6 text-[#aab3bd]">{p.profile ?? "No profile is disclosed in the filing."}</p>
            <div className="mt-3 flex flex-wrap gap-3 text-[11px]">
              {p.page && <a className="text-[#8fd3b7] hover:underline" href={pageLink(source, p.page)} target="_blank" rel="noreferrer">Filing · p. {p.page}</a>}
              {p.name && <a className="inline-flex items-center gap-1 text-[#9ba6b2] hover:text-white" href={`https://www.linkedin.com/search/results/people/?keywords=${encodeURIComponent(p.name.replace(/^(Mr|Ms|Mrs|Dr|Shri|Smt)\.?\s+/, ""))}`} target="_blank" rel="noreferrer">Search LinkedIn <Icon name="external" size={12} /></a>}
            </div>
          </div>
        ))}
      </div>
      {e.status === "no_profile" && people.length > 0 && <p className="mt-3 text-[10px] text-[#6f7a86]">The disclosure names the person but carries no background. Use the LinkedIn search link above; FINN does not write bios from memory.</p>}
    </Panel>
  );
}

function Eod({ e }: { e: Enrichment }) {
  const rows: [string, string][] = [
    ["Trading day", e.trading_date ? new Date(e.trading_date).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }) : "—"],
    ["Close", rupees(e.close)], ["Daily move", pct(e.change_pct, 2)],
    ["Volume", e.volume?.toLocaleString("en-IN") ?? "—"], ["20-day average volume", e.avg_volume_20d?.toLocaleString("en-IN") ?? "—"],
    ["Volume multiple", multiple(e.volume_multiple)],
  ];
  return (
    <Panel className="p-5 sm:p-6">
      <SectionTitle title="The move" detail="end-of-day data" />
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">{rows.map(([k, v]) => <div key={k} className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3"><p className="text-[10px] text-[#78838f]">{k}</p><p className="mt-1 text-[13px] font-semibold tabular-nums text-[#e3e7eb]">{v}</p></div>)}</div>
      <p className="mt-4 text-[12px] leading-6 text-[#aab3bd]">{e.matched_filing ? <>Same-session filing: <Link className="text-[#8fd3b7] hover:underline" href={`/events/${e.matched_filing}`}>{e.matched_filing_title}</Link></> : "No company filing in the preceding session, so the move has no disclosed catalyst."}</p>
    </Panel>
  );
}

export default function AlertDetailPage() {
  const params = useParams<{ eventId: string }>();
  const router = useRouter();
  const [alert, setAlert] = useState<ApiAlert | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    let alive = true;
    getAlert(params.eventId).then((r) => { if (alive) setAlert(r); }).catch((reason: unknown) => { if (alive) setError(reason instanceof Error ? reason.message : "Could not load this alert."); }).finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [params.eventId]);

  if (loading) return <Panel><p className="py-12 text-center text-[12px] text-[#85909c]">Loading…</p></Panel>;
  if (error || !alert) return <Panel>{error ? <p role="alert" className="p-5 text-[12px] text-[#f1aaaa]">{error}</p> : <EmptyState icon="file" title="Alert not found" description="Return to Today to view current updates." />}</Panel>;

  const e = alert.enrichment ?? {};
  const saved = alert.is_saved;
  const isEod = e.kind === "eod";
  async function toggleSave() {
    if (!alert) return;
    try { await updateAlert(alert.id, { is_saved: !saved }); setAlert({ ...alert, is_saved: !saved }); } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not update."); }
  }

  return (
    <div>
      <div className="mb-5 flex items-center justify-between">
        <button className="inline-flex min-h-9 items-center gap-2 text-[12px] font-medium text-[#89939f] hover:text-white" onClick={() => router.back()} type="button"><Icon name="arrowLeft" size={15} />Back</button>
        <SmallButton icon={saved ? "check" : "bookmark"} active={saved} onClick={() => void toggleSave()}>{saved ? "Saved" : "Save"}</SmallButton>
      </div>

      <Panel className="mb-5 overflow-hidden">
        <div className="h-[2px] bg-gradient-to-r from-[#67c5a3] via-[#304c42] to-transparent" />
        <div className="p-5 sm:p-7">
          <div className="flex items-start gap-4">
            <CompanyMark color="#5e9f87" initials={alert.symbol.slice(0, 2)} size="lg" />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2"><span className="text-[13px] font-medium text-[#bcc4cd]">{alert.company}</span><Badge>{alert.type}</Badge><Badge>{alert.impact}</Badge><span className="text-[11px] text-[#6f7985]">{alert.time}</span></div>
              <h1 className="mt-3 text-[21px] font-semibold leading-[1.35] tracking-[-0.03em] text-[#f1f3f6] sm:text-[27px]">{alert.title}</h1>
              <p className="mt-2 text-[13px] leading-6 text-[#929ba7]">{alert.summary}</p>
            </div>
          </div>
        </div>
      </Panel>

      <div className="grid grid-cols-[minmax(0,1fr)] gap-5 lg:grid-cols-[minmax(0,1.45fr)_minmax(285px,0.75fr)]">
        <div className="space-y-5">
          {alert.why && <Panel className="p-5 sm:p-6"><SectionTitle title="Why it matters" /><p className="text-[13px] leading-[1.85] text-[#b7bfc8]">{alert.why}</p></Panel>}
          {e.kind === "results" && <ResultsTable e={e} source={alert.source} />}
          {e.kind === "people" && <People e={e} source={alert.source} />}
          {isEod && <Eod e={e} />}
          {!e.kind && alert.details.length > 0 && (
            <Panel className="p-5 sm:p-6"><SectionTitle title="Filing details" />
              <div className="divide-y divide-white/[0.055]">{alert.details.map((d) => { const [k, v] = d.split(": "); return <div className="flex justify-between gap-3 py-2.5 text-[12px]" key={d}><span className="text-[#7e8894]">{k}</span><span className="text-right font-medium text-[#d6dce3]">{v ?? ""}</span></div>; })}</div>
            </Panel>
          )}
          <a className="group flex items-center gap-3 rounded-2xl border border-white/[0.075] bg-[#11161d] p-4 transition hover:border-white/[0.14]" href={alert.source} rel="noreferrer" target="_blank">
            <span className="grid size-10 place-items-center rounded-lg border border-white/[0.08] bg-[#1b222b] text-[#9ba7b4]"><Icon name="file" size={18} /></span>
            <span className="min-w-0 flex-1"><span className="block truncate text-[12px] font-semibold text-[#dbe0e6]">{isEod ? "Price history" : "Original filing"} · {alert.sourceName}</span><span className="mt-0.5 block text-[10px] text-[#76818d]">{alert.sourceDate}</span></span>
            <Icon className="text-[#75808c] group-hover:text-[#a9e0c8]" name="external" size={15} />
          </a>
        </div>

        <aside className="space-y-5">
          <Panel className="p-5">
            <SectionTitle title="In your portfolio" />
            <div className="grid grid-cols-2 gap-2">
              <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3"><p className="text-[10px] text-[#78838f]">Weight</p><p className="mt-1 text-[14px] font-semibold text-[#e3e7eb]">{alert.portfolio_weight != null ? `${alert.portfolio_weight.toFixed(1)}%` : "—"}</p></div>
              <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3"><p className="text-[10px] text-[#78838f]">Last close</p><p className="mt-1 text-[14px] font-semibold text-[#e3e7eb]">{rupees(alert.market_data?.close)}</p><p className={`text-[11px] ${alert.daily_change == null ? "text-[#6d7783]" : alert.daily_change >= 0 ? "text-[#7fd8b4]" : "text-[#ee9a9a]"}`}>{pct(alert.daily_change, 2)}</p></div>
            </div>
            <Link className="mt-4 flex min-h-10 items-center justify-center gap-2 rounded-lg bg-[#c8f0dd] text-[12px] font-semibold text-[#10231c] hover:bg-[#ddf8e9]" href={`/research?symbol=${alert.symbol}`}>Research {alert.symbol} <Icon name="arrowRight" size={14} /></Link>
          </Panel>
          <p className="px-1 text-[10px] leading-5 text-[#626d79]">FINN extracts; it does not invent. Numbers and profiles come from the filing itself, and anything it could not verify is left blank.</p>
        </aside>
      </div>
    </div>
  );
}
