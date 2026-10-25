#!/usr/bin/env python3
"""The broker map must match holders.json. No invented share counts."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from broker_13f import HOLDERS, build


class Broker13FTest(unittest.TestCase):
    def setUp(self) -> None:
        self.document = json.loads(HOLDERS.read_text())
        self.payload = build(self.document)
        period = self.payload["reportPeriod"]
        self.rows = {
            row["filingManager"]: row
            for row in self.document["holders"]
            if row["reportPeriod"] == period
        }

    def test_matches_use_the_file_share_count(self) -> None:
        for broker, mapped in self.payload["brokers"].items():
            if mapped["status"] != "matched":
                continue
            source = self.rows[mapped["filer"]]
            self.assertEqual(mapped["shares"], source["shares"], broker)
            self.assertEqual(mapped["sourceUrl"], source["sourceUrl"], broker)

    def test_named_rules(self) -> None:
        brokers = self.payload["brokers"]
        self.assertEqual(brokers["Schwab"]["filer"], "CHARLES SCHWAB INVESTMENT MANAGEMENT INC")
        self.assertEqual(brokers["Fidelity"]["filer"], "FMR LLC")
        self.assertEqual(brokers["Vanguard"]["filer"], "VANGUARD CAPITAL MANAGEMENT LLC")
        self.assertEqual(brokers["E*TRADE/Morgan Stanley"]["filer"], "MORGAN STANLEY")
        self.assertEqual(brokers["Merrill"]["filer"], "BANK OF AMERICA CORP /DE/")
        for broker in ("Robinhood", "Webull", "SoFi", "Public", "Interactive Brokers", "Other"):
            self.assertEqual(brokers[broker]["status"], "none", broker)

    def test_vanguard_is_the_largest_vanguard_name(self) -> None:
        period = self.payload["reportPeriod"]
        vanguard = [
            row["shares"]
            for row in self.document["holders"]
            if row["reportPeriod"] == period and "vanguard" in row["filingManager"].lower()
        ]
        self.assertGreater(len(vanguard), 1)
        self.assertEqual(self.payload["brokers"]["Vanguard"]["shares"], max(vanguard))

    def test_table_total_is_the_sum_of_primary_rows(self) -> None:
        period = self.payload["reportPeriod"]
        total = sum(row["shares"] for row in self.document["holders"] if row["reportPeriod"] == period)
        self.assertEqual(self.payload["tableShares"], total)

    def test_schwab_sixty_shares_is_a_tiny_real_percent(self) -> None:
        shares = self.payload["brokers"]["Schwab"]["shares"]
        pct = 60 / shares * 100
        self.assertEqual(f"{pct:.4f}%", "0.0003%")


if __name__ == "__main__":
    unittest.main()
