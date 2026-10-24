export function formatInt(value: number): string {
  return new Intl.NumberFormat("en-US").format(value);
}

/** Share of a reported-share denominator. Not a percent of shares outstanding. */
export function formatSharePct(shares: number, total: number): string {
  if (!Number.isFinite(shares) || !Number.isFinite(total) || total <= 0) return "—";
  if (shares === 0) return "0%";
  const pct = (shares / total) * 100;
  if (pct > 0 && pct < 0.01) return "<0.01%";
  return `${pct.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`;
}

export function formatUsd(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);
}

export function formatPeriod(iso: string | null | undefined): string {
  if (!iso) return "Report period not labeled";
  if (!/^\d{4}-\d{2}-\d{2}$/.test(iso)) return iso;
  const [year, month, day] = iso.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  const pretty = date.toLocaleDateString("en-US", {
    timeZone: "UTC",
    month: "long",
    day: "numeric",
    year: "numeric",
  });
  return `Report period ended ${pretty}`;
}

export function formatDay(iso: string): string {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(iso)) return iso;
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day)).toLocaleDateString("en-US", {
    timeZone: "UTC",
    month: "long",
    day: "numeric",
    year: "numeric",
  });
}
