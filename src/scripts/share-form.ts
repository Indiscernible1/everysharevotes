import { formatInt, formatPeriod, formatTinyPct } from "../lib/format";
import { usableTurnstileSiteKey } from "../lib/turnstile-sitekey";

const TEST_SITEKEY = "1x00000000000000000000AA";
const DUMMY_TOKEN = "XXXX.DUMMY.TOKEN.XXXX";
const UNCONFIGURED =
  "Turnstile is not configured. Set PUBLIC_TURNSTILE_SITE_KEY to the real site key and redeploy.";

interface TurnstileApi {
  render(selector: string, options: { sitekey: string; callback: (token: string) => void }): string;
  reset(id?: string): void;
}

declare global {
  interface Window {
    turnstile?: TurnstileApi;
  }
}

const BROKERS = [
  "Schwab",
  "Fidelity",
  "Robinhood",
  "Webull",
  "E*TRADE/Morgan Stanley",
  "Vanguard",
  "Interactive Brokers",
  "Merrill",
  "SoFi",
  "Public",
  "Other",
];

const numberFormat = new Intl.NumberFormat("en-US");

interface BrokerMatch {
  status: "matched" | "none";
  filer?: string;
  shortLabel?: string;
  shares?: number;
  filingDate?: string;
  reportPeriod?: string;
  sourceUrl?: string;
  rule?: string;
}

interface BrokerMapFile {
  reportPeriod: string;
  tableShares: number;
  tableManagers: number;
  note?: string;
  brokers: Record<string, BrokerMatch>;
}

interface Totals {
  totals: { for: number; against: number; undecided: number };
  holders: number;
  byBroker: { broker: string; for: number; against: number; undecided: number }[];
  heldCount: number;
  yours?: { id: number; createdAt: string; broker: string; stance: string; shares: number; status: string }[];
  stored?: { status: string };
  error?: string;
  message?: string;
}

let widgetId = "";
let turnstileToken = "";
let acceptSubmit = false;
let brokerMap: BrokerMapFile | null = null;

export function mountShareForm(): void {
  const form = document.querySelector<HTMLFormElement>("#share-form");
  const status = document.querySelector<HTMLElement>("#share-status");
  if (!form || !status) return;
  const submitButton = form.querySelector<HTMLButtonElement>('button[type="submit"]');
  if (submitButton) submitButton.disabled = true;

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!acceptSubmit) return;
    void submitShare(form, status);
  });

  void (async () => {
    const [sitekey, map] = await Promise.all([resolveSiteKey(), loadBrokerMap()]);
    brokerMap = map;
    if (!sitekey) {
      showStatus(status, UNCONFIGURED, true);
      form.querySelectorAll("button, input, select, textarea").forEach((node) => {
        (node as HTMLInputElement).disabled = true;
      });
      void refresh();
      return;
    }
    acceptSubmit = true;
    if (submitButton) submitButton.disabled = false;
    void renderTurnstile(sitekey);
    void refresh();
  })();
}

async function submitShare(form: HTMLFormElement, status: HTMLElement): Promise<void> {
  const data = new FormData(form);
  const stance = String(data.get("stance") || "");
  const broker = String(data.get("broker") || "");
  const shares = Number(String(data.get("shares") || "").trim());
  if (!BROKERS.includes(broker) || !["for", "against", "undecided"].includes(stance)) {
    showStatus(status, "Choose a stance and a broker.", true);
    return;
  }
  if (!Number.isInteger(shares) || shares === 0) {
    showStatus(status, "Enter a whole number of shares, positive to add or negative to reduce. Zero is not stored.", true);
    return;
  }
  const token = turnstileToken || (isLocal() ? DUMMY_TOKEN : "");
  if (!token) {
    showStatus(status, "Complete the check above the button, then submit again.", true);
    return;
  }
  showStatus(status, "Saving…", false);
  const response = await fetch("/api/shares", {
    method: "POST",
    headers: { "content-type": "application/json", accept: "application/json" },
    body: JSON.stringify({ stance, broker, shares, turnstileToken: token }),
  });
  let payload: Partial<Totals> = {};
  try {
    payload = (await response.json()) as Partial<Totals>;
  } catch {
    payload = {};
  }
  turnstileToken = "";
  if (window.turnstile && widgetId) window.turnstile.reset(widgetId);
  if (!response.ok) {
    showStatus(status, payload.message || messageFor(payload.error), true);
    return;
  }
  if (payload.stored?.status === "held") {
    showStatus(status, "Stored and held for review. It is not in the public totals, so it is not shown against a 13F filer.", true);
  } else {
    showStoredComparison(status, broker, shares);
  }
  if (payload.totals) paint(payload as Totals);
  const sharesInput = form.querySelector<HTMLInputElement>('input[name="shares"]');
  if (sharesInput) sharesInput.value = "";
}

