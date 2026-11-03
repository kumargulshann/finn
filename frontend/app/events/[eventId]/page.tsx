"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Icon } from "@/components/icons";
import { Badge, Change, CompanyMark, EmptyState, PageHeading, Panel, SectionTitle, SmallButton } from "@/components/ui";
import { getAlert, updateAlert, type ApiAlert } from "@/lib/api";

export default function AlertDetailPage() {
  const params = useParams<{ eventId: string }>();
  const router = useRouter();
  const [alert, setAlert] = useState<ApiAlert | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    let alive = true;
    getAlert(params.eventId).then((result) => { if (alive) setAlert(result); }).catch((reason: unknown) => { if (alive) setError(reason instanceof Error ? reason.message : "Could not load this alert."); }).finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [params.eventId]);
  const saved = alert?.is_saved ?? false;
  const read = alert?.is_read ?? false;
  async function setEventState(update: { is_saved?: boolean; is_read?: boolean }) {
    if (!alert) return;
    try { await updateAlert(alert.id, update); setAlert({ ...alert, ...update }); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Could not update this alert."); }
  }

  if (loading) {
    return <Panel><p className="py-12 text-center text-[11px] text-[#85909c]">Loading alert details…</p></Panel>;
  }
  if (error || !alert) {
    return <Panel>{error ? <p role="alert" className="p-5 text-[11px] text-[#f1aaaa]">{error}</p> : <EmptyState icon="file" title="Alert not found" description="This event may have been removed. Return to Today to view current updates." />}</Panel>;
  }

  return (
    <div>
      <button className="mb-5 inline-flex items-center gap-2 text-[11px] font-medium text-[#89939f] transition hover:text-white" onClick={() => router.back()} type="button"><Icon name="arrowLeft" size={15} />Back to Today</button>
      <PageHeading
        eyebrow={`${alert.type} · ${alert.time}`}
        title="Alert detail"
        description="A concise read on the event, its portfolio context, and the evidence behind it."
        action={<div className="flex gap-2"><SmallButton icon={saved ? "check" : "bookmark"} active={saved} onClick={() => void setEventState({ is_saved: !saved })}>{saved ? "Saved" : "Save"}</SmallButton><SmallButton icon="check" active={read} onClick={() => void setEventState({ is_read: !read })}>{read ? "Read" : "Mark read"}</SmallButton></div>}
      />

      <Panel className="mb-5 overflow-hidden">
        <div className="h-[2px] bg-gradient-to-r from-[#67c5a3] via-[#304c42] to-transparent" />
        <div className="p-5 sm:p-7">
          <div className="flex flex-wrap items-start gap-4">
            <CompanyMark color={alert.color} initials={alert.initials} size="lg" />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2"><span className="text-[12px] font-medium text-[#bcc4cd]">{alert.company}</span><span className="rounded border border-white/[0.08] px-1.5 py-0.5 text-[9px] text-[#7e8894]">{alert.symbol}</span><Badge>{alert.type}</Badge><Badge>{alert.impact}</Badge><Badge>{alert.is_demo ? "SAMPLE" : `${alert.source_exchange} FILING`}</Badge></div>
              <h1 className="mt-3 max-w-4xl text-[21px] font-semibold leading-[1.35] tracking-[-0.035em] text-[#f1f3f6] sm:text-[29px]">{alert.title}</h1>
              <p className="mt-3 max-w-3xl text-[12px] leading-6 text-[#929ba7] sm:text-[13px]">{alert.summary}</p>
            </div>
            <Link className="hidden min-h-9 items-center gap-2 rounded-lg bg-[#c8f0dd] px-3.5 text-[10px] font-semibold text-[#10231c] transition hover:bg-[#ddf8e9] sm:inline-flex" href="/research">Research this company <Icon name="arrowRight" size={14} /></Link>
          </div>
        </div>
      </Panel>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1.45fr)_minmax(285px,0.75fr)]">
        <div className="space-y-5">
          {Boolean(alert.why) && <Panel className="p-5 sm:p-6">
            <SectionTitle title="Why it matters" detail="FINN's read" />
            <p className="text-[12px] leading-[1.9] text-[#b0b8c2] sm:text-[13px]">{alert.why}</p>
            <div className="mt-5 flex items-start gap-2.5 rounded-xl border border-[#795f35]/30 bg-[#282319]/70 p-3.5">
              <Icon className="mt-0.5 shrink-0 text-[#d9b269]" name="info" size={15} />
              <p className="text-[10px] leading-[1.75] text-[#baaa88]">This is an interpretation of the selected source and sample market context. It is not a recommendation. Verify the underlying facts before acting.</p>
            </div>
          </Panel>}

          <Panel className="p-5 sm:p-6">
            <SectionTitle title="Event facts" detail="As reported in the source" />
            <div className="divide-y divide-white/[0.055]">
              {alert.details.map((detail, index) => {
                const [label, value] = detail.split(": ");
                return <div className="flex flex-col gap-1 py-3 first:pt-1 last:pb-1 sm:flex-row sm:items-center sm:justify-between" key={detail}><span className="text-[10px] text-[#7e8894]">{label}</span><span className="text-[11px] font-medium text-[#d6dce3] sm:text-right">{value ?? detail}{index === 0 && alert.type === "Earnings" && <span className="ml-2 text-[9px] text-[#727d88]">sample</span>}</span></div>;
              })}
            </div>
          </Panel>

          <Panel className="p-5 sm:p-6">
            <SectionTitle title="Source document" detail="Primary source" />
            <a className="group flex items-center gap-3 rounded-xl border border-white/[0.07] bg-white/[0.02] p-3.5 transition hover:border-white/[0.13] hover:bg-white/[0.045]" href={alert.source} rel="noreferrer" target="_blank">
              <span className="grid size-10 place-items-center rounded-lg border border-white/[0.08] bg-[#1b222b] text-[#9ba7b4]"><Icon name="file" size={18} /></span>
              <span className="min-w-0 flex-1"><span className="block truncate text-[11px] font-semibold text-[#dbe0e6]">{alert.sourceName}</span><span className="mt-1 block text-[9px] text-[#76818d]">Published {alert.sourceDate} · Original exchange filing</span></span>
              <Icon className="text-[#75808c] transition group-hover:text-[#a9e0c8]" name="external" size={15} />
            </a>
            <div className="mt-3 flex items-center gap-2 text-[9px] text-[#68737f]"><Icon name="shield" size={12} />{alert.is_demo ? "This record is illustrative sample data; its source link is a demo reference." : "Headline, summary, and publication time are taken from the exchange feed. Open the filing to verify full details."}</div>
          </Panel>
        </div>

        <aside className="space-y-5">
          <Panel className="p-5">
            <SectionTitle title="Portfolio context" />
              <div className="flex items-center gap-3"><CompanyMark color={alert.color} initials={alert.initials} size="sm" /><div><p className="text-[11px] font-semibold text-[#dce1e7]">{alert.company}</p><p className="mt-1 text-[9px] text-[#737e8a]">{alert.portfolio_weight !== null ? "In your portfolio · " + alert.portfolio_weight.toFixed(1) + "% weight" : "Outside your portfolio"}</p></div></div>
            <div className="mt-5 grid grid-cols-2 gap-3">
              <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3"><p className="text-[9px] text-[#78838f]">Today</p><p className="mt-1.5">{alert.daily_change === null ? <span className="text-[10px] text-[#78838f]">Unavailable</span> : <Change positive={alert.daily_change >= 0} value={(alert.daily_change >= 0 ? "+" : "−") + Math.abs(alert.daily_change).toFixed(2) + "%"} />}</p></div>
              <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3"><p className="text-[9px] text-[#78838f]">Alert priority</p><p className="mt-1.5 text-[11px] font-medium text-[#d9c394]">{alert.impact}</p></div>
            </div>
                      <div className="mt-3 rounded-lg border border-white/[0.06] bg-white/[0.02] p-3">
              <div className="flex items-center justify-between gap-3"><span className="text-[9px] text-[#78838f]">Latest NSE daily close</span><span className="text-[11px] font-semibold text-[#dce1e7]">{alert.market_data?.close == null ? "Unavailable" : "INR " + alert.market_data.close.toLocaleString("en-IN", { maximumFractionDigits: 2 })}</span></div>
              <div className="mt-1 flex items-center justify-between gap-3"><span className="text-[9px] text-[#78838f]">Trading volume</span><span className="text-[10px] text-[#c0c8d1]">{alert.market_data?.volume?.toLocaleString("en-IN") ?? "Unavailable"}</span></div>
              <p className="mt-2 text-[9px] text-[#68737f]">{alert.market_data?.source ?? "Yahoo Finance"} · {alert.market_data?.market_as_of ? new Date(alert.market_data.market_as_of).toLocaleString() : "No market timestamp"} · {alert.market_data?.status === "stale" ? "Cached / stale" : alert.market_data?.status === "unavailable" ? "Unavailable" : "Daily EOD"}</p>
            </div></Panel>

          <Panel className="p-5">
            <div className="flex items-start gap-3"><span className="grid size-9 place-items-center rounded-lg border border-[#396651]/40 bg-[#172a22] text-[#8ad6b5]"><Icon name="spark" size={17} /></span><div><p className="text-[12px] font-semibold text-[#e0e5e9]">What to watch next</p><p className="mt-1 text-[10px] leading-5 text-[#89939e]">Check the next quarterly update for whether this trend continues and how it flows through to margins and cash generation.</p></div></div>
            <Link className="mt-4 flex min-h-10 items-center justify-center gap-2 rounded-lg border border-white/[0.09] text-[10px] font-medium text-[#bdc5ce] transition hover:bg-white/[0.05] hover:text-white sm:hidden" href="/research">Research {alert.company} <Icon name="arrowRight" size={13} /></Link>
          </Panel>

          <Panel className="p-5">
            <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[#727c88]">Event timeline</p>
            <div className="mt-4 flex gap-3"><span className="relative mt-1 flex w-3 justify-center"><span className="absolute bottom-[-20px] top-3 w-px bg-white/[0.1]" /><span className="relative size-2 rounded-full bg-[#71d0ad] ring-4 ring-[#17352d]" /></span><div><p className="text-[10px] font-medium text-[#cbd2da]">Source published</p><p className="mt-1 text-[9px] text-[#737e8a]">{alert.sourceDate}</p></div></div>
            <div className="mt-5 flex gap-3"><span className="mt-1 grid w-3 place-items-center"><span className="size-1.5 rounded-full bg-[#d6ae68]" /></span><div><p className="text-[10px] font-medium text-[#cbd2da]">FINN surfaced this update</p><p className="mt-1 text-[9px] text-[#737e8a]">{alert.time}</p></div></div>
          </Panel>
        </aside>
      </div>
    </div>
  );
}
