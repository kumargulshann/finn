import type { AlertItem, Holding } from "@/lib/types";

const apiBaseUrl = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "").replace(/\/$/, "");

export type MarketData = { status: "fresh" | "cached" | "stale" | "unavailable"; source: string; close: number | null; previous_close: number | null; change_percent: number | null; volume: number | null; market_as_of: string | null; fetched_at: string; error: string | null; is_demo: false };
export type PortfolioResponse = { id: number | null; name: string; is_demo: boolean; holdings: ApiHolding[]; market_data_source?: string; latest_available_as_of?: string | null; summary?: { companies_tracked: number; portfolio_value: number | null; daily_change_value: number | null; daily_change_percent: number | null; valuation_status: string; valuation_note: string } };
export type ApiHolding = { id: string; company_id: number; name: string; symbol: string; exchange: string; sector: string; price: number | null; change: number | null; positive: boolean | null; weight: number; market_data: MarketData | null; is_demo: boolean };
export type ApiAlert = AlertItem & { company_id: number; sector: string; published_at: string; is_demo: boolean; is_read: boolean; is_saved: boolean; portfolio_weight: number | null; price: number | null; daily_change: number | null; market_data?: MarketData | null };
export type CompanySearchResult = { id: number; name: string; symbol: string; exchange: string; sector: string; in_portfolio: boolean; is_demo: boolean };
export type CompanyInfo = { id: number; name: string; sector: string; instruments: { symbol: string; exchange: string }[]; market_data: MarketData | null; in_portfolio: boolean; weight: number | null; metrics: { metric: string; value: number; unit: string; period: string; is_demo: boolean }[]; announcements: { id: string; title: string; summary: string; category: string; published_at: string; source_name: string; source_url: string; is_demo: boolean }[]; source_status: string; is_demo: boolean };
export type AlertRule = { id: number; name: string; category: string; enabled: boolean; threshold: number | null };
export type PriceHistory = { symbol: string; source: string; status: string; market_as_of: string | null; fetched_at: string; error?: string | null; items: { date: string; open: number | null; high: number | null; low: number | null; close: number; volume: number | null }[] };
export type ResearchDocument = { id: number; title: string; document_type: "annual_report" | "earnings_transcript"; fiscal_period: string | null; published_at: string | null; source_name: string; source_url: string; page_count: number; fetched_at: string; is_demo: boolean };
export type KeyClaim = { claim: string; document_title: string; fiscal_period: string | null; page: number; source_url: string };
export type EvidenceSufficiency = { status: "sufficient" | "partial" | "insufficient"; explanation: string };
export type ResearchAnswer = { company_id: number; lens: string; question: string; answer: string; evidence_gap: string | null; key_claims?: KeyClaim[]; conflicting_info?: string | null; evidence_sufficiency?: EvidenceSufficiency; citations: { document_id: number; document_title: string; document_type: string; fiscal_period: string | null; page: number; excerpt: string; source_url: string; source_name: string }[]; financial_metrics: string[]; management_guidance: string[]; business_updates: string[]; bull_evidence: { excerpt: string; document_title: string; page: number; source_url: string }[]; bear_evidence: { excerpt: string; document_title: string; page: number; source_url: string }[]; document_count: number; is_demo: false };
export type GuidanceActual = { company_id: number; evidence_gap: string | null; is_demo: false; quarters: { period: string; metrics: { metric: string; unit: string | null; guided_value: string | null; actual_value: string | null; variance: string | null; met_guidance: string; guided_source: { excerpt: string; document_title: string; page: number; source_url: string } | null; actual_source: { excerpt: string; document_title: string; page: number; source_url: string } | null }[] }[] };

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}/api/v1${path}`, { ...init, cache: "no-store", signal: init?.signal ?? AbortSignal.timeout(30000), headers: { "Content-Type": "application/json", ...init?.headers } });
  } catch {
    throw new Error(`Could not connect to FINN API at ${apiBaseUrl}. Check that the backend is running.`);
  }
  if (!response.ok) {
    let message = `FINN API returned HTTP ${response.status}.`;
    try { const body = await response.json() as { detail?: string }; if (body.detail) message = body.detail; } catch { /* Keep the HTTP status message. */ }
    throw new Error(message);
  }
  return (await response.json()) as T;
}

export const getPortfolio = () => apiFetch<PortfolioResponse>("/portfolio");
export const getDigest = (period: string) => apiFetch<{ items: ApiAlert[]; count: number; is_demo: boolean }>(`/digest?period=${encodeURIComponent(period)}`);
export const getAlert = (id: string) => apiFetch<ApiAlert>(`/events/${encodeURIComponent(id)}`);
export const updateAlert = (id: string, update: { is_read?: boolean; is_saved?: boolean }) => apiFetch<{ id: string; is_read: boolean; is_saved: boolean }>(`/events/${encodeURIComponent(id)}?${new URLSearchParams(Object.entries(update).map(([key, value]) => [key, String(value)]))}`, { method: "PATCH" });
export const searchCompanies = (q = "") => apiFetch<{ items: CompanySearchResult[]; is_demo: boolean }>(`/companies?q=${encodeURIComponent(q)}`);
export const getCompany = (id: number) => apiFetch<CompanyInfo>(`/companies/${id}`);
export const getCompanyPrices = (id: number, period = "1mo") => apiFetch<PriceHistory>("/companies/" + id + "/prices?period=" + encodeURIComponent(period));
export const getResearchDocuments = (id: number) => apiFetch<{ items: ResearchDocument[]; count: number; company_id: number }>(`/companies/${id}/research/documents`);
export const refreshResearchDocuments = (limit = 5, symbol?: string, transcriptsPerCompany = 1) => apiFetch<{ companies: string[]; catalogued: number; indexed: number; unchanged: number; errors: string[] }>(`/research/documents/refresh?limit=${limit}&include_transcripts=true&transcripts_per_company=${transcriptsPerCompany}${symbol ? `&symbols=${encodeURIComponent(symbol)}` : ""}`, { method: "POST", signal: AbortSignal.timeout(300000) });
export const askResearch = (company_id: number, question: string, lens: string) => apiFetch<ResearchAnswer>("/research/answer", { method: "POST", body: JSON.stringify({ company_id, question, lens }) });
export const getGuidanceActual = (company_id: number) => apiFetch<GuidanceActual>("/research/guidance-vs-actual", { method: "POST", body: JSON.stringify({ company_id }) });
export const getAlertRules = () => apiFetch<{ items: AlertRule[]; is_demo: boolean }>("/alert-rules");
export const updateAlertRule = (id: number, params: { enabled?: boolean; threshold?: number }) => apiFetch<AlertRule>(`/alert-rules/${id}?${new URLSearchParams(Object.entries(params).map(([key, value]) => [key, String(value)]))}`, { method: "PATCH" });
export const setHoldingTracked = (symbol: string, enabled: boolean) => apiFetch<{ symbol: string; tracked: boolean }>(`/portfolio/holdings/${encodeURIComponent(symbol)}?enabled=${enabled}`, { method: "PUT" });

export function toHolding(item: ApiHolding): Holding {
  const available = item.price !== null && item.change !== null;
  const move = item.change === null ? "Unavailable" : (item.change >= 0 ? "+" : "-") + Math.abs(item.change).toFixed(2) + "%";
  return { id: item.id, name: item.name, symbol: item.symbol, sector: item.sector, price: item.price === null ? "Unavailable" : item.price.toLocaleString("en-IN", { maximumFractionDigits: 2 }), change: move, positive: available ? item.positive ?? false : false, weight: item.weight.toFixed(1) + "%", initials: item.name.slice(0, 1), color: "#5e9f87" };
}
export function toAlert(item: ApiAlert): AlertItem {
  return { ...item, is_demo: item.is_demo } as AlertItem;
}
