#!/usr/bin/env python3
"""Find major-family Form N-PX filings that mention TSLA and extract those rows.

SEC fair access: https://www.sec.gov/os/accessing-edgar-data
The script sends a User-Agent with a contact email and waits between requests.

It does not invent a vote. A family with no matching row stays "Not found".
Norges Bank does not file Form N-PX; that row is filled only from NBIM's
public voting pages when a Tesla meeting page can be fetched.

Usage:
  SEC_CONTACT_EMAIL=you@example.com python3 scripts/fetch_npx.py
"""

from __future__ import annotations

import gzip
import http.client
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from npx_classify import classify_item, normalize_date, normalize_how, parse_shares, rollup

ROOT = Path(__file__).resolve().parents[1]
TMP = ROOT / "tmp" / "npx"
OUT = ROOT / "public" / "data" / "institutional-votes.json"
EFTS = "https://efts.sec.gov/LATEST/search-index"
CUSIP = "88160R101"
DEFAULT_EMAIL = "contact@everysharevotes.com"
MIN_INTERVAL = 0.35
# voteRecord is inside proxyTable. Treating it as its own record clears the
# vote direction before the parent table is read.
RECORD_TAGS = {"proxytable", "proxyvote"}

# Display-name tests. Order matters only for reporting; a filer can match one family.
FAMILIES: list[tuple[str, str, tuple[str, ...]]] = [
    ("blackrock", "BlackRock / iShares", ("blackrock", "ishares")),
    ("vanguard", "Vanguard", ("vanguard",)),
    ("statestreet", "State Street / SPDR", ("state street", "ssga", "spdr")),
    ("fidelity", "Fidelity", ("fidelity",)),
    ("geode", "Geode", ("geode",)),
    (
        "capital",
        "Capital Group / American Funds",
        (
            "capital group",
            "capital research",
            "american funds",
            "capital world",
            "capital income builder",
            "growth fund of america",
            "investment company of america",
            "new perspective fund",
            "smallcap world fund",
            "fundamental investors",
            "american mutual fund",
            "income fund of america",
            "europacific",
            "amcap fund",
        ),
    ),
]

PERIODS = {"2024-06-30", "2026-06-30"}
COLUMNS = (
    "solarcity",
    "pay2018",
    "ratify2024",
    "texas2024",
    "directors2024",
    "xai2025",
    "pay2025",
    "directors2025",
    "supermajority2025",
)


def user_agent() -> str:
    email = os.environ.get("SEC_CONTACT_EMAIL", "").strip() or DEFAULT_EMAIL
    if email == DEFAULT_EMAIL:
        print(
            "warning: SEC_CONTACT_EMAIL is unset; using the project default.",
            file=sys.stderr,
        )
    return f"everysharevotes.com/1.0 (Jason Crawford; {email})"


class Client:
    def __init__(self, agent: str) -> None:
        self.agent = agent
        self.last = 0.0

    def get(self, url: str, timeout: int = 180) -> tuple[int, bytes, str]:
        elapsed = time.monotonic() - self.last
        if elapsed < MIN_INTERVAL:
            time.sleep(MIN_INTERVAL - elapsed)
        request = urllib.request.Request(
            url,
            headers={"User-Agent": self.agent, "Accept": "*/*", "Accept-Encoding": "gzip"},
        )
        delay = 2.0
        for attempt in range(4):
            try:
                self.last = time.monotonic()
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    body = response.read()
                    if response.headers.get("Content-Encoding") == "gzip":
                        body = gzip.decompress(body)
                    return response.status, body, response.headers.get("Content-Type", "")
            except urllib.error.HTTPError as error:
                if error.code in (429, 500, 502, 503, 504) and attempt < 3:
                    time.sleep(delay)
                    delay *= 2
                    continue
                detail = error.read()[:300]
                raise RuntimeError(f"HTTP {error.code} for {url}: {detail!r}") from error
            except urllib.error.URLError as error:
                if attempt < 3:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise RuntimeError(f"network error for {url}: {error}") from error
            except (http.client.IncompleteRead, TimeoutError, ConnectionResetError) as error:
                if attempt < 3:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise RuntimeError(f"truncated response for {url}: {error}") from error
        raise RuntimeError(f"failed {url}")


def local(tag: str) -> str:
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1].lower()


