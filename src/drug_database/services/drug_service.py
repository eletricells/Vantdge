"""
Drug Service

High-level service layer that orchestrates repositories and handles business logic.
Provides a clean API for drug database operations.
"""

import logging
from typing import Optional, List, Dict, Any
from dataclasses import asdict

from src.drug_extraction_system.database.connection import DatabaseConnection
from src.drug_database.repositories import (
    DrugRepository,
    DiseaseRepository,
    IndicationRepository,
    DosingRepository,
    MetadataRepository,
)
from src.drug_database.models import (
    Drug,
    Disease,
    Indication,
    DosingRegimen,
    DrugMetadata,
    DrugOverview,
    DrugCreateData,
)

logger = logging.getLogger(__name__)


class DrugService:
    """
    High-level service for drug database operations.
    
    Orchestrates multiple repositories and handles complex business logic
    that spans multiple tables.
    
    Usage:
        with DatabaseConnection() as db:
            service = DrugService(db)
            
            # Get complete drug overview
            overview = service.get_drug_overview(drug_id=1)
            
            # Add drug with indications
            drug_id = service.add_drug_with_indications(data)
            
            # Search drugs
            results = service.search_drugs("humira")
    """
    
    def __init__(self, db: DatabaseConnection):
        """
        Initialize service with database connection.
        
        Args:
            db: DatabaseConnection instance
        """
        self.db = db
        self.drugs = DrugRepository(db)
        self.diseases = DiseaseRepository(db)
        self.indications = IndicationRepository(db)
        self.dosing = DosingRepository(db)
        self.metadata = MetadataRepository(db)
    
    # =========================================================================
    # DRUG OPERATIONS
    # =========================================================================
    
    def get_drug(self, drug_id: int) -> Optional[Drug]:
        """Get drug by ID."""
        return self.drugs.find_by_id(drug_id)
    
    def get_drug_by_name(self, name: str) -> Optional[Drug]:
        """Get drug by brand or generic name."""
        # Try brand name first
        drug = self.drugs.find_by_brand_name(name)
        if drug:
            return drug
        # Try generic name
        return self.drugs.find_by_generic_name(name)
    
    def search_drugs(
        self,
        query: str,
        approval_status: str = None,
        manufacturer: str = None,
        limit: int = 20
    ) -> List[Drug]:
        """Search drugs by name."""
        return self.drugs.search(query, approval_status, manufacturer, limit)
    
    def get_drug_overview(self, drug_id: int) -> Optional[DrugOverview]:
        """
        Get complete drug overview with all related data.
        
        Args:
            drug_id: Drug ID
            
        Returns:
            DrugOverview with drug, indications, dosing, and metadata
        """
        drug = self.drugs.find_by_id(drug_id)
        if not drug:
            return None
        
        indications = self.indications.find_by_drug(drug_id)
        dosing_regimens = self.dosing.find_by_drug(drug_id)
        metadata = self.metadata.find_by_drug(drug_id)
        
        return DrugOverview(
            drug=drug,
            indications=indications,
            dosing_regimens=dosing_regimens,
            metadata=metadata,
        )
    
    def get_drug_overview_dict(self, drug_id: int) -> Optional[Dict[str, Any]]:
        """
        Get drug overview as dictionary (for JSON serialization).
        
        Args:
            drug_id: Drug ID
            
        Returns:
            Dictionary with all drug data
        """
        overview = self.get_drug_overview(drug_id)
        if not overview:
            return None
        
        result = asdict(overview.drug)
        result["indications"] = [asdict(i) for i in overview.indications]
        result["dosing_regimens"] = [asdict(d) for d in overview.dosing_regimens]
        result["metadata"] = asdict(overview.metadata) if overview.metadata else None
        
        return result
    
    # =========================================================================
    # DISEASE OPERATIONS  
    # =========================================================================
    
    def get_disease(self, disease_id: int) -> Optional[Disease]:
        """Get disease by ID."""
        return self.diseases.find_by_id(disease_id)
    
    def get_disease_by_name(self, name: str) -> Optional[Disease]:
        """Get disease by name or alias."""
        return self.diseases.find_by_name_or_alias(name)
    
    def add_disease(
        self,
        disease_name: str,
        aliases: List[str] = None,
        icd10_codes: List[str] = None,
        therapeutic_area: str = None
    ) -> int:
        """Add disease (or get existing ID)."""
        return self.diseases.get_or_create(
            disease_name, aliases, icd10_codes, therapeutic_area
        )
    
    def get_drugs_by_disease(self, disease_id: int) -> List[Dict[str, Any]]:
        """Get all drugs for a disease."""
        return self.indications.find_by_disease(disease_id)

    # =========================================================================
    # COMPLEX OPERATIONS (Multi-table)
    # =========================================================================

    def add_drug(self, data: DrugCreateData, overwrite: bool = False) -> int:
        """
        Add a drug to the database.

        Args:
            data: Drug data dictionary
            overwrite: If True, delete existing related data first

        Returns:
            drug_id
        """
        # Check if drug exists
        existing_id = self.drugs.exists(
            brand_name=data.get("brand_name"),
            generic_name=data.get("generic_name")
        )

        if existing_id and not overwrite:
            logger.debug(f"Drug already exists (ID: {existing_id})")
            return existing_id

        if existing_id and overwrite:
            # Delete related data but keep the drug record
            self.drugs.delete_related_data(existing_id)
            # Update the drug
            self.drugs.update(existing_id, data)
            logger.info(f"Overwrote drug ID: {existing_id}")
            return existing_id

        # Create new drug
        return self.drugs.create(data)

    def add_drug_with_indications(
        self,
        drug_data: DrugCreateData,
        indications: List[Dict] = None,
        dosing_regimens: List[Dict] = None,
        metadata: Dict = None,
        overwrite: bool = False
    ) -> int:
        """
        Add drug with all related data in a single transaction.

        Args:
            drug_data: Drug data
            indications: List of indication data dicts
            dosing_regimens: List of dosing data dicts
            metadata: Metadata dict
            overwrite: If True, delete existing data first

        Returns:
            drug_id
        """
        try:
            # Add drug
            drug_id = self.add_drug(drug_data, overwrite=overwrite)

            # Add indications
            # Note: Schema stores disease_name directly, not via disease_id
            if indications:
                for ind_data in indications:
                    self.indications.create_from_dict(drug_id, ind_data)

            # Add dosing regimens
            if dosing_regimens:
                for dosing_data in dosing_regimens:
                    self.dosing.create_from_dict(drug_id, dosing_data)

            # Add metadata
            if metadata:
                self.metadata.upsert(
                    drug_id,
                    orphan_designation=metadata.get("orphan_designation", False),
                    breakthrough_therapy=metadata.get("breakthrough_therapy", False),
                    fast_track=metadata.get("fast_track", False),
                    has_black_box_warning=metadata.get("has_black_box_warning", False),
                    safety_notes=metadata.get("safety_notes"),
                )

            self.db.commit()
            logger.info(f"Added drug with all related data (ID: {drug_id})")
            return drug_id

        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to add drug with indications: {e}")
            raise

    def add_indication(
        self,
        drug_id: int,
        disease_name: str,
        **kwargs
    ) -> int:
        """Add indication for a drug."""
        return self.indications.create(drug_id, disease_name, **kwargs)

    def add_dosing_regimen(self, drug_id: int, **kwargs) -> int:
        """Add dosing regimen for a drug."""
        return self.dosing.create(drug_id, **kwargs)

    def add_drug_metadata(self, drug_id: int, **kwargs) -> bool:
        """Add or update drug metadata."""
        return self.metadata.upsert(drug_id, **kwargs)

    def get_drug_indications(self, drug_id: int) -> List[Indication]:
        """Get all indications for a drug."""
        return self.indications.find_by_drug(drug_id)

    def get_dosing_regimens(
        self,
        drug_id: int,
        indication_id: int = None
    ) -> List[DosingRegimen]:
        """Get dosing regimens for a drug."""
        return self.dosing.find_by_drug(drug_id, indication_id)

