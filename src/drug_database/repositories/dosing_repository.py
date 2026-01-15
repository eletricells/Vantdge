"""
Dosing Repository

CRUD operations for the drug_dosing_regimens table.
"""

import logging
from typing import Optional, List

from src.drug_database.repositories.base import BaseRepository, require_connection
from src.drug_database.models import DosingRegimen, DosingCreateData
from src.drug_database.queries import DosingQueries
from src.utils.drug_standardization import (
    standardize_frequency,
    standardize_route,
    standardize_dose_unit,
)

logger = logging.getLogger(__name__)


class DosingRepository(BaseRepository[DosingRegimen]):
    """
    Repository for dosing regimen CRUD operations.
    
    Handles all direct database operations for drug dosing regimens.
    """
    
    @require_connection
    def find_by_drug(
        self, 
        drug_id: int, 
        indication_id: int = None
    ) -> List[DosingRegimen]:
        """
        Get dosing regimens for a drug.
        
        Args:
            drug_id: Drug ID
            indication_id: Optional filter by indication
            
        Returns:
            List of DosingRegimen instances
        """
        if indication_id:
            rows = self._execute(
                DosingQueries.GET_BY_DRUG_AND_INDICATION,
                (drug_id, indication_id),
                fetch="all"
            )
        else:
            rows = self._execute(
                DosingQueries.GET_BY_DRUG,
                (drug_id,),
                fetch="all"
            )
        
        return self._rows_to_list(rows, DosingRegimen)
    
    @require_connection
    def create(
        self,
        drug_id: int,
        indication_id: int = None,
        regimen_phase: str = "single",
        dose_amount: float = None,
        dose_unit: str = None,
        frequency_raw: str = None,
        route_raw: str = None,
        duration_weeks: int = None,
        weight_based: bool = False,
        sequence_order: int = 1,
        dosing_notes: str = None,
        data_source: str = "Manual",
    ) -> int:
        """
        Create a new dosing regimen.
        
        Automatically standardizes frequency, route, and dose unit.
        
        Args:
            drug_id: Drug ID
            indication_id: Indication ID (optional)
            regimen_phase: Phase (loading, maintenance, single, induction)
            dose_amount: Dose amount
            dose_unit: Dose unit (will be standardized)
            frequency_raw: Raw frequency text (will be standardized)
            route_raw: Raw route text (will be standardized)
            duration_weeks: Duration in weeks
            weight_based: Is dose weight-based
            sequence_order: Order in sequence
            dosing_notes: Additional notes
            data_source: Data source
            
        Returns:
            dosing_id
        """
        # Standardize fields
        frequency_std = None
        if frequency_raw:
            freq_result = standardize_frequency(frequency_raw)
            frequency_std = freq_result[0] if freq_result else None
        
        route_std = None
        if route_raw:
            route_result = standardize_route(route_raw)
            route_std = route_result[0] if route_result else None
        
        dose_unit_std = standardize_dose_unit(dose_unit) if dose_unit else None
        
        params = (
            drug_id,
            indication_id,
            regimen_phase,
            dose_amount,
            dose_unit_std,
            frequency_std,
            frequency_raw,
            route_std,
            route_raw,
            duration_weeks,
            weight_based,
            sequence_order,
            dosing_notes,
            data_source,
        )
        
        result = self._execute_returning(DosingQueries.INSERT, params)
        dosing_id = result["dosing_id"]
        
        logger.info(f"Added dosing regimen for drug {drug_id}")
        return dosing_id
    
    @require_connection
    def create_from_dict(self, drug_id: int, data: DosingCreateData) -> int:
        """
        Create dosing regimen from dictionary data.
        
        Args:
            drug_id: Drug ID
            data: Dosing data dictionary
            
        Returns:
            dosing_id
        """
        return self.create(
            drug_id=drug_id,
            indication_id=data.get("indication_id"),
            regimen_phase=data.get("regimen_phase", "single"),
            dose_amount=data.get("dose_amount"),
            dose_unit=data.get("dose_unit"),
            frequency_raw=data.get("frequency_raw"),
            route_raw=data.get("route_raw"),
            duration_weeks=data.get("duration_weeks"),
            weight_based=data.get("weight_based", False),
            sequence_order=data.get("sequence_order", 1),
            dosing_notes=data.get("dosing_notes"),
            data_source=data.get("data_source", "Manual"),
        )
    
    @require_connection
    def delete_by_drug(self, drug_id: int) -> int:
        """
        Delete all dosing regimens for a drug.
        
        Args:
            drug_id: Drug ID
            
        Returns:
            Number of deleted rows
        """
        rowcount = self._execute(
            "DELETE FROM drug_dosing_regimens WHERE drug_id = %s",
            (drug_id,),
            fetch="rowcount"
        )
        self.commit()
        logger.info(f"Deleted {rowcount} dosing regimens for drug {drug_id}")
        return rowcount

