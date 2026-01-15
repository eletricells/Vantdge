"""
Drug Database Package

Provides a clean, well-organized API for drug database operations.

This package replaces the monolithic DrugDatabase class with a layered architecture:
- Models: Type-safe dataclasses for all entities
- Repositories: CRUD operations for individual tables
- Services: Business logic and cross-table orchestration
- Queries: Centralized SQL queries

Usage:
    from src.drug_extraction_system.database import DatabaseConnection
    from src.drug_database import DrugService
    
    with DatabaseConnection() as db:
        service = DrugService(db)
        
        # Get drug overview
        overview = service.get_drug_overview(drug_id=1)
        
        # Search drugs
        drugs = service.search_drugs("humira")
        
        # Add drug with indications
        drug_id = service.add_drug_with_indications(
            drug_data={"generic_name": "upadacitinib", "brand_name": "Rinvoq"},
            indications=[{"disease_name": "Rheumatoid Arthritis"}]
        )

For backwards compatibility, you can also import individual components:
    from src.drug_database.repositories import DrugRepository, DiseaseRepository
    from src.drug_database.models import Drug, Indication, DosingRegimen
"""

# Re-export DatabaseConnection for convenience
from src.drug_extraction_system.database.connection import DatabaseConnection

# Models
from src.drug_database.models import (
    Drug,
    Disease,
    Indication,
    DosingRegimen,
    DrugMetadata,
    DrugOverview,
)

# Repositories
from src.drug_database.repositories import (
    BaseRepository,
    DrugRepository,
    DiseaseRepository,
    IndicationRepository,
    DosingRepository,
    MetadataRepository,
)

# Services
from src.drug_database.services import DrugService

# Queries
from src.drug_database.queries import (
    DrugQueries,
    DiseaseQueries,
    IndicationQueries,
    DosingQueries,
    MetadataQueries,
)


__all__ = [
    # Connection
    "DatabaseConnection",
    # Models
    "Drug",
    "Disease",
    "Indication",
    "DosingRegimen",
    "DrugMetadata",
    "DrugOverview",
    # Repositories
    "BaseRepository",
    "DrugRepository",
    "DiseaseRepository",
    "IndicationRepository",
    "DosingRepository",
    "MetadataRepository",
    # Services
    "DrugService",
    # Queries
    "DrugQueries",
    "DiseaseQueries",
    "IndicationQueries",
    "DosingQueries",
    "MetadataQueries",
]

