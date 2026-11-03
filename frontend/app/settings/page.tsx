"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { Icon } from "@/components/icons";
import { Toggle } from "@/components/toggle";
import { Badge, CompanyMark, PageHeading, Panel, SectionTitle, SmallButton } from "@/components/ui";
import { getAlertRules, getPortfolio, searchCompanies, setHoldingTracked, toHolding, updateAlertRule, type AlertRule } from "@/lib/api";
import type { Holding } from "@/lib/types";

const eventTypes = [
  { id: "Results", label: "Results", description: "Financial results and earnings updates" },
  { id: "Order wins", label: "Order wins", description: "New contracts and material order announcements" },
  { id: "Acquisitions", label: "Acquisitions", description: "Mergers, acquisitions, investments, and divestments" },
  { id: "Management changes", label: "Management changes", description: "Leadership, board, and auditor changes" },
  { id: "Fundraising", label: "Fundraising", description: "Equity and debt issuance or capital raising" },
  { id: "Regulatory updates", label: "Regulatory updates", description: "Regulatory, legal, and compliance events" },
  { id: "Corporate actions", label: "Corporate actions", description: "Dividends, buybacks, splits, and shareholder events" },
  { id: "Earnings", label: "Sample results", description: "Illustrative results records retained for the demo" },
  { id: "Corporate action", label: "Sample corporate actions", description: "Illustrative corporate records retained for the demo" },
  { id: "Price move", label: "Price and volume moves", description: "Unusual moves against recent company trading" },
  { id: "Macro", label: "Macro and sector context", description: "Developments that may affect your tracked sectors" },
];

