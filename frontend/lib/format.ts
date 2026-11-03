export const pct = (value: number | null | undefined, digits = 1) =>
  value == null ? "—" : `${value >= 0 ? "+" : "−"}${Math.abs(value).toFixed(digits)}%`;

export const crore = (value: number | null | undefined) =>
  value == null ? "—" : `₹${value.toLocaleString("en-IN", { maximumFractionDigits: value >= 1000 ? 0 : 1 })} Cr`;

export const rupees = (value: number | null | undefined) =>
  value == null ? "—" : `₹${value.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;

export const multiple = (value: number | null | undefined) => (value == null ? "—" : `${value.toFixed(1)}×`);

export function istNow() {
  const now = new Date();
  const hour = Number(new Intl.DateTimeFormat("en-IN", { hour: "numeric", hour12: false, timeZone: "Asia/Kolkata" }).format(now));
  const greeting = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
  const date = new Intl.DateTimeFormat("en-IN", { weekday: "long", day: "numeric", month: "long", timeZone: "Asia/Kolkata" }).format(now);
  return { greeting, date };
}
