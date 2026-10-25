import { formatInt, formatPeriod, formatTinyPct } from "../lib/format";
import { renderChart, type ChartSeries } from "./chart";

const numberFormat = new Intl.NumberFormat("en-US");
const EXTRA_COLORS = ["#6b4c9a", "#0e7490", "#9a3412", "#3f6212", "#9f1239", "#155e75"];

interface ShareResponse {
  totals?: { for: number; against: number; undecided: number };
  holders?: number;
  series?: { date: string; pctFor: number | null }[];
  heldCount?: number;
  error?: string;
}

interface MarketSeries {
  id: string;
  venue?: string;
  question?: string;
  url?: string;
  points?: { date: string; yes: number }[];
  historyStatus?: number;
  asOf?: string;
}

interface SentimentFile {
  generatedAt?: string | null;
  media?: {
    method?: string;
    points?: { date: string; display: number }[];
    requests?: { status: number; points: number }[];
    cached?: boolean;
    cachedFrom?: string | null;
  };
  market?: {
    primary?: { question?: string; points?: { date: string; yes: number }[]; asOf?: string } | null;
    chartable?: MarketSeries[];
  };
}

interface BrokerMapFile {
  reportPeriod: string;
  tableShares: number;
  brokers: Record<string, { status: string }>;
}

export async function mountDashboard(compact: boolean): Promise<void> {
  const chartHost = document.querySelector<HTMLElement>("#sentiment-chart");
  const [sharesResult, sentimentResult, brokerResult] = await Promise.allSettled([
    fetch("/api/shares", { headers: { accept: "application/json" } }).then(async (response) => {
      const payload = (await response.json()) as ShareResponse;
      if (!response.ok) throw new Error(payload.error || "unavailable");
      return payload;
    }),
    fetch("/data/sentiment.json", { headers: { accept: "application/json" } }).then(async (response) => {
      if (!response.ok) throw new Error("sentiment file");
      return (await response.json()) as SentimentFile;
    }),
    fetch("/data/broker-13f.json", { headers: { accept: "application/json" } }).then(async (response) => {
      if (!response.ok) throw new Error("broker map");
      return (await response.json()) as BrokerMapFile;
    }),
  ]);

  const shares = sharesResult.status === "fulfilled" ? sharesResult.value : null;
  const sentiment = sentimentResult.status === "fulfilled" ? sentimentResult.value : null;
  const brokerMap = brokerResult.status === "fulfilled" ? brokerResult.value : null;
  paintTotals(shares, brokerMap);
  if (!chartHost) return;

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
  const extras = (sentiment?.market?.chartable ?? []).filter((series) => (series.points?.length ?? 0) > 0);
  const extraSeries: ChartSeries[] = extras.map((series, index) => ({
    id: series.id,
    label: series.question || series.venue || series.id,
    color: EXTRA_COLORS[index % EXTRA_COLORS.length],
    points: (series.points ?? []).map((point) => ({ date: point.date, value: Number(point.yes) * 100 })),
  }));

  const selected = new Set<string>();
  const draw = () => {
    const shown = [retail, media, market, ...extraSeries.filter((series) => selected.has(series.id))];
    renderChart(chartHost, shown, compact);
    paintNote(sentiment, media.points.length > 0, market.points.length > 0);
    paintStamps(shares, sentiment, retail, media, market);
  };

  if (!compact) mountToggles(extras, selected, draw);
  draw();
}

function paintNote(sentiment: SentimentFile | null, hasMedia: boolean, hasMarket: boolean): void {
  const note = document.querySelector<HTMLElement>("#chart-note");
  if (!note) return;
  const mediaText = hasMedia ? "Media score is on the chart." : "Media: no scored headlines yet.";
  const marketText = hasMarket
    ? `Default market line: ${sentiment?.market?.primary?.question ?? "Polymarket"}.`
    : "Market: no market yet.";
  const extra = sentiment?.market?.chartable?.length
    ? " Other questions stay off the default line until selected."
    : "";
  note.textContent = `${mediaText} ${marketText}${extra}`;
}

