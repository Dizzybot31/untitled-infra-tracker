"""Guards on the published data that the frontend's interface depends on.

The globe shows four counts side by side. That is only honest if the four sets
genuinely partition the corpus - if they overlapped, a reader adding them up
would get a number larger than the dataset. These tests encode that invariant so
a future adapter or status-vocabulary change cannot quietly break it.

They run against data/derived, so they are skipped when it has not been built.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
DERIVED = os.path.join(ROOT, "data", "derived")


def _load(name):
    with open(os.path.join(DERIVED, name), encoding="utf-8") as fh:
        return json.load(fh)


@unittest.skipUnless(os.path.exists(os.path.join(DERIVED, "projects.geojson")),
                     "data/derived not built; run `python3 -m pipeline.run all`")
class TestPublishedPartition(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fc = _load("projects.geojson")
        cls.meta = _load("meta.json")
        cls.rows = [f["properties"] for f in cls.fc["features"]]
        cls.as_of = dt.date.fromisoformat(cls.meta["generated_at"][:10])

    # These mirror lifecycleOf()/bucketOf() in web/js/data.js. If you change one,
    # change the other - this test exists to make that coupling loud.
    def lifecycle(self, p):
        if p.get("is_blocked") or p.get("block_reason"):
            return "stopped"
        if p["status"] == "commissioned":
            return "open"
        if p["status"] == "unknown":
            return "unstated"
        return "building"

    def bucket(self, p):
        lc = self.lifecycle(p)
        if lc != "building":
            return lc
        d = p.get("revised_completion_date")
        if not d:
            return "no_date"
        try:
            return "past_due" if dt.date.fromisoformat(d[:10]) < self.as_of else "on_schedule"
        except ValueError:
            return "no_date"

    def test_lifecycle_sets_partition_the_corpus(self):
        counts = {}
        for p in self.rows:
            k = self.lifecycle(p)
            counts[k] = counts.get(k, 0) + 1
        self.assertEqual(sum(counts.values()), len(self.rows),
                         "lifecycle sets must cover every row exactly once")

    def test_buckets_partition_the_drawn_set(self):
        drawn = [p for p in self.rows if self.lifecycle(p) in ("building", "stopped")]
        counts = {}
        for p in drawn:
            counts[self.bucket(p)] = counts.get(self.bucket(p), 0) + 1
        self.assertEqual(sum(counts.values()), len(drawn))
        # The four bucket names the interface prints in its key row.
        self.assertLessEqual(set(counts), {"past_due", "on_schedule", "no_date", "stopped"})

    def test_finished_projects_are_never_past_due(self):
        # A commissioned project's completion date being in the past is the
        # expected outcome, not an alarm. Regression guard: an earlier version
        # coloured all 1,122 finished rows amber.
        for p in self.rows:
            if p["status"] == "commissioned" and not p.get("is_blocked") and not p.get("block_reason"):
                self.assertEqual(self.bucket(p), "open", p.get("title"))

    def test_every_drawn_row_has_a_title_and_coordinates(self):
        for f in self.fc["features"]:
            p = f["properties"]
            if self.lifecycle(p) not in ("building", "stopped"):
                continue
            self.assertTrue(p.get("title"), p.get("id"))
            lon, lat = f["geometry"]["coordinates"]
            self.assertTrue(65 <= lon <= 98 and 5 <= lat <= 38, (p.get("id"), lon, lat))

    def test_census_counts_reconcile(self):
        c = self.meta["counts"]
        self.assertEqual(
            c["published"] + c.get("unlocated", 0) + c.get("superseded", 0),
            c["total_in_store"],
            "every stored record must be published, listed as unlocated, or superseded")

    def test_no_cross_source_duplicate_titles(self):
        """Standing guard against the PAIMANA/NHAI road double-count.

        PAIMANA carries 993 road projects that are largely the same contracts
        NHAI already publishes under a different spelling. Only its railways are
        ingested today; the day someone adds roads without the title join, this
        fails loudly instead of silently inflating every headline number.

        Scoped to CROSS-source collisions on purpose. Within a single source,
        that source's own key is authoritative and identical titles are legal:
        NHAI really does publish three pairs of distinct contract packages that
        share a title (e.g. N/07016/01001/BR and N/07016/01004/BR, "Balance Work
        of Piprakothi-Motihari-Raxaul on NH-28A"). Those are different packages
        of one stretch, not duplicates - the same principle ids.find_links()
        already applies by refusing to merge within a source.
        """
        import re
        seen = {}
        for f in self.fc["features"]:
            p = f["properties"]
            title = p.get("title") or ""
            key = re.sub(r"[^a-z0-9]", "", title.lower())
            if not key:
                continue
            source = (p.get("id") or "").rsplit("-", 1)[0]
            if key in seen and seen[key][0] != source:
                self.fail("the same project appears under two sources: %r is published by "
                          "both %s (%s) and %s (%s)"
                          % (title, seen[key][0], seen[key][1], source, p.get("id")))
            seen[key] = (source, p.get("id"))

    def test_meta_exposes_what_the_about_sheet_reads(self):
        for key in ("generated_at", "sources", "disclaimer", "counts", "vocab"):
            self.assertIn(key, self.meta)
        self.assertTrue(self.meta["sources"], "About sheet lists sources; none published")
        for s in self.meta["sources"]:
            self.assertTrue(s.get("source_name") and s.get("source_url"))


@unittest.skipUnless(os.path.exists(os.path.join(ROOT, "web", "index.html")), "no web/")
def _strip_html_comments(html):
    import re
    return re.sub(r"<!--.*?-->", "", html, flags=re.S)


def _strip_js_comments(src):
    import re
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^\s*//.*$", "", src, flags=re.M)


class TestFrontendContract(unittest.TestCase):
    """Cheap structural checks. These caught two real bugs during the redesign.

    Comments are stripped before asserting: the source deliberately *documents*
    what was removed (the esm.sh graph, delayText), and a naive substring match
    would fail on the explanation of the fix rather than on the fix.
    """

    def test_no_hardcoded_counts_in_markup(self):
        # Counts are computed at runtime precisely so they cannot ship stale.
        # An earlier plan baked "675"/"398" into index.html; the numbers were
        # already wrong by the time they were written down.
        with open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8") as fh:
            html = fh.read()
        for n in ("1,849", "675", "398", "1,122"):
            self.assertNotIn(n, html,
                             f"{n!r} is hardcoded in index.html; render it from meta.json instead")

    def test_globe_library_is_vendored_not_cdn(self):
        with open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8") as fh:
            html = _strip_html_comments(fh.read())
        self.assertIn("vendor/globe.gl", html)
        self.assertNotIn("esm.sh", html)
        self.assertTrue(os.path.exists(os.path.join(ROOT, "web", "vendor", "globe.gl-2.46.2.min.js")))

    def test_no_module_imports_a_remote_url(self):
        js_dir = os.path.join(ROOT, "web", "js")
        for name in os.listdir(js_dir):
            if not name.endswith(".js"):
                continue
            with open(os.path.join(js_dir, name), encoding="utf-8") as fh:
                src = _strip_js_comments(fh.read())
            self.assertNotIn("https://esm.sh", src, name)
            self.assertNotIn("https://unpkg.com", src, name)

    def test_slip_language_is_gated_not_absent(self):
        """Slip figures returned with PAIMANA, but only behind a guard.

        Before PAIMANA no source published a baseline, so these figures were
        removed outright. Now some records have one and most do not, which is a
        sharper hazard: an absent slip figure must never read as "on schedule".
        The rule is no longer "never mention slip" but "never mention it without
        first checking this record has a baseline".
        """
        for rel in ("js/format.js", "js/panel.js", "js/app.js"):
            with open(os.path.join(ROOT, "web", rel), encoding="utf-8") as fh:
                src = _strip_js_comments(fh.read())
            self.assertNotIn("behind original schedule", src, rel)
            self.assertNotIn("delayText", src, rel)

        with open(os.path.join(ROOT, "web", "js", "panel.js"), encoding="utf-8") as fh:
            panel = _strip_js_comments(fh.read())
        if "delay_months" in panel:
            self.assertIn("r.original_completion_date && r.delay_months", panel,
                          "delay_months must be gated on the baseline existing")
        if "cost_overrun_pct" in panel:
            self.assertIn("!= null", panel,
                          "cost_overrun_pct must be null-guarded before display")
        self.assertIn("not the same as being on schedule", panel,
                      "a missing slip figure must say what its absence means")

if __name__ == "__main__":
    unittest.main(verbosity=2)
