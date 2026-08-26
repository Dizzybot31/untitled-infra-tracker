"""SQLite store with an append-only change log.

The change log is the reason this project is more than a scraper. A government
dashboard shows you today's number. It does not tell you that this project's
completion date has been pushed back four times, or that its cost estimate
doubled, or that a clearance was granted and then withdrawn. We keep every
observed transition, with the source URL that justified it.

SQLite because: zero setup, ships in the Python stdlib, the whole database is
one file we can commit or attach to a GitHub Release, and Datasette can serve
it read-only for free. See docs/adr/0003-storage.md.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, Iterable, List, Optional, Tuple

from . import schema

# Fields whose changes we consider newsworthy enough to log and surface.
TRACKED_FIELDS = (
    "title", "status", "status_detail", "block_reason",
    "cost_inr_crore", "original_completion_date", "revised_completion_date",
    "commissioned_date", "progress_pct", "executing_agency",
)

DDL = """
CREATE TABLE IF NOT EXISTS projects (
    id                TEXT PRIMARY KEY,
    doc               TEXT NOT NULL,          -- full canonical record as JSON
    source_id         TEXT,
    sector            TEXT,
    status            TEXT,
    is_blocked        INTEGER,
    state             TEXT,
    cost_inr_crore    REAL,
    first_seen        TEXT,
    last_seen         TEXT,
    last_changed      TEXT
);
CREATE INDEX IF NOT EXISTS idx_projects_sector ON projects(sector);
CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status);
CREATE INDEX IF NOT EXISTS idx_projects_state  ON projects(state);

CREATE TABLE IF NOT EXISTS changes (
    change_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    field       TEXT NOT NULL,
    old_value   TEXT,
    new_value   TEXT,
    source_url  TEXT,
    run_id      TEXT
);
CREATE INDEX IF NOT EXISTS idx_changes_project ON changes(project_id);
CREATE INDEX IF NOT EXISTS idx_changes_time    ON changes(observed_at);

CREATE TABLE IF NOT EXISTS runs (
    run_id      TEXT PRIMARY KEY,
    started_at  TEXT,
    finished_at TEXT,
    source_id   TEXT,
    ok          INTEGER,
    fetched     INTEGER,
    written     INTEGER,
    changed     INTEGER,
    rejected    INTEGER,
    notes       TEXT
);

