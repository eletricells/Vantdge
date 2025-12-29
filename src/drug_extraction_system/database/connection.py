"""
Database Connection Manager

Provides PostgreSQL connection management using psycopg2.
Follows the same patterns as other database modules in the codebase.
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Optional
import logging
from contextlib import contextmanager

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not installed, rely on system env vars

logger = logging.getLogger(__name__)


class DatabaseConnection:
    """
    Database connection manager for drug extraction system.
    
    Follows the psycopg2 pattern used throughout the codebase.
    """

    def __init__(self, database_url: Optional[str] = None):
        """
        Initialize database connection manager.

        Args:
            database_url: PostgreSQL connection string. 
                         Defaults to DRUG_DATABASE_URL env var.
        """
        self.database_url = database_url or os.getenv("DRUG_DATABASE_URL")
        if not self.database_url:
            raise ValueError(
                "Database URL required. Set DRUG_DATABASE_URL environment variable "
                "or pass database_url parameter."
            )
        self.connection: Optional[psycopg2.extensions.connection] = None

    @property
    def conn(self):
        """Alias for connection (compatibility with existing code)."""
        return self.connection

    def connect(self) -> None:
        """Establish database connection."""
        try:
            self.connection = psycopg2.connect(self.database_url)
            logger.info("Connected to drug extraction database")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    def close(self) -> None:
        """Close database connection."""
        if self.connection:
            self.connection.close()
            self.connection = None
            logger.info("Closed drug extraction database connection")

    def is_connected(self) -> bool:
        """Check if connection is active."""
        if not self.connection:
            return False
        try:
            # Try a simple query to verify connection is alive
            with self.connection.cursor() as cur:
                cur.execute("SELECT 1")
            return True
        except Exception:
            return False

    def ensure_connected(self) -> None:
        """Ensure connection is active, reconnect if needed."""
        if not self.is_connected():
            self.connect()

    @contextmanager
    def cursor(self, dict_cursor: bool = True):
        """
        Context manager for database cursor.

        Args:
            dict_cursor: If True, returns RealDictCursor for dict-like row access

        Yields:
            Database cursor

        Example:
            with db.cursor() as cur:
                cur.execute("SELECT * FROM drugs WHERE drug_id = %s", (1,))
                row = cur.fetchone()
        """
        self.ensure_connected()
        cursor_factory = RealDictCursor if dict_cursor else None
        cursor = self.connection.cursor(cursor_factory=cursor_factory)
        try:
            yield cursor
        finally:
            cursor.close()

    @contextmanager
    def transaction(self):
        """
        Context manager for database transactions.

        Auto-commits on success, rolls back on exception.

        Example:
            with db.transaction():
                db.execute("INSERT INTO drugs ...")
                db.execute("INSERT INTO indications ...")
        """
        self.ensure_connected()
        try:
            yield self
            self.connection.commit()
        except Exception as e:
            self.connection.rollback()
            logger.error(f"Transaction rolled back: {e}")
            raise

    def execute(self, query: str, params: tuple = None, dict_cursor: bool = True):
        """
        Execute query and return results.

        Args:
            query: SQL query string
            params: Query parameters
            dict_cursor: If True, returns dict-like rows

        Returns:
            List of rows for SELECT, or number of affected rows for INSERT/UPDATE/DELETE
        """
        self.ensure_connected()
        cursor_factory = RealDictCursor if dict_cursor else None

        with self.connection.cursor(cursor_factory=cursor_factory) as cur:
            cur.execute(query, params)

            if cur.description:  # SELECT query
                return cur.fetchall()
            else:  # INSERT/UPDATE/DELETE
                return cur.rowcount

    def execute_one(self, query: str, params: tuple = None, dict_cursor: bool = True):
        """Execute query and return single result."""
        self.ensure_connected()
        cursor_factory = RealDictCursor if dict_cursor else None

        with self.connection.cursor(cursor_factory=cursor_factory) as cur:
            cur.execute(query, params)
            return cur.fetchone()

    def commit(self) -> None:
        """Commit current transaction."""
        if self.connection:
            self.connection.commit()

    def rollback(self) -> None:
        """Rollback current transaction."""
        if self.connection:
            self.connection.rollback()

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

