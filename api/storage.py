"""SQLite-backed storage for ingested traces and their computed scores.

Kept intentionally simple (stdlib sqlite3, no ORM) so the whole project
stays dependency-light and easy to read end to end. Swap for Postgres by
replacing this module's connection/query calls when moving to real
deployment scale.
"""
from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Dict, List

DB_PATH = "traces.db"


def get_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS traces (
            trace_id TEXT PRIMARY KEY,
            task_description TEXT,
            trace_json TEXT,
            combined_score REAL,
            is_anomalous INTEGER,
            policy_action TEXT,
            created_at REAL
        )
        """
    )
    conn.commit()
    return conn


def save_trace_result(
    conn: sqlite3.Connection,
    trace_id: str,
    task_description: str,
    trace_json: Dict[str, Any],
    combined_score: float,
    is_anomalous: bool,
    policy_action: str,
) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO traces
        (trace_id, task_description, trace_json, combined_score, is_anomalous, policy_action, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            trace_id,
            task_description,
            json.dumps(trace_json),
            combined_score,
            int(is_anomalous),
            policy_action,
            time.time(),
        ),
    )
    conn.commit()


def list_recent(conn: sqlite3.Connection, limit: int = 50) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT trace_id, task_description, combined_score, is_anomalous, policy_action, created_at
        FROM traces ORDER BY created_at DESC LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [
        {
            "trace_id": r[0],
            "task_description": r[1],
            "combined_score": r[2],
            "is_anomalous": bool(r[3]),
            "policy_action": r[4],
            "created_at": r[5],
        }
        for r in rows
    ]


def get_stats(conn: sqlite3.Connection) -> Dict[str, Any]:
    total = conn.execute("SELECT COUNT(*) FROM traces").fetchone()[0]
    anomalous = conn.execute("SELECT COUNT(*) FROM traces WHERE is_anomalous = 1").fetchone()[0]
    avg_row = conn.execute("SELECT AVG(combined_score) FROM traces").fetchone()
    avg_score = avg_row[0] if avg_row[0] is not None else 0.0
    return {"total_traces": total, "anomalous_traces": anomalous, "avg_combined_score": avg_score}
