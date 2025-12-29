"""
Database module for drug extraction system.

Provides connection management and CRUD operations with versioning.
"""

from src.drug_extraction_system.database.connection import DatabaseConnection
from src.drug_extraction_system.database.operations import DrugDatabaseOperations

__all__ = [
    "DatabaseConnection",
    "DrugDatabaseOperations",
]

