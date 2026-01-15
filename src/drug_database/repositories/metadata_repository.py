"""
Metadata Repository

CRUD operations for the drug_metadata table.
"""

import logging
from typing import Optional

from src.drug_database.repositories.base import BaseRepository, require_connection
from src.drug_database.models import DrugMetadata
from src.drug_database.queries import MetadataQueries

logger = logging.getLogger(__name__)


class MetadataRepository(BaseRepository[DrugMetadata]):
    """
    Repository for drug metadata CRUD operations.
    
    Handles regulatory designations, safety info, etc.
    """
    
    @require_connection
    def find_by_drug(self, drug_id: int) -> Optional[DrugMetadata]:
        """
        Get metadata for a drug.
        
        Args:
            drug_id: Drug ID
            
        Returns:
            DrugMetadata instance or None
        """
        row = self._execute(MetadataQueries.GET_BY_DRUG, (drug_id,), fetch="one")
        return self._dict_to_dataclass(row, DrugMetadata) if row else None
    
    @require_connection
    def upsert(
        self,
        drug_id: int,
        orphan_designation: bool = False,
        breakthrough_therapy: bool = False,
        fast_track: bool = False,
        has_black_box_warning: bool = False,
        safety_notes: str = None,
    ) -> bool:
        """
        Create or update drug metadata.
        
        Args:
            drug_id: Drug ID
            orphan_designation: Has orphan designation
            breakthrough_therapy: Has breakthrough therapy
            fast_track: Has fast track
            has_black_box_warning: Has black box warning
            safety_notes: Safety notes
            
        Returns:
            True if successful
        """
        params = (
            drug_id,
            orphan_designation,
            breakthrough_therapy,
            fast_track,
            has_black_box_warning,
            safety_notes,
        )
        
        self._execute(MetadataQueries.UPSERT, params, fetch="none")
        self.commit()
        
        logger.info(f"Upserted metadata for drug {drug_id}")
        return True
    
    @require_connection
    def delete_by_drug(self, drug_id: int) -> int:
        """
        Delete metadata for a drug.
        
        Args:
            drug_id: Drug ID
            
        Returns:
            Number of deleted rows
        """
        rowcount = self._execute(
            "DELETE FROM drug_metadata WHERE drug_id = %s",
            (drug_id,),
            fetch="rowcount"
        )
        self.commit()
        logger.info(f"Deleted metadata for drug {drug_id}")
        return rowcount

