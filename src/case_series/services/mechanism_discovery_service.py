"""
Mechanism Discovery Service

Discovers drugs by molecular target or mechanism of action.
Searches both the local drug database and external sources.
"""

import logging
import asyncio
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class DiscoveredDrug:
    """Drug discovered for a mechanism/target."""
    generic_name: str
    brand_name: Optional[str] = None
    manufacturer: Optional[str] = None
    drug_type: Optional[str] = None
    mechanism_of_action: Optional[str] = None
    target: Optional[str] = None
    moa_category: Optional[str] = None
    approval_status: Optional[str] = None
    highest_phase: Optional[str] = None
    first_approval_date: Optional[str] = None
    approved_indications: List[str] = field(default_factory=list)
    source: str = "database"  # "database", "openfda", "clinicaltrials", "web"
    in_database: bool = False
    drug_id: Optional[int] = None
    drug_key: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "generic_name": self.generic_name,
            "brand_name": self.brand_name,
            "manufacturer": self.manufacturer,
            "drug_type": self.drug_type,
            "mechanism_of_action": self.mechanism_of_action,
            "target": self.target,
            "moa_category": self.moa_category,
            "approval_status": self.approval_status,
            "highest_phase": self.highest_phase,
            "first_approval_date": self.first_approval_date,
            "approved_indications": self.approved_indications,
            "source": self.source,
            "in_database": self.in_database,
            "drug_id": self.drug_id,
            "drug_key": self.drug_key,
        }


@dataclass
class MechanismSearchResult:
    """Result of mechanism-based drug search."""
    target_query: str
    drugs_from_database: List[DiscoveredDrug] = field(default_factory=list)
    drugs_from_external: List[DiscoveredDrug] = field(default_factory=list)
    drugs_added_to_database: List[DiscoveredDrug] = field(default_factory=list)
    all_drugs: List[DiscoveredDrug] = field(default_factory=list)
    sources_searched: List[str] = field(default_factory=list)

    @property
    def total_drugs(self) -> int:
        return len(self.all_drugs)


