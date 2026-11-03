"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Icon } from "@/components/icons";
import { Toggle } from "@/components/toggle";
import { PageHeading, Panel, SectionTitle } from "@/components/ui";
import { getAlertRules, getPortfolio, searchCompanies, setHoldingTracked, updateAlertRule, type AlertRule, type CompanySearchResult } from "@/lib/api";

const DESCRIPTIONS: Record<string, string> = {
  Results: "Quarterly results with a QoQ / YoY first cut read from the filing",
  Acquisitions: "Mergers, acquisitions, demergers, joint ventures",
  Fundraising: "Rights issues, QIPs, preferential allotments, debt, buybacks",
  "Management changes": "CEO, CFO, MD and director moves, with the profile from the filing",
  "Regulatory updates": "Litigation, regulatory orders, penalties, insolvency",
  "Order wins": "Contract wins and press releases",
  Capex: "New plants and capacity expansion",
  "Credit rating": "Upgrades, downgrades, reaffirmations",
  Pledging: "Promoter pledge creation or release",
  "Insider trading": "Promoter / insider dealing disclosures",
  "Corporate actions": "Dividends, record dates, bonus and splits (shown as routine)",
  "Earnings call": "Call notices, transcripts and recordings (shown as routine)",
  "Investor meetings": "Analyst and investor meeting schedules (shown as routine)",
  Routine: "Compliance paperwork, newspaper ads, certificates (collapsed)",
};
const THRESHOLD_RULES = new Set(["Price move", "Price change"]);

