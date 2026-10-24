"""Classify Tesla N-PX vote descriptions and roll them up.

The rules are deliberately narrow. A row that does not match a known meeting
date and a known proposal phrase stays unclassified instead of being forced
into a cell.
"""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

MEETINGS = {
    "2024-06-13": "2024",
    "2025-11-06": "2025",
}

HOWS = ("FOR", "AGAINST", "ABSTAIN", "WITHHOLD")


def normalize_date(value: str) -> str:
    raw = re.sub(r"\s+", " ", (value or "").strip())
    if not raw:
        return ""
    formats = (
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%m-%d-%Y",
        "%d-%b-%Y",
        "%d-%B-%Y",
        "%b %d, %Y",
        "%B %d, %Y",
        "%Y%m%d",
    )
    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def normalize_how(value: str) -> str:
    token = re.sub(r"[^A-Za-z]", "", value or "").upper()
    if token in ("FOR", "YES", "AYE"):
        return "FOR"
    if token in ("AGAINST", "NO", "NAY"):
        return "AGAINST"
    if token in ("ABSTAIN", "ABSTENTION"):
        return "ABSTAIN"
    if token in ("WITHHOLD", "WITHHELD"):
        return "WITHHOLD"
    return ""


def parse_shares(value: str) -> Decimal | None:
    raw = (value or "").strip().replace(",", "").replace(" ", "")
    if not raw:
        return None
    try:
        number = Decimal(raw)
    except InvalidOperation:
        return None
    if not number.is_finite():
        return None
    return number


def format_shares(amount: Decimal) -> str:
    if amount == amount.to_integral_value():
        return f"{int(amount):,}"
    text = f"{amount.quantize(Decimal('0.001')):,f}"
    return text.rstrip("0").rstrip(".")


def classify_item(meeting_date: str, description: str) -> str | None:
    """Return a column id, or None when the row is not one of the tracked items."""
    meeting = normalize_date(meeting_date)
    text = re.sub(r"\s+", " ", (description or "").lower()).strip()
    if meeting not in MEETINGS or not text:
        return None
    year = MEETINGS[meeting]
    if year == "2024":
        if any(phrase in text for phrase in ("redomestic", "reincorporat", "re-incorporat", "texas", "conversion")):
            return "texas2024"
        if "ratif" in text and any(phrase in text for phrase in ("2018", "award", "performance", "compensation", "pay")):
            return "ratify2024"
        if "director" in text or text.startswith("elect "):
            return "directors2024"
        return None
    # Some N-PX XML spells the 2025 proposal "xAl" (lowercase L) instead of "xAI".
    # The rest of the sentence matches Tesla's proposal 7, so that spelling is included.
    if "x.ai" in text or "xai" in text or "investment in xal" in text:
        return "xai2025"
    if "supermajority" in text:
        return "supermajority2025"
    if "director" in text or text.startswith("elect "):
        return "directors2025"
    advisory = "advisory" in text or "say-on-pay" in text or "say on pay" in text
    incentive_plan = "equity incentive" in text or "incentive plan" in text
    if advisory or incentive_plan:
        return None
    if "performance award" in text or ("ceo" in text and "award" in text):
        return "pay2025"
    return None


def rollup(rows: list[dict]) -> dict | None:
    """Combine parsed vote rows into one sourced cell. Returns None if rows is empty."""
    if not rows:
        return None
    totals = {how: Decimal("0") for how in HOWS}
    unnumeric = 0
    filings: set[str] = set()
    descriptions: list[str] = []
    best_shares = Decimal("-1")
    source_row = rows[0]
    for row in rows:
        how = normalize_how(str(row.get("how", "")))
        shares = row.get("shares")
        if not isinstance(shares, Decimal):
            shares = parse_shares(str(shares if shares is not None else ""))
        filings.add(str(row.get("href", "")))
        description = str(row.get("description", "")).strip()
        if description and description not in descriptions and len(descriptions) < 3:
            descriptions.append(description)
        if how in totals and isinstance(shares, Decimal) and shares > 0:
            totals[how] += shares
            if shares >= best_shares:
                best_shares = shares
                source_row = row
        elif how in totals:
            unnumeric += 1
            if best_shares < 0:
                source_row = row
        else:
            unnumeric += 1
    present = [how for how, amount in totals.items() if amount > 0]
    if len(present) == 1:
        label = {"FOR": "For", "AGAINST": "Against", "ABSTAIN": "Abstain", "WITHHOLD": "Withhold"}[present[0]]
    elif len(present) > 1:
        label = "Split"
    elif rows and all(normalize_how(str(row.get("how", ""))) == "FOR" for row in rows):
        label = "For"
    elif rows and all(normalize_how(str(row.get("how", ""))) == "AGAINST" for row in rows):
        label = "Against"
    else:
        label = "Split" if len({normalize_how(str(row.get("how", ""))) for row in rows} - {""}) > 1 else "Not numeric"
    parts = [f"{label} across {len(filings)} filing link{'s' if len(filings) != 1 else ''}."]
    share_bits = [f"{'For' if how == 'FOR' else how.title()} {format_shares(totals[how])}" for how in HOWS if totals[how] > 0]
    if share_bits:
        parts.append("Shares in the parsed rows: " + "; ".join(share_bits) + ".")
    if unnumeric:
        parts.append(f"{unnumeric} row{'s' if unnumeric != 1 else ''} had a vote direction without a numeric share count and {'are' if unnumeric != 1 else 'is'} not in the share sum.")
    if descriptions:
        parts.append("Filing description: " + descriptions[0])
    return {
        "status": "found",
        "label": label,
        "detail": " ".join(parts),
        "href": source_row.get("href", ""),
        "source": source_row.get("source", "SEC Form N-PX"),
        "asOf": source_row.get("asOf", ""),
    }
