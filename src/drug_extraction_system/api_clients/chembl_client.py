"""
ChEMBL API Client

Client for accessing the ChEMBL database for drug information including:
- ChEMBL IDs
- Mechanism of action
- Drug type (small molecule, biologic, etc.)
- Chemical identifiers (InChI Key, SMILES)
- Development phase
"""

import logging
from typing import Dict, List, Optional
from urllib.parse import quote

from src.drug_extraction_system.api_clients.base_client import BaseAPIClient

logger = logging.getLogger(__name__)


class ChEMBLClient(BaseAPIClient):
    """
    Client for ChEMBL database API.
    
    ChEMBL is a manually curated database of bioactive molecules with drug-like properties.
    Free API with no authentication required.
    Rate limit: 5 requests/second (conservative)
    
    API Documentation: https://chembl.gitbook.io/chembl-interface-documentation/web-services
    """

    BASE_URL = "https://www.ebi.ac.uk/chembl/api/data"

    def __init__(self):
        """Initialize ChEMBL client."""
        super().__init__(
            base_url=self.BASE_URL,
            rate_limit=5,  # Conservative rate limit (5 req/sec = 300 req/min)
            name="ChEMBL"
        )

    def search_by_name(self, drug_name: str) -> Optional[Dict]:
        """
        Search ChEMBL by drug name.
        
        Args:
            drug_name: Drug name to search
        
        Returns:
            Dictionary with ChEMBL data or None if not found:
            {
                "chembl_id": str,
                "pref_name": str,
                "max_phase": int (0-4),
                "molecule_type": str,
                "inchi_key": str,
                "canonical_smiles": str,
                "mechanism_of_action": str (if available)
            }
        """
        try:
            # Search for molecule by name
            endpoint = f"/molecule/search.json"
            params = {"q": drug_name, "limit": 5}
            
            result = self.get(endpoint, params=params)
            
            if not result or "molecules" not in result:
                logger.debug(f"No ChEMBL results for '{drug_name}'")
                return None
            
            molecules = result.get("molecules", [])
            if not molecules:
                return None
            
            # Get the first (best) match
            molecule = molecules[0]
            
            chembl_id = molecule.get("molecule_chembl_id")
            if not chembl_id:
                return None
            
            # Get detailed information including mechanism
            details = self.get_molecule_details(chembl_id)
            
            return details
            
        except Exception as e:
            logger.warning(f"ChEMBL search failed for '{drug_name}': {e}")
            return None

    def get_molecule_details(self, chembl_id: str) -> Optional[Dict]:
        """
        Get detailed information for a ChEMBL molecule.
        
        Args:
            chembl_id: ChEMBL ID (e.g., "CHEMBL1201585")
        
        Returns:
            Dictionary with molecule details or None
        """
        try:
            endpoint = f"/molecule/{chembl_id}.json"
            result = self.get(endpoint)
            
            if not result:
                return None
            
            # Extract relevant fields
            data = {
                "chembl_id": result.get("molecule_chembl_id"),
                "pref_name": result.get("pref_name"),
                "max_phase": result.get("max_phase", 0),
                "molecule_type": result.get("molecule_type"),
                "first_approval": result.get("first_approval"),
            }
            
            # Extract chemical structures
            structures = result.get("molecule_structures", {})
            if structures:
                data["inchi_key"] = structures.get("standard_inchi_key")
                data["canonical_smiles"] = structures.get("canonical_smiles")
            
            # Get mechanism of action
            moa = self.get_mechanism_of_action(chembl_id)
            if moa:
                data["mechanism_of_action"] = moa
            
            return data
            
        except Exception as e:
            logger.warning(f"Failed to get ChEMBL details for '{chembl_id}': {e}")
            return None

    def get_mechanism_of_action(self, chembl_id: str) -> Optional[str]:
        """
        Get mechanism of action for a ChEMBL molecule.
        
        Args:
            chembl_id: ChEMBL ID
        
        Returns:
            Mechanism of action description or None
        """
        try:
            endpoint = f"/mechanism.json"
            params = {"molecule_chembl_id": chembl_id}
            
            result = self.get(endpoint, params=params)
            
            if not result or "mechanisms" not in result:
                return None
            
            mechanisms = result.get("mechanisms", [])
            if not mechanisms:
                return None
            
            # Combine all mechanisms into a single description
            moa_parts = []
            for mech in mechanisms:
                action_type = mech.get("action_type", "")
                target_name = mech.get("target_name", "")
                
                if action_type and target_name:
                    moa_parts.append(f"{action_type} of {target_name}")
                elif target_name:
                    moa_parts.append(f"Acts on {target_name}")
            
            return "; ".join(moa_parts) if moa_parts else None
            
        except Exception as e:
            logger.debug(f"Failed to get MOA for '{chembl_id}': {e}")
            return None

    def health_check(self) -> bool:
        """Check if ChEMBL API is accessible."""
        try:
            result = self.get("/status.json")
            return result is not None
        except Exception:
            return False

