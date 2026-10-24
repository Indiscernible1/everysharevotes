import { renderChart, type ChartSeries } from "./chart";

const numberFormat = new Intl.NumberFormat("en-US");

interface ShareResponse {
  totals?: { for: number; against: number; undecided: number };
  holders?: number;
  series?: { date: string; pctFor: number | null }[];
  heldCount?: number;
  error?: string;
}

interface SentimentFile {
  media?: { points?: { date: string; display: number }[]; method?: string };
  market?: { primary?: { question?: string; points?: { date: string; yes: number }[] } | null };
}

export async function mountDashboard(compact: boolean): Promise<void> {
  const chartHost = document.querySelector<HTMLElement>("#sentiment-chart");
  const [sharesResult, sentimentResult] = await Promise.allSettled([
    fetch("/api/shares", { headers: { accept: "application/json" } }).then(async (response) => {
      const payload = (await response.json()) as ShareResponse;
      if (!response.ok) throw new Error(payload.error || "unavailable");
      return payload;
    }),
    fetch("/data/sentiment.json", { headers: { accept: "application/json" } }).then(async (response) => {
      if (!response.ok) throw new Error("sentiment file");
      return (await response.json()) as SentimentFile;
    }),
  ]);

  const shares = sharesResult.status === "fulfilled" ? sharesResult.value : null;
  paintTotals(shares);
  if (!chartHost) return;
  const sentiment = sentimentResult.status === "fulfilled" ? sentimentResult.value : null;
  const retail: ChartSeries = {
    id: "retail",
    label: "Retail % For",
    color: "#0c4f3c",
    points: (shares?.series ?? [])
      .filter((point) => point.pctFor !== null && point.pctFor !== undefined)
      .map((point) => ({ date: point.date, value: Number(point.pctFor) })),
  };
  const media: ChartSeries = {
    id: "media",
    label: "Media score",
    color: "#7a3412",
    points: (sentiment?.media?.points ?? []).map((point) => ({ date: point.date, value: Number(point.display) })),
  };
  const market: ChartSeries = {
    id: "market",
    label: "Polymarket YES",
    color: "#0b3a82",
    points: (sentiment?.market?.primary?.points ?? []).map((point) => ({ date: point.date, value: Number(point.yes) * 100 })),
  };
  renderChart(chartHost, [retail, media, market], compact);
  const note = document.querySelector<HTMLElement>("#chart-note");
  if (note) {
    const mediaText = media.points.length ? "Media score is on the chart." : "Media: no scored headlines yet.";
    const marketText = market.points.length
      ? `Market line: ${sentiment?.market?.primary?.question ?? "Polymarket"}.`
      : "Market: no market yet.";
    note.textContent = `${mediaText} ${marketText}`;
  }
}

function paintTotals(shares: ShareResponse | null): void {
  const forNode = document.querySelector<HTMLElement>("#for-shares");
  const againstNode = document.querySelector<HTMLElement>("#against-shares");
  const meta = document.querySelector<HTMLElement>("#score-meta");
  if (!forNode || !againstNode || !meta) return;
  if (!shares?.totals) {
    forNode.textContent = "—";
    againstNode.textContent = "—";
    meta.textContent = "The tally is not connected. Nothing here is a made-up zero.";
    return;
  }
  forNode.textContent = numberFormat.format(shares.totals.for);
  againstNode.textContent = numberFormat.format(shares.totals.against);
  const holders = shares.holders ?? 0;
  const undecided = numberFormat.format(shares.totals.undecided);
  const held = shares.heldCount ? ` ${shares.heldCount} ${shares.heldCount === 1 ? "entry is" : "entries are"} held for review and not included.` : "";
  meta.textContent = `${numberFormat.format(holders)} ${holders === 1 ? "holder" : "holders"} · ${undecided} undecided shares.${held}`;
}
