"""
Drug Processor

Orchestrates the full drug data extraction pipeline.
"""

import logging
from typing import Dict, Optional, Tuple, List
from dataclasses import dataclass
from enum import Enum
from psycopg2.extras import Json

from src.drug_extraction_system.resolvers.drug_name_resolver import DrugNameResolver
from src.drug_extraction_system.resolvers.status_detector import DrugStatusDetector, DrugStatus
from src.drug_extraction_system.extractors.approved_drug_extractor import ApprovedDrugExtractor, ExtractedDrugData
from src.drug_extraction_system.extractors.pipeline_drug_extractor import PipelineDrugExtractor
from src.drug_extraction_system.extractors.data_enricher import DataEnricher
from src.drug_extraction_system.parsers.indication_parser import IndicationParser
from src.drug_extraction_system.parsers.dosing_parser import DosingParser
from src.drug_extraction_system.parsers.target_moa_parser import TargetMoAParser
from src.drug_extraction_system.database.connection import DatabaseConnection
from src.drug_extraction_system.database.operations import DrugDatabaseOperations
from src.drug_extraction_system.config import get_config
from src.tools.approval_date_extractor import ApprovalDateExtractor

logger = logging.getLogger(__name__)

APPROVAL_DATE_EXTRACTOR_AVAILABLE = True


class ProcessingStatus(Enum):
    """Processing result status."""
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class ProcessingResult:
    """Result of processing a single drug."""
    drug_name: str
    status: ProcessingStatus
    drug_key: Optional[str] = None
    drug_id: Optional[int] = None
    completeness_score: float = 0.0
    error: Optional[str] = None
    data_sources: list = None

    def __post_init__(self):
        if self.data_sources is None:
            self.data_sources = []


