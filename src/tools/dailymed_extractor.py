"""
DailyMed Data Extraction Pipeline

Extracts structured drug information from DailyMed and populates the drug database.
"""
import logging
import re
from typing import Dict, List, Optional, Tuple
import xml.etree.ElementTree as ET

from src.tools.dailymed import DailyMedAPI
from src.tools.drug_database import DrugDatabase
from src.utils.drug_standardization import (
    standardize_frequency,
    standardize_route,
    standardize_drug_type
)

logger = logging.getLogger(__name__)


class DailyMedExtractor:
    """
    Extracts structured drug data from DailyMed and populates drug database.

    Pipeline:
    1. Search DailyMed for drug
    2. Get drug label XML
    3. Parse label into structured data
    4. Populate drug database
    """

    def __init__(self, drug_database: DrugDatabase):
        """
        Initialize DailyMed extractor.

        Args:
            drug_database: DrugDatabase instance
        """
        self.dailymed = DailyMedAPI()
        self.drug_db = drug_database

    def extract_and_store_drug(
        self,
        drug_name: str,
        save_to_database: bool = True
    ) -> Optional[Dict]:
        """
        Extract drug information from DailyMed and optionally save to database.

        Args:
            drug_name: Drug name (brand or generic)
            save_to_database: If True, save to database

        Returns:
            Extracted drug data dictionary or None if not found
        """
        logger.info(f"Extracting DailyMed data for: {drug_name}")

        # Step 1: Get drug info from DailyMed
        drug_info = self.dailymed.get_drug_info(drug_name)

        if not drug_info:
            logger.warning(f"No DailyMed data found for {drug_name}")
            return None

        # Step 2: Parse into structured format
        structured_data = self._structure_drug_data(drug_info)

        # Step 3: Save to database
        if save_to_database:
            try:
                drug_id = self._save_to_database(structured_data)
                structured_data["drug_id"] = drug_id
                logger.info(f"Saved {drug_name} to database (ID: {drug_id})")
            except Exception as e:
                logger.error(f"Failed to save {drug_name} to database: {e}")
                return None

        return structured_data

    def _structure_drug_data(self, dailymed_data: Dict) -> Dict:
        """
        Convert DailyMed raw data into structured format for database.

        Args:
            dailymed_data: Raw data from DailyMedAPI.get_drug_info()

        Returns:
            Structured data dictionary
        """
        drug_name = dailymed_data.get("drug_name", "")

        # Determine brand vs generic name
        # DailyMed usually returns brand name
        brand_name = drug_name
        generic_name = None

        # Check if active ingredients contain generic name
        active_ingredients = dailymed_data.get("active_ingredients", [])
        if active_ingredients:
            # Use first active ingredient as generic name
            generic_name = active_ingredients[0].lower()

        # Parse manufacturer
        manufacturer = dailymed_data.get("manufacturer")

        # Standardize routes
        routes_raw = dailymed_data.get("route_of_administration", [])
        routes_standard = []
        for route_raw in routes_raw:
            route_std, _ = standardize_route(route_raw)
            if route_std:
                routes_standard.append(route_std)

        # Parse indications
        indications_raw = dailymed_data.get("indications", [])
        indications = []

        for ind_text in indications_raw:
            # Try to extract disease names from indication text
            # This is simplistic - ideally would use NER or parsing
            # For now, just store raw text
            indications.append({
                "indication_raw": ind_text,
                "disease_name": self._extract_disease_from_indication(ind_text)
            })

        structured = {
            "brand_name": brand_name,
            "generic_name": generic_name or brand_name.lower(),
            "manufacturer": manufacturer,
            "drug_type": None,  # Would need to infer from active ingredients or other sources
            "mechanism_of_action": None,  # Not in DailyMed structured data
            "approval_status": "approved",  # All DailyMed drugs are approved
            "highest_phase": "Approved",
            "routes": routes_standard,
            "routes_raw": routes_raw,
            "indications": indications,
            "active_ingredients": active_ingredients,
            "dosing_frequency": dailymed_data.get("dosing_frequency", []),
            "dailymed_setid": None,  # Would need to extract from label
        }

        return structured

    def _extract_disease_from_indication(self, indication_text: str) -> Optional[str]:
        """
        Extract disease name from indication text.

        This is a simple pattern-based extraction.
        Better approach: Use NER or disease ontology matching.

        Args:
            indication_text: Raw indication text

        Returns:
            Disease name or None
        """
        # Common patterns:
        # "treatment of X"
        # "for the treatment of X"
        # "indicated for X"

        patterns = [
            r"treatment of ([^,\.]+)",
            r"indicated for ([^,\.]+)",
            r"management of ([^,\.]+)",
            r"therapy for ([^,\.]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, indication_text, re.IGNORECASE)
            if match:
                disease = match.group(1).strip()
                # Clean up common qualifiers
                disease = re.sub(r"\s+in\s+(adult|pediatric|patients).*", "", disease, flags=re.IGNORECASE)
                return disease

        return None

    def _save_to_database(self, structured_data: Dict) -> int:
        """
        Save structured drug data to database.

        Args:
            structured_data: Structured drug data

        Returns:
            drug_id
        """
        # Step 1: Add drug
        drug_id = self.drug_db.add_drug(
            generic_name=structured_data["generic_name"],
            brand_name=structured_data["brand_name"],
            manufacturer=structured_data["manufacturer"],
            drug_type=structured_data.get("drug_type"),
            mechanism=structured_data.get("mechanism_of_action"),
            approval_status=structured_data["approval_status"],
            highest_phase=structured_data["highest_phase"],
            dailymed_setid=structured_data.get("dailymed_setid")
        )

        # Step 2: Add indications
        for indication_data in structured_data.get("indications", []):
            disease_name = indication_data.get("disease_name")

            if disease_name:
                # Add disease (or get existing)
                disease_id = self.drug_db.add_disease(disease_name=disease_name)

                # Add drug-disease indication
                self.drug_db.add_indication(
                    drug_id=drug_id,
                    disease_id=disease_id,
                    indication_raw=indication_data.get("indication_raw"),
                    approval_status="approved",
                    data_source="DailyMed"
                )

        # Step 3: Add formulations
        routes_raw = structured_data.get("routes_raw", [])
        routes_std = structured_data.get("routes", [])

        for route_raw, route_std in zip(routes_raw, routes_std):
            # Add formulation (simplified - would need more data for strengths)
            # For now, just create basic formulation record
            pass  # TODO: Implement formulation extraction from label

        # Step 4: Add dosing regimens
        # DailyMed dosing is complex and varies by indication
        # For initial implementation, skip detailed dosing extraction
        # This would require parsing complex label sections

        # Step 5: Add metadata
        self.drug_db.add_drug_metadata(
            drug_id=drug_id,
            orphan_designation=False,  # Would need to check FDA databases
            breakthrough_therapy=False,
            fast_track=False,
            has_black_box_warning=False  # Would need to parse label warnings section
        )

        return drug_id

    def extract_dosing_from_label(
        self,
        label_xml: str,
        drug_id: int
    ) -> List[Dict]:
        """
        Extract dosing regimens from DailyMed label XML.

        This is complex and drug-specific. Initial implementation
        extracts basic patterns.

        Args:
            label_xml: DailyMed label XML
            drug_id: Drug ID in database

        Returns:
            List of extracted dosing regimens
        """
        try:
            root = ET.fromstring(label_xml)

            dosing_regimens = []

            # Find dosage and administration section
            # Section code: "34068-7"
            for section in root.findall('.//{urn:hl7-org:v3}section'):
                code = section.find('.//{urn:hl7-org:v3}code')

                if code is not None and code.get('code') == '34068-7':
                    # This is dosage section
                    text_elem = section.find('.//{urn:hl7-org:v3}text')

                    if text_elem is not None:
                        dosing_text = ''.join(text_elem.itertext())

                        # Extract dosing patterns
                        # This is highly simplified - real implementation would need
                        # drug-specific parsers or AI-based extraction

                        # Pattern: "X mg [frequency]"
                        pattern = r'(\d+)\s*mg\s+([a-z\s]+)'
                        matches = re.findall(pattern, dosing_text, re.IGNORECASE)

                        for dose_amount, frequency_raw in matches:
                            freq_std, _ = standardize_frequency(frequency_raw.strip())

                            dosing_regimens.append({
                                "drug_id": drug_id,
                                "dose_amount": float(dose_amount),
                                "dose_unit": "mg",
                                "frequency_raw": frequency_raw.strip(),
                                "frequency_standard": freq_std,
                                "data_source": "DailyMed"
                            })

            return dosing_regimens

        except Exception as e:
            logger.error(f"Failed to extract dosing from label: {e}")
            return []

    def batch_extract_drugs(self, drug_list: List[str]) -> Dict:
        """
        Extract multiple drugs in batch.

        Args:
            drug_list: List of drug names

        Returns:
            Summary dictionary with results
        """
        results = {
            "successful": [],
            "failed": [],
            "total": len(drug_list)
        }

        for drug_name in drug_list:
            try:
                data = self.extract_and_store_drug(drug_name, save_to_database=True)

                if data:
                    results["successful"].append(drug_name)
                else:
                    results["failed"].append(drug_name)

            except Exception as e:
                logger.error(f"Error extracting {drug_name}: {e}")
                results["failed"].append(drug_name)

        logger.info(
            f"Batch extraction complete: "
            f"{len(results['successful'])}/{results['total']} successful"
        )

        return results

    def close(self):
        """Clean up resources."""
        self.dailymed.close()


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def extract_drug_from_dailymed(
    drug_name: str,
    database_url: str
) -> Optional[int]:
    """
    Convenience function to extract a drug from DailyMed and save to database.

    Args:
        drug_name: Drug name to extract
        database_url: Drug database URL

    Returns:
        drug_id or None if failed

    Example:
        >>> drug_id = extract_drug_from_dailymed("Cosentyx", "postgresql://...")
        >>> print(f"Saved Cosentyx with ID: {drug_id}")
    """
    with DrugDatabase(database_url) as db:
        extractor = DailyMedExtractor(db)
        data = extractor.extract_and_store_drug(drug_name, save_to_database=True)
        extractor.close()

        return data.get("drug_id") if data else None


def batch_extract_from_list(
    drug_list: List[str],
    database_url: str
) -> Dict:
    """
    Batch extract drugs from DailyMed.

    Args:
        drug_list: List of drug names
        database_url: Drug database URL

    Returns:
        Summary dictionary

    Example:
        >>> drugs = ["Cosentyx", "Humira", "Enbrel"]
        >>> results = batch_extract_from_list(drugs, "postgresql://...")
        >>> print(f"Extracted {len(results['successful'])} drugs")
    """
    with DrugDatabase(database_url) as db:
        extractor = DailyMedExtractor(db)
        results = extractor.batch_extract_drugs(drug_list)
        extractor.close()

        return results
