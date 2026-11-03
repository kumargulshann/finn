import Link from "next/link";

import { Icon } from "@/components/icons";
import { Badge, CompanyMark } from "@/components/ui";
import type { Enrichment } from "@/lib/api";
import { multiple, pct } from "@/lib/format";
import type { AlertItem } from "@/lib/types";

function Chip({ label, value, tone }: { label: string; value: string; tone: "up" | "down" | "flat" }) {
  const color = tone === "up" ? "text-[#7fd8b4]" : tone === "down" ? "text-[#ee9a9a]" : "text-[#b6bec8]";
  return <span className="inline-flex items-baseline gap-1 rounded-md bg-white/[0.04] px-2 py-1 text-[10px]"><span className="text-[#717b87]">{label}</span><span className={`font-semibold tabular-nums ${color}`}>{value}</span></span>;
}
const tone = (v: number | null | undefined) => (v == null ? "flat" : v >= 0 ? "up" : "down");

function Strip({ e }: { e?: Enrichment }) {
  if (!e) return null;
  if (e.kind === "results" && e.status === "parsed" && e.metrics) {
    const rev = e.metrics.find((m) => m.metric === "Revenue");
    const pat = e.metrics.find((m) => m.metric === "PAT");
    return <div className="mt-2.5 flex flex-wrap gap-1.5">
      {rev && <Chip label="Rev YoY" value={pct(rev.yoy_pct)} tone={tone(rev.yoy_pct)} />}
      {rev && <Chip label="QoQ" value={pct(rev.qoq_pct)} tone={tone(rev.qoq_pct)} />}
      {pat && <Chip label="PAT YoY" value={pct(pat.yoy_pct)} tone={tone(pat.yoy_pct)} />}
      {pat && <Chip label="QoQ" value={pct(pat.qoq_pct)} tone={tone(pat.qoq_pct)} />}
    </div>;
  }
  if (e.kind === "eod") {
    return <div className="mt-2.5 flex flex-wrap gap-1.5">
      <Chip label="Move" value={pct(e.change_pct)} tone={tone(e.change_pct)} />
      <Chip label="Volume" value={`${multiple(e.volume_multiple)} avg`} tone="flat" />
      <Chip label="Catalyst" value={e.matched_filing ? "filed" : "none filed"} tone="flat" />
    </div>;
  }
  if (e.kind === "people" && e.people?.[0]?.name) {
    return <div className="mt-2.5 flex flex-wrap gap-1.5"><Chip label={e.action ?? "Person"} value={e.people[0].name} tone="flat" />{e.status === "parsed" && <Chip label="Profile" value="in filing" tone="flat" />}</div>;
  }
  return null;
}

export function AlertCard({
  alert,
  saved = false,
  onToggleSave,
}: {
  alert: AlertItem & { enrichment?: Enrichment };
  saved?: boolean;
  onToggleSave?: (id: string) => void;
}) {
  const source = alert.source_exchange === "EOD" ? "EOD" : alert.source_exchange ?? "NSE";
  return (
    <article className="group flex gap-2 border-b border-white/[0.055] px-4 py-4 last:border-b-0 sm:px-5">
      <Link className="flex min-w-0 flex-1 gap-3.5" href={`/events/${alert.id}`}>
        <CompanyMark color={alert.impact === "High" ? "#a0784a" : "#5e9f87"} initials={alert.symbol.slice(0, 2)} size="sm" />
        <div className="min-w-0 flex-1">
          <div className="mb-1.5 flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="text-[12px] font-semibold text-[#c9cfd6]">{alert.company}</span>
            <span className="text-[10px] text-[#69727e]">{alert.time}</span>
          </div>
          <h3 className="text-[14px] font-semibold leading-5 text-[#e9ecef] group-hover:text-white">{alert.title}</h3>
          <p className="mt-1 line-clamp-2 text-[12px] leading-[1.6] text-[#8d96a2]">{alert.summary}</p>
          <Strip e={alert.enrichment} />
          <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
            <Badge>{alert.type}</Badge><Badge>{alert.impact}</Badge><Badge>{source}</Badge>
            <span className="ml-auto hidden items-center gap-1 text-[10px] text-[#6f7985] group-hover:text-[#aab3be] sm:inline-flex">Open <Icon name="arrowRight" size={12} /></span>
          </div>
        </div>
      </Link>
      {onToggleSave && (
        <button aria-label={saved ? "Remove saved alert" : "Save alert"} type="button" onClick={() => onToggleSave(alert.id)}
          className={`mt-0.5 grid size-9 shrink-0 place-items-center rounded-lg transition ${saved ? "text-[#8ad8b9]" : "text-[#68727e] hover:bg-white/[0.06] hover:text-[#c2c8d0]"}`}>
          <Icon name="bookmark" size={15} />
        </button>
      )}
    </article>
  );
}