CREATE TABLE IF NOT EXISTS links (
    a_id    TEXT NOT NULL,
    b_id    TEXT NOT NULL,
    score   REAL,
    reasons TEXT,
    kind    TEXT,                              -- 'merge' or 'review'
    PRIMARY KEY (a_id, b_id)
);
"""


class Store:
    def __init__(self, path: str):
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(DDL)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # -- reads ---------------------------------------------------------------

    def get(self, project_id: str) -> Optional[Dict[str, Any]]:
        row = self.conn.execute("SELECT doc FROM projects WHERE id = ?", (project_id,)).fetchone()
        return json.loads(row["doc"]) if row else None

    def all_records(self) -> List[Dict[str, Any]]:
        return [json.loads(r["doc"]) for r in self.conn.execute("SELECT doc FROM projects")]

    def recent_changes(self, limit: int = 200) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT c.*, p.doc FROM changes c LEFT JOIN projects p ON p.id = c.project_id "
            "ORDER BY c.observed_at DESC, c.change_id DESC LIMIT ?", (limit,)
        ).fetchall()
        out = []
        for r in rows:
            doc = json.loads(r["doc"]) if r["doc"] else {}
            out.append({
                "project_id": r["project_id"],
                "title": doc.get("title"),
                "sector": doc.get("sector"),
                "observed_at": r["observed_at"],
                "field": r["field"],
                "old_value": r["old_value"],
                "new_value": r["new_value"],
                "source_url": r["source_url"],
            })
        return out

    def changes_for(self, project_id: str) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT observed_at, field, old_value, new_value, source_url FROM changes "
            "WHERE project_id = ? ORDER BY observed_at ASC, change_id ASC", (project_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    # -- writes --------------------------------------------------------------

    def upsert(self, rec: Dict[str, Any], run_id: str) -> Tuple[str, List[Dict[str, Any]]]:
        """Insert or update. Returns ('new'|'changed'|'unchanged', changes)."""
        schema.derive(rec)
        schema.validate(rec)

        now = rec.get("last_seen") or schema.utcnow()
        src_url = rec["provenance"][0]["source_url"] if rec.get("provenance") else None
        src_id = rec["provenance"][0]["source_id"] if rec.get("provenance") else None
        existing = self.get(rec["id"])

        if existing is None:
            rec["first_seen"] = rec.get("first_seen") or now
            rec["last_seen"] = now
            rec["last_changed"] = now
            self._write(rec, src_id)
            return "new", []

        diffs = []
        for f in TRACKED_FIELDS:
            old, new = existing.get(f), rec.get(f)
            if _norm(old) != _norm(new):
                diffs.append({"field": f, "old_value": old, "new_value": new})

        rec["first_seen"] = existing.get("first_seen") or now
        rec["last_seen"] = now
        rec["last_changed"] = now if diffs else existing.get("last_changed")

        # Carry forward provenance from other sources we already knew about.
        merged_prov = list(rec.get("provenance") or [])
        known = {(p.get("source_id"), p.get("source_url")) for p in merged_prov}
        for p in existing.get("provenance") or []:
            if (p.get("source_id"), p.get("source_url")) not in known:
                merged_prov.append(p)
        rec["provenance"] = merged_prov

        self._write(rec, src_id)
        for d in diffs:
            self.conn.execute(
                "INSERT INTO changes (project_id, observed_at, field, old_value, new_value, source_url, run_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (rec["id"], now, d["field"], _s(d["old_value"]), _s(d["new_value"]), src_url, run_id),
            )
        self.conn.commit()
        return ("changed" if diffs else "unchanged"), diffs

    def _write(self, rec: Dict[str, Any], src_id: Optional[str]) -> None:
        geo = rec.get("geo") or {}
        self.conn.execute(
            "INSERT INTO projects (id, doc, source_id, sector, status, is_blocked, state, "
            "cost_inr_crore, first_seen, last_seen, last_changed) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET doc=excluded.doc, source_id=excluded.source_id, "
            "sector=excluded.sector, status=excluded.status, is_blocked=excluded.is_blocked, "
            "state=excluded.state, cost_inr_crore=excluded.cost_inr_crore, "
            "last_seen=excluded.last_seen, last_changed=excluded.last_changed",
            (rec["id"], json.dumps(rec, ensure_ascii=False, sort_keys=True), src_id,
             rec.get("sector"), rec.get("status"), 1 if rec.get("is_blocked") else 0,
             (geo.get("admin") or {}).get("state"), rec.get("cost_inr_crore"),
             rec.get("first_seen"), rec.get("last_seen"), rec.get("last_changed")),
        )
        self.conn.commit()

    def record_run(self, run_id: str, source_id: str, started: str, finished: str,
                   ok: bool, fetched: int, written: int, changed: int, rejected: int,
                   notes: str = "") -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?,?,?,?,?)",
            (run_id, started, finished, source_id, 1 if ok else 0, fetched, written,
             changed, rejected, notes),
        )
        self.conn.commit()

    def save_links(self, links: Dict[str, List[Dict[str, Any]]]) -> None:
        self.conn.execute("DELETE FROM links")
        for kind in ("merge", "review"):
            for l in links.get(kind, []):
                self.conn.execute(
                    "INSERT OR REPLACE INTO links VALUES (?,?,?,?,?)",
                    (l["a"], l["b"], l["score"], json.dumps(l["reasons"]), kind),
                )
        self.conn.commit()

    def stats(self) -> Dict[str, Any]:
        c = self.conn.execute
        return {
            "projects": c("SELECT COUNT(*) n FROM projects").fetchone()["n"],
            "blocked": c("SELECT COUNT(*) n FROM projects WHERE is_blocked = 1").fetchone()["n"],
            "changes": c("SELECT COUNT(*) n FROM changes").fetchone()["n"],
            "runs": c("SELECT COUNT(*) n FROM runs").fetchone()["n"],
            "by_sector": {r["sector"]: r["n"] for r in c(
                "SELECT sector, COUNT(*) n FROM projects GROUP BY sector ORDER BY n DESC")},
            "by_status": {r["status"]: r["n"] for r in c(
                "SELECT status, COUNT(*) n FROM projects GROUP BY status ORDER BY n DESC")},
        }


def _norm(v: Any) -> Any:
    if isinstance(v, float) and v == int(v):
        return int(v)
    if isinstance(v, str):
        return v.strip()
    return v


def _s(v: Any) -> Optional[str]:
    return None if v is None else str(v)
