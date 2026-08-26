"""Tests. Standard library unittest, no pip install needed.

    python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.adapters.seed import SeedAdapter
from pipeline.adapters.nhai_geoserver import STATUS_MAP, _geometry_for, _num
from pipeline.core import gazetteer, ids, publish as publish_mod, schema
from pipeline.core.store import Store


def minimal(**over):
    r = schema.blank_record()
    r.update(id="t-1", title="Test project", sector="road", status="under_construction")
    r["provenance"] = [schema.make_provenance("t", "Test", "https://example.gov.in")]
    r["geo"]["point"] = [77.2, 28.6]
    r["geo"]["geo_confidence"] = "city"
    r["geo"]["geo_method"] = "gazetteer"
    r.update(over)
    return schema.derive(r)


class TestSchema(unittest.TestCase):
    def test_valid_record_passes(self):
        self.assertEqual(schema.validate(minimal()), [])

    def test_missing_title_fails(self):
        with self.assertRaises(schema.ValidationError):
            schema.validate(minimal(title=None))

    def test_unsourced_record_is_refused(self):
        r = minimal()
        r["provenance"] = []
        with self.assertRaises(schema.ValidationError):
            schema.validate(r)

    def test_provenance_needs_url_and_timestamp(self):
        r = minimal()
        r["provenance"] = [{"source_id": "t", "source_name": "T"}]
        problems = schema.validate(r, strict=False)
        self.assertTrue(any("source_url" in p for p in problems))
        self.assertTrue(any("retrieved_at" in p for p in problems))

    def test_latlon_swap_is_caught(self):
        r = minimal()
        r["geo"]["point"] = [28.6, 77.2]      # swapped
        problems = schema.validate(r, strict=False)
        self.assertTrue(any("swapped" in p for p in problems), problems)

    def test_point_outside_india_is_caught(self):
        r = minimal()
        r["geo"]["point"] = [-74.0, 40.7]     # New York
        self.assertTrue(schema.validate(r, strict=False))

    def test_unknown_vocab_rejected(self):
        self.assertTrue(schema.validate(minimal(sector="spaceport"), strict=False))
        self.assertTrue(schema.validate(minimal(status="vibing"), strict=False))

    def test_derive_computes_overrun_and_delay(self):
        r = minimal(cost_original_inr_crore=1000, cost_inr_crore=1500,
                    original_completion_date="2020-01", revised_completion_date="2023-07")
        schema.derive(r)
        self.assertEqual(r["cost_overrun_pct"], 50.0)
        self.assertEqual(r["delay_months"], 42)

    def test_is_blocked_is_derived_not_trusted(self):
        r = minimal(status="stalled", is_blocked=False)
        schema.derive(r)
        self.assertTrue(r["is_blocked"])

    def test_tolerant_date_parsing(self):
        for raw in ("2024-03", "01/03/2024", "Mar 2024", "March-2024", "2024-03-01"):
            self.assertIsNotNone(schema.parse_date(raw), raw)
        self.assertIsNone(schema.parse_date("whenever"))


class TestIds(unittest.TestCase):
    def test_id_is_deterministic(self):
        a = ids.record_id("nhai", "PKG-42", "Four laning of something")
        b = ids.record_id("nhai", "PKG-42", "A completely different title")
        self.assertEqual(a, b, "native_id should dominate, so titles can be corrected safely")

    def test_id_falls_back_to_title(self):
        a = ids.record_id("mospi", None, "Zojila Tunnel")
        b = ids.record_id("mospi", None, "  zojila   tunnel  ")
        self.assertEqual(a, b, "slugging should make the fallback stable")

    def test_id_requires_something(self):
        with self.assertRaises(ValueError):
            ids.record_id("x", None, "")

    def test_stopwords_dropped_from_tokens(self):
        toks = ids.title_tokens("Construction of new bridge project at Patna, Phase 2")
        self.assertIn("bridge", toks)
        self.assertIn("patna", toks)
        self.assertNotIn("construction", toks)
        self.assertNotIn("project", toks)
        self.assertNotIn("phase", toks)

    def test_same_source_records_never_merge(self):
        a = minimal(id="s-1", title="Zojila Tunnel approach road")
        b = minimal(id="s-2", title="Zojila Tunnel approach road")
        links = ids.find_links([a, b])
        self.assertEqual(links["merge"], [])

    def test_cross_source_duplicate_is_flagged(self):
        a = minimal(id="mospi-1", title="Zojila Tunnel on NH-1", cost_inr_crore=6800)
        a["provenance"][0]["source_id"] = "mospi"
        a["geo"]["admin"]["state"] = "Ladakh"
        b = minimal(id="nhidcl-1", title="Zojila Tunnel", cost_inr_crore=6800)
        b["provenance"][0]["source_id"] = "nhidcl"
        b["geo"]["admin"]["state"] = "Ladakh"
        links = ids.find_links([a, b])
        self.assertTrue(links["merge"] or links["review"],
                        "an obvious cross-source duplicate should at least reach review")

    def test_distant_projects_are_not_merged(self):
        a = minimal(id="a-1", title="Metro rail phase 2 Kochi")
        a["provenance"][0]["source_id"] = "a"
        a["geo"]["point"] = [76.2673, 9.9312]
        b = minimal(id="b-1", title="Metro rail phase 2 Kanpur")
        b["provenance"][0]["source_id"] = "b"
        b["geo"]["point"] = [80.3319, 26.4499]
        links = ids.find_links([a, b])
        self.assertEqual(links["merge"], [], "1800 km apart should never auto-merge")


class TestGazetteer(unittest.TestCase):
    def test_city_match(self):
        g = gazetteer.locate("Greenfield airport at Hollongi, Arunachal Pradesh")
        self.assertEqual(g["geo_confidence"], "city")
        self.assertEqual(g["admin"]["state"], "Arunachal Pradesh")

    def test_corridor_becomes_a_linestring(self):
        g = gazetteer.locate("Mumbai-Ahmedabad High Speed Rail Corridor")
        self.assertEqual(g["geometry"]["type"], "LineString")
        self.assertEqual(len(g["geometry"]["coordinates"]), 2)

    def test_state_fallback_is_labelled_honestly(self):
        g = gazetteer.locate("Widening of NH-44 from Km 235 to Km 310", state_hint="Telangana")
        self.assertEqual(g["geo_confidence"], "state")
        self.assertIn("unknown", g["geo_note"])

    def test_no_place_means_no_point(self):
        g = gazetteer.locate("An entirely unlocatable scheme")
        self.assertIsNone(g["point"])
        self.assertEqual(g["geo_confidence"], "none")

    def test_alias_resolution(self):
        g = gazetteer.locate("Project at Bangalore")
        self.assertEqual(g["admin"]["district"], "Bengaluru")

    def test_every_point_is_lon_lat_inside_india(self):
        for name, (lat, lon) in list(gazetteer.STATES.items()) + list(gazetteer.CITIES.items()):
            self.assertTrue(5 <= lat <= 38, "%s lat %s" % (name, lat))
            self.assertTrue(65 <= lon <= 98, "%s lon %s" % (name, lon))

    def test_aliases_point_at_real_entries(self):
        for alias, target in gazetteer.CITY_ALIASES.items():
            self.assertIn(target, gazetteer.CITIES, "city alias %s -> %s" % (alias, target))
        for alias, target in gazetteer.STATE_ALIASES.items():
            self.assertIn(target, gazetteer.STATES, "state alias %s -> %s" % (alias, target))


class TestStoreChangeDetection(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
        self.tmp.close()
        self.store = Store(self.tmp.name)

    def tearDown(self):
        self.store.close()
        os.unlink(self.tmp.name)

    def test_first_write_is_new(self):
        outcome, diffs = self.store.upsert(minimal(), "run-1")
        self.assertEqual(outcome, "new")
        self.assertEqual(diffs, [])

    def test_identical_rewrite_is_unchanged(self):
        self.store.upsert(minimal(), "run-1")
        outcome, diffs = self.store.upsert(minimal(), "run-2")
        self.assertEqual(outcome, "unchanged")
        self.assertEqual(self.store.stats()["changes"], 0)

    def test_slipped_deadline_is_recorded(self):
        self.store.upsert(minimal(revised_completion_date="2026-03"), "run-1")
        outcome, diffs = self.store.upsert(minimal(revised_completion_date="2028-03"), "run-2")
        self.assertEqual(outcome, "changed")
        fields = [d["field"] for d in diffs]
        self.assertIn("revised_completion_date", fields)
        hist = self.store.changes_for("t-1")
        self.assertEqual(len(hist), 1)
        self.assertEqual(hist[0]["old_value"], "2026-03")
        self.assertEqual(hist[0]["new_value"], "2028-03")
        self.assertEqual(hist[0]["source_url"], "https://example.gov.in")

    def test_status_flip_to_blocked_is_recorded(self):
        self.store.upsert(minimal(status="under_construction"), "run-1")
        self.store.upsert(minimal(status="stalled"), "run-2")
        hist = self.store.changes_for("t-1")
        self.assertTrue(any(h["field"] == "status" and h["new_value"] == "stalled" for h in hist))

    def test_history_accumulates_across_runs(self):
        for i, cost in enumerate([1000, 1200, 1500, 1500, 2000]):
            self.store.upsert(minimal(cost_inr_crore=cost), "run-%d" % i)
        hist = [h for h in self.store.changes_for("t-1") if h["field"] == "cost_inr_crore"]
        self.assertEqual(len(hist), 3, "three real moves, the repeat should not log")

    def test_float_int_noise_is_not_a_change(self):
        self.store.upsert(minimal(cost_inr_crore=1000), "run-1")
        outcome, _ = self.store.upsert(minimal(cost_inr_crore=1000.0), "run-2")
        self.assertEqual(outcome, "unchanged")

    def test_first_seen_survives_updates(self):
        self.store.upsert(minimal(), "run-1")
        first = self.store.get("t-1")["first_seen"]
        self.store.upsert(minimal(cost_inr_crore=99), "run-2")
        self.assertEqual(self.store.get("t-1")["first_seen"], first)

    def test_provenance_from_other_sources_is_kept(self):
        a = minimal()
        a["provenance"][0]["source_id"] = "mospi"
        self.store.upsert(a, "run-1")
        b = minimal(cost_inr_crore=500)
        b["provenance"] = [schema.make_provenance("nhai", "NHAI", "https://nhai.gov.in/x")]
        self.store.upsert(b, "run-2")
        sources = {p["source_id"] for p in self.store.get("t-1")["provenance"]}
        self.assertEqual(sources, {"mospi", "nhai"})


class TestSeedAdapter(unittest.TestCase):
    def test_seed_records_all_validate(self):
        a = SeedAdapter()
        recs = list(a.parse(a.fetch()))
        self.assertGreater(len(recs), 20)
        for r in recs:
            self.assertEqual(schema.validate(r), [], r["title"])

    def test_seed_is_always_tagged_unverified(self):
        a = SeedAdapter()
        for r in a.parse(a.fetch()):
            self.assertIn("unverified", r["tags"], r["title"])

    def test_seed_ids_are_unique(self):
        a = SeedAdapter()
        got = [r["id"] for r in a.parse(a.fetch())]
        self.assertEqual(len(got), len(set(got)))

    def test_every_seed_record_is_geocoded(self):
        a = SeedAdapter()
        for r in a.parse(a.fetch()):
            self.assertIsNotNone(r["geo"]["point"], r["title"])


class TestNhaiAdapterOffline(unittest.TestCase):
    """No network calls here - the live GeoServer is exercised manually
    (see docs/RUNBOOK.md), not in CI. This locks down the parts that don't
    need the network: the status vocabulary mapping and the geometry join."""

    def test_every_mapped_status_is_canonical(self):
        for raw, mapped in STATUS_MAP.items():
            self.assertIn(mapped, schema.STATUSES, raw)

    def test_num_parses_indian_grouping_and_junk(self):
        self.assertEqual(_num("263.00"), 263.0)
        self.assertEqual(_num("1,20,000"), 120000.0)
        self.assertIsNone(_num(None))
        self.assertIsNone(_num("N/A"))

    def test_geometry_prefers_source_coordinates(self):
        align = {"starting_l": 14.43, "starting_1": 75.91, "end_latitu": 14.16, "end_longit": 76.47}
        geo = _geometry_for(align, "Some highway", "Karnataka", "Bengaluru")
        self.assertEqual(geo["geo_confidence"], "site")
        self.assertEqual(geo["geo_method"], "source_latlon")
        self.assertEqual(geo["geometry"]["type"], "LineString")

    def test_geometry_falls_back_to_gazetteer_when_source_has_none(self):
        geo = _geometry_for(None, "Widening of road near Mysuru", "Karnataka", None)
        self.assertEqual(geo["geo_method"], "gazetteer")
        self.assertIsNotNone(geo["point"])

    def test_geometry_rejects_out_of_india_coordinates(self):
        align = {"starting_l": 40.7, "starting_1": -74.0, "end_latitu": None, "end_longit": None}
        geo = _geometry_for(align, "Widening of road near Mysuru", None, None)
        self.assertEqual(geo["geo_method"], "gazetteer", "an out-of-bbox source point must not be trusted silently")
        self.assertNotEqual(geo["point"], [-74.0, 40.7])


class TestPublish(unittest.TestCase):
    def test_records_without_geometry_are_dropped_not_faked(self):
        good = minimal(id="good")
        bad = minimal(id="bad")
        bad["geo"]["point"] = None
        with tempfile.TemporaryDirectory() as d:
            meta = publish_mod.publish([good, bad], [], [], out_dir=d)
            self.assertEqual(meta["counts"]["published"], 1)
            self.assertEqual(meta["counts"]["dropped_no_geometry"], 1)
            with open(os.path.join(d, "projects.geojson")) as fh:
                fc = json.load(fh)
            self.assertEqual(len(fc["features"]), 1)

    def test_verified_only_excludes_seed(self):
        seed = minimal(id="s", tags=["seed", "unverified"])
        real = minimal(id="r")
        with tempfile.TemporaryDirectory() as d:
            meta = publish_mod.publish([seed, real], [], [], out_dir=d,
                                       include_unverified=False)
            self.assertEqual(meta["counts"]["published"], 1)
            self.assertEqual(meta["counts"]["dropped_unverified"], 1)

    def test_geojson_coordinate_order(self):
        with tempfile.TemporaryDirectory() as d:
            publish_mod.publish([minimal()], [], [], out_dir=d)
            with open(os.path.join(d, "projects.geojson")) as fh:
                fc = json.load(fh)
            lon, lat = fc["features"][0]["geometry"]["coordinates"]
            self.assertAlmostEqual(lon, 77.2)
            self.assertAlmostEqual(lat, 28.6)

    def test_meta_carries_disclaimer_and_sources(self):
        with tempfile.TemporaryDirectory() as d:
            meta = publish_mod.publish([minimal()], [], [{"source_id": "x"}], out_dir=d)
            self.assertIn("Not investment advice", meta["disclaimer"])
            self.assertEqual(len(meta["sources"]), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
