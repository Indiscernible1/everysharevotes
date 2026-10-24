#!/usr/bin/env python3
"""Fixture test for the 13F aggregation. Does not contact the SEC."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from thirteen_f import aggregate_cusip, to_int  # noqa: E402


SUBMISSIONS = [
    {
        "ACCESSION_NUMBER": "0000000001-26-000001",
        "SUBMISSIONTYPE": "13F-HR",
        "CIK": "0000000001",
        "FILING_DATE": "2026-08-14",
    },
    {
        "ACCESSION_NUMBER": "0000000001-26-000002",
        "SUBMISSIONTYPE": "13F-HR/A",
        "CIK": "0000000001",
        "FILING_DATE": "2026-08-20",
    },
    {
        "ACCESSION_NUMBER": "0000000002-26-000010",
        "SUBMISSIONTYPE": "13F-HR",
        "CIK": "0000000002",
        "FILING_DATE": "20260813",
    },
    {
        "ACCESSION_NUMBER": "0000000003-26-000001",
        "SUBMISSIONTYPE": "13F-NT",
        "CIK": "0000000003",
        "FILING_DATE": "2026-08-01",
    },
]

COVERS = [
    {
        "ACCESSION_NUMBER": "0000000001-26-000001",
        "REPORTCALENDARORQUARTER": "30-JUN-2026",
        "ISAMENDMENT": "N",
        "AMENDMENTNO": "",
        "FILINGMANAGER_NAME": "Example Original LLC",
    },
    {
        "ACCESSION_NUMBER": "0000000001-26-000002",
        "REPORTCALENDARORQUARTER": "30-JUN-2026",
        "ISAMENDMENT": "Y",
        "AMENDMENTNO": "1",
        "FILINGMANAGER_NAME": "Example Capital LLC",
    },
    {
        "ACCESSION_NUMBER": "0000000002-26-000010",
        "REPORTCALENDARORQUARTER": "30-JUN-2026",
        "ISAMENDMENT": "N",
        "AMENDMENTNO": "",
        "FILINGMANAGER_NAME": "Second Manager Inc",
    },
]


def info_row(**overrides: str) -> dict[str, str]:
    base = {
        "ACCESSION_NUMBER": "0000000001-26-000002",
        "NAMEOFISSUER": "TESLA INC",
        "TITLEOFCLASS": "COM",
        "CUSIP": "88160R101",
        "VALUE": "100",
        "SSHPRNAMT": "10",
        "SSHPRNAMTTYPE": "SH",
        "PUTCALL": "",
        "INVESTMENTDISCRETION": "SOLE",
        "VOTING_AUTH_SOLE": "10",
        "VOTING_AUTH_SHARED": "0",
        "VOTING_AUTH_NONE": "0",
    }
    base.update(overrides)
    return base


class AggregateTests(unittest.TestCase):
    def test_to_int_rounds_half_up(self) -> None:
        self.assertEqual(to_int("10.5"), 11)
        self.assertEqual(to_int(""), 0)
        self.assertEqual(to_int(None), 0)

    def test_amendment_replaces_original_and_options_are_excluded(self) -> None:
        rows = [
            info_row(
                ACCESSION_NUMBER="0000000001-26-000001",
                SSHPRNAMT="999",
                VALUE="999",
                VOTING_AUTH_SOLE="999",
            ),
            info_row(SSHPRNAMT="40", VALUE="400", VOTING_AUTH_SOLE="25", VOTING_AUTH_SHARED="15"),
            info_row(
                SSHPRNAMT="5",
                VALUE="50",
                INVESTMENTDISCRETION="DFND",
                VOTING_AUTH_SOLE="0",
                VOTING_AUTH_SHARED="0",
                VOTING_AUTH_NONE="5",
            ),
            info_row(PUTCALL="Call", SSHPRNAMT="1000", VALUE="1", TITLEOFCLASS="CALL"),
            info_row(
                ACCESSION_NUMBER="0000000002-26-000010",
                NAMEOFISSUER="TESLA INC",
                SSHPRNAMT="7",
                VALUE="70",
                VOTING_AUTH_SOLE="7",
            ),
            info_row(CUSIP="000000000", SSHPRNAMT="5", VALUE="5"),
        ]
        document = aggregate_cusip(SUBMISSIONS, COVERS, rows)
        self.assertEqual(document["stats"]["managers"], 2)
        self.assertEqual(document["stats"]["optionRowsExcluded"], 1)
        self.assertEqual(document["primaryReportPeriod"], "2026-06-30")

        by_cik = {holder["cik"]: holder for holder in document["holders"]}
        example = by_cik["1"]
        self.assertEqual(example["filingManager"], "Example Capital LLC")
        self.assertEqual(example["shares"], 45)
        self.assertEqual(example["valueUsd"], 450)
        self.assertEqual(example["votingSole"], 25)
        self.assertEqual(example["votingShared"], 15)
        self.assertEqual(example["votingNone"], 5)
        self.assertTrue(example["isAmendment"])
        self.assertEqual(example["filingDate"], "2026-08-20")
        self.assertEqual(
            example["sourceUrl"],
            "https://www.sec.gov/Archives/edgar/data/1/000000000126000002/0000000001-26-000002-index.html",
        )
        self.assertEqual(by_cik["2"]["shares"], 7)
        self.assertEqual(by_cik["2"]["filingDate"], "2026-08-13")
        self.assertGreater(document["holders"][0]["shares"], document["holders"][1]["shares"])

    def test_missing_column_raises(self) -> None:
        with self.assertRaises(ValueError):
            aggregate_cusip(
                [{"ACCESSION_NUMBER": "x", "SUBMISSIONTYPE": "13F-HR", "CIK": "1", "FILING_DATE": "2026-01-01"}],
                [{"ACCESSION_NUMBER": "x"}],
                [],
            )


if __name__ == "__main__":
    unittest.main()