function paintStamps(
  shares: ShareResponse | null,
  sentiment: SentimentFile | null,
  retail: ChartSeries,
  media: ChartSeries,
  market: ChartSeries,
): void {
  const list = document.querySelector<HTMLElement>("#series-stamps");
  if (!list) return;
  list.replaceChildren();
  const retailLatest = retail.points[retail.points.length - 1];
  addStamp(
    list,
    retailLatest
      ? `Retail: live ledger, ${retailLatest.value.toFixed(1)} on ${retailLatest.date}. For divided by For plus Against.`
      : "Retail: no counted For and Against shares yet, so the line has no point.",
  );
  const mediaRequest = sentiment?.media?.requests?.[sentiment.media.requests.length - 1];
  const mediaStatus = mediaRequest ? ` Last request HTTP ${mediaRequest.status}.` : "";
  const mediaCache = sentiment?.media?.cached ? ` Kept points from ${sentiment.media.cachedFrom ?? "an earlier fetch"}.` : "";
  addStamp(
    list,
    media.points.length
      ? `Media: ${sentiment?.media?.method ?? "scored"}, file ${sentiment?.generatedAt ?? "undated"}, ${media.points.length} days.${mediaStatus}${mediaCache}`
      : `Media: no points. File ${sentiment?.generatedAt ?? "undated"}.${mediaStatus}`,
  );
  const marketLatest = market.points[market.points.length - 1];
  addStamp(
    list,
    marketLatest
      ? `Polymarket Dec 31 YES: ${marketLatest.value.toFixed(1)} on ${marketLatest.date}. File ${sentiment?.generatedAt ?? "undated"}.`
      : "Polymarket: no YES history in the file.",
  );
  if (!shares) addStamp(list, "The ledger did not load, so the retail line is missing rather than drawn as zero.");
}

function addStamp(list: HTMLElement, text: string): void {
  const li = document.createElement("li");
  li.textContent = text;
  list.append(li);
}

function mountToggles(extras: MarketSeries[], selected: Set<string>, draw: () => void): void {
  const host = document.querySelector<HTMLElement>("#market-toggles");
  if (!host) return;
  host.replaceChildren();
  if (extras.length === 0) {
    host.textContent = "No other market returned a price history, so nothing else can be added to the chart.";
    return;
  }
  const legend = document.createElement("p");
  legend.className = "source";
  legend.textContent = "Each box is a different question. Turning one on draws it. The lines are not averaged.";
  host.append(legend);
  for (const series of extras) {
    const label = document.createElement("label");
    label.className = "choice";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.addEventListener("change", () => {
      if (input.checked) selected.add(series.id);
      else selected.delete(series.id);
      draw();
    });
    const text = document.createElement("span");
    const latest = series.points?.[series.points.length - 1];
    text.textContent = `${series.venue ?? "Market"}: ${series.question ?? series.id}${latest ? ` · last YES ${(latest.yes * 100).toFixed(1)} on ${latest.date}` : ""}`;
    label.append(input, text);
    host.append(label);
  }
}

function paintTotals(shares: ShareResponse | null, brokerMap: BrokerMapFile | null): void {
  const forNode = document.querySelector<HTMLElement>("#for-shares");
  const againstNode = document.querySelector<HTMLElement>("#against-shares");
  const meta = document.querySelector<HTMLElement>("#score-meta");
  const versus = document.querySelector<HTMLElement>("#retail-vs-13f");
  if (forNode && againstNode && meta) {
    if (!shares?.totals) {
      forNode.textContent = "—";
      againstNode.textContent = "—";
      meta.textContent = "The tally is not connected. Nothing here is a made-up zero.";
    } else {
      forNode.textContent = numberFormat.format(shares.totals.for);
      againstNode.textContent = numberFormat.format(shares.totals.against);
      const holders = shares.holders ?? 0;
      const undecided = numberFormat.format(shares.totals.undecided);
      const held = shares.heldCount
        ? ` ${shares.heldCount} ${shares.heldCount === 1 ? "entry is" : "entries are"} held for review and not included.`
        : "";
      meta.textContent = `${numberFormat.format(holders)} ${holders === 1 ? "holder" : "holders"} · ${undecided} undecided shares.${held}`;
    }
  }
  if (!versus) return;
  if (!shares?.totals || !brokerMap || brokerMap.tableShares <= 0) {
    versus.textContent = "";
    return;
  }
  const forPct = formatTinyPct(shares.totals.for, brokerMap.tableShares);
  const againstPct = formatTinyPct(shares.totals.against, brokerMap.tableShares);
  versus.textContent = `Self-reported For is ${forPct} of ${formatInt(brokerMap.tableShares)} reported 13F shares in the holders table (${formatPeriod(brokerMap.reportPeriod)}). Against is ${againstPct}. Not part of any institution’s vote.`;
}
