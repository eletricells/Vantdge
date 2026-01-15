"""
Drug database repositories.

Each repository handles CRUD operations for a specific domain entity.
"""

from src.drug_database.repositories.base import BaseRepository, require_connection
from src.drug_database.repositories.drug_repository import DrugRepository
from src.drug_database.repositories.disease_repository import DiseaseRepository
from src.drug_database.repositories.indication_repository import IndicationRepository
from src.drug_database.repositories.dosing_repository import DosingRepository
from src.drug_database.repositories.metadata_repository import MetadataRepository

__all__ = [
    "BaseRepository",
    "require_connection",
    "DrugRepository",
    "DiseaseRepository",
    "IndicationRepository",
    "DosingRepository",
    "MetadataRepository",
]

