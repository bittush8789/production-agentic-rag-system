import json
import sqlite3
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def init_db() -> None:
    """Initializes enterprise audit database with schema supporting security, PII, and RBAC telemetry."""
    con = sqlite3.connect(settings.audit_db_path)
    con.execute(
        """CREATE TABLE IF NOT EXISTS query_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            user_id TEXT NOT NULL DEFAULT 'usr-anon',
            username TEXT NOT NULL DEFAULT 'anonymous',
            roles_json TEXT NOT NULL DEFAULT '[]',
            question_original TEXT NOT NULL,
            question_redacted TEXT NOT NULL,
            pii_detected_json TEXT NOT NULL DEFAULT '[]',
            guardrail_status TEXT NOT NULL DEFAULT 'PASSED',
            source_used TEXT NOT NULL,
            retrieval_mode TEXT NOT NULL DEFAULT 'Hybrid',
            latency_ms INTEGER NOT NULL DEFAULT 0,
            trace_json TEXT NOT NULL
        )"""
    )
    # Ensure backward compatibility if columns were missing in older schema
    cursor = con.cursor()
    cursor.execute("PRAGMA table_info(query_audit)")
    columns = [row[1] for row in cursor.fetchall()]

    new_columns = {
        "user_id": "TEXT NOT NULL DEFAULT 'usr-anon'",
        "username": "TEXT NOT NULL DEFAULT 'anonymous'",
        "roles_json": "TEXT NOT NULL DEFAULT '[]'",
        "question_redacted": "TEXT NOT NULL DEFAULT ''",
        "pii_detected_json": "TEXT NOT NULL DEFAULT '[]'",
        "guardrail_status": "TEXT NOT NULL DEFAULT 'PASSED'",
        "retrieval_mode": "TEXT NOT NULL DEFAULT 'Hybrid'",
        "latency_ms": "INTEGER NOT NULL DEFAULT 0",
    }
    for col_name, col_type in new_columns.items():
        if col_name not in columns:
            try:
                cursor.execute(f"ALTER TABLE query_audit ADD COLUMN {col_name} {col_type}")
            except Exception as e:
                logger.debug("Column %s might already exist: %s", col_name, e)

    con.commit()
    con.close()
    logger.info("Enterprise audit database initialized at: %s", settings.audit_db_path)


def write_audit(
    question: str,
    source_used: str,
    trace: list[str],
    user_id: str = "usr-employee",
    username: str = "employee",
    roles: Optional[List[str]] = None,
    question_redacted: str = "",
    pii_detected: Optional[List[Dict[str, Any]]] = None,
    guardrail_status: str = "PASSED",
    retrieval_mode: str = "Hybrid",
    latency_ms: int = 0
) -> None:
    try:
        con = sqlite3.connect(settings.audit_db_path)
        con.execute(
            """INSERT INTO query_audit (
                created_at, user_id, username, roles_json,
                question_original, question_redacted, pii_detected_json,
                guardrail_status, source_used, retrieval_mode, latency_ms, trace_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.now(timezone.utc).isoformat(),
                user_id,
                username,
                json.dumps(roles or []),
                question,
                question_redacted or question,
                json.dumps(pii_detected or []),
                guardrail_status,
                source_used,
                retrieval_mode,
                int(latency_ms),
                json.dumps(trace),
            ),
        )
        con.commit()
        con.close()
    except Exception as exc:
        logger.error("Failed to write to audit log: %s", exc)


def get_recent_audits(limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    """Retrieves audit entries for authorized IT Support and Security Admins."""
    con = sqlite3.connect(settings.audit_db_path)
    con.row_factory = sqlite3.Row
    cursor = con.cursor()
    cursor.execute(
        """SELECT * FROM query_audit ORDER BY id DESC LIMIT ? OFFSET ?""",
        (limit, offset)
    )
    rows = cursor.fetchall()
    results = []
    for r in rows:
        results.append({
            "id": r["id"],
            "created_at": r["created_at"],
            "user_id": r["user_id"] if "user_id" in r.keys() else "legacy",
            "username": r["username"] if "username" in r.keys() else "legacy",
            "roles": json.loads(r["roles_json"]) if "roles_json" in r.keys() and r["roles_json"] else [],
            "question": r["question_original"] if "question_original" in r.keys() else r["question"],
            "question_redacted": r["question_redacted"] if "question_redacted" in r.keys() else "",
            "pii_detected": json.loads(r["pii_detected_json"]) if "pii_detected_json" in r.keys() and r["pii_detected_json"] else [],
            "guardrail_status": r["guardrail_status"] if "guardrail_status" in r.keys() else "PASSED",
            "source_used": r["source_used"],
            "retrieval_mode": r["retrieval_mode"] if "retrieval_mode" in r.keys() else "Hybrid",
            "latency_ms": r["latency_ms"] if "latency_ms" in r.keys() else 0,
            "trace": json.loads(r["trace_json"]) if r["trace_json"] else []
        })
    con.close()
    return results
