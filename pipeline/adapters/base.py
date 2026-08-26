"""The adapter contract.

One adapter per source. An adapter's only job is: go get the source's rows and
return canonical records. It must not write to the store, must not print, and
must not silently swallow failure - if the source shape changed, say so loudly
so schema drift shows up as a red CI run instead of a quietly empty dataset.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from ..core import gazetteer, ids, schema


class SourceUnavailable(RuntimeError):
    """The source could not be reached. Not the same as 'the source is empty'."""


class SchemaDrift(RuntimeError):
    """We reached the source but it no longer looks like what we parse."""


class Adapter:
    #: short, stable, filename-safe. Becomes the id prefix for its records.
    source_id: str = ""
    #: human-readable name shown in the UI's provenance line.
    source_name: str = ""
    #: landing page a human can open to check us.
    source_url: str = ""
    #: the organisation that publishes it.
    publisher: str = ""
    #: how often the upstream source itself actually changes.
    upstream_cadence: str = "unknown"
    #: 'api' | 'html' | 'pdf' | 'csv' | 'bundled' - drives expectations, not code.
    access_mode: str = "html"
    #: licence/terms under which we reuse it. Shown in the UI footer.
    licence: str = "unknown"
    #: set False for adapters that ship static data rather than fetching.
    networked: bool = True

    def fetch(self) -> Any:
        """Return whatever raw payload `parse` expects. May raise SourceUnavailable."""
        raise NotImplementedError

    def parse(self, raw: Any) -> Iterable[Dict[str, Any]]:
        """Yield canonical records. May raise SchemaDrift."""
        raise NotImplementedError

    # -- helpers available to every adapter ---------------------------------

    def new_record(self, native_id: Optional[str], title: str, retrieved_at: Optional[str] = None,
                   page_url: Optional[str] = None) -> Dict[str, Any]:
        rec = schema.blank_record()
        rec["native_id"] = native_id
        rec["title"] = (title or "").strip()
        rec["id"] = ids.record_id(self.source_id, native_id, rec["title"])
        rec["provenance"] = [schema.make_provenance(
            self.source_id, self.source_name, page_url or self.source_url, retrieved_at)]
        return rec

    def geocode(self, rec: Dict[str, Any], extra_text: str = "",
                state: Optional[str] = None, district: Optional[str] = None) -> Dict[str, Any]:
        text = " ".join(x for x in ((rec.get("title") or ""), extra_text) if x)
        rec["geo"] = gazetteer.locate(text, state_hint=state, district_hint=district)
        return rec

    def describe(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_name": self.source_name,
            "source_url": self.source_url,
            "publisher": self.publisher,
            "upstream_cadence": self.upstream_cadence,
            "access_mode": self.access_mode,
            "licence": self.licence,
            "networked": self.networked,
        }
