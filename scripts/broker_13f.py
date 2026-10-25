#!/usr/bin/env python3
"""Map Add-shares broker labels to one 13F filer in holders.json.

The percent on the site is counted self-reported shares divided by that one
filer's reported shares. Filers are not added together. A retail row is not
part of the filer's vote.

Reads public/data/holders.json and writes public/data/broker-13f.json.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOLDERS = ROOT / "public" / "data" / "holders.json"
OUT = ROOT / "public" / "data" / "broker-13f.json"


def load_primary(document: dict) -> tuple[str, list[dict]]:
    period = document.get("primaryReportPeriod")
    if not isinstance(period, str) or not period:
        raise SystemExit("holders.json has no primaryReportPeriod")
    rows = [
        row
        for row in document.get("holders") or []
        if isinstance(row, dict) and row.get("reportPeriod") == period
    ]
    if not rows:
        raise SystemExit(f"no holders for {period}")
    return period, rows


def exact(rows: list[dict], name: str) -> dict | None:
    hits = [row for row in rows if row.get("filingManager") == name]
    if len(hits) > 1:
        raise SystemExit(f"more than one exact row for {name}")
    return hits[0] if hits else None


def largest_containing(rows: list[dict], needle: str) -> tuple[dict | None, list[dict]]:
    hits = [row for row in rows if needle in str(row.get("filingManager") or "").lower()]
    if not hits:
        return None, []
    winner = max(hits, key=lambda row: (int(row["shares"]), str(row["filingManager"])))
    return winner, hits


def matched(row: dict, period: str, short: str, rule: str) -> dict:
    return {
        "status": "matched",
        "filer": row["filingManager"],
        "shortLabel": short,
        "cik": str(row.get("cik") or ""),
        "shares": int(row["shares"]),
        "filingDate": row.get("filingDate"),
        "reportPeriod": period,
        "sourceUrl": row.get("sourceUrl"),
        "rule": rule,
    }


def unmatched(period: str, rule: str) -> dict:
    return {"status": "none", "reportPeriod": period, "rule": rule}


def build(document: dict) -> dict:
    period, rows = load_primary(document)
    schwab = exact(rows, "CHARLES SCHWAB INVESTMENT MANAGEMENT INC")
    fmr = exact(rows, "FMR LLC")
    morgan = exact(rows, "MORGAN STANLEY")
    bofa = exact(rows, "BANK OF AMERICA CORP /DE/")
    vanguard, vanguard_hits = largest_containing(rows, "vanguard")
    if schwab is None or fmr is None or morgan is None or bofa is None or vanguard is None:
        raise SystemExit("a required 13F filer is missing from the primary period")
    if len(vanguard_hits) < 2:
        raise SystemExit("expected more than one Vanguard filer")

    def no_name(needle: str) -> None:
        if any(needle in str(row.get("filingManager") or "").lower() for row in rows):
            raise SystemExit(f"found an unexpected name match for {needle}; update the map")

    for needle in ("robinhood", "webull", "sofi", "social finance", "interactive broker", "ibkr", "e*trade", "etrade", "e-trade"):
        no_name(needle)
    if any(
        str(row.get("filingManager") or "").strip().lower() in {"public", "public.com", "public holdings"}
        for row in rows
    ):
        raise SystemExit("a Public broker filer appeared; update the map")

    brokers = {
        "Schwab": matched(
            schwab,
            period,
            "Charles Schwab IM",
            "The only filing-manager name containing Schwab in this period is CHARLES SCHWAB INVESTMENT MANAGEMENT INC. That is the asset-manager 13F, not every share custodied at Schwab brokerage.",
        ),
        "Fidelity": matched(
            fmr,
            period,
            "FMR LLC",
            "No filing-manager name contains Fidelity. FMR LLC is the Fidelity parent’s 13F. Geode Capital Management is a separate filer and is not used.",
        ),
        "Vanguard": matched(
            vanguard,
            period,
            "Vanguard Capital Management",
            f"{len(vanguard_hits)} filing-manager names contain Vanguard. This map uses the one with the most reported shares and does not add the others.",
        ),
        "E*TRADE/Morgan Stanley": matched(
            morgan,
            period,
            "Morgan Stanley",
            "No filing-manager name is E*TRADE. The broker label on this site is E*TRADE/Morgan Stanley, so the row is the exact name MORGAN STANLEY. JPMorgan is a different firm and is not used.",
        ),
        "Merrill": matched(
            bofa,
            period,
            "Bank of America",
            "No filing-manager name contains Merrill Lynch. Merrill’s parent, BANK OF AMERICA CORP /DE/, is the 13F row. The percent is of that filer’s reported shares, not of Merrill brokerage accounts.",
        ),
        "Robinhood": unmatched(period, "No filing-manager name in this period contains Robinhood."),
        "Webull": unmatched(period, "No filing-manager name in this period contains Webull."),
        "SoFi": unmatched(period, "No filing-manager name in this period contains SoFi or Social Finance."),
        "Public": unmatched(
            period,
            "Pension funds with “Public” in the name are not the broker Public. No manager is named Public or Public.com.",
        ),
        "Interactive Brokers": unmatched(
            period,
            "No filing-manager name in this period contains Interactive Brokers or IBKR.",
        ),
        "Other": unmatched(period, "Other is not a filer."),
    }
    return {
        "generatedFrom": "public/data/holders.json",
        "holdersGeneratedAt": document.get("generatedAt"),
        "cusip": document.get("cusip"),
        "reportPeriod": period,
        "tableShares": sum(int(row["shares"]) for row in rows),
        "tableManagers": len(rows),
        "datasetPage": (document.get("source") or {}).get("datasetPage"),
        "datasetUrl": (document.get("source") or {}).get("datasetUrl"),
        "note": "Self-reported retail shares divided by one filer’s reported 13F shares. Not the filer’s vote, and not a percent of shares outstanding. Parent and sub-adviser rows are not added.",
        "brokers": brokers,
    }


def main() -> int:
    document = json.loads(HOLDERS.read_text())
    payload = build(document)
    OUT.write_text(json.dumps(payload, indent=2) + "\n")
    matched_n = sum(1 for row in payload["brokers"].values() if row["status"] == "matched")
    print(f"wrote {OUT} matched {matched_n} of {len(payload['brokers'])} period {payload['reportPeriod']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