def child_text(elem: ET.Element, name: str) -> str:
    for child in list(elem):
        if local(child.tag) == name:
            return "".join(child.itertext()).strip()
    return ""


def family_of(name: str) -> tuple[str, str] | None:
    lowered = name.lower()
    for key, label, needles in FAMILIES:
        if any(needle in lowered for needle in needles):
            return key, label
    return None


def page_efts(client: Client) -> tuple[list[dict], dict]:
    hits: list[dict] = []
    start = 0
    total = None
    pages = 0
    while True:
        params = urllib.parse.urlencode(
            {
                "q": f'"{CUSIP}"',
                "forms": "N-PX",
                "dateRange": "custom",
                "startdt": "2024-07-01",
                "enddt": "2026-10-24",
                "from": str(start),
                "size": "100",
            }
        )
        status, body, _ = client.get(f"{EFTS}?{params}")
        payload = json.loads(body.decode("utf-8"))
        found = payload.get("hits", {}).get("hits", [])
        if total is None:
            total = payload.get("hits", {}).get("total", {}).get("value")
        pages += 1
        print(f"efts page {pages} status {status} rows {len(found)} from {start} total {total}", flush=True)
        if not found:
            break
        for hit in found:
            source = hit.get("_source", {})
            names = source.get("display_names") or []
            if isinstance(names, str):
                names = [names]
            matched = None
            for name in names:
                matched = family_of(str(name))
                if matched:
                    break
            if not matched:
                continue
            period = str(source.get("period_ending") or "")
            if period not in PERIODS:
                continue
            hits.append(
                {
                    "family": matched[0],
                    "familyName": matched[1],
                    "filer": names[0] if names else "",
                    "cik": str((source.get("ciks") or [""])[0]),
                    "adsh": source.get("adsh"),
                    "form": source.get("form"),
                    "period": period,
                    "fileDate": source.get("file_date"),
                    "fileName": str(hit.get("_id", "")).split(":", 1)[-1],
                }
            )
        start += len(found)
        if isinstance(total, int) and start >= total:
            break
        if len(found) < 100:
            break
    return hits, {"totalHits": total, "pages": pages, "familyPeriodHits": len(hits)}


def latest_filings(hits: list[dict]) -> list[dict]:
    """Keep the latest filing per CIK and period. An amendment replaces the original."""
    chosen: dict[tuple[str, str], dict] = {}
    for hit in hits:
        key = (hit["cik"], hit["period"])
        current = chosen.get(key)
        if current is None or (hit.get("fileDate") or "") >= (current.get("fileDate") or ""):
            chosen[key] = hit
    return list(chosen.values())


def edgar_url(cik: str, adsh: str, filename: str) -> str:
    cik_int = str(int(cik)) if cik.isdigit() else cik.lstrip("0")
    accession = adsh.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession}/{filename}"


def index_url(cik: str, adsh: str) -> str:
    cik_int = str(int(cik)) if cik.isdigit() else cik.lstrip("0")
    accession = adsh.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession}/{adsh}-index.html"


def parse_xml(path: Path, href: str, source: str, as_of: str, family: str) -> list[dict]:
    rows: list[dict] = []
    series_name = ""
    series_stack: list[str] = []
    for event, elem in ET.iterparse(path, events=("start", "end")):
        tag = local(elem.tag)
        if event == "start":
            if tag == "series":
                series_stack.append(series_name)
                series_name = ""
            continue
        if tag in ("seriesname", "nameofseries", "fundname"):
            value = "".join(elem.itertext()).strip()
            if value:
                series_name = value
        if tag in RECORD_TAGS:
            cusip = "".join(child_text(elem, "cusip").split()).upper()
            if cusip == CUSIP:
                description = child_text(elem, "votedescription") or child_text(elem, "proposaltext")
                meeting = child_text(elem, "meetingdate")
                issuer = child_text(elem, "issuername")
                votes: list[tuple[str, str, str]] = []
                for node in elem.iter():
                    if local(node.tag) not in ("voterecord", "voteinfo"):
                        continue
                    how = child_text(node, "howvoted") or child_text(node, "howvotedescription")
                    shares = child_text(node, "sharesvoted")
                    if how or shares:
                        votes.append((how, shares, child_text(node, "managementrecommendation")))
                if not votes:
                    how = child_text(elem, "howvoted")
                    shares = child_text(elem, "sharesvoted")
                    if how or shares:
                        votes.append((how, shares, child_text(elem, "managementrecommendation")))
                for how, shares, _mgmt in votes:
                    rows.append(
                        {
                            "family": family,
                            "series": series_name,
                            "issuer": issuer,
                            "meeting": meeting,
                            "description": description,
                            "how": normalize_how(how),
                            "shares": parse_shares(shares),
                            "item": classify_item(meeting, description),
                            "href": href,
                            "source": source,
                            "asOf": as_of,
                        }
                    )
            elem.clear()
        elif tag == "series":
            series_name = series_stack.pop() if series_stack else ""
            elem.clear()
    return rows