export default function SettingsPage() {
  const [universe, setUniverse] = useState<CompanySearchResult[]>([]);
  const [tracked, setTracked] = useState(() => new Set<string>());
  const [weights, setWeights] = useState<Record<string, number>>({});
  const [rules, setRules] = useState<AlertRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([getPortfolio(), getAlertRules(), searchCompanies("")])
      .then(([portfolio, r, companies]) => {
        setTracked(new Set(portfolio.holdings.map((h) => h.symbol)));
        setWeights(Object.fromEntries(portfolio.holdings.map((h) => [h.symbol, h.weight])));
        setRules(r.items);
        const held = new Set(portfolio.holdings.map((h) => h.symbol));
        setUniverse([...companies.items].sort((a, b) => Number(held.has(b.symbol)) - Number(held.has(a.symbol)) || a.name.localeCompare(b.name)));
      })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Could not load preferences."))
      .finally(() => setLoading(false));
  }, []);

  async function patchRule(rule: AlertRule, update: { enabled?: boolean; threshold?: number }) {
    setRules((all) => all.map((r) => (r.id === rule.id ? { ...r, ...update } : r)));
    try { const saved = await updateAlertRule(rule.id, update); setRules((all) => all.map((r) => (r.id === rule.id ? saved : r))); setError(""); }
    catch (reason) { setRules((all) => all.map((r) => (r.id === rule.id ? rule : r))); setError(reason instanceof Error ? reason.message : "Could not save."); }
  }
  async function toggleHolding(symbol: string) {
    const next = !tracked.has(symbol);
    setTracked((s) => { const n = new Set(s); if (next) n.add(symbol); else n.delete(symbol); return n; });
    try { await setHoldingTracked(symbol, next); }
    catch (reason) { setTracked((s) => { const n = new Set(s); if (next) n.delete(symbol); else n.add(symbol); return n; }); setError(reason instanceof Error ? reason.message : "Could not update portfolio."); }
  }

  const volume = rules.find((r) => r.category === "Price move");
  const move = rules.find((r) => r.category === "Price change");
  const categories = rules.filter((r) => !THRESHOLD_RULES.has(r.category));

  return (
    <div>
      <PageHeading eyebrow="Your rules" title="Settings" description="You decide what counts as unusual. Changes apply to Today immediately." />
      {loading && <p className="mb-4 text-[11px] text-[#85909c]">Loading…</p>}
      {error && <p role="alert" className="mb-4 rounded-lg border border-[#673d3d] bg-[#2b191a] p-3 text-[11px] text-[#f1aaaa]">{error}</p>}

      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="space-y-5">
          <Panel className="p-4 sm:p-5">
            <SectionTitle title="Triggers" detail="end-of-day, per holding" />
            {[{ rule: volume, label: "Unusual volume", hint: "Session volume vs its 20-day average", options: [1.5, 2, 2.5, 3, 4], fmt: (v: number) => `${v.toFixed(1)}× average` },
              { rule: move, label: "Large daily move", hint: "Close vs previous close, either direction", options: [2, 3, 4, 5, 7], fmt: (v: number) => `±${v}%` }].map(({ rule, label, hint, options, fmt }) => rule && (
              <div key={label} className="flex items-center gap-3 border-t border-white/[0.06] py-3.5 first:border-0 first:pt-0">
                <div className="min-w-0 flex-1"><p className="text-[12px] font-medium text-[#dbe0e6]">{label}</p><p className="mt-0.5 text-[10px] text-[#75808c]">{hint}</p></div>
                <select aria-label={`${label} threshold`} disabled={!rule.enabled} value={String(rule.threshold ?? options[1])} onChange={(ev) => void patchRule(rule, { threshold: Number(ev.target.value) })}
                  className="h-9 rounded-lg border border-white/[0.09] bg-[#0c1015] px-2 text-[11px] text-[#d9dfe6] outline-none focus:border-[#58967c] disabled:opacity-40">
                  {options.map((o) => <option key={o} value={String(o)}>{fmt(o)}</option>)}
                </select>
                <Toggle checked={rule.enabled} label={`${rule.enabled ? "Disable" : "Enable"} ${label}`} onChange={() => void patchRule(rule, { enabled: !rule.enabled })} />
              </div>
            ))}
            <p className="mt-2 text-[10px] leading-5 text-[#69747f]">An alert fires if either enabled trigger is crossed. Each alert notes whether the company filed anything that session.</p>
          </Panel>

          <Panel className="p-4 sm:p-5">
            <SectionTitle title="Filing categories" detail="what reaches Today" />
            <div className="divide-y divide-white/[0.05]">
              {categories.map((rule) => (
                <div className="flex items-center gap-4 py-3 first:pt-0 last:pb-0" key={rule.id}>
                  <div className="min-w-0 flex-1"><p className="text-[12px] font-medium text-[#d9dee5]">{rule.name}</p><p className="mt-0.5 text-[10px] leading-4 text-[#75808c]">{DESCRIPTIONS[rule.category] ?? rule.category}</p></div>
                  <Toggle checked={rule.enabled} label={`${rule.enabled ? "Disable" : "Enable"} ${rule.name}`} onChange={() => void patchRule(rule, { enabled: !rule.enabled })} />
                </div>
              ))}
            </div>
          </Panel>
        </div>

        <Panel className="overflow-hidden">
          <div className="px-4 pt-4 sm:px-5 sm:pt-5"><SectionTitle title="Portfolio" detail={`${tracked.size} holdings`} /></div>
          <div className="divide-y divide-white/[0.05]">
            {universe.map((c) => (
              <div className="flex items-center gap-3 px-4 py-2.5 sm:px-5" key={c.symbol}>
                <div className="min-w-0 flex-1"><p className="truncate text-[12px] font-medium text-[#d9dee5]">{c.name}</p><p className="text-[10px] text-[#75808c]">{c.symbol} · {c.sector}</p></div>
                {tracked.has(c.symbol) && weights[c.symbol] != null && <span className="text-[11px] tabular-nums text-[#9ba4af]">{weights[c.symbol].toFixed(1)}%</span>}
                <Toggle checked={tracked.has(c.symbol)} label={`${tracked.has(c.symbol) ? "Remove" : "Add"} ${c.name}`} onChange={() => void toggleHolding(c.symbol)} />
              </div>
            ))}
          </div>
          <Link className="flex min-h-11 items-center justify-center gap-2 border-t border-white/[0.06] text-[11px] font-medium text-[#9fd8c0] hover:bg-white/[0.03]" href="/research">Research any NSE company <Icon name="arrowRight" size={13} /></Link>
        </Panel>
      </div>
    </div>
  );
}
