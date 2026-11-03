"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { Icon, type IconName } from "@/components/icons";
import { getPortfolio, toHolding } from "@/lib/api";
import type { Holding } from "@/lib/types";

const navigation: { label: string; href: string; icon: IconName }[] = [
  { label: "Today", href: "/", icon: "home" },
  { label: "Research", href: "/research", icon: "spark" },
  { label: "Settings", href: "/settings", icon: "settings" },
];

function NavLinks({ mobile = false }: { mobile?: boolean }) {
  const pathname = usePathname();
  return navigation.map((item) => {
    const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
    return (
      <Link
        aria-current={active ? "page" : undefined}
        className={`group flex items-center gap-3 rounded-lg px-3 py-2.5 text-[13px] font-medium transition ${
          active
            ? "bg-white/[0.085] text-white"
            : "text-[#87909e] hover:bg-white/[0.045] hover:text-[#e6e9ef]"
        } ${mobile ? "flex-col gap-1 px-2 py-2 text-[10px]" : ""}`}
        href={item.href}
        key={item.href}
      >
        <Icon className={active ? "text-[#77d4b4]" : "text-current"} name={item.icon} size={mobile ? 20 : 17} />
        <span>{item.label}</span>
      </Link>
    );
  });
}

export function AppShell({ children }: Readonly<{ children: ReactNode }>) {
  const pathname = usePathname();
  const [watchlist, setWatchlist] = useState<Holding[]>([]);
  useEffect(() => {
    let active = true;
    getPortfolio().then((result) => { if (active) setWatchlist(result.holdings.slice(0, 4).map(toHolding)); }).catch(() => { if (active) setWatchlist([]); });
    return () => { active = false; };
  }, []);
  const pageLabel = pathname.startsWith("/events/")
    ? "Alert detail"
    : pathname.startsWith("/research")
      ? "Research"
      : pathname.startsWith("/settings")
        ? "Settings"
        : "Today";

  return (
    <div className="min-h-screen bg-[#0b0e13] text-[#f4f6f8]">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-[246px] flex-col border-r border-white/[0.065] bg-[#0e1218] px-4 py-5 lg:flex">
        <Link className="mb-9 flex items-center gap-3 px-2" href="/">
          <span className="grid size-9 place-items-center rounded-xl border border-[#3b695b] bg-[#17352d] text-[#91e3c4]">
            <Icon name="activity" size={19} />
          </span>
          <span className="text-[18px] font-semibold tracking-[-0.04em]">FINN<span className="text-[#73c9aa]">.</span></span>
        </Link>

        <p className="mb-2 px-3 text-[10px] font-semibold uppercase tracking-[0.16em] text-[#5d6673]">Workspace</p>
        <nav aria-label="Main navigation" className="space-y-1">
          <NavLinks />
        </nav>

        <div className="mt-9">
          <div className="mb-3 flex items-center justify-between px-3">
            <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[#5d6673]">Watchlist</p>
            <span className="text-[10px] text-[#626c79]">{watchlist.length || "—"}</span>
          </div>
          <div className="space-y-1">
            {watchlist.map((holding) => (
              <div className="flex items-center justify-between rounded-lg px-3 py-2 text-[11px]" key={holding.symbol}>
                <div>
                  <p className="font-medium text-[#d8dce3]">{holding.symbol}</p>
                  <p className="mt-0.5 text-[#69727f]">INR {holding.price}</p>
                </div>
                <span className={holding.positive ? "text-[#72d1af]" : "text-[#e98888]"}>{holding.change}</span>
              </div>
            ))}
            {!watchlist.length && <p className="px-3 py-2 text-[10px] text-[#69727f]">Portfolio unavailable</p>}
          </div>
        </div>

        <div className="mt-auto rounded-xl border border-white/[0.07] bg-[#121820] p-3.5">
          <div className="flex items-center gap-2">
            <span className="size-1.5 rounded-full bg-[#e4ae63]" />
            <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[#a2abb8]">Demo environment</span>
          </div>
          <p className="mt-2 text-[11px] leading-5 text-[#727d8a]">Demo portfolio · live NSE filings and EOD prices</p>
        </div>
        <div className="mt-4 flex items-center gap-3 px-2 pb-1">
          <div className="grid size-8 place-items-center rounded-full bg-[#253239] text-[11px] font-semibold text-[#a8d7c5]">SK</div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-[11px] font-medium text-[#d9dde3]">Sam Kapoor</p>
            <p className="truncate text-[10px] text-[#68727e]">ENAM Holdings</p>
          </div>
          <Icon className="text-[#636c77]" name="dots" size={17} />
        </div>
      </aside>

      <div className="lg:pl-[246px]">
        <header className="sticky top-0 z-20 flex h-[62px] items-center justify-between border-b border-white/[0.065] bg-[#0b0e13]/95 px-5 backdrop-blur sm:px-8">
          <div className="flex items-center gap-3 lg:hidden">
            <span className="grid size-8 place-items-center rounded-lg border border-[#3b695b] bg-[#17352d] text-[#91e3c4]"><Icon name="activity" size={17} /></span>
            <span className="text-[16px] font-semibold tracking-[-0.04em]">FINN<span className="text-[#73c9aa]">.</span></span>
          </div>
          <div className="hidden items-center gap-2 text-[11px] text-[#727c89] lg:flex">
            <span>ENAM HOLDINGS</span><span className="text-[#454e59]">/</span><span className="text-[#c8cdd5]">{pageLabel}</span>
          </div>
          <div className="ml-auto flex items-center gap-2 sm:gap-4">
            <div className="hidden items-center gap-2 rounded-full border border-white/[0.075] px-3 py-1.5 md:flex">
              <span className="size-1.5 rounded-full bg-[#75d0ae]" />
              <span className="text-[10px] font-medium text-[#9ea7b3]">Daily EOD</span>
              <span className="text-[10px] text-[#68727e]">·</span>
              <span className="text-[10px] text-[#7e8793]">NSE</span>
            </div>
            <Link aria-label="Search research" className="grid size-9 place-items-center rounded-lg text-[#8a94a1] transition hover:bg-white/[0.06] hover:text-white" href="/research"><Icon name="search" size={18} /></Link>
            <Link aria-label="Settings" className="grid size-9 place-items-center rounded-lg text-[#8a94a1] transition hover:bg-white/[0.06] hover:text-white" href="/settings"><Icon name="bell" size={18} /><span className="absolute ml-5 mt-[-14px] size-1.5 rounded-full bg-[#e9b465]" /></Link>
            <div className="hidden size-8 place-items-center rounded-full border border-white/[0.09] bg-[#1c252b] text-[10px] font-semibold text-[#b8ddce] sm:grid">SK</div>
          </div>
        </header>

        <main className="mx-auto min-h-[calc(100vh-62px)] max-w-[1520px] px-4 pb-28 pt-6 sm:px-8 sm:pt-8 lg:px-10 lg:pb-10">
          {children}
        </main>
      </div>

      <nav aria-label="Mobile navigation" className="fixed inset-x-0 bottom-0 z-40 grid grid-cols-3 border-t border-white/[0.08] bg-[#0e1218]/95 px-5 pb-[max(env(safe-area-inset-bottom),8px)] pt-2 backdrop-blur-lg lg:hidden">
        <NavLinks mobile />
      </nav>
    </div>
  );
}
