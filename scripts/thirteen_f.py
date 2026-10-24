"""Aggregate one CUSIP out of the SEC's quarterly Form 13F data sets.

The SEC publishes flattened TSV files inside each quarterly ZIP. This module
does not download anything. It reads the TSVs, keeps common-stock rows for one
CUSIP, and keeps only the latest 13F-HR / 13F-HR/A per manager and report period.

See https://www.sec.gov/files/form_13f_readme.pdf for column definitions.
Market value is whole dollars for filings on or after January 3, 2023.
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Iterable, Iterator, Mapping

CUSIP = "88160R101"
HR_FORMS = {"13F-HR", "13F-HR/A"}

# Documented names. The reader also accepts the header row as published,
# so a renamed column fails loudly instead of silently dropping data.


def to_int(value: str | None) -> int:
    text = (value or "").strip()
    if text == "" or text.upper() == "NULL":
        return 0
    number = Decimal(text)
    return int(number.to_integral_value(rounding=ROUND_HALF_UP))


def normalize_date(value: str | None) -> str:
    """Return YYYY-MM-DD when the SEC date is recognizable, otherwise the raw text."""
    text = (value or "").strip()
    if not text or text.upper() == "NULL":
        return ""
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%d-%b-%Y", "%d-%B-%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return text


def _upper_row(row: Mapping[str, str | None]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in row.items():
        if key is None:
            continue
        out[key.strip().upper()] = (value or "").strip()
    return out


def iter_tsv(path: Path) -> Iterator[dict[str, str]]:
    """Stream a SEC TSV. The information table is large enough that loading it all is unnecessary."""
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise ValueError(f"{path.name} has no header row")
        for row in reader:
            yield _upper_row(row)


def load_table(path: Path) -> list[dict[str, str]]:
    return list(iter_tsv(path))


def _require(row: Mapping[str, str], *names: str, file_label: str) -> None:
    missing = [name for name in names if name not in row]
    if missing:
        raise ValueError(
            f"{file_label} is missing column(s) {', '.join(missing)}. "
            f"Columns present: {', '.join(sorted(row))}"
        )


def edgar_index_url(cik: str, accession: str) -> str:
    cik_int = str(int(cik))
    accession_compact = accession.replace("-", "")
    return (
        "https://www.sec.gov/Archives/edgar/data/"
        f"{cik_int}/{accession_compact}/{accession}-index.html"
    )


def _is_common_stock(row: Mapping[str, str], cusip: str) -> tuple[bool, str]:
    """Return (include, skip_reason). skip_reason is empty when included."""
    if row.get("CUSIP", "").upper() != cusip:
        return False, "cusip"
    put_call = row.get("PUTCALL", "").strip().upper()
    if put_call and put_call != "NULL":
        return False, "option"
    share_type = row.get("SSHPRNAMTTYPE", "").strip().upper()
    if share_type != "SH":
        return False, "not-shares"
    return True, ""


def _rank(filing: Mapping[str, str]) -> tuple[str, int, str]:
    filed = normalize_date(filing.get("FILING_DATE", ""))
    try:
        amendment = int((filing.get("AMENDMENTNO") or "0").strip() or "0")
    except ValueError:
        amendment = 0
    return (filed, amendment, filing.get("ACCESSION_NUMBER", ""))


def aggregate_cusip(
    submission_rows: Iterable[Mapping[str, str]],
    cover_rows: Iterable[Mapping[str, str]],
    info_rows: Iterable[Mapping[str, str]],
    cusip: str = CUSIP,
) -> dict:
    """Build the holdings document from already-parsed TSV rows."""
    submissions: dict[str, dict[str, str]] = {}
    for row in submission_rows:
        _require(row, "ACCESSION_NUMBER", "SUBMISSIONTYPE", "CIK", "FILING_DATE", file_label="SUBMISSION")
        form = row["SUBMISSIONTYPE"].upper()
        if form not in HR_FORMS:
            continue
        submissions[row["ACCESSION_NUMBER"]] = dict(row)

    covers: dict[str, dict[str, str]] = {}
    for row in cover_rows:
        _require(
            row,
            "ACCESSION_NUMBER",
            "REPORTCALENDARORQUARTER",
            "FILINGMANAGER_NAME",
            file_label="COVERPAGE",
        )
        # First cover row wins. A duplicate would be a dataset defect.
        covers.setdefault(row["ACCESSION_NUMBER"], dict(row))

    grouped: dict[str, dict] = {}
    skipped_options = 0
    skipped_not_shares = 0
    info_rows_used = 0
    scanned = 0

    for raw in info_rows:
        scanned += 1
        if scanned % 2_000_000 == 0:
            print(f"  scanned {scanned:,} information-table rows", file=sys.stderr)
        row = dict(raw)
        _require(
            row,
            "ACCESSION_NUMBER",
            "CUSIP",
            "VALUE",
            "SSHPRNAMT",
            "SSHPRNAMTTYPE",
            "VOTING_AUTH_SOLE",
            "VOTING_AUTH_SHARED",
            "VOTING_AUTH_NONE",
            file_label="INFOTABLE",
        )
        if row.get("CUSIP", "").upper() != cusip:
            continue
        include, reason = _is_common_stock(row, cusip)
        if not include:
            if reason == "option":
                skipped_options += 1
            elif reason == "not-shares":
                skipped_not_shares += 1
            continue
        accession = row["ACCESSION_NUMBER"]
        if accession not in submissions:
            continue
        bucket = grouped.setdefault(
            accession,
            {
                "shares": 0,
                "valueUsd": 0,
                "votingSole": 0,
                "votingShared": 0,
                "votingNone": 0,
                "titles": set(),
                "issuers": set(),
                "rows": 0,
            },
        )
        bucket["shares"] += to_int(row.get("SSHPRNAMT"))
        bucket["valueUsd"] += to_int(row.get("VALUE"))
        bucket["votingSole"] += to_int(row.get("VOTING_AUTH_SOLE"))
        bucket["votingShared"] += to_int(row.get("VOTING_AUTH_SHARED"))
        bucket["votingNone"] += to_int(row.get("VOTING_AUTH_NONE"))
        title = row.get("TITLEOFCLASS", "")
        issuer = row.get("NAMEOFISSUER", "")
        if title:
            bucket["titles"].add(title)
        if issuer:
            bucket["issuers"].add(issuer)
        bucket["rows"] += 1
        info_rows_used += 1

    # Latest filing per CIK + report period replaces earlier amendments.
    winners: dict[tuple[str, str], tuple[tuple[str, int, str], dict]] = {}
    for accession, bucket in grouped.items():
        submission = submissions[accession]
        cover = covers.get(accession)
        if cover is None:
            continue
        cik = str(int(submission["CIK"]))
        report_period = normalize_date(cover.get("REPORTCALENDARORQUARTER", ""))
        filing = {
            "filingManager": cover.get("FILINGMANAGER_NAME", ""),
            "cik": cik,
            "accessionNumber": accession,
            "filingDate": normalize_date(submission.get("FILING_DATE", "")),
            "form": submission["SUBMISSIONTYPE"].upper(),
            "reportPeriod": report_period,
            "reportPeriodRaw": cover.get("REPORTCALENDARORQUARTER", ""),
            "shares": bucket["shares"],
            "valueUsd": bucket["valueUsd"],
            "votingSole": bucket["votingSole"],
            "votingShared": bucket["votingShared"],
            "votingNone": bucket["votingNone"],
            "titleOfClass": "; ".join(sorted(bucket["titles"])),
            "nameOfIssuer": "; ".join(sorted(bucket["issuers"])),
            "infoRows": bucket["rows"],
            "isAmendment": submission["SUBMISSIONTYPE"].upper() == "13F-HR/A",
            "sourceUrl": edgar_index_url(cik, accession),
            "_rank_amendment": cover.get("AMENDMENTNO", ""),
            "_filing_date_raw": submission.get("FILING_DATE", ""),
        }
        # Rank uses the cover amendment number when the submission is an amendment.
        rank_row = {
            "FILING_DATE": submission.get("FILING_DATE", ""),
            "AMENDMENTNO": cover.get("AMENDMENTNO", ""),
            "ACCESSION_NUMBER": accession,
        }
        key = (cik, report_period)
        rank = _rank(rank_row)
        current = winners.get(key)
        if current is None or rank >= current[0]:
            winners[key] = (rank, filing)

    holders = []
    for _rank_key, filing in winners.values():
        filing.pop("_rank_amendment", None)
        filing.pop("_filing_date_raw", None)
        holders.append(filing)

    holders.sort(key=lambda item: (-item["shares"], item["filingManager"].upper(), item["cik"]))

    period_counts: dict[str, int] = defaultdict(int)
    for holder in holders:
        period_counts[holder["reportPeriod"] or "unknown"] += 1
    periods = [
        {"reportPeriod": period, "managers": count}
        for period, count in sorted(period_counts.items(), key=lambda item: item[0], reverse=True)
    ]
    primary = ""
    if periods:
        primary = sorted(periods, key=lambda item: (item["managers"], item["reportPeriod"]))[-1]["reportPeriod"]

    return {
        "holders": holders,
        "primaryReportPeriod": primary,
        "periods": periods,
        "stats": {
            "managers": len(holders),
            "infoRowsUsed": info_rows_used,
            "optionRowsExcluded": skipped_options,
            "nonShareRowsExcluded": skipped_not_shares,
            "hrFilingsSeen": len(submissions),
        },
    }


def aggregate_directory(extracted_dir: Path, cusip: str = CUSIP) -> dict:
    submission = _find_one(extracted_dir, "SUBMISSION.tsv")
    cover = _find_one(extracted_dir, "COVERPAGE.tsv")
    info = _find_one(extracted_dir, "INFOTABLE.tsv")
    # Submission and cover pages are one row per filing. Stream the information table.
    return aggregate_cusip(load_table(submission), load_table(cover), iter_tsv(info), cusip=cusip)


def _find_one(directory: Path, name: str) -> Path:
    matches = list(directory.rglob(name))
    if not matches:
        raise FileNotFoundError(f"{name} not found under {directory}")
    return matches[0]
