"""
Indication Repository

CRUD operations for the drug_indications table.

Note: The schema stores disease_name directly in drug_indications,
not as a foreign key to diseases table.
"""

import logging
from typing import Optional, List, Dict, Any

from src.drug_database.repositories.base import BaseRepository, require_connection
from src.drug_database.models import Indication, IndicationCreateData
from src.drug_database.queries import IndicationQueries

logger = logging.getLogger(__name__)


class IndicationRepository(BaseRepository[Indication]):
    """
    Repository for drug indication CRUD operations.

    Handles all direct database operations for drug-disease relationships.
    Note: disease_name is stored directly, not linked via disease_id.
    """

    @require_connection
    def find_by_drug(self, drug_id: int) -> List[Indication]:
        """
        Get all indications for a drug.

        Args:
            drug_id: Drug ID

        Returns:
            List of Indication instances
        """
        rows = self._execute(IndicationQueries.GET_BY_DRUG, (drug_id,), fetch="all")
        return self._rows_to_list(rows, Indication)

    @require_connection
    def find_by_disease_name(self, disease_name: str) -> List[Dict[str, Any]]:
        """
        Get all indications for a disease by name (with drug info).

        Args:
            disease_name: Disease name to search

        Returns:
            List of indication dicts with drug info
        """
        rows = self._execute(
            IndicationQueries.GET_BY_DISEASE_NAME,
            (f"%{disease_name}%",),
            fetch="all"
        )
        return [dict(row) for row in rows]

    @require_connection
    def create(
        self,
        drug_id: int,
        disease_name: str,
        mesh_id: str = None,
        population: str = None,
        severity: str = None,
        line_of_therapy: str = None,
        combination_therapy: str = None,
        approval_status: str = "investigational",
        approval_date: str = None,
        special_conditions: str = None,
        raw_source_text: str = None,
        confidence_score: float = None,
        data_source: str = "Manual",
    ) -> int:
        """
        Create a new drug indication.

        Args:
            drug_id: Drug ID
            disease_name: Disease name
            mesh_id: MeSH ID
            population: Population restrictions
            severity: Disease severity
            line_of_therapy: Treatment line
            combination_therapy: Combination therapy info
            approval_status: Approval status
            approval_date: Approval date
            special_conditions: Special conditions
            raw_source_text: Raw source text
            confidence_score: Confidence score
            data_source: Data source

        Returns:
            indication_id
        """
        params = (
            drug_id,
            disease_name,
            mesh_id,
            population,
            severity,
            line_of_therapy,
            combination_therapy,
            approval_status,
            approval_date,
            special_conditions,
            raw_source_text,
            confidence_score,
            data_source,
        )

        result = self._execute_returning(IndicationQueries.INSERT, params)
        indication_id = result["indication_id"]

        logger.info(f"Added indication for drug {drug_id}: {disease_name}")
        return indication_id

    @require_connection
    def create_from_dict(self, drug_id: int, data: IndicationCreateData) -> int:
        """
        Create indication from dictionary data.

        Args:
            drug_id: Drug ID
            data: Indication data dictionary

        Returns:
            indication_id
        """
        disease_name = data.get("disease_name") or data.get("disease_name_standard")

        return self.create(
            drug_id=drug_id,
            disease_name=disease_name,
            mesh_id=data.get("mesh_id"),
            population=data.get("population"),
            severity=data.get("severity"),
            line_of_therapy=data.get("line_of_therapy"),
            combination_therapy=data.get("combination_therapy"),
            approval_status=data.get("approval_status", "investigational"),
            approval_date=data.get("approval_date"),
            special_conditions=data.get("special_conditions"),
            raw_source_text=data.get("raw_source_text") or data.get("indication_raw"),
            confidence_score=data.get("confidence_score"),
            data_source=data.get("data_source", "Manual"),
        )
    
    @require_connection
    def delete_by_drug(self, drug_id: int) -> int:
        """
        Delete all indications for a drug.
        
        Args:
            drug_id: Drug ID
            
        Returns:
            Number of deleted rows
        """
        rowcount = self._execute(
            "DELETE FROM drug_indications WHERE drug_id = %s",
            (drug_id,),
            fetch="rowcount"
        )
        self.commit()
        logger.info(f"Deleted {rowcount} indications for drug {drug_id}")
        return rowcount

