#!/usr/bin/env python3
"""Download the latest SEC Form 13F data set and write TSLA holdings JSON.

SEC fair-access expectations (https://www.sec.gov/os/accessing-edgar-data):

- Send a User-Agent that names the application and a contact email.
- Stay far under the 10 requests per second limit. This script makes two
  requests (the dataset index, then one ZIP) and waits between them.
- Treat the response as public filings data, not as investment advice.

Set SEC_CONTACT_EMAIL to a mailbox a person monitors. The default is the
project address and should be replaced before unattended runs.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from thirteen_f import CUSIP, aggregate_directory

ROOT = Path(__file__).resolve().parents[1]
INDEX_URL = "https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets"
README_URL = "https://www.sec.gov/files/form_13f_readme.pdf"
DEFAULT_EMAIL = "contact@everysharevotes.com"
MIN_INTERVAL_SECONDS = 0.5
OUTPUT_PATH = ROOT / "public" / "data" / "holders.json"


def user_agent() -> str:
    email = os.environ.get("SEC_CONTACT_EMAIL", "").strip() or DEFAULT_EMAIL
    if email == DEFAULT_EMAIL:
        print(
            "warning: SEC_CONTACT_EMAIL is unset; using the project default. "
            "Point it at a monitored mailbox before scheduled runs.",
            file=sys.stderr,
        )
    return f"everysharevotes.com/1.0 (Jason Crawford; {email})"


class SecClient:
    def __init__(self, agent: str) -> None:
        self.agent = agent
        self._last_request = 0.0

    def get(self, url: str) -> bytes:
        elapsed = time.monotonic() - self._last_request
        if elapsed < MIN_INTERVAL_SECONDS:
            time.sleep(MIN_INTERVAL_SECONDS - elapsed)
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": self.agent,
                "Accept": "*/*",
                "Accept-Encoding": "gzip, deflate",
            },
        )
        delay = 2.0
        last_error: Exception | None = None
        for attempt in range(4):
            try:
                self._last_request = time.monotonic()
                with urllib.request.urlopen(request, timeout=180) as response:
                    body = response.read()
                    encoding = response.headers.get("Content-Encoding", "")
                    if encoding == "gzip":
                        import gzip

                        body = gzip.decompress(body)
                    return body
            except urllib.error.HTTPError as error:
                last_error = error
                if error.code not in {429, 500, 502, 503, 504} or attempt == 3:
                    detail = error.read().decode("utf-8", "replace")[:500]
                    raise SystemExit(f"SEC request failed {error.code} for {url}\n{detail}") from error
            except urllib.error.URLError as error:
                last_error = error
                if attempt == 3:
                    raise SystemExit(f"SEC request failed for {url}: {error}") from error
            time.sleep(delay)
            delay *= 2
        raise SystemExit(f"SEC request failed for {url}: {last_error}")


def latest_zip_url(index_html: str) -> tuple[str, str]:
    matches = re.findall(r'href="([^"]+\.zip)"', index_html, flags=re.I)
    if not matches:
        raise SystemExit("No Form 13F ZIP links found on the SEC data-sets page.")
    href = matches[0]
    if href.startswith("http://") or href.startswith("https://"):
        url = href
    else:
        url = "https://www.sec.gov" + (href if href.startswith("/") else "/" + href)
    label = Path(url).name
    return url, label


def write_holders(document: dict, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    temporary.replace(output)


def build_document(extracted: Path, dataset_url: str, dataset_label: str) -> dict:
    aggregated = aggregate_directory(extracted, CUSIP)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return {
        "schemaVersion": 1,
        "generatedAt": now,
        "cusip": CUSIP,
        "source": {
            "datasetPage": INDEX_URL,
            "datasetUrl": dataset_url,
            "datasetLabel": dataset_label,
            "documentation": README_URL,
            "valueUnit": (
                "U.S. dollars, as reported. The SEC readme says that starting "
                "January 3, 2023, Form 13F market value is rounded to the nearest dollar."
            ),
        },
        "method": {
            "included": (
                "Rows from 13F-HR and 13F-HR/A information tables with this CUSIP, "
                "SSHPRNAMTTYPE of SH, and a blank put/call flag."
            ),
            "amendments": (
                "When one CIK files more than once for the same report period, "
                "only the latest filing date (then the higher amendment number) is kept."
            ),
            "doubleCount": (
                "A parent and a sub-adviser can both report the same shares. "
                "Do not add these rows into a total ownership figure."
            ),
            "omitted": (
                "People and institutions that do not file Form 13F are absent. "
                "That includes most retail holders and many holders outside the United States. "
                "Insider stakes reported on Forms 3, 4, and 5 are not in this file."
            ),
        },
        "primaryReportPeriod": aggregated["primaryReportPeriod"],
        "periods": aggregated["periods"],
        "stats": aggregated["stats"],
        "holders": aggregated["holders"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh TSLA 13F holdings JSON from EDGAR.")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument(
        "--workdir",
        type=Path,
        default=ROOT / "tmp" / "13f",
        help="Where the ZIP is unpacked. Not committed.",
    )
    args = parser.parse_args()

    client = SecClient(user_agent())
    print(f"Fetching dataset index {INDEX_URL}")
    index_html = client.get(INDEX_URL).decode("utf-8", "replace")
    dataset_url, dataset_label = latest_zip_url(index_html)
    print(f"Latest data set: {dataset_label}")

    args.workdir.mkdir(parents=True, exist_ok=True)
    zip_path = args.workdir / dataset_label
    if not zip_path.exists() or zip_path.stat().st_size < 1000:
        print(f"Downloading {dataset_url}")
        zip_path.write_bytes(client.get(dataset_url))
    else:
        print(f"Reusing downloaded {zip_path}")

    extract_dir = args.workdir / "extracted"
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(extract_dir)

    document = build_document(extract_dir, dataset_url, dataset_label)
    write_holders(document, args.output)
    stats = document["stats"]
    print(
        f"Wrote {args.output} with {stats['managers']} managers "
        f"for primary period {document['primaryReportPeriod']} "
        f"({stats['infoRowsUsed']} information-table rows; "
        f"{stats['optionRowsExcluded']} option rows excluded)."
    )


if __name__ == "__main__":
    main()
