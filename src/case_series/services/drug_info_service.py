"""
Drug Information Service

Retrieves drug metadata using a layered approach:
1. Drug Database (primary cache) - check if drug already extracted
2. ApprovedDrugExtractor (Batch Drug Extraction flow) - comprehensive extraction
3. Save to database for future lookups

This integrates with the drug_extraction_system for robust, comprehensive drug info.
"""

import logging
import os
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

from src.case_series.protocols.llm_protocol import LLMClient
from src.case_series.protocols.web_protocol import WebFetcher
from src.case_series.protocols.database_protocol import CaseSeriesRepositoryProtocol

logger = logging.getLogger(__name__)


@dataclass
class DrugInfo:
    """Drug information data class."""
    drug_name: str
    generic_name: Optional[str] = None
    brand_name: Optional[str] = None
    mechanism: Optional[str] = None
    target: Optional[str] = None
    drug_type: Optional[str] = None
    approved_indications: List[str] = field(default_factory=list)
    dosing_regimens: List[Dict] = field(default_factory=list)
    clinical_trials: List[Dict] = field(default_factory=list)
    data_sources: List[str] = field(default_factory=list)
    drug_id: Optional[int] = None  # Database ID if loaded from DB
    drug_key: Optional[str] = None  # Unique drug key

    def __post_init__(self):
        if self.approved_indications is None:
            self.approved_indications = []
        if self.data_sources is None:
            self.data_sources = []

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'drug_name': self.drug_name,
            'generic_name': self.generic_name,
            'brand_name': self.brand_name,
            'mechanism': self.mechanism,
            'target': self.target,
            'drug_type': self.drug_type,
            'approved_indications': self.approved_indications,
            'dosing_regimens': self.dosing_regimens,
            'clinical_trials': self.clinical_trials,
            'data_sources': self.data_sources,
            'drug_id': self.drug_id,
            'drug_key': self.drug_key,
        }


