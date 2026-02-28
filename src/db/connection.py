"""
Database connection management for the GeoPackage/SQLite database.

Provides a context manager for safe connection handling with WAL mode
and foreign key enforcement.
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from config.settings import GEOPACKAGE_PATH


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Create a new database connection with standard pragmas.

    Args:
        db_path: Path to the GeoPackage file. Defaults to GEOPACKAGE_PATH.
            Use ":memory:" for testing.
    """
    if db_path is None:
        db_path = GEOPACKAGE_PATH

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def db_connection(db_path: Path | None = None):
    """Context manager for database connections.

    Commits on success, rolls back on exception, always closes.

    Args:
        db_path: Path to the GeoPackage file. Use ":memory:" for testing.
    """
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