class DrugProcessor:
    """
    Orchestrates the full drug extraction pipeline.
    
    Pipeline:
    1. Resolve drug name (brand/generic/research code)
    2. Detect status (approved vs pipeline)
    3. Extract data from appropriate sources
    4. Enrich data with AI/search
    5. Store in database
    """

    def __init__(
        self,
        db: Optional[DatabaseConnection] = None,
        config: Optional[Dict] = None,
        skip_parsing: bool = False
    ):
        """
        Initialize processor with dependencies.

        Args:
            db: Database connection (created if not provided)
            config: Configuration dict (loaded from env if not provided)
            skip_parsing: If True, skip Phase 2 (Claude parsing) for faster processing
        """
        self.config = config or get_config()
        self.skip_parsing = skip_parsing

        # Initialize database
        if db:
            self.db = db
            self.db_ops = DrugDatabaseOperations(db)
        else:
            self.db = None
            self.db_ops = None

        # Phase 1 components (fast API extraction)
        self.resolver = DrugNameResolver()
        self.status_detector = DrugStatusDetector()
        self.approved_extractor = ApprovedDrugExtractor()
        self.pipeline_extractor = PipelineDrugExtractor()
        self.enricher = DataEnricher()

        # Phase 2 parsers (Claude-based, slower)
        self.indication_parser = IndicationParser() if not skip_parsing else None
        self.dosing_parser = DosingParser() if not skip_parsing else None
        self.target_moa_parser = TargetMoAParser() if not skip_parsing else None

        # Thresholds from config
        self.success_threshold = self.config.processing.completeness_threshold
        self.partial_threshold = self.config.processing.partial_threshold

    def process(
        self,
        drug_name: str,
        force_refresh: bool = False,
        batch_id: Optional[str] = None
    ) -> ProcessingResult:
        """
        Process a single drug through the full pipeline.

        Args:
            drug_name: Drug name to process
            force_refresh: If True, refresh even if drug exists
            batch_id: Optional batch ID for tracking

        Returns:
            ProcessingResult with status and details
        """
        result = ProcessingResult(drug_name=drug_name, status=ProcessingStatus.FAILED)

        try:
            logger.info(f"Processing drug: '{drug_name}'")

            # Step 1: Check if drug already exists (unless force refresh)
            if self.db_ops and not force_refresh:
                existing = self.db_ops.find_drug_by_identifier(drug_name)
                if existing:
                    logger.info(f"Drug '{drug_name}' already exists (ID: {existing['drug_id']})")
                    result.status = ProcessingStatus.SKIPPED
                    result.drug_id = existing["drug_id"]
                    result.drug_key = existing.get("drug_key")
                    result.completeness_score = existing.get("completeness_score", 0)
                    return result

            # Step 2: Detect drug status
            status_result = self.status_detector.detect(drug_name)

            # Step 3: Extract data based on status
            if status_result.status == DrugStatus.APPROVED:
                extracted = self.approved_extractor.extract(drug_name)
            elif status_result.status == DrugStatus.PIPELINE:
                extracted = self.pipeline_extractor.extract(drug_name)
            else:
                # Unknown - try both
                extracted = self.approved_extractor.extract(drug_name)
                if extracted.completeness_score < 0.3:
                    extracted = self.pipeline_extractor.extract(drug_name)

            # Step 4: Enrich data
            extracted = self.enricher.enrich(extracted)

            # Step 5: Parse raw text into structured data (Phase 2 - Claude-based)
            if not self.skip_parsing:
                extracted = self._parse_structured_data(extracted)
            else:
                logger.info(f"Skipping Phase 2 parsing for '{drug_name}' (skip_parsing=True)")

            # Step 6: Determine processing status
            result.completeness_score = extracted.completeness_score
            result.drug_key = extracted.drug_key
            result.data_sources = extracted.data_sources

            if extracted.completeness_score >= self.success_threshold:
                result.status = ProcessingStatus.SUCCESS
            elif extracted.completeness_score >= self.partial_threshold:
                result.status = ProcessingStatus.PARTIAL
            else:
                result.status = ProcessingStatus.FAILED
                result.error = f"Completeness {extracted.completeness_score:.2%} below threshold"

            # Step 7: Store in database (if partial or better)
            if self.db_ops and result.status in [ProcessingStatus.SUCCESS, ProcessingStatus.PARTIAL]:
                drug_id, drug_key = self._store_drug(extracted, batch_id)
                result.drug_id = drug_id
                result.drug_key = drug_key

            logger.info(f"Processed '{drug_name}': {result.status.value} ({result.completeness_score:.2%})")
            return result

        except Exception as e:
            logger.error(f"Failed to process '{drug_name}': {e}")
            result.status = ProcessingStatus.FAILED
            result.error = str(e)
            return result

    def _store_drug(self, data: ExtractedDrugData, batch_id: Optional[str]) -> Tuple[int, str]:
        """Store extracted drug data in database."""
        from uuid import UUID

        # Parse target and MoA category from mechanism text
        target, moa_category = self._parse_target_and_moa(data)

        # Convert ExtractedDrugData to dict for database
        drug_data = {
            "drug_key": data.drug_key,
            "generic_name": data.generic_name,
            "brand_name": data.brand_name,
            "manufacturer": data.manufacturer,
            "development_code": data.development_code,
            "drug_type": data.drug_type,
            "mechanism_of_action": data.mechanism_of_action,
            "target": target,
            "moa_category": moa_category,
            "approval_status": data.approval_status,
            "highest_phase": data.highest_phase,
            "dailymed_setid": data.dailymed_setid,
            "first_approval_date": data.first_approval_date,
            "rxcui": data.rxcui,
            "chembl_id": data.chembl_id,
            "inchi_key": data.inchi_key,
            "cas_number": data.cas_number,
            "unii": data.unii,
            "completeness_score": data.completeness_score,
        }

        batch_uuid = UUID(batch_id) if batch_id else None
        drug_id, drug_key = self.db_ops.upsert_drug(drug_data, batch_id=batch_uuid)

        # Store related data (clinical trials, data sources, indications, dosing, metadata)
        self._store_clinical_trials(drug_id, data)
        self._store_data_sources(drug_id, data)
        indication_map = self._store_indications(drug_id, data)
        self._store_dosing_regimens(drug_id, data, indication_map)
        self._store_metadata(drug_id, data)

        return drug_id, drug_key

    def _parse_target_and_moa(self, data: ExtractedDrugData) -> Tuple[Optional[str], Optional[str]]:
        """
        Parse molecular target and MoA category from mechanism text.

        Args:
            data: Extracted drug data

        Returns:
            Tuple of (target, moa_category)
        """
        if not self.target_moa_parser or not data.mechanism_of_action:
            return None, None

        try:
            drug_name = data.generic_name or data.brand_name or "unknown"
            result = self.target_moa_parser.parse(
                drug_name=drug_name,
                mechanism_text=data.mechanism_of_action,
                drug_type=data.drug_type
            )
            return result.get("target"), result.get("moa_category")
        except Exception as e:
            logger.warning(f"Failed to parse target/MoA: {e}")
            return None, None

    def _parse_structured_data(self, data: ExtractedDrugData) -> ExtractedDrugData:
        """
        Phase 2: Parse raw text into structured data using Claude.

        This parses:
        - Raw indication text -> structured ParsedIndication records
        - Raw dosing text -> structured ParsedDosingRegimen records
        """
        drug_name = data.generic_name or data.brand_name or "unknown"

        # Parse indications
        if data.indications:
            raw_indication_text = None
            for ind in data.indications:
                if isinstance(ind, dict) and ind.get("raw_text"):
                    raw_indication_text = ind["raw_text"]
                    break

            if raw_indication_text:
                try:
                    parsed_indications = self.indication_parser.parse(raw_indication_text, drug_name)
                    if parsed_indications:
                        # Convert ParsedIndication objects to dicts
                        data.indications = [
                            {
                                "disease_name": pi.disease_name,
                                "population": pi.population,
                                "severity": pi.severity,
                                "line_of_therapy": pi.line_of_therapy,
                                "combination_therapy": pi.combination_therapy,
                                "special_conditions": pi.special_conditions,
                                "mesh_id": pi.mesh_id,
                                "confidence_score": pi.confidence_score,
                            }
                            for pi in parsed_indications
                        ]
                        logger.info(f"Parsed {len(parsed_indications)} indications for {drug_name}")
                except Exception as e:
                    logger.warning(f"Failed to parse indications for {drug_name}: {e}")

        # Parse dosing regimens
        if data.dosing_regimens:
            raw_dosing_text = None
            for dr in data.dosing_regimens:
                if isinstance(dr, dict) and dr.get("raw_text"):
                    raw_dosing_text = dr["raw_text"]
                    break

            if raw_dosing_text:
                try:
                    parsed_dosing = self.dosing_parser.parse(raw_dosing_text, drug_name)
                    if parsed_dosing:
                        # Convert ParsedDosingRegimen objects to dicts
                        data.dosing_regimens = [
                            {
                                "indication_name": pd.indication_name,
                                "dose_amount": pd.dose_amount,
                                "dose_unit": pd.dose_unit,
                                "dose_range_min": pd.dose_range_min,
                                "dose_range_max": pd.dose_range_max,
                                "frequency": pd.frequency,
                                "route": pd.route,
                                "duration": pd.duration,
                                "max_daily_dose": pd.max_daily_dose,
                                "max_daily_dose_unit": pd.max_daily_dose_unit,
                                "population": pd.population,
                                "titration_schedule": pd.titration_schedule,
                                "special_instructions": pd.special_instructions,
                                "formulation": pd.formulation,
                                "confidence_score": pd.confidence_score,
                            }
                            for pd in parsed_dosing
                        ]

                        # Ensure every indication has at least one dosing regimen
                        # If dosing exists but doesn't cover all indications, expand it
                        if data.indications and data.dosing_regimens:
                            data.dosing_regimens = self._expand_dosing_to_indications(
                                data.dosing_regimens, data.indications
                            )

                        logger.info(f"Parsed {len(data.dosing_regimens)} dosing regimens for {drug_name}")
                except Exception as e:
                    logger.warning(f"Failed to parse dosing for {drug_name}: {e}")

        return data

    def _expand_dosing_to_indications(
        self, dosing_regimens: List[dict], indications: List[dict]
    ) -> List[dict]:
        """
        Ensure every indication has at least one dosing regimen.

        If there's a 'General' dosing regimen and indications without specific dosing,
        create copies of the General dosing for those indications.
        """
        if not indications:
            return dosing_regimens

        # Get set of indication names that already have dosing
        indication_names = {ind.get('disease_name', '').lower().strip() for ind in indications}
        covered_indications = set()

        for dr in dosing_regimens:
            ind_name = dr.get('indication_name', '').lower().strip()
            if ind_name and ind_name != 'general':
                covered_indications.add(ind_name)

        # Find uncovered indications
        uncovered = indication_names - covered_indications

        if not uncovered:
            return dosing_regimens

        # Find a template dosing (prefer 'General', otherwise use first)
        template_dosing = None
        for dr in dosing_regimens:
            if dr.get('indication_name', '').lower().strip() == 'general':
                template_dosing = dr
                break

        if not template_dosing and dosing_regimens:
            template_dosing = dosing_regimens[0]

        if not template_dosing:
            return dosing_regimens

        # Create dosing entries for uncovered indications
        expanded_regimens = list(dosing_regimens)
        for ind in indications:
            ind_name = ind.get('disease_name', '').lower().strip()
            if ind_name in uncovered:
                new_regimen = template_dosing.copy()
                new_regimen['indication_name'] = ind.get('disease_name')
                expanded_regimens.append(new_regimen)
                logger.debug(f"Expanded dosing to cover indication: {ind.get('disease_name')}")

        # Remove 'General' entries if we've now covered all indications with specific entries
        final_regimens = [
            dr for dr in expanded_regimens
            if dr.get('indication_name', '').lower().strip() != 'general'
        ]

        return final_regimens if final_regimens else expanded_regimens

    def _store_clinical_trials(self, drug_id: int, data: ExtractedDrugData) -> None:
        """Store clinical trials for a drug and standardize conditions."""
        # Check if ExtractedDrugData has clinical_trials attribute
        trials = getattr(data, 'clinical_trials', [])
        if not trials:
            return

        logger.info(f"Storing {len(trials)} clinical trials for drug_id={drug_id}")

        trial_ids = []  # Track inserted trial IDs for condition standardization

        try:
            with self.db.cursor() as cur:
                for trial in trials:
                    cur.execute("""
                        INSERT INTO drug_clinical_trials (
                            drug_id, nct_id, trial_title, trial_phase,
                            trial_status, conditions, sponsors
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (drug_id, nct_id) DO UPDATE SET
                            trial_title = EXCLUDED.trial_title,
                            trial_phase = EXCLUDED.trial_phase,
                            trial_status = EXCLUDED.trial_status,
                            conditions = EXCLUDED.conditions,
                            sponsors = EXCLUDED.sponsors,
                            updated_at = CURRENT_TIMESTAMP
                        RETURNING trial_id
                    """, (
                        drug_id,
                        trial.get('nct_id'),
                        trial.get('title'),
                        trial.get('phase'),
                        trial.get('status'),
                        Json(trial.get('conditions', [])) if trial.get('conditions') else None,
                        Json(trial.get('sponsors', [])) if trial.get('sponsors') else None
                    ))
                    result = cur.fetchone()
                    if result:
                        trial_ids.append((result[0], trial.get('conditions', [])))

                self.db.commit()
                logger.info(f"Stored {len(trials)} clinical trials for drug_id={drug_id}")

            # Standardize conditions for all stored trials
            self._standardize_trial_conditions(trial_ids)

        except Exception as e:
            logger.warning(f"Failed to store clinical trials: {e}")
            self.db.rollback()

    def _standardize_trial_conditions(self, trial_data: List[Tuple[int, List[str]]]) -> None:
        """
        Standardize conditions for stored trials.

        Args:
            trial_data: List of (trial_id, conditions) tuples
        """
        if not trial_data:
            return

        try:
            from src.drug_extraction_system.services.condition_standardizer import ConditionStandardizer
            standardizer = ConditionStandardizer(self.db)

            total_mapped = 0
            for trial_id, conditions in trial_data:
                if conditions:
                    results = standardizer.standardize_trial_conditions(trial_id, conditions)
                    total_mapped += len([r for r in results if r.get('confidence', 0) > 0])

            if total_mapped > 0:
                logger.info(f"Standardized {total_mapped} trial conditions")
            else:
                logger.debug("No conditions were standardized (may need MeSH lookup)")

        except Exception as e:
            logger.warning(f"Failed to standardize trial conditions: {e}")

    def _store_data_sources(self, drug_id: int, data: ExtractedDrugData) -> None:
        """Store data sources for a drug."""
        if not data.data_sources:
            return

        try:
            with self.db.cursor() as cur:
                for source_name in data.data_sources:
                    cur.execute("""
                        INSERT INTO drug_data_sources (drug_id, source_name)
                        VALUES (%s, %s)
                        ON CONFLICT (drug_id, source_name) DO UPDATE SET
                            data_retrieved_at = CURRENT_TIMESTAMP
                    """, (drug_id, source_name))
                self.db.commit()
                logger.info(f"Stored {len(data.data_sources)} data sources for drug_id={drug_id}")
        except Exception as e:
            logger.warning(f"Failed to store data sources: {e}")
            self.db.rollback()

    def _extract_approval_dates(self, data: ExtractedDrugData, indications: List[Dict]) -> Dict[str, Dict]:
        """
        Extract approval dates for indications using hybrid approach.

        Args:
            data: Extracted drug data containing brand_name and dailymed_setid
            indications: List of indication dictionaries with disease_name

        Returns:
            Dictionary mapping disease_name (lowercase) to approval info:
            {
                "rheumatoid arthritis": {
                    "year": 2002,
                    "date": "2002-12-31",
                    "source": "Drugs.com"
                },
                ...
            }
        """
        # Skip if approval date extractor is not available
        if not APPROVAL_DATE_EXTRACTOR_AVAILABLE:
            logger.debug("Approval date extraction skipped (module not available)")
            return {}

        if not indications:
            return {}

        # Extract indication names
        indication_names = [ind.get('disease_name') for ind in indications if ind.get('disease_name')]
        if not indication_names:
            return {}

        # Use brand name for Drugs.com lookup (more reliable than generic)
        drug_name = data.brand_name or data.generic_name
        if not drug_name:
            logger.warning("No drug name available for approval date extraction")
            return {}

        # Get DailyMed label XML if available (for AI agent fallback)
        label_xml = None
        if data.dailymed_setid:
            try:
                from src.tools.dailymed import DailyMedAPI
                dailymed = DailyMedAPI()
                label_data = dailymed.get_drug_label(data.dailymed_setid)
                if label_data:
                    label_xml = label_data.get('label_xml')
            except Exception as e:
                logger.debug(f"Could not fetch DailyMed label for approval dates: {e}")

        # Extract approval dates using hybrid approach
        try:
            extractor = ApprovalDateExtractor(
                use_scraper=True,
                use_ai_agent=True
            )
            approval_dates = extractor.get_approval_dates(
                drug_name=drug_name,
                indications=indication_names,
                label_xml=label_xml
            )

            # Convert to lowercase keys for matching
            result = {}
            for indication, info in approval_dates.items():
                result[indication.lower().strip()] = info

            return result

        except Exception as e:
            logger.warning(f"Failed to extract approval dates for {drug_name}: {e}")
            return {}

    def _store_indications(self, drug_id: int, data: ExtractedDrugData) -> dict:
        """
        Store parsed indications for a drug.

        Returns:
            Dictionary mapping disease_name (lowercase) to indication_id for linking dosing regimens
        """
        indications = getattr(data, 'indications', [])
        if not indications:
            return {}

        # Skip if only raw text (not parsed)
        if len(indications) == 1 and indications[0].get('raw_text'):
            return {}

        # Determine default approval status from drug's status
        default_approval_status = 'approved'
        if data.approval_status in ('investigational', 'pipeline'):
            default_approval_status = 'investigational'

        # Extract approval dates for indications (only for approved drugs)
        approval_dates = {}
        if default_approval_status == 'approved':
            approval_dates = self._extract_approval_dates(data, indications)

        indication_map = {}  # Map disease_name -> indication_id

        try:
            with self.db.cursor() as cur:
                # First, delete existing indications for this drug
                cur.execute("DELETE FROM drug_indications WHERE drug_id = %s", (drug_id,))

                for ind in indications:
                    if not ind.get('disease_name'):
                        continue

                    # Use indication-specific status or default to drug's status
                    ind_status = ind.get('approval_status', default_approval_status)

                    # Get approval date for this indication
                    disease_name_lower = ind.get('disease_name', '').lower().strip()
                    approval_info = approval_dates.get(disease_name_lower, {})
                    approval_date = approval_info.get('date')

                    cur.execute("""
                        INSERT INTO drug_indications (
                            drug_id, disease_name, population, severity,
                            line_of_therapy, combination_therapy, special_conditions,
                            mesh_id, confidence_score, approval_status, approval_date, data_source
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING indication_id
                    """, (
                        drug_id,
                        ind.get('disease_name'),
                        ind.get('population') or '',
                        ind.get('severity'),
                        ind.get('line_of_therapy'),
                        ind.get('combination_therapy'),
                        ind.get('special_conditions'),
                        ind.get('mesh_id'),
                        ind.get('confidence_score', 0.0),
                        ind_status,
                        approval_date,
                        ind.get('source') or ind.get('data_source')
                    ))

                    # Get the inserted indication_id and map it
                    result = cur.fetchone()
                    indication_id = result['indication_id']
                    if disease_name_lower:
                        indication_map[disease_name_lower] = indication_id

                self.db.commit()
                dates_found = sum(1 for info in approval_dates.values() if info.get('date'))
                logger.info(f"Stored {len(indications)} indications for drug_id={drug_id} ({dates_found} with approval dates)")
                return indication_map
        except Exception as e:
            logger.warning(f"Failed to store indications: {e}", exc_info=True)
            self.db.rollback()
            return {}

        return indication_map

    def _store_dosing_regimens(self, drug_id: int, data: ExtractedDrugData, indication_map: dict = None) -> None:
        """
        Store parsed dosing regimens for a drug.

        Args:
            drug_id: Database ID of the drug
            data: Extracted drug data containing dosing regimens
            indication_map: Dictionary mapping disease_name (lowercase) to indication_id
        """
        regimens = getattr(data, 'dosing_regimens', [])
        if not regimens:
            return

        # Skip if only raw text (not parsed)
        if len(regimens) == 1 and regimens[0].get('raw_text'):
            return

        if indication_map is None:
            indication_map = {}

        try:
            with self.db.cursor() as cur:
                # First, delete existing dosing regimens for this drug
                cur.execute("DELETE FROM drug_dosing_regimens WHERE drug_id = %s", (drug_id,))

                for reg in regimens:
                    # Map parsed fields to existing schema
                    # Existing schema: dosing_id, drug_id, indication_id, regimen_phase,
                    # dose_amount, dose_unit, frequency_standard, frequency_raw,
                    # route_standard, route_raw, duration_weeks, weight_based,
                    # sequence_order, dosing_notes, data_source

                    # Build dosing notes from special instructions and titration
                    notes_parts = []
                    if reg.get('special_instructions'):
                        notes_parts.append(reg['special_instructions'])
                    if reg.get('titration_schedule'):
                        notes_parts.append(f"Titration: {reg['titration_schedule']}")
                    if reg.get('formulation'):
                        notes_parts.append(f"Formulation: {reg['formulation']}")
                    dosing_notes = "; ".join(notes_parts) if notes_parts else None

                    # Get population (age group) - stored in dedicated column
                    population = reg.get('population')

                    # Parse duration to weeks if possible
                    duration_weeks = None
                    duration_str = reg.get('duration')
                    if duration_str:
                        import re
                        week_match = re.search(r'(\d+)\s*week', duration_str.lower())
                        if week_match:
                            duration_weeks = int(week_match.group(1))

                    # regimen_phase must be one of: loading, maintenance, single, induction
                    # Default to 'maintenance' for most regimens
                    regimen_phase = 'maintenance'
                    indication_name = reg.get('indication_name', '')
                    if indication_name:
                        indication_lower = indication_name.lower()
                        if 'loading' in indication_lower:
                            regimen_phase = 'loading'
                        elif 'induction' in indication_lower:
                            regimen_phase = 'induction'
                        elif 'single' in indication_lower or 'once' in indication_lower:
                            regimen_phase = 'single'

                    # Match indication_name to indication_id using the map
                    indication_id = None
                    if indication_name:
                        indication_name_lower = indication_name.lower().strip()
                        indication_id = indication_map.get(indication_name_lower)

                        # If no exact match, try fuzzy matching (contains)
                        if not indication_id:
                            for disease_name, ind_id in indication_map.items():
                                if indication_name_lower in disease_name or disease_name in indication_name_lower:
                                    indication_id = ind_id
                                    logger.debug(f"Fuzzy matched '{indication_name}' to '{disease_name}'")
                                    break

                    # Add indication name to notes (only if not linked to indication_id)
                    if indication_name and not indication_id and indication_name not in (dosing_notes or ''):
                        dosing_notes = f"Indication: {indication_name}; {dosing_notes}" if dosing_notes else f"Indication: {indication_name}"

                    # Truncate fields to fit schema constraints
                    dose_unit = (reg.get('dose_unit') or '')[:20]
                    frequency = reg.get('frequency') or ''
                    frequency_standard = frequency[:20]  # varchar(20)
                    route = reg.get('route') or ''
                    route_standard = route[:10]  # varchar(10)

                    cur.execute("""
                        INSERT INTO drug_dosing_regimens (
                            drug_id, indication_id, regimen_phase, dose_amount, dose_unit,
                            frequency_standard, frequency_raw, route_standard, route_raw,
                            duration_weeks, population, dosing_notes, data_source
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        drug_id,
                        indication_id,  # Now properly linked!
                        regimen_phase,
                        reg.get('dose_amount'),
                        dose_unit,
                        frequency_standard,
                        frequency,  # frequency_raw (text, no limit)
                        route_standard,
                        route,  # route_raw (text, no limit)
                        duration_weeks,
                        population,  # Age group (adults, pediatric, etc.)
                        dosing_notes,
                        'claude_parser'
                    ))
                self.db.commit()
                linked_count = sum(1 for reg in regimens if indication_map.get(reg.get('indication_name', '').lower().strip()))
                logger.info(f"Stored {len(regimens)} dosing regimens for drug_id={drug_id} ({linked_count} linked to indications)")
        except Exception as e:
            logger.warning(f"Failed to store dosing regimens: {e}")
            self.db.rollback()

    def _store_metadata(self, drug_id: int, data: ExtractedDrugData) -> None:
        """
        Store drug metadata including black box warnings.

        Args:
            drug_id: Database ID of the drug
            data: Extracted drug data containing dailymed_setid
        """
        # Only extract metadata for approved drugs with DailyMed labels
        if data.approval_status != 'approved' or not data.dailymed_setid:
            return

        try:
            # Check for black box warning in DailyMed label
            has_black_box = False
            if data.dailymed_setid:
                has_black_box = self._check_black_box_warning(data.dailymed_setid)

            # Insert or update metadata
            with self.db.cursor() as cur:
                cur.execute("""
                    INSERT INTO drug_metadata (
                        drug_id, has_black_box_warning
                    ) VALUES (%s, %s)
                    ON CONFLICT (drug_id)
                    DO UPDATE SET
                        has_black_box_warning = EXCLUDED.has_black_box_warning,
                        updated_at = CURRENT_TIMESTAMP
                """, (drug_id, has_black_box))
                self.db.commit()

                if has_black_box:
                    logger.info(f"Stored metadata for drug_id={drug_id} (BLACK BOX WARNING detected)")
                else:
                    logger.info(f"Stored metadata for drug_id={drug_id} (no black box warning)")
        except Exception as e:
            logger.warning(f"Failed to store metadata: {e}")
            self.db.rollback()

    def _check_black_box_warning(self, dailymed_setid: str) -> bool:
        """
        Check if drug has a black box warning (boxed warning).

        DailyMed section code for boxed warnings: 34066-1

        Args:
            dailymed_setid: DailyMed Set ID

        Returns:
            True if black box warning exists, False otherwise
        """
        try:
            from src.tools.dailymed import DailyMedAPI
            import xml.etree.ElementTree as ET

            dailymed = DailyMedAPI()
            label_data = dailymed.get_drug_label(dailymed_setid)

            if not label_data or not label_data.get('label_xml'):
                return False

            label_xml = label_data['label_xml']
            root = ET.fromstring(label_xml)

            # Look for boxed warning section (code 34066-1)
            # DailyMed uses HL7 v3 namespace
            namespaces = {'hl7': 'urn:hl7-org:v3'}

            for section in root.findall('.//hl7:section', namespaces):
                code = section.find('.//hl7:code', namespaces)
                if code is not None and code.get('code') == '34066-1':
                    logger.info(f"Black box warning section found for setid={dailymed_setid}")
                    return True

            # Also try without namespace (some labels may not use it)
            for section in root.findall('.//section'):
                code = section.find('.//code')
                if code is not None and code.get('code') == '34066-1':
                    logger.info(f"Black box warning section found for setid={dailymed_setid}")
                    return True

            return False

        except Exception as e:
            logger.debug(f"Error checking black box warning for setid={dailymed_setid}: {e}")
            return False
