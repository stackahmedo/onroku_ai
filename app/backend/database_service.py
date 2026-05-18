"""
database_service.py
SQLite-backed job store for V2.
"""

import sqlite3
import uuid
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)


class DatabaseService:
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        """Create tables if they don't exist."""
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id               TEXT PRIMARY KEY,
                    file_id          TEXT NOT NULL,
                    filename         TEXT NOT NULL,
                    file_path        TEXT NOT NULL,
                    status           TEXT NOT NULL DEFAULT 'pending',
                    progress_pct     INTEGER NOT NULL DEFAULT 0,
                    progress_label   TEXT NOT NULL DEFAULT '',
                    hardware_tier    TEXT,
                    model_name       TEXT,
                    language         TEXT DEFAULT 'ja',
                    speaker_count    INTEGER,
                    duration_seconds REAL,
                    created_at       TEXT NOT NULL,
                    updated_at       TEXT NOT NULL,
                    transcript_file  TEXT,
                    segment_count    INTEGER,
                    error_message    TEXT
                )
            """)
            conn.commit()
        logger.info("Database initialised")

    def create_job(
        self,
        file_id: str,
        filename: str,
        file_path: str,
        hardware_tier: Optional[str] = None,
        model_name: Optional[str] = None,
        language: str = "ja",
        duration_seconds: Optional[float] = None,
    ) -> str:
        job_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO jobs
                    (id, file_id, filename, file_path, status, hardware_tier,
                     model_name, language, duration_seconds, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (job_id, file_id, filename, file_path, "pending",
                 hardware_tier, model_name, language, duration_seconds, now, now),
            )
            conn.commit()
        logger.info(f"Job created: {job_id}")
        return job_id

    def update_job_status(self, job_id: str, status: str, error_message: Optional[str] = None):
        now = datetime.now().isoformat()
        with self._conn() as conn:
            conn.execute(
                "UPDATE jobs SET status=?, updated_at=?, error_message=? WHERE id=?",
                (status, now, error_message, job_id),
            )
            conn.commit()

    def update_progress(self, job_id: str, pct: int, label: str = ""):
        now = datetime.now().isoformat()
        with self._conn() as conn:
            conn.execute(
                "UPDATE jobs SET progress_pct=?, progress_label=?, updated_at=? WHERE id=?",
                (pct, label, now, job_id),
            )
            conn.commit()

    def update_job_duration(self, job_id: str, duration_seconds: float):
        now = datetime.now().isoformat()
        with self._conn() as conn:
            conn.execute(
                "UPDATE jobs SET duration_seconds=?, updated_at=? WHERE id=?",
                (duration_seconds, now, job_id),
            )
            conn.commit()

    def update_job_language(self, job_id: str, language: str):
        now = datetime.now().isoformat()
        with self._conn() as conn:
            conn.execute(
                "UPDATE jobs SET language=?, updated_at=? WHERE id=?",
                (language, now, job_id),
            )
            conn.commit()

    def save_transcript(
        self, job_id: str, transcript_file: str, segment_count: int, speaker_count: int = 0
    ):
        now = datetime.now().isoformat()
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE jobs
                SET transcript_file=?, segment_count=?, speaker_count=?, updated_at=?
                WHERE id=?
                """,
                (transcript_file, segment_count, speaker_count, now, job_id),
            )
            conn.commit()

    def get_job(self, job_id: str) -> Optional[Dict]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return dict(row) if row else None

    def get_jobs(self, skip: int = 0, limit: int = 20) -> List[Dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, skip),
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_job(self, job_id: str):
        with self._conn() as conn:
            conn.execute("DELETE FROM jobs WHERE id=?", (job_id,))
            conn.commit()
        logger.info(f"Job deleted: {job_id}")
