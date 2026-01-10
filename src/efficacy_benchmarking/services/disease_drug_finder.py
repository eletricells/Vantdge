"""
Service to find approved drugs for a given disease.

Enhanced to:
1. Search local database for existing drugs
2. Search OpenFDA for drugs approved for the indication
3. Auto-extract missing drugs using ApprovedDrugExtractor
"""

import logging
import re
from typing import List, Optional, Dict, Any, Callable, Set

from src.drug_extraction_system.database.connection import DatabaseConnection
from src.drug_extraction_system.services.condition_standardizer import ConditionStandardizer
from src.drug_extraction_system.api_clients.openfda_client import OpenFDAClient
from ..models import DiseaseMatch, ApprovedDrug, AUTOIMMUNE_ENDPOINTS, get_endpoints_for_disease

logger = logging.getLogger(__name__)


class DiseaseDrugFinder:
    """
    Finds approved drugs for a standardized disease name.

    Flow:
    1. Standardize disease name (SLE -> Systemic Lupus Erythematosus)
    2. Search local database for drugs with this indication
    3. Search OpenFDA for drugs approved for this indication
    4. Auto-extract missing drugs using ApprovedDrugExtractor
    5. Return combined list for user selection
    """

    def __init__(self, db: DatabaseConnection):
        """
        Initialize with database connection.

        Args:
            db: DatabaseConnection instance
        """
        self.db = db
        self.condition_standardizer = ConditionStandardizer(db)
        self.openfda_client = OpenFDAClient()

    def standardize_disease(self, disease_input: str) -> Optional[DiseaseMatch]:
        """
        Standardize disease name using ConditionStandardizer.

        Args:
            disease_input: User-provided disease name (e.g., "SLE", "lupus")

        Returns:
            DiseaseMatch with standardized name and MeSH ID, or None if not found
        """
        if not disease_input or not disease_input.strip():
            return None

        result = self.condition_standardizer.standardize(disease_input.strip())

        if not result:
            logger.warning(f"Could not standardize disease: {disease_input}")
            # Return a basic match using the input as-is
            return DiseaseMatch(
                raw_input=disease_input,
                standard_name=disease_input,
                mesh_id=None,
                therapeutic_area=None,
                confidence=0.5,
                synonyms=[]
            )

        # Get synonyms for broader search
        synonyms = self._get_disease_synonyms(
            result.get("standard_name", disease_input),
            result.get("mesh_id")
        )

        return DiseaseMatch(
            raw_input=disease_input,
            standard_name=result.get("standard_name", disease_input),
            mesh_id=result.get("mesh_id"),
            therapeutic_area=result.get("therapeutic_area"),
            confidence=result.get("confidence", 1.0),
            synonyms=synonyms
        )

    def _get_disease_synonyms(self, standard_name: str, mesh_id: Optional[str]) -> List[str]:
        """
        Get disease synonyms for broader search.
        """
        synonyms = []

        # Common SLE synonyms
        if "lupus" in standard_name.lower() or standard_name == "Systemic Lupus Erythematosus":
            synonyms.extend(["SLE", "lupus", "systemic lupus", "lupus erythematosus"])

        # Common RA synonyms
        if "rheumatoid" in standard_name.lower():
            synonyms.extend(["RA", "rheumatoid"])

        # Common psoriasis synonyms
        if "psoriasis" in standard_name.lower():
            synonyms.extend(["plaque psoriasis", "psoriasis vulgaris"])

        # Try MeSH for additional terms
        if mesh_id:
            try:
                from src.drug_extraction_system.api_clients.mesh_client import MeSHClient
                mesh = MeSHClient()
                related = mesh.get_related_terms(mesh_id)
                synonyms.extend([r.get("label", "") for r in related[:3] if r.get("label")])
            except Exception as e:
                logger.debug(f"Could not get MeSH synonyms: {e}")

        return list(set(s for s in synonyms if s))  # Deduplicate and remove empty

    def find_approved_drugs_from_database(
        self,
        disease: DiseaseMatch,
        approval_status: str = "approved"
    ) -> List[ApprovedDrug]:
        """
        Find drugs approved for the disease from local database.
        """
        self.db.ensure_connected()

        # Build search terms including synonyms
        search_terms = [disease.standard_name] + disease.synonyms
        search_terms = [t for t in search_terms if t]

        if not search_terms:
            return []

        with self.db.cursor() as cur:
            conditions = []
            params = []

            for term in search_terms:
                conditions.append("di.disease_name ILIKE %s")
                params.append(f"%{term}%")

            where_clause = " OR ".join(conditions)
            params.append(approval_status)

            query = f"""
                SELECT DISTINCT
                    d.drug_id, d.drug_key, d.generic_name, d.brand_name,
                    d.manufacturer, d.first_approval_date,
                    di.disease_name, di.population, di.severity,
                    di.line_of_therapy, di.approval_date as indication_approval_date
                FROM drugs d
                JOIN drug_indications di ON d.drug_id = di.drug_id
                WHERE ({where_clause})
                  AND di.approval_status = %s
                  AND d.approval_status = 'approved'
                ORDER BY d.generic_name
            """

            cur.execute(query, params)

            drugs = []
            seen_drug_ids = set()

            for row in cur.fetchall():
                if row['drug_id'] in seen_drug_ids:
                    continue
                seen_drug_ids.add(row['drug_id'])

                details_parts = []
                if row.get('population'):
                    details_parts.append(row['population'])
                if row.get('severity'):
                    details_parts.append(row['severity'])
                if row.get('line_of_therapy'):
                    details_parts.append(row['line_of_therapy'])

                drugs.append(ApprovedDrug(
                    drug_id=row['drug_id'],
                    drug_key=row['drug_key'] or "",
                    generic_name=row['generic_name'],
                    brand_name=row.get('brand_name'),
                    manufacturer=row.get('manufacturer'),
                    approval_date=str(row.get('indication_approval_date') or row.get('first_approval_date') or ''),
                    indication_details=" | ".join(details_parts) if details_parts else None
                ))

            logger.info(f"Found {len(drugs)} drugs in database for {disease.standard_name}")
            return drugs

    def search_openfda_by_indication(
        self,
        disease: DiseaseMatch,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Search OpenFDA for drugs approved for the indication.

        Args:
            disease: Standardized disease match
            limit: Maximum number of results

        Returns:
            List of drug info dicts with generic_name, brand_name, manufacturer
        """
        search_terms = [disease.standard_name] + disease.synonyms
        all_drugs: Dict[str, Dict] = {}  # generic_name -> drug info

        for term in search_terms:
            try:
                # Search indications_and_usage field
                clean_term = term.replace('"', '').replace("'", "")

                # OpenFDA query to search in indications
                params = {
                    "search": f'indications_and_usage:"{clean_term}"',
                    "limit": limit
                }

                if self.openfda_client.api_key:
                    params["api_key"] = self.openfda_client.api_key

                result = self.openfda_client.get("/drug/label.json", params=params)

                if result and "results" in result:
                    for label in result["results"]:
                        openfda = label.get("openfda", {})

                        generic_names = openfda.get("generic_name", [])
                        brand_names = openfda.get("brand_name", [])
                        manufacturers = openfda.get("manufacturer_name", [])

                        if not generic_names:
                            continue

                        generic_name = generic_names[0].lower()

                        # Skip if already found
                        if generic_name in all_drugs:
                            continue

                        all_drugs[generic_name] = {
                            "generic_name": generic_names[0],
                            "brand_name": brand_names[0] if brand_names else None,
                            "manufacturer": manufacturers[0] if manufacturers else None,
                            "source": "openfda"
                        }

                    logger.info(f"OpenFDA search for '{term}' found {len(result['results'])} labels")

            except Exception as e:
                logger.warning(f"OpenFDA search failed for '{term}': {e}")
                continue

        logger.info(f"Total unique drugs from OpenFDA: {len(all_drugs)}")
        return list(all_drugs.values())

    def find_approved_drugs(
        self,
        disease: DiseaseMatch,
        include_openfda_search: bool = True,
        progress_callback: Optional[Callable[[str, float], None]] = None
    ) -> List[ApprovedDrug]:
        """
        Find drugs approved for the standardized disease.

        Combines database search with OpenFDA search.

        Args:
            disease: Standardized disease match
            include_openfda_search: Whether to search OpenFDA for additional drugs
            progress_callback: Optional callback for progress updates

        Returns:
            List of approved drugs for this indication
        """
        progress = progress_callback or (lambda msg, pct: None)

        # Step 1: Get drugs from local database
        progress("Searching local database...", 0.1)
        db_drugs = self.find_approved_drugs_from_database(disease)
        db_drug_names = {d.generic_name.lower() for d in db_drugs}

        logger.info(f"Database has {len(db_drugs)} drugs for {disease.standard_name}")

        if not include_openfda_search:
            return db_drugs

        # Step 2: Search OpenFDA for additional drugs
        progress("Searching OpenFDA for approved drugs...", 0.3)
        openfda_drugs = self.search_openfda_by_indication(disease)

        # Find drugs in OpenFDA that are NOT in our database
        missing_drugs = []
        for drug_info in openfda_drugs:
            generic_lower = drug_info["generic_name"].lower()
            if generic_lower not in db_drug_names:
                missing_drugs.append(drug_info)

        logger.info(f"Found {len(missing_drugs)} drugs in OpenFDA not in database")

        # Return only database drugs for efficacy extraction
        # (OpenFDA drugs need to be extracted first via extract_missing_drugs)
        return db_drugs

    def extract_missing_drugs(
        self,
        missing_drugs: List[Dict[str, Any]],
        disease: DiseaseMatch,
        progress_callback: Optional[Callable[[str, float], None]] = None
    ) -> List[ApprovedDrug]:
        """
        Extract missing drugs using ApprovedDrugExtractor.

        Args:
            missing_drugs: List of drug info dicts from OpenFDA
            disease: Disease context
            progress_callback: Progress callback

        Returns:
            List of newly extracted ApprovedDrug objects
        """
        from src.drug_extraction_system.extractors.approved_drug_extractor import ApprovedDrugExtractor
        from src.drug_extraction_system.database.operations import DrugDatabaseOperations

        progress = progress_callback or (lambda msg, pct: None)
        extractor = ApprovedDrugExtractor()
        ops = DrugDatabaseOperations(self.db)

        extracted_drugs = []
        total = len(missing_drugs)

        for i, drug_info in enumerate(missing_drugs):
            drug_name = drug_info["generic_name"]
            pct = 0.4 + (i / total) * 0.5 if total > 0 else 0.9
            progress(f"Extracting {drug_name} ({i+1}/{total})...", pct)

            try:
                logger.info(f"Extracting: {drug_name}")

                # Extract comprehensive drug data
                extracted = extractor.extract(drug_name)

                if not extracted or not extracted.generic_name:
                    logger.warning(f"No data extracted for {drug_name}")
                    continue

                # Build drug dict for database
                drug_dict = {
                    'drug_key': extracted.drug_key,
                    'generic_name': extracted.generic_name,
                    'brand_name': extracted.brand_name,
                    'manufacturer': extracted.manufacturer,
                    'drug_type': extracted.drug_type,
                    'mechanism_of_action': extracted.mechanism_of_action,
                    'approval_status': 'approved',
                    'highest_phase': 'Approved',
                    'first_approval_date': extracted.first_approval_date,
                    'rxcui': extracted.rxcui,
                    'chembl_id': extracted.chembl_id,
                    'unii': extracted.unii,
                    'completeness_score': extracted.completeness_score,
                }

                # Upsert drug
                drug_id, drug_key = ops.upsert_drug(drug_dict)

                # Store indications
                if extracted.indications:
                    ops.store_indications(drug_id, extracted.indications)

                # Store dosing regimens
                if extracted.dosing_regimens:
                    ops.store_dosing_regimens(drug_id, extracted.dosing_regimens)

                # Store clinical trials
                if extracted.clinical_trials:
                    ops.store_clinical_trials(drug_id, extracted.clinical_trials)

                logger.info(f"Stored {drug_name} (ID: {drug_id}, completeness: {extracted.completeness_score:.0%})")

                # Create ApprovedDrug object
                extracted_drugs.append(ApprovedDrug(
                    drug_id=drug_id,
                    drug_key=drug_key,
                    generic_name=extracted.generic_name,
                    brand_name=extracted.brand_name,
                    manufacturer=extracted.manufacturer,
                    approval_date=str(extracted.first_approval_date) if extracted.first_approval_date else None,
                    indication_details=f"Newly extracted | Completeness: {extracted.completeness_score:.0%}"
                ))

            except Exception as e:
                logger.error(f"Failed to extract {drug_name}: {e}")
                continue

        logger.info(f"Successfully extracted {len(extracted_drugs)} new drugs")
        return extracted_drugs

    def find_and_extract_approved_drugs(
        self,
        disease: DiseaseMatch,
        auto_extract: bool = True,
        progress_callback: Optional[Callable[[str, float], None]] = None
    ) -> Dict[str, Any]:
        """
        Complete workflow: Find drugs from DB + OpenFDA, optionally auto-extract missing.

        Args:
            disease: Standardized disease match
            auto_extract: Whether to automatically extract missing drugs
            progress_callback: Progress callback

        Returns:
            {
                "database_drugs": List[ApprovedDrug],  # Already in database
                "openfda_drugs": List[Dict],           # Found in OpenFDA, not in DB
                "extracted_drugs": List[ApprovedDrug], # Newly extracted (if auto_extract)
                "all_drugs": List[ApprovedDrug]        # Combined list
            }
        """
        progress = progress_callback or (lambda msg, pct: None)

        # Step 1: Search database
        progress("Searching database...", 0.1)
        db_drugs = self.find_approved_drugs_from_database(disease)
        db_drug_names = {d.generic_name.lower() for d in db_drugs}

        # Step 2: Search OpenFDA
        progress("Searching OpenFDA...", 0.2)
        openfda_results = self.search_openfda_by_indication(disease)

        # Filter to drugs not in database
        missing_drugs = [
            d for d in openfda_results
            if d["generic_name"].lower() not in db_drug_names
        ]

        # Step 3: Auto-extract if requested
        extracted_drugs = []
        if auto_extract and missing_drugs:
            progress(f"Extracting {len(missing_drugs)} new drugs...", 0.3)
            extracted_drugs = self.extract_missing_drugs(
                missing_drugs, disease, progress_callback
            )

        # Combine all drugs
        all_drugs = db_drugs + extracted_drugs

        progress("Complete!", 1.0)

        return {
            "database_drugs": db_drugs,
            "openfda_drugs": missing_drugs,
            "extracted_drugs": extracted_drugs,
            "all_drugs": all_drugs
        }

    def get_expected_endpoints(self, disease: DiseaseMatch) -> Dict[str, List[str]]:
        """
        Get expected efficacy endpoints for this disease area.
        """
        return get_endpoints_for_disease(disease.standard_name)

    def search_drugs_by_name(self, drug_name: str) -> List[ApprovedDrug]:
        """
        Search for drugs by name (for manual addition).
        """
        self.db.ensure_connected()

        with self.db.cursor() as cur:
            cur.execute("""
                SELECT drug_id, drug_key, generic_name, brand_name, manufacturer
                FROM drugs
                WHERE generic_name ILIKE %s OR brand_name ILIKE %s
                ORDER BY generic_name
                LIMIT 10
            """, (f"%{drug_name}%", f"%{drug_name}%"))

            return [
                ApprovedDrug(
                    drug_id=row['drug_id'],
                    drug_key=row['drug_key'] or "",
                    generic_name=row['generic_name'],
                    brand_name=row.get('brand_name'),
                    manufacturer=row.get('manufacturer'),
                )
                for row in cur.fetchall()
            ]
