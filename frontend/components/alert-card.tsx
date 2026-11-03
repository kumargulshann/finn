import Link from "next/link";

import { Icon } from "@/components/icons";
import { Badge, CompanyMark } from "@/components/ui";
import type { AlertItem } from "@/lib/types";

export function AlertCard({
  alert,
  saved = false,
  onToggleSave,
}: {
  alert: AlertItem;
  saved?: boolean;
  onToggleSave?: (id: string) => void;
}) {
  return (
    <article className="group flex gap-2 border-b border-white/[0.055] px-4 py-4 last:border-b-0 sm:px-5">
      <Link className="flex min-w-0 flex-1 gap-3.5" href={`/events/${alert.id}`}>
        <CompanyMark color={alert.color} initials={alert.initials} size="sm" />
        <div className="min-w-0 flex-1">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <span className="text-[11px] font-medium text-[#c2c8d0]">{alert.company}</span>
            <span className="text-[10px] text-[#69727e]">{alert.symbol}</span>
            <span className="text-[10px] text-[#58616d]">·</span>
            <span className="text-[10px] text-[#69727e]">{alert.time}</span>
          </div>
          <h3 className="text-[13px] font-semibold leading-5 text-[#e5e8ec] transition group-hover:text-white sm:text-[14px]">{alert.title}</h3>
          <p className="mt-1.5 line-clamp-2 text-[11px] leading-[1.65] text-[#89929f]">{alert.summary}</p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Badge>{alert.type}</Badge><Badge>{alert.impact}</Badge><Badge>{alert.is_demo ? "SAMPLE" : "EXCHANGE"}</Badge>
            <span className="ml-auto hidden items-center gap-1 text-[10px] text-[#6f7985] group-hover:text-[#aab3be] sm:inline-flex">Read analysis <Icon name="arrowRight" size={12} /></span>
          </div>
        </div>
      </Link>
      {onToggleSave && (
        <button
          aria-label={saved ? "Remove saved alert" : "Save alert"}
          className={`mt-0.5 grid size-8 shrink-0 place-items-center rounded-lg transition ${saved ? "text-[#8ad8b9]" : "text-[#68727e] hover:bg-white/[0.06] hover:text-[#c2c8d0]"}`}
          onClick={() => onToggleSave(alert.id)}
          type="button"
        >
          <Icon name="bookmark" size={15} />
        </button>
      )}
    </article>
  );
}
