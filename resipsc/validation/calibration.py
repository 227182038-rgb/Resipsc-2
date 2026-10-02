"""Calibration drift monitor with SQLite persistence.

Tracks the model's score distribution (and biomarker agreement) per batch.
Drift metrics: KL divergence, JS divergence, Wasserstein-1 (earth mover)
and KS statistic against the stored reference distribution. Each check is
persisted to db/calibration.db so the dashboard can chart drift over time.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from scipy import stats as sps

from resipsc.utils.logging import get_logger

LOGGER = get_logger("validation.calibration")

DB_PATH = "db/calibration.db"

KL_THRESH = 0.10
JS_THRESH = 0.05
WASS_THRESH = 0.10
KS_THRESH = 0.15


def _js(p: np.ndarray, q: np.ndarray, bins: int = 40) -> float:
    """Jensen-Shannon divergence on histogram densities."""
    lo = min(p.min(), q.min())
    hi = max(p.max(), q.max())
    if hi <= lo:
        return 0.0
    edges = np.linspace(lo, hi, bins + 1)
    ph, _ = np.histogram(p, bins=edges, density=False)
    qh, _ = np.histogram(q, bins=edges, density=False)
    ph = ph / max(1, ph.sum())
    qh = qh / max(1, qh.sum())
    ph = np.clip(ph, 1e-12, None)
    qh = np.clip(qh, 1e-12, None)
    m = 0.5 * (ph + qh)
    kl_pm = float(np.sum(ph * np.log(ph / m)))
    kl_qm = float(np.sum(qh * np.log(qh / m)))
    return 0.5 * (kl_pm + kl_qm)


def _kl(p: np.ndarray, q: np.ndarray, bins: int = 40) -> float:
    lo = min(p.min(), q.min())
    hi = max(p.max(), q.max())
    if hi <= lo:
        return 0.0
    edges = np.linspace(lo, hi, bins + 1)
    ph, _ = np.histogram(p, bins=edges, density=False)
    qh, _ = np.histogram(q, bins=edges, density=False)
    ph = ph / max(1, ph.sum())
    qh = qh / max(1, qh.sum())
    ph = np.clip(ph, 1e-12, None)
    qh = np.clip(qh, 1e-12, None)
    return float(np.sum(ph * np.log(ph / qh)))


class CalibrationMonitor:
    """Per-batch drift monitoring with SQLite persistence."""

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
                CREATE TABLE IF NOT EXISTS calibration_checks (
                    check_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp_utc TEXT NOT NULL,
                    batch_id TEXT NOT NULL,
                    n_cells INTEGER NOT NULL,
                    mean_probability REAL,
                    p95_probability REAL,
                    kl_divergence REAL,
                    js_divergence REAL,
                    wasserstein REAL,
                    ks_statistic REAL,
                    ks_pvalue REAL,
                    status TEXT,
                    reference_n INTEGER
                )
                """
            )
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS reference (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    created_at TEXT NOT NULL,
                    n_cells INTEGER NOT NULL,
                    probabilities_json TEXT NOT NULL
                )
                """
            )

    # ------------------------------------------------------------------
    def baseline_exists(self) -> bool:
        with self._conn() as c:
            row = c.execute("SELECT COUNT(*) FROM reference WHERE id=1").fetchone()
        return bool(row and row[0])

    def set_baseline(self, probabilities: np.ndarray) -> None:
        probs = np.asarray(probabilities, dtype=float)
        # store at most 4000 samples to keep the row small
        if probs.size > 4000:
            idx = np.random.default_rng(0).choice(probs.size, 4000, replace=False)
            probs = probs[idx]
        with self._conn() as c:
            c.execute("DELETE FROM reference WHERE id=1")
            c.execute(
                "INSERT INTO reference (id, created_at, n_cells, probabilities_json) VALUES (1, ?, ?, ?)",
                (time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()) + " UTC",
                 int(probs.size), json.dumps(probs.tolist())),
            )
        LOGGER.info("baseline set with %d probabilities", probs.size)

    def get_reference(self) -> Optional[np.ndarray]:
        with self._conn() as c:
            row = c.execute(
                "SELECT probabilities_json FROM reference WHERE id=1"
            ).fetchone()
        if not row:
            return None
        return np.array(json.loads(row[0]), dtype=float)

    # ------------------------------------------------------------------
    def check(
        self,
        probabilities: np.ndarray,
        batch_id: str = "BATCH-000",
    ) -> Dict[str, Any]:
        """Run a drift check against the stored reference distribution."""
        p = np.asarray(probabilities, dtype=float)
        ref = self.get_reference()
        if ref is None:
            self.set_baseline(p)
            ref = p

        kl = _kl(p, ref)
        js = _js(p, ref)
        try:
            wass = float(sps.wasserstein_distance(p, ref))
        except Exception:  # noqa: BLE001
            wass = float(np.abs(p.mean() - ref.mean()))
        try:
            ks_stat, ks_p = sps.ks_2samp(p, ref)
            ks_stat, ks_p = float(ks_stat), float(ks_p)
        except Exception:  # noqa: BLE001
            ks_stat, ks_p = float("nan"), float("nan")

        drifted = (kl > KL_THRESH) or (js > JS_THRESH) or (wass > WASS_THRESH) or (ks_stat > KS_THRESH)
        status = "DRIFTED" if drifted else "STABLE"

        with self._conn() as c:
            c.execute(
                """INSERT INTO calibration_checks
                   (timestamp_utc, batch_id, n_cells, mean_probability, p95_probability,
                    kl_divergence, js_divergence, wasserstein, ks_statistic, ks_pvalue,
                    status, reference_n)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()) + " UTC",
                    batch_id,
                    int(p.size),
                    float(np.mean(p)),
                    float(np.percentile(p, 95)),
                    kl, js, wass, ks_stat, ks_p,
                    status,
                    int(ref.size),
                ),
            )
        return {
            "batch_id": batch_id,
            "n_cells": int(p.size),
            "mean_probability": float(np.mean(p)),
            "p95_probability": float(np.percentile(p, 95)),
            "kl_divergence": kl,
            "js_divergence": js,
            "wasserstein": wass,
            "ks_statistic": ks_stat,
            "ks_pvalue": ks_p,
            "status": status,
            "thresholds": {
                "kl": KL_THRESH, "js": JS_THRESH,
                "wasserstein": WASS_THRESH, "ks": KS_THRESH,
            },
        }

    # ------------------------------------------------------------------
    def status(self) -> Dict[str, Any]:
        """Aggregate status for the dashboard."""
        with self._conn() as c:
            rows = c.execute(
                """SELECT timestamp_utc, batch_id, n_cells, mean_probability,
                          kl_divergence, js_divergence, wasserstein, ks_statistic,
                          ks_pvalue, status
                   FROM calibration_checks ORDER BY check_id DESC LIMIT 50"""
            ).fetchall()
            ref = c.execute(
                "SELECT created_at, n_cells FROM reference WHERE id=1"
            ).fetchone()
        history = [
            {
                "timestamp_utc": r[0],
                "batch_id": r[1],
                "n_cells": r[2],
                "mean_probability": r[3],
                "kl_divergence": r[4],
                "js_divergence": r[5],
                "wasserstein": r[6],
                "ks_statistic": r[7],
                "ks_pvalue": r[8],
                "status": r[9],
            }
            for r in reversed(rows)
        ]
        latest = history[-1] if history else None
        return {
            "model": "resipsc-ensemble-2.0.0",
            "baseline_established": bool(ref),
            "baseline_created_at": ref[0] if ref else None,
            "baseline_n_cells": ref[1] if ref else 0,
            "batches_monitored": len(history),
            "latest": latest,
            "latest_metrics": (
                {
                    "kl": latest["kl_divergence"],
                    "js": latest["js_divergence"],
                    "wasserstein": latest["wasserstein"],
                    "ks": latest["ks_statistic"],
                    "status": latest["status"],
                }
                if latest
                else None
            ),
            "thresholds": {
                "kl": KL_THRESH, "js": JS_THRESH,
                "wasserstein": WASS_THRESH, "ks": KS_THRESH,
            },
            "history": history,
        }
