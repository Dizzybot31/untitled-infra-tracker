"""Bundled seed adapter - no network, no dependencies.

Its job is to make the walking skeleton walk: the globe renders real,
recognisable Indian projects on first run, so the frontend, the change log and
the publish step can all be exercised before a single .gov.in page is scraped.

Everything it emits carries tags ['seed', 'unverified'] and is badged in the UI.
Records from a networked adapter always win over a seed record on merge.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Iterable, List

from ..core import schema
from .base import Adapter

_REF = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ref", "seed_projects.json")


class SeedAdapter(Adapter):
    source_id = "seed"
    source_name = "Curated seed (hand-entered)"
    source_url = "https://github.com/dizzybot31/nirmaan/blob/main/pipeline/ref/seed_projects.json"
    publisher = "This project"
    upstream_cadence = "manual"
    access_mode = "bundled"
    licence = "CC0 for the curation; underlying facts are public record"
    networked = False

    def fetch(self) -> Any:
        with open(_REF, "r", encoding="utf-8") as fh:
            return json.load(fh)

    def parse(self, raw: Any) -> Iterable[Dict[str, Any]]:
        curated_on = raw.get("_curated_on")
        for p in raw["projects"]:
            rec = self.new_record(p["native_id"], p["title"],
                                  retrieved_at=(curated_on + "T00:00:00+00:00") if curated_on else None,
                                  page_url=p.get("source_url") or self.source_url)
            rec["sector"] = p.get("sector", "other")
            rec["subsector"] = p.get("subsector")
            rec["status"] = p.get("status", "unknown")
            rec["status_detail"] = p.get("note")
            rec["block_reason"] = p.get("block_reason")
            rec["block_detail"] = p.get("block_detail")
            rec["cost_inr_crore"] = p.get("cost_inr_crore")
            rec["sanctioned_date"] = schema.iso_month(p.get("sanctioned_date"))
            rec["original_completion_date"] = schema.iso_month(p.get("original_completion_date"))
            rec["revised_completion_date"] = schema.iso_month(p.get("revised_completion_date"))
            rec["commissioned_date"] = schema.iso_month(p.get("commissioned_date"))
            rec["progress_pct"] = p.get("progress_pct")
            rec["executing_agency"] = p.get("executing_agency")
            rec["ministry"] = p.get("ministry")
            rec["tags"] = ["seed", "unverified"]
            rec["provenance"][0]["note"] = (
                "Hand-curated for the walking skeleton. Figures are approximate public "
                "reporting, not primary-source values. Open the source link to check."
            )
            self.geocode(rec, extra_text=p.get("state") or "", state=p.get("state"))
            yield schema.derive(rec)