function showStatus(status: HTMLElement, message: string, alert: boolean): void {
  status.classList.remove("is-note");
  status.classList.toggle("is-alert", alert);
  status.replaceChildren(document.createTextNode(message));
  if (!alert) return;
  status.scrollIntoView({ behavior: "smooth", block: "center" });
}

function showStoredComparison(status: HTMLElement, broker: string, shares: number): void {
  status.classList.remove("is-alert");
  status.classList.add("is-note");
  const match = brokerMap?.brokers?.[broker];
  const size = Math.abs(shares);
  const shareText = `${shares > 0 ? "+" : ""}${numberFormat.format(shares)} shares`;
  status.replaceChildren();
  if (match?.status === "matched" && match.shares && match.shortLabel) {
    const pct = formatTinyPct(size, match.shares);
    status.append(
      document.createTextNode(
        `Stored. ${shareText} · ${pct} of ${match.shortLabel}’s reported 13F TSLA (${formatInt(match.shares)} shares, ${formatPeriod(match.reportPeriod)}, filed ${match.filingDate ?? "date not labeled"}). `,
      ),
    );
    if (match.sourceUrl) {
      const link = document.createElement("a");
      link.href = match.sourceUrl;
      link.textContent = "13F index";
      status.append(link, document.createTextNode(". "));
    }
    status.append(document.createTextNode("Self-reported retail, not part of that filer’s vote."));
  } else if (match?.status === "none") {
    status.append(
      document.createTextNode(`Stored. ${shareText} at ${broker}. No matching 13F filer in this file. Self-reported retail, not an institution’s vote.`),
    );
  } else {
    status.append(document.createTextNode(`Stored. ${shareText}. The 13F comparison did not load, so no percent is shown.`));
  }
  status.scrollIntoView({ behavior: "smooth", block: "center" });
}

async function loadBrokerMap(): Promise<BrokerMapFile | null> {
  try {
    const response = await fetch("/data/broker-13f.json", { headers: { accept: "application/json" } });
    if (!response.ok) return null;
    return (await response.json()) as BrokerMapFile;
  } catch {
    return null;
  }
}

function messageFor(error: string | undefined): string {
  if (error === "duplicate") return "That same share change at that broker is already stored on this browser.";
  if (error === "below_zero") return "That would take the counted shares for this broker and stance below zero.";
  if (error === "rate_limit") return "Too many submissions from this network. Try again later.";
  if (error === "turnstile") return "The check failed. Reload the page and try again.";
  if (error === "unconfigured") return "The tally is not configured on this server.";
  if (error === "invalid_shares") return "Enter a whole number of shares other than zero, up to one billion.";
  return "That submission was not stored.";
}

async function refresh(): Promise<void> {
  const response = await fetch("/api/shares", { headers: { accept: "application/json" } });
  if (!response.ok) {
    const status = document.querySelector<HTMLElement>("#share-status");
    if (status && !status.textContent) status.textContent = "The tally is not connected.";
    return;
  }
  paint((await response.json()) as Totals);
}

