#!/usr/bin/env python3
"""Unit tests for N-PX classification and rollup. No network."""

from __future__ import annotations

import unittest

from decimal import Decimal

from npx_classify import classify_item, normalize_date, parse_shares, rollup


class ClassifyTests(unittest.TestCase):
    def test_dates(self) -> None:
        self.assertEqual(normalize_date("06/13/2024"), "2024-06-13")
        self.assertEqual(normalize_date("2025-11-06"), "2025-11-06")
        self.assertEqual(normalize_date("13-Jun-2024"), "2024-06-13")
        self.assertEqual(normalize_date(""), "")

    def test_2024_items(self) -> None:
        self.assertEqual(
            classify_item("06/13/2024", "Ratify 2018 CEO performance award"),
            "ratify2024",
        )
        self.assertEqual(
            classify_item("2024-06-13", "Approve conversion and redomestication to Texas"),
            "texas2024",
        )
        self.assertEqual(classify_item("2024-06-13", "Elect Director Kimbal Musk"), "directors2024")
        self.assertIsNone(classify_item("2024-06-13", "Ratify PricewaterhouseCoopers LLP as auditors"))

    def test_2025_items(self) -> None:
        self.assertEqual(
            classify_item("11/06/2025", "Board authorization of an investment in xAI"),
            "xai2025",
        )
        self.assertEqual(
            classify_item("11/06/2025", "A shareholder proposal regarding Board authorization of an investment in xAl."),
            "xai2025",
        )
        self.assertEqual(
            classify_item("2025-11-06", "Approval of the 2025 CEO performance award"),
            "pay2025",
        )
        self.assertIsNone(
            classify_item("2025-11-06", "Advisory vote to approve executive compensation"),
        )
        self.assertIsNone(classify_item("2025-11-06", "Approval of the A&R 2019 equity incentive plan"))
        self.assertEqual(
            classify_item("2025-11-06", "Eliminate applicable supermajority voting requirements"),
            "supermajority2025",
        )
        self.assertEqual(classify_item("2025-11-06", "Elect Director Ira Ehrenpreis"), "directors2025")
        self.assertIsNone(classify_item("2025-01-01", "Approval of the 2025 CEO performance award"))

    def test_shares(self) -> None:
        self.assertEqual(parse_shares("1,234"), Decimal("1234"))
        self.assertEqual(parse_shares("1179.880000"), Decimal("1179.880000"))
        self.assertIsNone(parse_shares(""))
        self.assertIsNone(parse_shares("n/a"))

    def test_rollup_split_and_source(self) -> None:
        cell = rollup(
            [
                {
                    "how": "For",
                    "shares": 10,
                    "description": "Elect Director A",
                    "href": "https://example.test/a",
                    "source": "Fund A N-PX",
                    "asOf": "2024-08-30",
                },
                {
                    "how": "Against",
                    "shares": 40,
                    "description": "Elect Director A",
                    "href": "https://example.test/b",
                    "source": "Fund B N-PX",
                    "asOf": "2024-08-31",
                },
            ]
        )
        self.assertIsNotNone(cell)
        assert cell is not None
        self.assertEqual(cell["label"], "Split")
        self.assertEqual(cell["href"], "https://example.test/b")
        self.assertIn("For 10", cell["detail"])
        self.assertIn("Against 40", cell["detail"])

    def test_rollup_empty(self) -> None:
        self.assertIsNone(rollup([]))


if __name__ == "__main__":
    unittest.main()
