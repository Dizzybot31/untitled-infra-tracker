#!/usr/bin/env python3
"""Pipeline entry point.

    python3 -m pipeline.run ingest            # run every enabled adapter
    python3 -m pipeline.run ingest --only seed
    python3 -m pipeline.run link              # cross-source entity resolution
    python3 -m pipeline.run publish           # write data/derived/*.json
    python3 -m pipeline.run all
    python3 -m pipeline.run sources           # list adapters and what they are
    python3 -m pipeline.run stats

Standard library only, Python 3.9+. No pip install required.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
import traceback
from typing import Dict, List, Type

from .adapters.base import Adapter, SchemaDrift, SourceUnavailable
from .adapters.seed import SeedAdapter
from .adapters.nhai_geoserver import NhaiGeoserverAdapter
from .core import gazetteer, ids, publish as publish_mod, schema
from .core.store import Store

DB_PATH = os.path.join("data", "nirmaan.sqlite")

# Register adapters here. Order matters only for tie-breaking on merge:
# later adapters are treated as more authoritative than earlier ones.
ADAPTERS: List[Type[Adapter]] = [
    SeedAdapter,
    NhaiGeoserverAdapter,
]

try:  # optional, added once the source is verified reachable
    from .adapters.mospi_flash import MospiFlashAdapter
    ADAPTERS.append(MospiFlashAdapter)
except ImportError:
    pass


def _run_id(source_id: str, started: str) -> str:
    return "%s-%s" % (source_id, hashlib.sha1(started.encode()).hexdigest()[:8])


def cmd_sources(args: argparse.Namespace) -> int:
    print("%-16s %-9s %-11s %s" % ("SOURCE", "MODE", "CADENCE", "NAME"))
    for cls in ADAPTERS:
        a = cls()
        d = a.describe()
        print("%-16s %-9s %-11s %s" % (d["source_id"], d["access_mode"],
                                       d["upstream_cadence"], d["source_name"]))
        print("%-16s %s" % ("", d["source_url"]))
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    store = Store(DB_PATH)
    total_new = total_changed = total_rejected = 0
    failures = []

    for cls in ADAPTERS:
        adapter = cls()
        if args.only and adapter.source_id not in args.only:
            continue
        started = schema.utcnow()
        run_id = _run_id(adapter.source_id, started)
        print("\n=== %s (%s) ===" % (adapter.source_name, adapter.source_id))
        n_new = n_changed = n_unchanged = n_rejected = 0
        ok = True
        notes = ""

        try:
            raw = adapter.fetch()
            records = list(adapter.parse(raw))
            if not records:
                raise SchemaDrift("adapter returned zero records - treat as failure, not as an empty world")
            for rec in records:
                try:
                    outcome, diffs = store.upsert(rec, run_id)
                except schema.ValidationError as e:
                    n_rejected += 1
                    print("  REJECT %s" % e)
                    continue
                if outcome == "new":
                    n_new += 1
                elif outcome == "changed":
                    n_changed += 1
                    for d in diffs:
                        print("  CHANGE %s: %s %r -> %r" % (rec["id"], d["field"], d["old_value"], d["new_value"]))
                else:
                    n_unchanged += 1
            print("  fetched=%d new=%d changed=%d unchanged=%d rejected=%d"
                  % (len(records), n_new, n_changed, n_unchanged, n_rejected))
        except (SourceUnavailable, SchemaDrift) as e:
            ok = False
            notes = "%s: %s" % (type(e).__name__, e)
            failures.append((adapter.source_id, notes))
            print("  FAILED %s" % notes)
        except Exception as e:  # noqa: BLE001 - we want the run recorded either way
            ok = False
            notes = "unexpected %s: %s" % (type(e).__name__, e)
            failures.append((adapter.source_id, notes))
            print("  FAILED %s" % notes)
            if args.traceback:
                traceback.print_exc()

        store.record_run(run_id, adapter.source_id, started, schema.utcnow(), ok,
                         n_new + n_changed + n_unchanged, n_new + n_changed,
                         n_changed, n_rejected, notes)
        total_new += n_new
        total_changed += n_changed
        total_rejected += n_rejected

    recs = store.all_records()
    print("\ntotals: new=%d changed=%d rejected=%d in_store=%d"
          % (total_new, total_changed, total_rejected, len(recs)))
    print("geocoding coverage: %s" % gazetteer.coverage_report(recs))
    store.close()

    if failures and args.strict:
        print("\nstrict mode: %d adapter(s) failed" % len(failures), file=sys.stderr)
        return 1
    return 0


def cmd_link(args: argparse.Namespace) -> int:
    store = Store(DB_PATH)
    recs = store.all_records()
    links = ids.find_links(recs)
    store.save_links(links)
    print("merge candidates: %d" % len(links["merge"]))
    for l in links["merge"][:20]:
        print("  %.2f  %s <-> %s  (%s)" % (l["score"], l["a"], l["b"], ", ".join(l["reasons"])))
    print("needs review: %d" % len(links["review"]))
    store.close()
    return 0


def cmd_publish(args: argparse.Namespace) -> int:
    store = Store(DB_PATH)
    recs = store.all_records()
    for r in recs:
        r["history"] = store.changes_for(r["id"])
    sources = [cls().describe() for cls in ADAPTERS]
    meta = publish_mod.publish(recs, store.recent_changes(500), sources,
                              include_unverified=not args.verified_only)
    print("published %d features (%d corridors), %d blocked"
          % (meta["counts"]["published"], meta["counts"]["corridors"], meta["counts"]["blocked"]))
    print("dropped for missing geometry: %d" % meta["counts"]["dropped_no_geometry"])
    print("geo confidence: %s" % meta["geo_confidence"])
    print("-> %s" % publish_mod.OUT_DIR)
    store.close()
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    store = Store(DB_PATH)
    s = store.stats()
    for k, v in s.items():
        print("%-12s %s" % (k, v))
    store.close()
    return 0


def cmd_all(args: argparse.Namespace) -> int:
    rc = cmd_ingest(args)
    cmd_link(args)
    cmd_publish(args)
    return rc


def main(argv: List[str]) -> int:
    p = argparse.ArgumentParser(prog="pipeline.run", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--traceback", action="store_true", help="print tracebacks on adapter failure")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("ingest"); pi.set_defaults(fn=cmd_ingest)
    pi.add_argument("--only", nargs="*", help="run only these source ids")
    pi.add_argument("--strict", action="store_true", help="exit non-zero if any adapter fails")

    sub.add_parser("link").set_defaults(fn=cmd_link)

    pp = sub.add_parser("publish"); pp.set_defaults(fn=cmd_publish)
    pp.add_argument("--verified-only", action="store_true",
                    help="exclude hand-curated seed records from the output")

    sub.add_parser("stats").set_defaults(fn=cmd_stats)
    sub.add_parser("sources").set_defaults(fn=cmd_sources)

    pa = sub.add_parser("all"); pa.set_defaults(fn=cmd_all)
    pa.add_argument("--only", nargs="*")
    pa.add_argument("--strict", action="store_true")
    pa.add_argument("--verified-only", action="store_true")

    args = p.parse_args(argv)
    for attr, default in (("only", None), ("strict", False), ("verified_only", False)):
        if not hasattr(args, attr):
            setattr(args, attr, default)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