class MechanismDiscoveryService:
    """
    Service for discovering drugs by mechanism/target.

    Searches:
    1. Local drug database
    2. OpenFDA for approved drugs
    3. ClinicalTrials.gov for investigational drugs
    4. Web search for additional context

    Can automatically add missing drugs to the database using batch extraction.
    """

    def __init__(
        self,
        database_url: Optional[str] = None,
        llm_client: Optional[Any] = None,
        web_searcher: Optional[Any] = None,
    ):
        """
        Initialize the mechanism discovery service.

        Args:
            database_url: PostgreSQL database URL for drug database
            llm_client: LLM client for drug extraction
            web_searcher: Web search client for external discovery
        """
        self._database_url = database_url
        self._llm_client = llm_client
        self._web_searcher = web_searcher
        self._db_ops = None
        self._approved_extractor = None

    def _get_db_ops(self):
        """Lazy initialization of database operations."""
        if self._db_ops is None and self._database_url:
            try:
                from src.drug_extraction_system.database.connection import DatabaseConnection
                from src.drug_extraction_system.database.operations import DrugDatabaseOperations
                db = DatabaseConnection(self._database_url)
                self._db_ops = DrugDatabaseOperations(db)
            except Exception as e:
                logger.warning(f"Could not initialize database: {e}")
        return self._db_ops

    def _get_extractor(self):
        """Lazy initialization of drug extractor."""
        if self._approved_extractor is None:
            try:
                from src.drug_extraction_system.extractors.approved_drug_extractor import ApprovedDrugExtractor
                self._approved_extractor = ApprovedDrugExtractor()
            except Exception as e:
                logger.warning(f"Could not initialize drug extractor: {e}")
        return self._approved_extractor

    async def discover_drugs_by_target(
        self,
        target: str,
        search_external: bool = True,
        add_missing_to_database: bool = True,
        approval_status_filter: Optional[str] = None,
    ) -> MechanismSearchResult:
        """
        Discover all drugs targeting a specific molecule.

        Args:
            target: Molecular target (e.g., 'JAK1', 'IL-6', 'TNF-alpha')
            search_external: Whether to search external sources
            add_missing_to_database: Whether to add discovered drugs to database
            approval_status_filter: Filter by 'approved' or 'investigational'

        Returns:
            MechanismSearchResult with all discovered drugs
        """
        result = MechanismSearchResult(target_query=target)
        seen_drugs: Set[str] = set()  # Track by lowercase generic name

        # Step 1: Search local database
        db_drugs = self._search_database(target, approval_status_filter)
        for drug in db_drugs:
            key = drug.generic_name.lower()
            if key not in seen_drugs:
                seen_drugs.add(key)
                result.drugs_from_database.append(drug)
                result.all_drugs.append(drug)
        result.sources_searched.append("Drug Database")
        logger.info(f"Found {len(db_drugs)} drugs in database for target '{target}'")

        # Step 2: Search external sources
        if search_external:
            external_drugs = await self._search_external_sources(target, approval_status_filter)
            for drug in external_drugs:
                key = drug.generic_name.lower()
                if key not in seen_drugs:
                    seen_drugs.add(key)
                    result.drugs_from_external.append(drug)
                    result.all_drugs.append(drug)
            logger.info(f"Found {len(external_drugs)} additional drugs from external sources")

        # Step 3: Add missing drugs to database
        if add_missing_to_database and result.drugs_from_external:
            added = await self._add_drugs_to_database(result.drugs_from_external)
            result.drugs_added_to_database = added
            logger.info(f"Added {len(added)} new drugs to database")

            # Update the drugs in all_drugs to reflect they're now in database
            for drug in result.all_drugs:
                if drug in added:
                    drug.in_database = True

        return result

    def _search_database(
        self,
        target: str,
        approval_status: Optional[str] = None,
    ) -> List[DiscoveredDrug]:
        """Search drug database for drugs with target."""
        drugs = []
        db_ops = self._get_db_ops()

        if not db_ops:
            return drugs

        try:
            results = db_ops.search_by_target(
                target=target,
                include_moa_category=True,
                approval_status=approval_status,
            )

            for r in results:
                # Get approved indications
                indications = []
                if r.get("drug_id"):
                    try:
                        drug_details = db_ops.get_drug_with_details(r["drug_id"])
                        if drug_details and drug_details.get("indications"):
                            indications = [
                                ind.get("disease_name", "")
                                for ind in drug_details["indications"]
                                if ind.get("approval_status") == "approved"
                            ]
                    except Exception as e:
                        logger.debug(f"Could not get indications: {e}")

                drugs.append(DiscoveredDrug(
                    generic_name=r.get("generic_name", ""),
                    brand_name=r.get("brand_name"),
                    manufacturer=r.get("manufacturer"),
                    drug_type=r.get("drug_type"),
                    mechanism_of_action=r.get("mechanism_of_action"),
                    target=r.get("target"),
                    moa_category=r.get("moa_category"),
                    approval_status=r.get("approval_status"),
                    highest_phase=r.get("highest_phase"),
                    first_approval_date=str(r["first_approval_date"]) if r.get("first_approval_date") else None,
                    approved_indications=indications,
                    source="database",
                    in_database=True,
                    drug_id=r.get("drug_id"),
                    drug_key=r.get("drug_key"),
                ))

        except Exception as e:
            logger.error(f"Database search failed: {e}")

        return drugs

    async def _search_external_sources(
        self,
        target: str,
        approval_status: Optional[str] = None,
    ) -> List[DiscoveredDrug]:
        """Search external sources for drugs with target."""
        drugs = []
        seen_names: Set[str] = set()

        # Search OpenFDA
        try:
            openfda_drugs = await self._search_openfda(target)
            for drug in openfda_drugs:
                key = drug.generic_name.lower()
                if key not in seen_names:
                    seen_names.add(key)
                    if approval_status is None or drug.approval_status == approval_status:
                        drugs.append(drug)
            logger.info(f"OpenFDA returned {len(openfda_drugs)} drugs for '{target}'")
        except Exception as e:
            logger.warning(f"OpenFDA search failed: {e}")

        # Search ClinicalTrials.gov for investigational drugs
        if approval_status != "approved":
            try:
                ct_drugs = await self._search_clinical_trials(target)
                for drug in ct_drugs:
                    key = drug.generic_name.lower()
                    if key not in seen_names:
                        seen_names.add(key)
                        drugs.append(drug)
                logger.info(f"ClinicalTrials.gov returned {len(ct_drugs)} drugs for '{target}'")
            except Exception as e:
                logger.warning(f"ClinicalTrials.gov search failed: {e}")

        # Web search for additional drugs
        if self._web_searcher:
            try:
                web_drugs = await self._search_web(target)
                for drug in web_drugs:
                    key = drug.generic_name.lower()
                    if key not in seen_names:
                        seen_names.add(key)
                        if approval_status is None or drug.approval_status == approval_status:
                            drugs.append(drug)
                logger.info(f"Web search returned {len(web_drugs)} drugs for '{target}'")
            except Exception as e:
                logger.warning(f"Web search failed: {e}")

        return drugs

    async def _search_openfda(self, target: str) -> List[DiscoveredDrug]:
        """Search OpenFDA for drugs with a target/mechanism."""
        drugs = []

        try:
            from src.drug_extraction_system.api_clients.openfda_client import OpenFDAClient
            client = OpenFDAClient()

            # Search in mechanism of action field
            search_terms = [
                f'openfda.pharm_class_moa:"{target}"',
                f'mechanism_of_action:"{target}"',
            ]

            seen = set()
            for search_term in search_terms:
                try:
                    results = client.search_drugs(search_term, limit=50)
                    for r in results:
                        generic_name = r.get("generic_name", "").lower()
                        if generic_name and generic_name not in seen:
                            seen.add(generic_name)
                            drugs.append(DiscoveredDrug(
                                generic_name=r.get("generic_name", ""),
                                brand_name=r.get("brand_name"),
                                manufacturer=r.get("manufacturer"),
                                mechanism_of_action=r.get("mechanism_of_action"),
                                approval_status="approved",
                                source="openfda",
                                in_database=False,
                            ))
                except Exception as e:
                    logger.debug(f"OpenFDA query '{search_term}' failed: {e}")
                    continue

        except ImportError:
            logger.warning("OpenFDA client not available")
        except Exception as e:
            logger.error(f"OpenFDA search error: {e}")

        return drugs

    async def _search_clinical_trials(self, target: str) -> List[DiscoveredDrug]:
        """Search ClinicalTrials.gov for investigational drugs with target."""
        drugs = []

        try:
            from src.drug_extraction_system.api_clients.clinical_trials_client import ClinicalTrialsClient
            client = ClinicalTrialsClient()

            # Search for trials with this target/mechanism
            results = client.search_trials_by_intervention(target, max_results=100)

            seen = set()
            for trial in results:
                interventions = trial.get("interventions", [])
                for intervention in interventions:
                    if intervention.get("type") == "Drug":
                        drug_name = intervention.get("name", "").strip()
                        if drug_name and drug_name.lower() not in seen:
                            # Check if this is actually related to target
                            if target.lower() in str(trial).lower():
                                seen.add(drug_name.lower())
                                drugs.append(DiscoveredDrug(
                                    generic_name=drug_name,
                                    approval_status="investigational",
                                    highest_phase=trial.get("phase", "Unknown"),
                                    source="clinicaltrials",
                                    in_database=False,
                                ))

        except ImportError:
            logger.warning("ClinicalTrials client not available")
        except Exception as e:
            logger.error(f"ClinicalTrials search error: {e}")

        return drugs

    async def _search_web(self, target: str) -> List[DiscoveredDrug]:
        """Use web search to find drugs with target."""
        drugs = []

        if not self._web_searcher:
            return drugs

        try:
            query = f"{target} inhibitor approved drugs list FDA"
            results = await self._web_searcher.search(
                query=query,
                max_results=10,
                search_depth="basic",
            )

            # Use LLM to extract drug names from results
            if self._llm_client and results:
                content = "\n".join([
                    f"Title: {r.get('title', '')}\nContent: {r.get('content', '')[:500]}"
                    for r in results[:5]
                ])

                prompt = f"""Extract the names of FDA-approved drugs that target {target} from this web search content.

{content}

Return a JSON array of drug names only (generic names preferred). Example: ["drug1", "drug2"]
If no drugs found, return empty array: []"""

                try:
                    response = await self._llm_client.complete(prompt, max_tokens=500)
                    import json
                    drug_names = json.loads(response)

                    for name in drug_names:
                        if isinstance(name, str) and name.strip():
                            drugs.append(DiscoveredDrug(
                                generic_name=name.strip(),
                                target=target,
                                approval_status="approved",
                                source="web",
                                in_database=False,
                            ))

                except Exception as e:
                    logger.debug(f"LLM extraction failed: {e}")

        except Exception as e:
            logger.warning(f"Web search failed: {e}")

        return drugs

    async def _add_drugs_to_database(
        self,
        drugs: List[DiscoveredDrug],
    ) -> List[DiscoveredDrug]:
        """Add discovered drugs to the database using batch extraction."""
        added = []
        extractor = self._get_extractor()
        db_ops = self._get_db_ops()

        if not extractor or not db_ops:
            return added

        for drug in drugs:
            try:
                # Check if already in database
                existing = db_ops.find_drug_by_identifier(drug.generic_name)
                if existing:
                    drug.in_database = True
                    drug.drug_id = existing.get("drug_id")
                    drug.drug_key = existing.get("drug_key")
                    continue

                # Extract full drug info
                logger.info(f"Extracting info for {drug.generic_name}...")
                extracted = await asyncio.to_thread(
                    extractor.extract,
                    drug.generic_name
                )

                if extracted:
                    # Prepare data for database
                    from src.drug_extraction_system.processors.drug_processor import DrugProcessor
                    processor = DrugProcessor(db_ops, skip_parsing=True)

                    drug_data = {
                        "generic_name": extracted.generic_name or drug.generic_name,
                        "brand_name": extracted.brand_names[0] if extracted.brand_names else drug.brand_name,
                        "manufacturer": extracted.manufacturer,
                        "drug_type": extracted.drug_type,
                        "mechanism_of_action": extracted.mechanism_of_action,
                        "approval_status": extracted.approval_status or "approved",
                        "first_approval_date": extracted.first_approval_date,
                    }

                    drug_id, drug_key = db_ops.upsert_drug(drug_data)
                    drug.in_database = True
                    drug.drug_id = drug_id
                    drug.drug_key = drug_key
                    added.append(drug)

                    # Also store indications
                    if extracted.indications:
                        indications_data = [
                            {
                                "disease_name": ind.disease if hasattr(ind, 'disease') else str(ind),
                                "approval_status": "approved",
                            }
                            for ind in extracted.indications
                        ]
                        db_ops.store_indications(drug_id, indications_data)

                    logger.info(f"Added {drug.generic_name} to database (ID: {drug_id})")

                # Rate limiting
                await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(f"Failed to add {drug.generic_name}: {e}")

        return added

    def get_drug_details(self, drug_id: int) -> Optional[Dict]:
        """Get full drug details from database."""
        db_ops = self._get_db_ops()
        if db_ops:
            return db_ops.get_drug_with_details(drug_id)
        return None

    def list_all_targets(self) -> List[Dict[str, Any]]:
        """List all targets in the database with drug counts."""
        db_ops = self._get_db_ops()
        if db_ops:
            return db_ops.get_all_targets()
        return []

    def list_all_moa_categories(self) -> List[Dict[str, Any]]:
        """List all MoA categories in the database with drug counts."""
        db_ops = self._get_db_ops()
        if db_ops:
            return db_ops.get_all_moa_categories()
        return []