function paint(payload: Totals): void {
  const totals = document.querySelector<HTMLElement>("#live-totals");
  if (totals && payload.totals) {
    const holderWord = payload.holders === 1 ? "holder" : "holders";
    totals.textContent = `${numberFormat.format(payload.totals.for)} For · ${numberFormat.format(payload.totals.against)} Against · ${numberFormat.format(payload.totals.undecided)} Undecided · ${numberFormat.format(payload.holders)} ${holderWord}`;
  }
  const body = document.querySelector<HTMLElement>("#broker-body");
  if (body) {
    body.replaceChildren();
    const rows = payload.byBroker ?? [];
    if (rows.length === 0) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 6;
      td.textContent = "No counted shares yet.";
      tr.append(td);
      body.append(tr);
    } else {
      for (const row of rows) {
        const tr = document.createElement("tr");
        const counted = row.for + row.against + row.undecided;
        const match = brokerMap?.brokers?.[row.broker];
        for (const value of [row.broker, numberFormat.format(row.for), numberFormat.format(row.against), numberFormat.format(row.undecided)]) {
          const td = document.createElement("td");
          td.textContent = value;
          tr.append(td);
        }
        const pctCell = document.createElement("td");
        const filerCell = document.createElement("td");
        if (match?.status === "matched" && match.shares && match.shortLabel) {
          pctCell.textContent = `${formatInt(counted)} counted · ${formatTinyPct(counted, match.shares)} of ${match.shortLabel}’s reported 13F`;
          if (match.sourceUrl) {
            const link = document.createElement("a");
            link.href = match.sourceUrl;
            link.textContent = match.filer || "13F index";
            filerCell.append(link);
          } else {
            filerCell.textContent = match.filer || match.shortLabel;
          }
        } else if (!brokerMap) {
          pctCell.textContent = "—";
          filerCell.textContent = "13F comparison did not load";
        } else {
          pctCell.textContent = "—";
          filerCell.textContent = "no matching 13F filer";
        }
        tr.append(pctCell, filerCell);
        body.append(tr);
      }
    }
  }
  const yours = document.querySelector<HTMLElement>("#your-rows");
  if (yours) {
    yours.replaceChildren();
    const entries = payload.yours ?? [];
    if (entries.length === 0) {
      const li = document.createElement("li");
      li.textContent = "No rows stored on this browser yet.";
      yours.append(li);
    } else {
      for (const entry of entries) {
        const li = document.createElement("li");
        const sign = entry.shares > 0 ? "+" : "";
        li.textContent = `${entry.createdAt.slice(0, 16).replace("T", " ")} UTC · ${sign}${numberFormat.format(entry.shares)} ${entry.broker} · ${entry.stance} · ${entry.status}`;
        yours.append(li);
      }
    }
  }
  const held = document.querySelector<HTMLElement>("#held-note");
  if (held) {
    held.textContent = payload.heldCount
      ? `${payload.heldCount} ${payload.heldCount === 1 ? "entry is" : "entries are"} over 100,000 shares and held out of the totals.`
      : "";
  }
}

function isLocal(): boolean {
  return location.hostname === "localhost" || location.hostname === "127.0.0.1";
}

async function resolveSiteKey(): Promise<string> {
  const fromApi = usableTurnstileSiteKey(await fetchRuntimeSiteKey());
  if (fromApi) return fromApi;
  const fromMeta = usableTurnstileSiteKey(
    document.querySelector('meta[name="turnstile-sitekey"]')?.getAttribute("content"),
  );
  if (fromMeta) return fromMeta;
  if (isLocal()) return TEST_SITEKEY;
  return "";
}

async function fetchRuntimeSiteKey(): Promise<string> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 4000);
  try {
    const response = await fetch("/api/config", {
      headers: { accept: "application/json" },
      signal: controller.signal,
    });
    if (!response.ok) return "";
    const payload = (await response.json()) as { turnstileSiteKey?: unknown };
    return typeof payload.turnstileSiteKey === "string" ? payload.turnstileSiteKey : "";
  } catch {
    return "";
  } finally {
    window.clearTimeout(timer);
  }
}

function renderTurnstile(sitekey: string): void {
  const start = () => {
    if (!window.turnstile) return;
    widgetId = window.turnstile.render("#turnstile", {
      sitekey,
      callback: (token) => {
        turnstileToken = token;
      },
    });
  };
  if (window.turnstile) {
    start();
    return;
  }
  const timer = window.setInterval(() => {
    if (window.turnstile) {
      window.clearInterval(timer);
      start();
    }
  }, 200);
  window.setTimeout(() => window.clearInterval(timer), 10000);
}