class DrugInfoService:
    """
    Service for retrieving drug information.

    Uses a layered approach:
    1. Drug Database (check if already extracted)
    2. ApprovedDrugExtractor (comprehensive extraction from DailyMed, OpenFDA, etc.)
    3. Save to database for future lookups

    This leverages the drug_extraction_system's robust extraction pipeline.
    """

    def __init__(
        self,
        repository: Optional[CaseSeriesRepositoryProtocol] = None,
        llm_client: Optional[LLMClient] = None,
        web_fetcher: Optional[WebFetcher] = None,
        database_url: Optional[str] = None,
    ):
        """
        Initialize the drug info service.

        Args:
            repository: Optional case series repository for caching
            llm_client: Optional LLM for extraction (used by ApprovedDrugExtractor)
            web_fetcher: Optional web fetcher for API calls
            database_url: PostgreSQL database URL for drug database
        """
        self._repository = repository
        self._llm_client = llm_client
        self._web_fetcher = web_fetcher
        self._database_url = database_url or os.getenv("DATABASE_URL")

        # Lazy-loaded components
        self._drug_db_ops = None
        self._approved_extractor = None

    def _get_drug_db_ops(self):
        """Lazy-load drug database operations."""
        if self._drug_db_ops is None and self._database_url:
            try:
                from src.drug_extraction_system.database.connection import DatabaseConnection
                from src.drug_extraction_system.database.operations import DrugDatabaseOperations

                db = DatabaseConnection(self._database_url)
                self._drug_db_ops = DrugDatabaseOperations(db)
                logger.info("Drug database connection initialized")
            except Exception as e:
                logger.warning(f"Could not initialize drug database: {e}")
        return self._drug_db_ops

    def _get_approved_extractor(self):
        """Lazy-load the ApprovedDrugExtractor."""
        if self._approved_extractor is None:
            try:
                from src.drug_extraction_system.extractors.approved_drug_extractor import ApprovedDrugExtractor
                self._approved_extractor = ApprovedDrugExtractor()
                logger.info("ApprovedDrugExtractor initialized")
            except Exception as e:
                logger.warning(f"Could not initialize ApprovedDrugExtractor: {e}")
        return self._approved_extractor

    async def get_drug_info(self, drug_name: str) -> DrugInfo:
        """
        Get drug information using layered approach.

        1. Check drug database first
        2. If not found, use ApprovedDrugExtractor
        3. Save to database for future lookups

        Args:
            drug_name: Name of the drug (brand or generic)

        Returns:
            DrugInfo with available data
        """
        # STEP 1: Check drug database first
        drug_db = self._get_drug_db_ops()
        if drug_db:
            db_result = self._load_from_drug_database(drug_name)
            if db_result:
                logger.info(f"Found '{drug_name}' in drug database")
                return db_result

        # STEP 2: Use ApprovedDrugExtractor (the Batch Drug Extraction flow)
        extractor = self._get_approved_extractor()
        if extractor:
            extracted = self._extract_with_approved_extractor(drug_name)
            if extracted:
                logger.info(f"Extracted drug info for '{drug_name}' using ApprovedDrugExtractor")

                # STEP 3: Save to drug database for future lookups
                if drug_db:
                    self._save_to_drug_database(extracted)

                return extracted

        # STEP 4: Fallback to legacy methods if extractor unavailable
        logger.info(f"Using legacy extraction for '{drug_name}'")
        return await self._legacy_get_drug_info(drug_name)

    def _load_from_drug_database(self, drug_name: str) -> Optional[DrugInfo]:
        """
        Load drug info from the drug database.

        Args:
            drug_name: Drug name to search for

        Returns:
            DrugInfo if found, None otherwise
        """
        drug_db = self._get_drug_db_ops()
        if not drug_db:
            return None

        try:
            # Try to find by identifier (handles generic name, brand name, drug_key)
            drug_record = drug_db.find_drug_by_identifier(drug_name)

            if not drug_record:
                return None

            drug_id = drug_record.get('drug_id')

            # Get full details including indications, dosing, trials
            full_record = drug_db.get_drug_with_details(drug_id)
            if not full_record:
                return None

            # Extract indication names
            indications = []
            for ind in full_record.get('indications', []):
                disease_name = ind.get('disease_name')
                if disease_name:
                    indications.append(disease_name)

            return DrugInfo(
                drug_name=drug_name,
                generic_name=full_record.get('generic_name'),
                brand_name=full_record.get('brand_name'),
                mechanism=full_record.get('mechanism_of_action'),
                target=full_record.get('target'),
                drug_type=full_record.get('drug_type'),
                approved_indications=indications,
                dosing_regimens=full_record.get('dosing_regimens', []),
                clinical_trials=full_record.get('clinical_trials', []),
                data_sources=['Drug Database'],
                drug_id=drug_id,
                drug_key=full_record.get('drug_key'),
            )

        except Exception as e:
            logger.warning(f"Error loading from drug database: {e}")
            return None

    def _extract_with_approved_extractor(self, drug_name: str) -> Optional[DrugInfo]:
        """
        Extract drug info using ApprovedDrugExtractor.

        This uses the full Batch Drug Extraction pipeline:
        - DailyMed (primary for MOA)
        - OpenFDA (labels, indications, dosing)
        - RxNorm (name standardization)
        - MeSH (indication standardization)
        - ClinicalTrials.gov (industry-sponsored trials)

        Args:
            drug_name: Drug name to extract

        Returns:
            DrugInfo if successful, None otherwise
        """
        extractor = self._get_approved_extractor()
        if not extractor:
            return None

        try:
            # Get development code if available in database
            dev_code = None
            drug_db = self._get_drug_db_ops()
            if drug_db:
                dev_code = drug_db.get_development_code(drug_name)

            # Run extraction
            extracted_data = extractor.extract(drug_name, development_code=dev_code)

            if not extracted_data:
                return None

            # Extract indication names from structured data
            indications = []
            for ind in extracted_data.indications:
                if isinstance(ind, dict):
                    # Try standardized name first, then raw text
                    name = ind.get('standardized_name') or ind.get('disease_name') or ind.get('raw_text', '')
                    if name and len(name) < 500:  # Skip raw text that's too long
                        indications.append(name)
                elif isinstance(ind, str):
                    indications.append(ind)

            # Build data sources list
            data_sources = extracted_data.data_sources or []
            if not data_sources:
                data_sources = ['ApprovedDrugExtractor']

            return DrugInfo(
                drug_name=drug_name,
                generic_name=extracted_data.generic_name,
                brand_name=extracted_data.brand_name,
                mechanism=extracted_data.mechanism_of_action,
                target=None,  # Could be extracted from MOA
                drug_type=extracted_data.drug_type,
                approved_indications=indications,
                dosing_regimens=extracted_data.dosing_regimens or [],
                clinical_trials=extracted_data.clinical_trials or [],
                data_sources=data_sources,
                drug_key=extracted_data.drug_key,
            )

        except Exception as e:
            logger.error(f"ApprovedDrugExtractor failed for '{drug_name}': {e}")
            return None

    def _save_to_drug_database(self, drug_info: DrugInfo) -> bool:
        """
        Save extracted drug info to the drug database.

        Args:
            drug_info: DrugInfo to save

        Returns:
            True if saved successfully, False otherwise
        """
        drug_db = self._get_drug_db_ops()
        if not drug_db:
            return False

        try:
            # Prepare data for upsert
            data = {
                'generic_name': drug_info.generic_name or drug_info.drug_name,
                'brand_name': drug_info.brand_name,
                'mechanism_of_action': drug_info.mechanism,
                'drug_type': drug_info.drug_type,
                'drug_key': drug_info.drug_key,
                'approval_status': 'approved',
            }

            # Upsert drug
            drug_id, drug_key = drug_db.upsert_drug(data)
            drug_info.drug_id = drug_id
            drug_info.drug_key = drug_key

            # Store indications
            if drug_info.approved_indications:
                indication_dicts = [
                    {'disease_name': ind} for ind in drug_info.approved_indications
                ]
                drug_db.store_indications(drug_id, indication_dicts)

            # Store dosing regimens
            if drug_info.dosing_regimens:
                drug_db.store_dosing_regimens(drug_id, drug_info.dosing_regimens)

            # Store clinical trials
            if drug_info.clinical_trials:
                drug_db.store_clinical_trials(drug_id, drug_info.clinical_trials)

            logger.info(f"Saved drug info to database: {drug_key} (ID: {drug_id})")
            return True

        except Exception as e:
            logger.warning(f"Failed to save to drug database: {e}")
            return False

    async def _legacy_get_drug_info(self, drug_name: str) -> DrugInfo:
        """
        Legacy method for getting drug info when ApprovedDrugExtractor unavailable.

        Falls back to:
        - Case series repository cache
        - DailyMed API
        - Drugs.com
        - OpenFDA API
        """
        # Check case series repository cache
        if self._repository:
            cached = self._repository.load_drug(drug_name)
            if cached:
                logger.info(f"Found cached drug info for {drug_name}")
                return DrugInfo(
                    drug_name=cached.get('drug_name', drug_name),
                    generic_name=cached.get('generic_name'),
                    mechanism=cached.get('mechanism'),
                    target=cached.get('target'),
                    approved_indications=cached.get('approved_indications', []),
                    data_sources=cached.get('data_sources', ['cache']),
                )

        # Try DailyMed
        dailymed_info = await self._fetch_from_dailymed(drug_name)
        if dailymed_info:
            info = self._merge_drug_info(DrugInfo(drug_name=drug_name), dailymed_info)
            info.data_sources.append('DailyMed')

            if self._repository:
                self._repository.save_drug(drug_name, info.to_dict())

            return info

        # Try Drugs.com
        drugs_com_info = await self._fetch_from_drugs_com(drug_name)
        if drugs_com_info:
            info = self._merge_drug_info(DrugInfo(drug_name=drug_name), drugs_com_info)
            info.data_sources.append('Drugs.com')

            if self._repository:
                self._repository.save_drug(drug_name, info.to_dict())

            return info

        # Try OpenFDA
        openfda_info = await self._fetch_from_openfda(drug_name)
        if openfda_info:
            info = self._merge_drug_info(DrugInfo(drug_name=drug_name), openfda_info)
            info.data_sources.append('OpenFDA')

            if self._repository:
                self._repository.save_drug(drug_name, info.to_dict())

            return info

        # Return minimal info
        logger.warning(f"No drug info found for {drug_name}")
        return DrugInfo(drug_name=drug_name)

    async def _fetch_from_dailymed(self, drug_name: str) -> Optional[Dict[str, Any]]:
        """Fetch drug info from DailyMed."""
        if not self._web_fetcher:
            return None

        try:
            url = f"https://dailymed.nlm.nih.gov/dailymed/services/v2/spls.json?drug_name={drug_name}"
            content = await self._web_fetcher.fetch_json(url)

            if not content or 'data' not in content:
                return None

            spls = content.get('data', [])
            if not spls:
                return None

            spl = spls[0]
            set_id = spl.get('setid')

            if not set_id:
                return None

            spl_url = f"https://dailymed.nlm.nih.gov/dailymed/services/v2/spls/{set_id}.json"
            spl_content = await self._web_fetcher.fetch_json(spl_url)

            if not spl_content:
                return None

            return {
                'generic_name': spl.get('generic_name'),
                'approved_indications': [],
                'mechanism': None,
            }

        except Exception as e:
            logger.warning(f"DailyMed fetch failed for {drug_name}: {e}")
            return None

    async def _fetch_from_drugs_com(self, drug_name: str) -> Optional[Dict[str, Any]]:
        """Fetch drug info from Drugs.com."""
        if not self._web_fetcher or not self._llm_client:
            return None

        try:
            url = f"https://www.drugs.com/{drug_name.lower().replace(' ', '-')}.html"
            content = await self._web_fetcher.fetch(url)

            if not content:
                return None

            from src.case_series.prompts.extraction_prompts import build_drug_info_prompt
            prompt = build_drug_info_prompt(drug_name, drugs_com_content=content[:20000])

            response = await self._llm_client.complete(prompt, max_tokens=2000)

            import json
            result = json.loads(response)

            return result

        except Exception as e:
            logger.warning(f"Failed to fetch https://www.drugs.com/{drug_name.lower().replace(' ', '-')}.html: {e}")
            return None

    async def _fetch_from_openfda(self, drug_name: str) -> Optional[Dict[str, Any]]:
        """Fetch drug info from OpenFDA."""
        if not self._web_fetcher:
            return None

        try:
            url = f"https://api.fda.gov/drug/label.json?search=openfda.brand_name:{drug_name}&limit=1"
            content = await self._web_fetcher.fetch_json(url)

            if not content or 'results' not in content:
                return None

            result = content['results'][0]
            openfda = result.get('openfda', {})

            return {
                'generic_name': openfda.get('generic_name', [None])[0],
                'mechanism': openfda.get('mechanism_of_action', [None])[0],
                'approved_indications': result.get('indications_and_usage', []),
            }

        except Exception as e:
            logger.warning(f"OpenFDA fetch failed for {drug_name}: {e}")
            return None

    def _merge_drug_info(self, base: DrugInfo, new_data: Dict[str, Any]) -> DrugInfo:
        """Merge new data into base DrugInfo."""
        if new_data.get('generic_name') and not base.generic_name:
            base.generic_name = new_data['generic_name']

        if new_data.get('mechanism') and not base.mechanism:
            base.mechanism = new_data['mechanism']

        if new_data.get('target') and not base.target:
            base.target = new_data['target']

        if new_data.get('approved_indications'):
            existing = set(ind.lower() for ind in base.approved_indications)
            for ind in new_data['approved_indications']:
                if ind.lower() not in existing:
                    base.approved_indications.append(ind)
                    existing.add(ind.lower())

        return base
