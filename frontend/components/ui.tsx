import type { ReactNode } from "react";

import { Icon, type IconName } from "@/components/icons";

export function Panel({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`rounded-2xl border border-white/[0.075] bg-[#11161d] ${className}`}>{children}</section>;
}

export function PageHeading({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="mb-7 flex flex-col justify-between gap-4 sm:mb-8 sm:flex-row sm:items-end">
      <div>
        {eyebrow && <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-[#70cba9]">{eyebrow}</p>}
        <h1 className="text-[27px] font-semibold tracking-[-0.045em] text-[#f1f3f5] sm:text-[32px]">{title}</h1>
        {description && <p className="mt-2 max-w-2xl text-[13px] leading-6 text-[#858e9a]">{description}</p>}
      </div>
      {action}
    </div>
  );
}

export function SectionTitle({
  title,
  detail,
  action,
}: {
  title: string;
  detail?: string;
  action?: ReactNode;
}) {
  return (
    <div className="mb-4 flex items-center justify-between gap-3">
      <div className="flex min-w-0 items-baseline gap-2.5">
        <h2 className="text-[14px] font-semibold text-[#e7eaee]">{title}</h2>
        {detail && <span className="truncate text-[11px] text-[#707a87]">{detail}</span>}
      </div>
      {action}
    </div>
  );
}

export function CompanyMark({
  initials,
  color,
  size = "md",
}: {
  initials: string;
  color: string;
  size?: "sm" | "md" | "lg";
}) {
  const sizes = { sm: "size-8 text-[10px]", md: "size-10 text-[12px]", lg: "size-12 text-sm" };
  return (
    <span
      className={`grid shrink-0 place-items-center rounded-xl border border-white/[0.1] font-semibold text-white ${sizes[size]}`}
      style={{ background: `linear-gradient(145deg, ${color}cc, ${color}55)` }}
    >
      {initials}
    </span>
  );
}

export function Change({ value, positive }: { value: string; positive: boolean }) {
  return <span className={`inline-flex items-center gap-1 text-[11px] font-medium ${positive ? "text-[#71d0ad]" : "text-[#e58a8a]"}`}>
    <Icon name={positive ? "arrowUp" : "arrowDown"} size={12} strokeWidth={2} />{value}
  </span>;
}

const badgeColors: Record<string, string> = {
  Results: "border-[#665636]/50 bg-[#352b1b] text-[#e2bc79]",
  "Management changes": "border-[#4b4f7a]/50 bg-[#20223a] text-[#aab0f0]",
  Acquisitions: "border-[#62434a]/50 bg-[#332126] text-[#e0a1aa]",
  Fundraising: "border-[#62434a]/50 bg-[#332126] text-[#e0a1aa]",
  "Price move": "border-[#355d50]/50 bg-[#192d27] text-[#8fd2b6]",
  EOD: "border-[#355d50]/50 bg-[#192d27] text-[#8fd2b6]",
  High: "border-[#704847]/50 bg-[#35201f] text-[#ef9b93]",
  Medium: "border-[#564a38]/50 bg-[#2c271f] text-[#d6b981]",
};

export function Badge({ children, className = "" }: { children: string; className?: string }) {
  const color = badgeColors[children] ?? "border-white/[0.09] bg-white/[0.04] text-[#a5adb8]";
  return <span className={`inline-flex items-center rounded-md border px-2 py-1 text-[9px] font-semibold tracking-[0.03em] ${color} ${className}`}>{children}</span>;
}

export function SmallButton({
  children,
  icon,
  onClick,
  active = false,
  className = "",
}: {
  children?: ReactNode;
  icon?: IconName;
  onClick?: () => void;
  active?: boolean;
  className?: string;
}) {
  return (
    <button
      className={`inline-flex min-h-9 items-center justify-center gap-2 rounded-lg border px-3 text-[11px] font-medium transition ${active ? "border-[#477b68]/50 bg-[#17352d] text-[#8cdbbd]" : "border-white/[0.09] bg-white/[0.025] text-[#a4acb7] hover:bg-white/[0.07] hover:text-white"} ${className}`}
      onClick={onClick}
      type="button"
    >
      {icon && <Icon name={icon} size={14} />}{children}
    </button>
  );
}

export function Sparkline({ positive = true }: { positive?: boolean }) {
  return (
    <svg aria-hidden="true" className="h-7 w-[72px]" viewBox="0 0 72 28" fill="none">
      <path d={positive ? "M1 21 9 18 16 20 24 13 31 16 39 8 47 11 55 5 63 8 71 2" : "M1 5 9 8 16 6 24 12 31 9 39 16 47 13 55 20 63 17 71 25"} stroke={positive ? "#68c5a3" : "#d27d7d"} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function PortfolioChart({ range }: { range: string }) {
  const multiplier = range === "1M" ? "M0 78 C42 75 53 65 90 69 S138 45 172 51 220 38 252 45 300 22 338 31 390 20 428 25 470 9 520 12" : range === "1W" ? "M0 70 C38 72 48 54 92 60 S142 35 177 44 230 27 262 36 316 17 354 28 405 17 438 18 480 3 520 7" : "M0 67 C37 72 48 51 88 56 S133 36 169 45 215 24 254 33 305 18 345 26 389 12 429 18 474 5 520 8";
  return (
    <svg aria-label={`Portfolio value chart over ${range}`} className="h-[174px] w-full overflow-visible" preserveAspectRatio="none" role="img" viewBox="0 0 520 100">
      <defs><linearGradient id="portfolio-fill" x1="260" y1="0" x2="260" y2="100" gradientUnits="userSpaceOnUse"><stop stopColor="#55bd98" stopOpacity=".2"/><stop offset="1" stopColor="#55bd98" stopOpacity="0"/></linearGradient></defs>
      {[20, 45, 70, 95].map((y) => <line key={y} x1="0" x2="520" y1={y} y2={y} stroke="#ffffff" strokeOpacity=".07" strokeDasharray="3 5" />)}
      <path d={`${multiplier} L520 100 L0 100Z`} fill="url(#portfolio-fill)" />
      <path d={multiplier} fill="none" stroke="#72d0ae" strokeWidth="2" strokeLinecap="round" />
      <circle cx="520" cy={range === "1W" ? 7 : range === "1M" ? 12 : 8} r="3.5" fill="#85dfbd" stroke="#11161d" strokeWidth="2" />
    </svg>
  );
}

export function EmptyState({ icon = "search", title, description }: { icon?: IconName; title: string; description: string }) {
  return <div className="flex flex-col items-center py-14 text-center"><span className="grid size-11 place-items-center rounded-xl border border-white/[0.08] bg-white/[0.03] text-[#7e8996]"><Icon name={icon} size={19} /></span><p className="mt-4 text-[13px] font-semibold text-[#d9dee5]">{title}</p><p className="mt-1 max-w-sm text-[11px] leading-5 text-[#77818e]">{description}</p></div>;
}
