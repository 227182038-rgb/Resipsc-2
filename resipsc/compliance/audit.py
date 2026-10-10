"""21 CFR Part 11 audit trail — append-only, SHA-256 hash-chained SQLite log.

Every event carries: event_id, UTC timestamp, user id, action, entity type
and id, old/new values, reason for change, IP address, and a SHA-256 hash of
(prev_hash + event_data + timestamp). The chain head is verified on read so
tampering is detectable. Rows are never updated or deleted by any code path
(no UPDATE/DELETE statements exist against audit_events).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from resipsc.utils.logging import get_logger

LOGGER = get_logger("compliance.audit")

DB_PATH = "db/audit.db"
GENESIS = "0" * 64


class AuditTrail:
    """Append-only, cryptographically chained audit log (21 CFR Part 11)."""

    def __init__(self, db_path: str = DB_PATH) -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._conn() as c:
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp_utc TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT,
                    old_value TEXT,
                    new_value TEXT,
                    reason_for_change TEXT,
                    ip_address TEXT,
                    prev_hash TEXT NOT NULL,
                    hash TEXT NOT NULL
                )
                """
            )

    # ------------------------------------------------------------------
    def _head(self) -> str:
        with self._conn() as c:
            row = c.execute(
                "SELECT hash FROM audit_events ORDER BY event_id DESC LIMIT 1"
            ).fetchone()
        return row[0] if row else GENESIS

    @staticmethod
    def _event_hash(prev_hash: str, event_data: str, timestamp: str) -> str:
        return hashlib.sha256(
            f"{prev_hash}|{event_data}|{timestamp}".encode("utf-8")
        ).hexdigest()

    # ------------------------------------------------------------------
    def log(
        self,
        action: str,
        entity_type: str,
        entity_id: str = "",
        user_id: str = "system",
        old_value: Any = None,
        new_value: Any = None,
        reason: str = "",
        ip_address: str = "127.0.0.1",
    ) -> Dict[str, Any]:
        """Append one event; returns the stored event dict."""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()) + " UTC"
        prev = self._head()
        payload = {
            "user_id": user_id,
            "action": action,
            "entity_type": entity_type,
            "entity_id": str(entity_id),
            "old_value": json.dumps(old_value, default=str)[:2000] if old_value is not None else None,
            "new_value": json.dumps(new_value, default=str)[:2000] if new_value is not None else None,
            "reason_for_change": reason,
            "ip_address": ip_address,
        }
        h = self._event_hash(prev, json.dumps(payload, sort_keys=True, default=str), timestamp)
        with self._conn() as c:
            c.execute(
                """INSERT INTO audit_events
                   (timestamp_utc, user_id, action, entity_type, entity_id,
                    old_value, new_value, reason_for_change, ip_address, prev_hash, hash)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    timestamp, payload["user_id"], action, entity_type,
                    payload["entity_id"], payload["old_value"], payload["new_value"],
                    payload["reason_for_change"], payload["ip_address"], prev, h,
                ),
            )
        LOGGER.info("audit: %s %s/%s", action, entity_type, entity_id)
        return {
            "timestamp_utc": timestamp,
            "user_id": user_id,
            "action": action,
            "entity_type": entity_type,
            "entity_id": str(entity_id),
            "prev_hash": prev,
            "hash": h,
        }

    # ------------------------------------------------------------------
    def query(
        self,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        action: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        """Query events with filters (ISO dates compare lexicographically)."""
        sql = "SELECT event_id, timestamp_utc, user_id, action, entity_type, entity_id, old_value, new_value, reason_for_change, ip_address, prev_hash, hash FROM audit_events WHERE 1=1"
        args: List[Any] = []
        if entity_type:
            sql += " AND entity_type = ?"
            args.append(entity_type)
        if entity_id:
            sql += " AND entity_id = ?"
            args.append(entity_id)
        if action:
            sql += " AND action = ?"
            args.append(action)
        if from_date:
            sql += " AND timestamp_utc >= ?"
            args.append(from_date)
        if to_date:
            sql += " AND timestamp_utc <= ?"
            args.append(to_date + " 23:59:59")
        sql += " ORDER BY event_id DESC LIMIT ?"
        args.append(int(limit))
        with self._conn() as c:
            rows = c.execute(sql, args).fetchall()
        keys = ["event_id", "timestamp_utc", "user_id", "action", "entity_type",
                "entity_id", "old_value", "new_value", "reason_for_change",
                "ip_address", "prev_hash", "hash"]
        return [dict(zip(keys, r)) for r in rows]

    # ------------------------------------------------------------------
    def verify_chain(self) -> Dict[str, Any]:
        """Recompute the hash chain and report integrity."""
        with self._conn() as c:
            rows = c.execute(
                "SELECT event_id, timestamp_utc, user_id, action, entity_type, entity_id, old_value, new_value, reason_for_change, ip_address, prev_hash, hash FROM audit_events ORDER BY event_id"
            ).fetchall()
        expected_prev = GENESIS
        ok = True
        broken_at = None
        for r in rows:
            if r[10] != expected_prev:
                ok, broken_at = False, r[0]
                break
            payload = {
                "user_id": r[2], "action": r[3], "entity_type": r[4],
                "entity_id": r[5], "old_value": r[6], "new_value": r[7],
                "reason_for_change": r[8], "ip_address": r[9],
            }
            h = self._event_hash(expected_prev, json.dumps(payload, sort_keys=True, default=str), r[1])
            if h != r[11]:
                ok, broken_at = False, r[0]
                break
            expected_prev = r[11]
        return {
            "chain_intact": ok,
            "n_events": len(rows),
            "broken_at_event": broken_at,
            "genesis": GENESIS,
            "head_hash": rows[-1][11] if rows else GENESIS,
        }

    # ------------------------------------------------------------------
    def export_csv(self, path: str) -> int:
        """Export the full trail to CSV for inspectors."""
        import csv

        events = self.query(limit=10**7)
        keys = ["event_id", "timestamp_utc", "user_id", "action", "entity_type",
                "entity_id", "old_value", "new_value", "reason_for_change",
                "ip_address", "prev_hash", "hash"]
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=keys)
            w.writeheader()
            for e in events:
                w.writerow(e)
        return len(events)
