"""
Disease Repository

CRUD operations for the diseases table.
"""

import logging
from typing import Optional, List

from psycopg2.extras import Json

from src.drug_database.repositories.base import BaseRepository, require_connection
from src.drug_database.models import Disease
from src.drug_database.queries import DiseaseQueries

logger = logging.getLogger(__name__)


class DiseaseRepository(BaseRepository[Disease]):
    """
    Repository for disease CRUD operations.
    
    Handles all direct database operations for the diseases table.
    """
    
    @require_connection
    def find_by_id(self, disease_id: int) -> Optional[Disease]:
        """
        Find disease by ID.
        
        Args:
            disease_id: Disease ID
            
        Returns:
            Disease instance or None
        """
        row = self._execute(DiseaseQueries.GET_BY_ID, (disease_id,), fetch="one")
        return self._dict_to_dataclass(row, Disease) if row else None
    
    @require_connection
    def find_by_name(self, disease_name: str) -> Optional[Disease]:
        """
        Find disease by standardized name.
        
        Args:
            disease_name: Standardized disease name
            
        Returns:
            Disease instance or None
        """
        row = self._execute(DiseaseQueries.GET_BY_NAME, (disease_name,), fetch="one")
        return self._dict_to_dataclass(row, Disease) if row else None
    
    @require_connection
    def find_by_alias(self, alias: str) -> Optional[Disease]:
        """
        Find disease by alias (alternative name).
        
        Args:
            alias: Disease alias to search
            
        Returns:
            Disease instance or None
        """
        # Search in JSONB array
        row = self._execute(
            DiseaseQueries.GET_BY_ALIAS,
            (Json([alias]),),
            fetch="one"
        )
        return self._dict_to_dataclass(row, Disease) if row else None
    
    @require_connection
    def find_by_name_or_alias(self, name: str) -> Optional[Disease]:
        """
        Find disease by either standardized name or alias.
        
        Args:
            name: Name or alias to search
            
        Returns:
            Disease instance or None
        """
        # Try exact name match first
        disease = self.find_by_name(name)
        if disease:
            return disease
        
        # Try alias match
        return self.find_by_alias(name)
    
    @require_connection
    def create(
        self,
        disease_name: str,
        aliases: List[str] = None,
        icd10_codes: List[str] = None,
        therapeutic_area: str = None
    ) -> int:
        """
        Create a new disease.
        
        Args:
            disease_name: Standardized disease name
            aliases: Alternative names
            icd10_codes: ICD-10 codes
            therapeutic_area: Therapeutic area
            
        Returns:
            New disease_id
        """
        params = (
            disease_name,
            Json(aliases or []),
            Json(icd10_codes or []),
            therapeutic_area,
        )
        
        result = self._execute_returning(DiseaseQueries.INSERT, params)
        disease_id = result["disease_id"]
        
        logger.info(f"Created disease: {disease_name} (ID: {disease_id})")
        return disease_id
    
    @require_connection
    def get_or_create(
        self,
        disease_name: str,
        aliases: List[str] = None,
        icd10_codes: List[str] = None,
        therapeutic_area: str = None
    ) -> int:
        """
        Get existing disease or create new one.
        
        Args:
            disease_name: Standardized disease name
            aliases: Alternative names (used only on create)
            icd10_codes: ICD-10 codes (used only on create)
            therapeutic_area: Therapeutic area (used only on create)
            
        Returns:
            disease_id (existing or newly created)
        """
        existing = self.find_by_name(disease_name)
        if existing:
            logger.debug(f"Disease '{disease_name}' already exists (ID: {existing.disease_id})")
            return existing.disease_id
        
        return self.create(disease_name, aliases, icd10_codes, therapeutic_area)