export default function SettingsPage() {
  const [universe, setUniverse] = useState<Holding[]>([]);
  const [tracked, setTracked] = useState(() => new Set<string>());
  const [rules, setRules] = useState<AlertRule[]>([]);
  const [pageLoading, setPageLoading] = useState(true);
  const [error, setError] = useState("");
  const [enabledEvents, setEnabledEvents] = useState(() => new Set<string>());
  const [volumeThreshold, setVolumeThreshold] = useState("2.0");
  const [digest, setDigest] = useState(true);
  const [instantAlerts, setInstantAlerts] = useState(true);
  const [saved, setSaved] = useState(false);
  useEffect(() => {
    let alive = true;
    Promise.all([getPortfolio(), getAlertRules(), searchCompanies("")]).then(([portfolio, rulesResponse, companyResponse]) => {
      if (!alive) return;
      const all = portfolio.holdings.map(toHolding);
      setTracked(new Set(all.map((item) => item.id))); setRules(rulesResponse.items);
      const current = new Map(all.map((item) => [item.symbol, item]));
      setUniverse(companyResponse.items.map((item) => current.get(item.symbol) ?? { id: item.symbol.toLowerCase(), name: item.name, symbol: item.symbol, sector: item.sector, price: "—", change: "—", positive: true, weight: "—", initials: item.name[0], color: "#5e9f87" }));
      setEnabledEvents(new Set(rulesResponse.items.filter((rule) => rule.enabled).map((rule) => rule.category)));
      const volume = rulesResponse.items.find((rule) => rule.category === "Price move")?.threshold;
      if (volume) setVolumeThreshold(volume.toFixed(1));
    }).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Could not load preferences."))
      .finally(() => setPageLoading(false));
    return () => { alive = false; };
  }, []);

  async function toggleTracked(id: string) {
    const holding = universe.find((item) => item.id === id);
    if (!holding) return;
    setTracked((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
    setSaved(false);
    try { await setHoldingTracked(holding.symbol, !tracked.has(id)); setError(""); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Could not update portfolio."); setTracked((current) => { const next = new Set(current); if (tracked.has(id)) next.add(id); else next.delete(id); return next; }); }
  }

  async function toggleEvent(id: string) {
    setEnabledEvents((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
    setSaved(false);
    const rule = rules.find((item) => item.category === id);
    if (rule) {
      try { const updated = await updateAlertRule(rule.id, { enabled: !enabledEvents.has(rule.category) }); setRules((current) => current.map((item) => item.id === rule.id ? updated : item)); }
      catch (reason) { setError(reason instanceof Error ? reason.message : "Could not update alert rule."); }
    }
  }

  async function changeThreshold(value: string) {
    setVolumeThreshold(value); setSaved(false);
    const rule = rules.find((item) => item.category === "Price move");
    if (!rule) return;
    try { const updated = await updateAlertRule(rule.id, { threshold: Number(value) }); setRules((current) => current.map((item) => item.id === rule.id ? updated : item)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Could not update alert threshold."); }
  }

  return (
    <div>
      <PageHeading
        eyebrow="Personalize your signal"
        title="Settings"
        description="Shape the companies and changes FINN brings to your attention. Portfolio and alert rules persist in the sample database."
        action={<SmallButton icon={saved ? "check" : "shield"} active={saved} onClick={() => setSaved(true)}>{saved ? "Saved for this session" : "Save preferences"}</SmallButton>}
      />

      {pageLoading && <p className="mb-4 text-[10px] text-[#85909c]">Loading portfolio and alert preferences…</p>}
      {error && <p role="alert" className="mb-4 rounded-lg border border-[#673d3d] bg-[#2b191a] p-3 text-[10px] text-[#f1aaaa]">{error}</p>}
      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1.35fr)_minmax(290px,0.75fr)]">
        <div className="space-y-5">
          <Panel className="overflow-hidden">
            <div className="flex items-center justify-between border-b border-white/[0.06] px-4 py-4 sm:px-5">
              <div><SectionTitle title="Your portfolio" detail={`${tracked.size} companies tracked`} /><p className="-mt-2 text-[9px] text-[#6f7a86]">Select the companies included in your daily brief.</p></div>
              <SmallButton icon="plus" onClick={() => document.getElementById("research-directory")?.scrollIntoView({ behavior: "smooth", block: "center" })}>Add companies</SmallButton>
            </div>
            <div className="divide-y divide-white/[0.05]">
              {universe.map((holding) => {
                const checked = tracked.has(holding.id);
                return <div className="flex items-center gap-3 px-4 py-3 sm:px-5" key={holding.id}>
                  <CompanyMark color={holding.color} initials={holding.initials} size="sm" />
                  <div className="min-w-0 flex-1"><p className="truncate text-[11px] font-medium text-[#d9dee5]">{holding.name}</p><p className="mt-0.5 text-[9px] text-[#75808c]">{holding.symbol} · {holding.sector}</p></div>
                  <span className="hidden w-12 text-right text-[10px] text-[#9ba4af] sm:block">{holding.weight}</span>
                  <Toggle checked={checked} label={checked ? `Remove ${holding.name} from portfolio` : `Add ${holding.name} to portfolio`} onChange={() => toggleTracked(holding.id)} />
                </div>;
              })}
            </div>
            <div className="flex items-center gap-2 border-t border-white/[0.06] px-4 py-3 text-[9px] text-[#68737f] sm:px-5"><Icon name="info" size={13} />Changes persist to this local demo database; holdings remain illustrative sample data.</div>
          </Panel>

          <Panel className="p-4 sm:p-5">
            <SectionTitle title="Alert categories" detail="Choose what makes the brief" />
            <div className="divide-y divide-white/[0.05]">
              {eventTypes.map((item) => <div className="flex items-center gap-4 py-3.5 first:pt-1 last:pb-1" key={item.id}><div className="min-w-0 flex-1"><p className="text-[11px] font-medium text-[#d9dee5]">{item.label}</p><p className="mt-1 text-[9px] leading-4 text-[#75808c]">{item.description}</p></div><Toggle checked={enabledEvents.has(item.id)} label={`${enabledEvents.has(item.id) ? "Disable" : "Enable"} ${item.label}`} onChange={() => toggleEvent(item.id)} /></div>)}
            </div>
          </Panel>
        </div>

        <div className="space-y-5">
          <Panel className="p-4 sm:p-5">
            <SectionTitle title="Delivery" detail="How FINN reaches you" />
            <div className="divide-y divide-white/[0.05]">
              <div className="flex items-center gap-4 py-3.5 first:pt-1"><div className="min-w-0 flex-1"><p className="text-[11px] font-medium text-[#d9dee5]">Daily digest</p><p className="mt-1 text-[9px] leading-4 text-[#75808c]">A prioritized summary each morning</p></div><Toggle checked={digest} label="Daily digest" onChange={() => { setDigest(!digest); setSaved(false); }} /></div>
              <div className="flex items-center gap-4 py-3.5 last:pb-1"><div className="min-w-0 flex-1"><p className="text-[11px] font-medium text-[#d9dee5]">Triggered alerts</p><p className="mt-1 text-[9px] leading-4 text-[#75808c]">Surface selected material changes as they appear</p></div><Toggle checked={instantAlerts} label="Triggered alerts" onChange={() => { setInstantAlerts(!instantAlerts); setSaved(false); }} /></div>
            </div>
          </Panel>

          <Panel className="p-4 sm:p-5">
            <SectionTitle title="Signal sensitivity" detail="Demo rule" />
            <div className="rounded-xl border border-white/[0.06] bg-white/[0.015] p-3.5">
              <div className="flex items-center gap-2"><span className="grid size-7 place-items-center rounded-lg bg-[#1b2d26] text-[#86d3b2]"><Icon name="activity" size={14} /></span><div><p className="text-[10px] font-medium text-[#d7dde4]">Unusual trading volume</p><p className="mt-0.5 text-[8px] text-[#73808c]">Compared with the 20-day average</p></div></div>
              <div className="mt-4 flex items-center justify-between gap-3"><label className="text-[9px] text-[#88939f]" htmlFor="volume-threshold">Alert when volume exceeds</label><select className="h-9 rounded-lg border border-white/[0.09] bg-[#0c1015] px-2.5 text-[10px] text-[#d9dfe6] outline-none focus:border-[#58967c]" id="volume-threshold" onChange={(event) => void changeThreshold(event.target.value)} value={volumeThreshold}><option value="1.5">1.5× average</option><option value="2.0">2.0× average</option><option value="2.5">2.5× average</option><option value="3.0">3.0× average</option></select></div>
              <div className="mt-4 flex items-center justify-between border-t border-white/[0.06] pt-3"><span className="text-[9px] text-[#76818d]">Current sample rule</span><Badge>{`Above ${volumeThreshold}×`}</Badge></div>
            </div>
            <p className="mt-3 text-[9px] leading-5 text-[#69747f]">Threshold is configurable. A volume move alone does not confirm a catalyst.</p>
          </Panel>

          <Panel className="p-4 sm:p-5">
            <SectionTitle title="Research universe" detail="Ad-hoc coverage" />
            <p className="text-[10px] leading-5 text-[#87919d]">Search and research listed companies outside your portfolio from the Research workspace. The prototype includes a small curated NSE/BSE sample set.</p>
            <Link className="mt-3 flex min-h-9 w-full items-center justify-center gap-2 rounded-lg border border-white/[0.08] text-[10px] font-medium text-[#c0c7cf] transition hover:bg-white/[0.04]" id="research-directory" href="/research">Explore research universe <Icon name="arrowRight" size={13} /></Link>
          </Panel>

          <div className="flex items-start gap-2 px-1 text-[9px] leading-5 text-[#626d79]"><Icon className="mt-0.5 shrink-0" name="shield" size={12} />Local demo persistence only; delivery preferences remain session-only. No account data is used.</div>
        </div>
      </div>
    </div>
  );
}
