"""
Base repository with common database operations.

Provides connection management, cursor handling, and common patterns.
"""

import logging
from functools import wraps
from typing import Optional, List, Dict, Any, TypeVar, Generic, Callable
from contextlib import contextmanager

from psycopg2.extras import RealDictCursor

# Import the existing DatabaseConnection to reuse it
from src.drug_extraction_system.database.connection import DatabaseConnection

logger = logging.getLogger(__name__)

T = TypeVar('T')


def require_connection(f: Callable) -> Callable:
    """Decorator to ensure database connection before method execution."""
    @wraps(f)
    def wrapper(self, *args, **kwargs):
        self.db.ensure_connected()
        return f(self, *args, **kwargs)
    return wrapper


class BaseRepository(Generic[T]):
    """
    Base repository providing common database operations.
    
    All specific repositories (Drug, Disease, etc.) inherit from this.
    """
    
    def __init__(self, db: DatabaseConnection):
        """
        Initialize repository with database connection.
        
        Args:
            db: DatabaseConnection instance (shared across repositories)
        """
        self.db = db
    
    @contextmanager
    def _cursor(self, dict_cursor: bool = True):
        """
        Context manager for database cursor.
        
        Ensures connection and handles cursor lifecycle.
        
        Args:
            dict_cursor: If True, returns RealDictCursor for dict-like access
            
        Yields:
            Database cursor
        """
        self.db.ensure_connected()
        cursor_factory = RealDictCursor if dict_cursor else None
        cursor = self.db.connection.cursor(cursor_factory=cursor_factory)
        try:
            yield cursor
        finally:
            cursor.close()
    
    @require_connection
    def _execute(
        self, 
        query: str, 
        params: tuple = None,
        fetch: str = "all"
    ) -> Any:
        """
        Execute query and return results.
        
        Args:
            query: SQL query string
            params: Query parameters
            fetch: "all", "one", "none", or "rowcount"
            
        Returns:
            Query results based on fetch type
        """
        with self._cursor() as cur:
            cur.execute(query, params)
            
            if fetch == "all":
                return cur.fetchall()
            elif fetch == "one":
                return cur.fetchone()
            elif fetch == "rowcount":
                return cur.rowcount
            else:
                return None
    
    @require_connection
    def _execute_returning(
        self,
        query: str,
        params: tuple = None
    ) -> Optional[Dict]:
        """
        Execute query with RETURNING clause.
        
        Args:
            query: SQL query with RETURNING clause
            params: Query parameters
            
        Returns:
            Returned row as dict
        """
        with self._cursor() as cur:
            cur.execute(query, params)
            result = cur.fetchone()
            self.db.commit()
            return dict(result) if result else None
    
    def _dict_to_dataclass(self, row: Dict, dataclass_type: type) -> T:
        """
        Convert database row dict to dataclass.
        
        Args:
            row: Database row as dict
            dataclass_type: Target dataclass type
            
        Returns:
            Dataclass instance
        """
        if row is None:
            return None
        # Filter dict to only include fields that exist in dataclass
        valid_fields = {f.name for f in dataclass_type.__dataclass_fields__.values()}
        filtered = {k: v for k, v in row.items() if k in valid_fields}
        return dataclass_type(**filtered)
    
    def _rows_to_list(self, rows: List[Dict], dataclass_type: type) -> List[T]:
        """
        Convert list of database rows to list of dataclasses.
        
        Args:
            rows: List of database rows
            dataclass_type: Target dataclass type
            
        Returns:
            List of dataclass instances
        """
        return [self._dict_to_dataclass(row, dataclass_type) for row in rows]
    
    def commit(self):
        """Commit current transaction."""
        self.db.commit()
    
    def rollback(self):
        """Rollback current transaction."""
        self.db.rollback()