def older_search(client: Client) -> dict:
    """Look for pre-XML family N-PX hits. Text filings are recorded, not guessed."""
    params = urllib.parse.urlencode(
        {
            "q": '"Tesla"',
            "forms": "N-PX",
            "dateRange": "custom",
            "startdt": "2016-01-01",
            "enddt": "2024-06-30",
            "from": "0",
            "size": "100",
        }
    )
    try:
        status, body, _ = client.get(f"{EFTS}?{params}")
        payload = json.loads(body.decode("utf-8"))
    except (RuntimeError, json.JSONDecodeError) as error:
        return {"status": "error", "error": str(error)}
    total = payload.get("hits", {}).get("total", {}).get("value")
    family_hits = []
    for hit in payload.get("hits", {}).get("hits", []):
        source = hit.get("_source", {})
        names = source.get("display_names") or []
        if isinstance(names, str):
            names = [names]
        matched = None
        for name in names:
            matched = family_of(str(name))
            if matched:
                break
        if not matched:
            continue
        family_hits.append(
            {
                "family": matched[1],
                "filer": names[0] if names else "",
                "adsh": source.get("adsh"),
                "fileDate": source.get("file_date"),
                "period": source.get("period_ending"),
                "index": index_url(str((source.get("ciks") or ["0"])[0]), str(source.get("adsh"))),
            }
        )
    return {
        "status": status,
        "query": 'Tesla forms=N-PX filed 2016-01-01 through 2024-06-30, first 100 hits',
        "totalHits": total,
        "familyHitsOnFirstPage": family_hits,
        "note": "The first page is a sample, not a parse of every pre-2024 text filing. Cells for 2016 and 2018 stay Not found unless a row was actually read.",
    }


def fetch_norges(client: Client) -> dict:
    """Norges publishes voting instructions. Record only pages that return a Tesla table."""
    candidates = [
        "https://www.nbim.no/en/responsible-investment/voting/our-voting-records/",
    ]
    notes = []
    for url in candidates:
        try:
            status, body, content_type = client.get(url, timeout=60)
            notes.append({"url": url, "status": status, "contentType": content_type, "bytes": len(body)})
        except RuntimeError as error:
            notes.append({"url": url, "error": str(error)})
    return {
        "checkedAt": datetime.now(timezone.utc).isoformat(),
        "requests": notes,
        "cells": {},
        "note": "No per-meeting instruction table was parsed from these requests. Press citations, if any, are added separately in the page source and are not implied by this check.",
    }


def empty_cells(note: str) -> dict:
    return {column: {"status": "not-found", "note": note} for column in COLUMNS}


def build_cells(family_rows: list[dict], note: str) -> dict:
    cells = empty_cells(note)
    grouped: dict[str, list[dict]] = {}
    for row in family_rows:
        item = row.get("item")
        if item:
            grouped.setdefault(item, []).append(row)
    for item, rows in grouped.items():
        cell = rollup(rows)
        if cell and cell.get("href"):
            cells[item] = cell
    return cells


