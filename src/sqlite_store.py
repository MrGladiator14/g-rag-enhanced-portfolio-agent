import sqlite3
import json
import os
from typing import List, Dict, Any
from .config import settings
from .logger import get_logger

logger = get_logger("sqlite_store")


class SQLiteStore:
    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = os.path.join(settings.DATA_DIR, "local_data.db")
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS sec_filings (
                        accession_no TEXT PRIMARY KEY,
                        ticker TEXT,
                        form_type TEXT,
                        filed_at TEXT,
                        url TEXT,
                        text TEXT,
                        indexed INTEGER DEFAULT 0
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS gdelt_events (
                        event_id TEXT PRIMARY KEY,
                        title TEXT,
                        source TEXT,
                        url TEXT,
                        published_at TEXT,
                        tickers TEXT,
                        indexed INTEGER DEFAULT 0
                    )
                """)
                conn.commit()
                logger.info("SQLite database initialized at " + self.db_path)
        except Exception as e:
            logger.error(f"Failed to initialize SQLite database: {e}")

    def add_sec_filing(self, filing: Dict[str, Any]) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO sec_filings (accession_no, ticker, form_type, filed_at, url, text, indexed)
                    VALUES (?, ?, ?, ?, ?, ?, 0)
                """,
                    (
                        filing["accession_no"],
                        filing["ticker"],
                        filing["form_type"],
                        filing["filed_at"],
                        filing["url"],
                        filing["text"],
                    ),
                )
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(
                f"Failed to insert SEC filing {filing.get('accession_no')}: {e}"
            )
            return False

    def add_gdelt_event(self, event: Dict[str, Any]) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO gdelt_events (event_id, title, source, url, published_at, tickers, indexed)
                    VALUES (?, ?, ?, ?, ?, ?, 0)
                """,
                    (
                        event["event_id"],
                        event["title"],
                        event["source"],
                        event["url"],
                        event["published_at"],
                        json.dumps(event.get("tickers", [])),
                    ),
                )
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to insert GDELT event {event.get('event_id')}: {e}")
            return False

    def get_unindexed_sec_filings(self) -> List[Dict[str, Any]]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM sec_filings WHERE indexed = 0")
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to fetch unindexed SEC filings: {e}")
            return []

    def get_unindexed_gdelt_events(self) -> List[Dict[str, Any]]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM gdelt_events WHERE indexed = 0")
                rows = cursor.fetchall()
                results = []
                for row in rows:
                    d = dict(row)
                    d["tickers"] = json.loads(d["tickers"])
                    results.append(d)
                return results
        except Exception as e:
            logger.error(f"Failed to fetch unindexed GDELT events: {e}")
            return []

    def mark_sec_filings_indexed(self, accession_nos: List[str]):
        if not accession_nos:
            return
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                placeholders = ",".join(["?"] * len(accession_nos))
                cursor.execute(
                    f"UPDATE sec_filings SET indexed = 1 WHERE accession_no IN ({placeholders})",
                    accession_nos,
                )
        except Exception as e:
            logger.error(f"Failed to mark SEC filings as indexed: {e}")

    def mark_gdelt_events_indexed(self, event_ids: List[str]):
        if not event_ids:
            return
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                placeholders = ",".join(["?"] * len(event_ids))
                cursor.execute(
                    f"UPDATE gdelt_events SET indexed = 1 WHERE event_id IN ({placeholders})",
                    event_ids,
                )
        except Exception as e:
            logger.error(f"Failed to mark GDELT events as indexed: {e}")

    def clear_all(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM sec_filings")
                cursor.execute("DELETE FROM gdelt_events")
                conn.commit()
                logger.info("Cleared all records from SQLite local_data.db.")
        except Exception as e:
            logger.error(f"Failed to clear SQLite database: {e}")


sqlite_db = SQLiteStore()
