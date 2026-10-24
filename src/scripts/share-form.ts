const TEST_SITEKEY = "1x00000000000000000000AA";
const DUMMY_TOKEN = "XXXX.DUMMY.TOKEN.XXXX";

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

export function mountShareForm(): void {
  const form = document.querySelector<HTMLFormElement>("#share-form");
  const status = document.querySelector<HTMLElement>("#share-status");
  if (!form || !status) return;
  const sitekey = turnstileSiteKey();
  if (!sitekey) {
    status.textContent = "Turnstile is not configured for this host, so submissions are off.";
    form.querySelectorAll("button, input, select").forEach((node) => {
      (node as HTMLInputElement).disabled = true;
    });
    return;
  }
  void renderTurnstile(sitekey);
  void refresh();
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(form);
    const stance = String(data.get("stance") || "");
    const broker = String(data.get("broker") || "");
    const shares = Number(String(data.get("shares") || "").trim());
    if (!BROKERS.includes(broker) || !["for", "against", "undecided"].includes(stance)) {
      status.textContent = "Choose a stance and a broker.";
      return;
    }
    if (!Number.isInteger(shares) || shares === 0) {
      status.textContent = "Enter a whole number of shares, positive to add or negative to reduce. Zero is not stored.";
      return;
    }
    const token = turnstileToken || (isLocal() ? DUMMY_TOKEN : "");
    if (!token) {
      status.textContent = "Complete the check above the button, then submit again.";
      return;
    }
    status.textContent = "Saving…";
    const response = await fetch("/api/shares", {
      method: "POST",
      headers: { "content-type": "application/json", accept: "application/json" },
      body: JSON.stringify({ stance, broker, shares, turnstileToken: token }),
    });
    const payload = (await response.json()) as Totals;
    turnstileToken = "";
    if (window.turnstile && widgetId) window.turnstile.reset(widgetId);
    if (!response.ok) {
      status.textContent = payload.message || messageFor(payload.error);
      return;
    }
    status.textContent =
      payload.stored?.status === "held"
        ? "Stored and held for review. It is not in the public totals."
        : "Stored. The public totals include this row.";
    paint(payload);
    const sharesInput = form.querySelector<HTMLInputElement>('input[name="shares"]');
    if (sharesInput) sharesInput.value = "";
  });
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
    if (status) status.textContent = "The tally is not connected.";
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
      td.colSpan = 4;
      td.textContent = "No counted shares yet.";
      tr.append(td);
      body.append(tr);
    } else {
      for (const row of rows) {
        const tr = document.createElement("tr");
        for (const value of [row.broker, numberFormat.format(row.for), numberFormat.format(row.against), numberFormat.format(row.undecided)]) {
          const td = document.createElement("td");
          td.textContent = value;
          tr.append(td);
        }
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

function turnstileSiteKey(): string {
  if (isLocal()) return TEST_SITEKEY;
  return document.querySelector('meta[name="turnstile-sitekey"]')?.getAttribute("content")?.trim() || "";
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