def main() -> int:
    TMP.mkdir(parents=True, exist_ok=True)
    client = Client(user_agent())
    hits_path = TMP / "family-hits.json"
    if hits_path.exists() and "--refetch" not in sys.argv:
        saved = json.loads(hits_path.read_text())
        raw_hits = saved["hits"]
        search_meta = saved["search"]
        print(f"reusing {len(raw_hits)} cached family hits", flush=True)
    else:
        raw_hits, search_meta = page_efts(client)
        hits_path.write_text(json.dumps({"search": search_meta, "hits": raw_hits}))
    selected = latest_filings(raw_hits)
    print(f"selected {len(selected)} filings after keeping the latest per CIK and period", flush=True)
    all_rows: list[dict] = []
    errors: list[dict] = []
    for index, hit in enumerate(selected, start=1):
        adsh = str(hit["adsh"])
        filename = hit["fileName"]
        if not filename or filename == adsh:
            errors.append({"adsh": adsh, "error": "missing vote-table filename"})
            continue
        url = edgar_url(hit["cik"], adsh, filename)
        cache = TMP / "xml" / f"{adsh}.xml"
        cache.parent.mkdir(parents=True, exist_ok=True)
        if not cache.exists() or cache.stat().st_size == 0:
            try:
                _status, body, _ctype = client.get(url)
            except RuntimeError as error:
                errors.append({"adsh": adsh, "url": url, "error": str(error)})
                print(f"{index}/{len(selected)} FAIL {adsh} {error}", flush=True)
                continue
            cache.write_bytes(body)
        href = index_url(hit["cik"], adsh)
        source = f"{hit['filer']} Form {hit['form']}"
        try:
            rows = parse_xml(cache, href, source, str(hit["fileDate"]), hit["family"])
        except ET.ParseError as error:
            errors.append({"adsh": adsh, "url": url, "error": f"xml parse: {error}"})
            print(f"{index}/{len(selected)} XML FAIL {adsh}", flush=True)
            continue
        if not rows and b"88160R101" in cache.read_bytes():
            raw = cache.read_bytes()
            at = raw.find(b"88160R101")
            snippet = raw[max(0, at - 400) : at + 600].decode("utf-8", "replace")
            errors.append({"adsh": adsh, "url": url, "error": "cusip present but parser returned no rows", "snippet": snippet})
            print(f"{index}/{len(selected)} UNPARSED {hit['familyName']} {adsh}", flush=True)
        else:
            print(f"{index}/{len(selected)} {hit['familyName']} {adsh} tesla-rows {len(rows)}", flush=True)
        for row in rows:
            row["period"] = hit["period"]
        all_rows.extend(rows)

    by_family: dict[str, list[dict]] = {key: [] for key, _label, _needles in FAMILIES}
    for row in all_rows:
        by_family.setdefault(row["family"], []).append(row)

    not_found_note = (
        "No parsed N-PX row for this item in the family filings selected for the periods "
        "ended June 30, 2024 and June 30, 2026. The 2016 and 2018 meetings predate the XML N-PX format and were not parsed from text filings."
    )
    families = []
    for key, label, _needles in FAMILIES:
        filing_count = len([hit for hit in selected if hit["family"] == key])
        families.append(
            {
                "id": key,
                "name": label,
                "note": f"Form N-PX. {filing_count} latest filing(s) for the periods ended June 30, 2024 and June 30, 2026 matched this family and CUSIP {CUSIP}.",
                "filingCount": filing_count,
                "parsedRows": len(by_family.get(key, [])),
                "cells": build_cells(by_family.get(key, []), not_found_note),
            }
        )

    norges = fetch_norges(client)
    families.append(
        {
            "id": "norges",
            "name": "Norges Bank",
            "note": "Not an N-PX filer. Public voting-disclosure site checked; cells stay Not found unless a meeting table was parsed.",
            "filingCount": 0,
            "parsedRows": 0,
            "cells": empty_cells("Norges Bank does not file Form N-PX. No meeting instruction table was parsed from the public voting site in this run."),
            "disclosureCheck": norges,
        }
    )

    older = older_search(client)
    document = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "cusip": CUSIP,
        "search": {
            "endpoint": EFTS,
            "query": f'"{CUSIP}"',
            "forms": "N-PX",
            "filedFrom": "2024-07-01",
            "filedThrough": "2026-10-24",
            "periods": sorted(PERIODS),
            **search_meta,
            "filingsDownloaded": len(selected),
        },
        "olderTextSearch": older,
        "errors": errors,
        "families": families,
        "unclassifiedSample": [
            {
                "family": row["family"],
                "meeting": normalize_date(row["meeting"]) or row["meeting"],
                "description": row["description"],
                "how": row["how"],
                "shares": None if row["shares"] is None else format(row["shares"], "f"),
                "href": row["href"],
            }
            for row in all_rows
            if not row.get("item")
        ][:40],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(document, indent=2) + "\n")
    print(f"wrote {OUT} rows {len(all_rows)} errors {len(errors)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
