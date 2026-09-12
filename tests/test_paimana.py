"""Offline tests for the PAIMANA railways adapter.

No network. The fixture is a 12-row excerpt of the real 2026-07 freeze chosen to
hit every branch: slipped, no-revised-date, complete, zero-progress-with-spend,
revised-down, and unchanged.
"""
from __future__ import annotations

import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pipeline.adapters.base import SchemaDrift
from pipeline.adapters.mospi_paimana import (
    EXPECTED_FIELDS, MospiPaimanaAdapter, _health_check, _status_for, _geo_for, _num,
)
from pipeline.core import schema

FIXTURE = os.path.join(ROOT, "tests", "fixtures", "paimana_rail_2026-07.json")


def payload():
    with open(FIXTURE, encoding="utf-8") as fh:
        return json.load(fh)


class TestHealthCheck(unittest.TestCase):
    def test_accepts_the_real_shape(self):
        rows = _health_check(payload(), "2026-07")
        self.assertEqual(len(rows), payload()["data"]["totalProjectsTabData"][0]["TotalProject"])

    def test_rejects_row_count_mismatch(self):
        p = payload()
        p["data"]["totalProjectsTabData"][0]["TotalProject"] = 999
        with self.assertRaises(SchemaDrift):
            _health_check(p, "2026-07")

    def test_zero_rows_for_a_published_month_is_drift_not_a_clean_exit(self):
        # We only ever request lastFreeze, so the month IS published. Exiting
        # quietly here would let the site silently go stale.
        p = payload()
        p["data"]["ProjectsCountTabDetails"] = []
        p["data"]["totalProjectsTabData"][0]["TotalProject"] = 0
        with self.assertRaises(SchemaDrift):
            _health_check(p, "2026-07")

    def test_unexpected_field_set_raises(self):
        p = payload()
        p["data"]["ProjectsCountTabDetails"][0]["SomethingNew"] = 1
        with self.assertRaises(SchemaDrift):
            _health_check(p, "2026-07")

    def test_a_non_railway_row_raises(self):
        # The guard that stops PAIMANA's 993 road rows entering and duplicating NHAI.
        p = payload()
        p["data"]["ProjectsCountTabDetails"][0]["SectorName"] = "Roads & Highways"
        with self.assertRaises(SchemaDrift):
            _health_check(p, "2026-07")

    def test_missing_data_object_raises(self):
        with self.assertRaises(SchemaDrift):
            _health_check({"success": True}, "2026-07")

    def test_health_check_ignores_islive_and_projectcount(self):
        # Both report False/0 on a perfectly good response; reading them would
        # reject every run.
        p = payload()
        p["data"]["isLive"] = False
        p["data"]["ProjectCount"] = 0
        self.assertTrue(_health_check(p, "2026-07"))


class TestStatus(unittest.TestCase):
    def setUp(self):
        self.freeze = schema.parse_date("2026-07-01")

    def test_complete_and_past_its_date_is_commissioned(self):
        st, _ = _status_for({"PhysicalProgress": 100, "RevisedDate": "31/12/2025"}, self.freeze)
        self.assertEqual(st, "commissioned")

    def test_complete_but_future_dated_is_not_commissioned(self):
        st, detail = _status_for({"PhysicalProgress": 100, "RevisedDate": "31/12/2027"}, self.freeze)
        self.assertEqual(st, "under_construction")
        self.assertIn("100%", detail)

    def test_zero_progress_with_spend_is_under_construction(self):
        st, detail = _status_for({"PhysicalProgress": 0, "Expenditure": 42.5,
                                  "OriginalEndDate": "31/12/2027"}, self.freeze)
        self.assertEqual(st, "under_construction")
        self.assertIn("No physical progress", detail)

    def test_zero_progress_no_spend_but_sanctioned_is_approved(self):
        st, _ = _status_for({"PhysicalProgress": 0, "Expenditure": 0,
                             "SanctionDate": "01/01/2025"}, self.freeze)
        self.assertEqual(st, "approved")

    def test_nothing_known_is_unknown(self):
        st, _ = _status_for({"PhysicalProgress": 0, "Expenditure": 0}, self.freeze)
        self.assertEqual(st, "unknown")


class TestGeo(unittest.TestCase):
    def test_single_state_uses_it_as_a_hint(self):
        geo = _geo_for("Some rail line", ["Karnataka"])
        self.assertEqual(geo["admin"]["state"], "Karnataka")

    def test_multi_state_gets_no_state_centroid(self):
        # Placing a corridor crossing several states on one state's dot would
        # assert something the source does not say.
        geo = _geo_for("Some unplaceable corridor", ["Karnataka", "Telangana"])
        self.assertIsNone(geo["admin"]["state"])
        self.assertIsNone(geo["point"])


class TestParse(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        a = MospiPaimanaAdapter()
        rows = payload()["data"]["ProjectsCountTabDetails"]
        cls.records = list(a.parse({"freeze": "2026-07", "rows": rows, "states": {}}))

    def test_every_record_validates(self):
        for r in self.records:
            self.assertEqual(schema.validate(r), [], r["title"])

    def test_all_are_rail_with_verbatim_subsector(self):
        for r in self.records:
            self.assertEqual(r["sector"], "rail")
            self.assertEqual(r["subsector"], "Railways")

    def test_native_id_is_the_project_id(self):
        for r in self.records:
            self.assertTrue(r["native_id"].isdigit(), r["native_id"])

    def test_falsy_project_id_raises_rather_than_minting_a_new_record(self):
        # record_id() would fall back to slugify(title), and this source rewrites
        # titles often - that would destroy a project's change history.
        a = MospiPaimanaAdapter()
        row = dict(payload()["data"]["ProjectsCountTabDetails"][0])
        row["ProjectId"] = None
        with self.assertRaises(SchemaDrift):
            list(a.parse({"freeze": "2026-07", "rows": [row], "states": {}}))

    def test_no_record_is_ever_blocked(self):
        # This source publishes no obstruction information at all.
        for r in self.records:
            self.assertFalse(r["is_blocked"])
            self.assertIsNone(r["block_reason"])

    def test_every_record_carries_a_baseline(self):
        for r in self.records:
            self.assertTrue(r["original_completion_date"], r["title"])

    def test_revised_date_fallback_does_not_fabricate_zero_slip(self):
        fallback = [r for r in self.records if "no_revised_date" in r["tags"]]
        self.assertTrue(fallback, "fixture should contain a no-revised-date row")
        for r in fallback:
            self.assertIsNone(r["delay_months"],
                              "a missing revision must not read as zero slip")

    def test_cost_baseline_is_populated(self):
        for r in self.records:
            self.assertIsNotNone(r["cost_original_inr_crore"], r["title"])


class TestNum(unittest.TestCase):
    def test_tolerant(self):
        self.assertEqual(_num("1,234.5"), 1234.5)
        self.assertIsNone(_num(None))
        self.assertIsNone(_num(""))
        self.assertIsNone(_num("n/a"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
