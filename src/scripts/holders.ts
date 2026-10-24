import { formatInt, formatPeriod, formatSharePct, formatUsd } from "../lib/format";

type Holder = {
  filingManager: string;
  cik: string;
  accessionNumber: string;
  filingDate: string;
  form: string;
  reportPeriod: string;
  shares: number;
  valueUsd: number;
  votingSole: number;
  votingShared: number;
  votingNone: number;
  sourceUrl: string;
  isAmendment: boolean;
};

type Payload = {
  generatedAt: string | null;
  primaryReportPeriod: string | null;
  periods: { reportPeriod: string; managers: number }[];
  holders: Holder[];
  stats?: { optionRowsExcluded?: number };
};

const programs: { test: RegExp; name: string }[] = [
  { test: /blackrock/i, name: "BlackRock Voting Choice" },
  { test: /vanguard/i, name: "Vanguard Investor Choice" },
  { test: /state street|ssga/i, name: "State Street proxy voting choice" },
];

type SortKey = "filingManager" | "shares" | "pct" | "valueUsd" | "filingDate" | "reportPeriod";

export function mountHolders(): void {
  const app = document.querySelector<HTMLElement>("[data-holders-app]");
  if (!app) return;
  const body = document.querySelector<HTMLTableSectionElement>("#holder-rows");
  const count = document.querySelector<HTMLElement>("#holder-count");
  const search = document.querySelector<HTMLInputElement>("#holder-search");
  const period = document.querySelector<HTMLSelectElement>("#holder-period");
  const pager = document.querySelector<HTMLElement>("#holder-pager");
  if (!body || !count || !search || !period || !pager) return;
  const bodyEl = body;
  const countEl = count;
  const searchEl = search;
  const periodEl = period;
  const pagerEl = pager;

  const pageSize = 50;
  let rows: Holder[] = [];
  let periodShares = new Map<string, number>();
  let sortKey: SortKey = "shares";
  let sortDir: "asc" | "desc" = "desc";
  let page = 1;

  fetch("/data/holders.json")
    .then((response) => {
      if (!response.ok) throw new Error(String(response.status));
      return response.json() as Promise<Payload>;
    })
    .then((payload) => {
      rows = payload.holders ?? [];
      periodShares = new Map();
      for (const row of rows) {
        periodShares.set(row.reportPeriod, (periodShares.get(row.reportPeriod) ?? 0) + row.shares);
      }
      const staticNote = document.querySelector<HTMLElement>("#static-note");
      if (staticNote) staticNote.hidden = true;
      render();
    })
    .catch(() => {
      countEl.textContent = "The full file did not load. The first rows below are the copy baked into this page.";
    });

  searchEl.addEventListener("input", () => {
    page = 1;
    render();
  });
  periodEl.addEventListener("change", () => {
    page = 1;
    render();
  });
  document.querySelectorAll<HTMLButtonElement>("[data-sort]").forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.dataset.sort as SortKey;
      if (sortKey === key) sortDir = sortDir === "asc" ? "desc" : "asc";
      else {
        sortKey = key;
        sortDir = key === "filingManager" ? "asc" : "desc";
      }
      page = 1;
      render();
    });
  });

  function filtered(): Holder[] {
    const query = searchEl.value.trim().toLowerCase();
    const selected = periodEl.value;
    return rows.filter((row) => {
      if (selected && row.reportPeriod !== selected) return false;
      if (query && !row.filingManager.toLowerCase().includes(query)) return false;
      return true;
    });
  }

  function sortValue(row: Holder): string | number {
    if (sortKey === "pct") return pctOf(row);
    return row[sortKey];
  }

  function pctOf(row: Holder): number {
    const total = periodShares.get(row.reportPeriod) ?? 0;
    return total > 0 ? row.shares / total : 0;
  }

  function render(): void {
    const list = filtered().sort((a, b) => {
      const left = sortValue(a);
      const right = sortValue(b);
      let order = 0;
      if (typeof left === "number" && typeof right === "number") order = left - right;
      else order = String(left).localeCompare(String(right));
      return sortDir === "asc" ? order : -order;
    });
    const pages = Math.max(1, Math.ceil(list.length / pageSize));
    page = Math.min(page, pages);
    const slice = list.slice((page - 1) * pageSize, page * pageSize);
    const selected = periodEl.value;
    const periodLabel = selected ? formatPeriod(selected) : "All periods in this file";
    const denom = selected ? periodShares.get(selected) ?? 0 : 0;
    const denomText = selected
      ? ` · % of ${formatInt(denom)} reported 13F shares in this file`
      : " · % uses each row’s own report-period total in this file";
    countEl.textContent = `${formatInt(list.length)} filing managers · ${periodLabel}${denomText}`;
    bodyEl.replaceChildren(...slice.map(rowView));
    document.querySelectorAll<HTMLButtonElement>("[data-sort]").forEach((button) => {
      const active = button.dataset.sort === sortKey;
      const state = active ? (sortDir === "asc" ? "ascending" : "descending") : "none";
      button.setAttribute("aria-sort", state);
      button.closest("th")?.setAttribute("aria-sort", state);
    });
    renderPager(pages);
  }

  function renderPager(pages: number): void {
    pagerEl.replaceChildren();
    if (pages <= 1) return;
    const prev = document.createElement("button");
    prev.type = "button";
    prev.textContent = "Previous";
    prev.disabled = page === 1;
    prev.addEventListener("click", () => {
      page -= 1;
      render();
    });
    const next = document.createElement("button");
    next.type = "button";
    next.textContent = "Next";
    next.disabled = page === pages;
    next.addEventListener("click", () => {
      page += 1;
      render();
    });
    const status = document.createElement("span");
    status.textContent = `Page ${page} of ${pages}`;
    pagerEl.append(prev, status, next);
  }

  function rowView(row: Holder): HTMLTableRowElement {
    const tr = document.createElement("tr");
    const program = programs.find((item) => item.test.test(row.filingManager));
    tr.append(
      cell(
        `${row.filingManager}${row.isAmendment ? " (amendment)" : ""}${program ? ` · ${program.name}` : ""}`,
        "Manager",
        true,
      ),
      cell(formatInt(row.shares), "Shares", false, true),
      cell(formatSharePct(row.shares, periodShares.get(row.reportPeriod) ?? 0), "% of reported 13F shares", false, true),
      cell(formatUsd(row.valueUsd), "Value reported", false, true),
      cell(
        `${formatInt(row.votingSole)} sole · ${formatInt(row.votingShared)} shared · ${formatInt(row.votingNone)} none`,
        "Voting authority",
      ),
      cell(formatPeriod(row.reportPeriod), "Report period"),
      cell(row.filingDate, "Filed"),
      linkCell(row.sourceUrl),
    );
    return tr;
  }

  function cell(text: string, label: string, sticky = false, numeric = false): HTMLTableCellElement {
    const td = document.createElement("td");
    td.textContent = text;
    td.dataset.label = label;
    if (sticky) td.className = "sticky-col";
    if (numeric) td.classList.add("num");
    return td;
  }

  function linkCell(href: string): HTMLTableCellElement {
    const td = document.createElement("td");
    td.dataset.label = "Filing";
    const a = document.createElement("a");
    a.href = href;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    a.textContent = "13F index";
    td.append(a);
    return td;
  }
}
