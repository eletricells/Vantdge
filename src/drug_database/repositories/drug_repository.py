"""
Drug Repository

CRUD operations for the drugs table.
"""

import logging
from typing import Optional, List, Dict, Any

from src.drug_database.repositories.base import BaseRepository, require_connection
from src.drug_database.models import Drug, DrugCreateData, DrugUpdateData
from src.drug_database.queries import DrugQueries
from src.utils.drug_standardization import standardize_drug_type

logger = logging.getLogger(__name__)


class DrugRepository(BaseRepository[Drug]):
    """
    Repository for drug CRUD operations.
    
    Handles all direct database operations for the drugs table.
    """
    
    @require_connection
    def find_by_id(self, drug_id: int) -> Optional[Drug]:
        """
        Find drug by ID.
        
        Args:
            drug_id: Drug ID
            
        Returns:
            Drug instance or None
        """
        row = self._execute(DrugQueries.GET_BY_ID, (drug_id,), fetch="one")
        return self._dict_to_dataclass(row, Drug) if row else None
    
    @require_connection
    def find_by_key(self, drug_key: str) -> Optional[Drug]:
        """
        Find drug by drug_key.
        
        Args:
            drug_key: Drug key (e.g., "DRG-UPADACITINIB-7A2F")
            
        Returns:
            Drug instance or None
        """
        row = self._execute(DrugQueries.GET_BY_KEY, (drug_key,), fetch="one")
        return self._dict_to_dataclass(row, Drug) if row else None
    
    @require_connection
    def find_by_brand_name(
        self, 
        brand_name: str, 
        manufacturer: Optional[str] = None
    ) -> Optional[Drug]:
        """
        Find drug by brand name (optionally with manufacturer).
        
        Args:
            brand_name: Brand name
            manufacturer: Optional manufacturer filter
            
        Returns:
            Drug instance or None
        """
        if manufacturer:
            row = self._execute(
                DrugQueries.GET_BY_BRAND_AND_MANUFACTURER,
                (brand_name, manufacturer),
                fetch="one"
            )
        else:
            row = self._execute(DrugQueries.GET_BY_BRAND_NAME, (brand_name,), fetch="one")
        return self._dict_to_dataclass(row, Drug) if row else None
    
    @require_connection
    def find_by_generic_name(self, generic_name: str) -> Optional[Drug]:
        """
        Find drug by generic name (case-insensitive).
        
        Args:
            generic_name: Generic name to search
            
        Returns:
            Drug instance or None
        """
        row = self._execute(
            DrugQueries.GET_BY_GENERIC_NAME,
            (generic_name,),
            fetch="one"
        )
        return self._dict_to_dataclass(row, Drug) if row else None
    
    @require_connection
    def search(
        self,
        query: str,
        approval_status: Optional[str] = None,
        manufacturer: Optional[str] = None,
        limit: int = 20
    ) -> List[Drug]:
        """
        Search drugs by name (brand or generic).
        
        Args:
            query: Search term
            approval_status: Filter by approval status
            manufacturer: Filter by manufacturer
            limit: Max results
            
        Returns:
            List of matching Drug instances
        """
        filters = []
        params = [f"%{query}%", f"%{query}%"]
        
        if approval_status:
            filters.append("AND approval_status = %s")
            params.append(approval_status)
        
        if manufacturer:
            filters.append("AND manufacturer = %s")
            params.append(manufacturer)
        
        params.append(limit)
        
        sql = DrugQueries.SEARCH.format(filters=" ".join(filters))
        rows = self._execute(sql, tuple(params), fetch="all")
        
        return self._rows_to_list(rows, Drug)
    
    @require_connection
    def create(self, data: DrugCreateData) -> int:
        """
        Create a new drug.
        
        Args:
            data: Drug data dictionary
            
        Returns:
            New drug_id
        """
        # Standardize drug type if provided
        drug_type = data.get("drug_type")
        if drug_type:
            drug_type = standardize_drug_type(drug_type) or drug_type
        
        params = (
            data.get("brand_name"),
            data.get("generic_name"),
            data.get("manufacturer"),
            drug_type,
            data.get("mechanism_of_action"),
            data.get("approval_status", "investigational"),
            data.get("highest_phase"),
            data.get("dailymed_setid"),
            data.get("first_approval_date"),
            data.get("is_combination", False),
            data.get("combination_components"),
            data.get("drug_key"),
            data.get("target"),
            data.get("moa_category"),
            data.get("development_code"),
        )
        
        result = self._execute_returning(DrugQueries.INSERT, params)
        drug_id = result["drug_id"]

        logger.info(f"Created drug: {data.get('brand_name') or data.get('generic_name')} (ID: {drug_id})")
        return drug_id

    @require_connection
    def update(self, drug_id: int, data: DrugUpdateData) -> bool:
        """
        Update an existing drug.

        Args:
            drug_id: Drug ID to update
            data: Fields to update

        Returns:
            True if updated successfully
        """
        # Standardize drug type if provided
        drug_type = data.get("drug_type")
        if drug_type:
            drug_type = standardize_drug_type(drug_type) or drug_type
            data["drug_type"] = drug_type

        params = (
            data.get("brand_name"),
            data.get("generic_name"),
            data.get("manufacturer"),
            data.get("drug_type"),
            data.get("mechanism_of_action"),
            data.get("approval_status"),
            data.get("highest_phase"),
            data.get("dailymed_setid"),
            data.get("first_approval_date"),
            drug_id,
        )

        rowcount = self._execute(DrugQueries.UPDATE, params, fetch="rowcount")
        self.commit()

        if rowcount > 0:
            logger.info(f"Updated drug ID: {drug_id}")
            return True
        return False

    @require_connection
    def delete_related_data(self, drug_id: int, tables: List[str] = None) -> None:
        """
        Delete related data for a drug (for overwrite operations).

        Args:
            drug_id: Drug ID
            tables: List of tables to clear (default: metadata, dosing, indications, formulations)
        """
        if tables is None:
            tables = [
                "drug_metadata",
                "drug_dosing_regimens",
                "drug_indications",
                "drug_formulations",
            ]

        for table in tables:
            sql = DrugQueries.DELETE_RELATED.format(table=table)
            self._execute(sql, (drug_id,), fetch="none")

        self.commit()
        logger.info(f"Deleted related data for drug ID: {drug_id}")

    @require_connection
    def exists(self, brand_name: str = None, generic_name: str = None) -> Optional[int]:
        """
        Check if drug exists and return ID.

        Args:
            brand_name: Brand name to check
            generic_name: Generic name to check

        Returns:
            drug_id if exists, None otherwise
        """
        if brand_name:
            drug = self.find_by_brand_name(brand_name)
            if drug:
                return drug.drug_id

        if generic_name:
            drug = self.find_by_generic_name(generic_name)
            if drug:
                return drug.drug_id

        return None

