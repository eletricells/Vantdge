"""
ComprehensiveExtractor Service

Multi-stage LLM pipeline for extracting comprehensive efficacy data from trials.
Extracts trial metadata, baseline characteristics, and all efficacy endpoints.
"""

import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import anthropic

from src.utils.config import get_settings

from src.efficacy_comparison.models import (
    ApprovedDrug,
    BaselineCharacteristics,
    DataSourceType,
    EfficacyEndpoint,
    EndpointCategory,
    PivotalTrial,
    PriorTreatment,
    RaceBreakdown,
    ResolvedDataSource,
    SeverityScore,
    TrialArm,
    TrialExtraction,
    TrialMetadata,
)
from src.efficacy_comparison.prompts.extraction_prompts import (
    build_baseline_extraction_prompt,
    build_efficacy_extraction_prompt,
    build_trial_metadata_prompt,
    BASELINE_SYSTEM_PROMPT,
    EFFICACY_SYSTEM_PROMPT,
    TRIAL_METADATA_SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)


# Model configuration
EXTRACTION_MODEL = "claude-sonnet-4-20250514"  # Use Sonnet for extraction
MAX_CONTENT_LENGTH = 80000  # Max characters to send to LLM


class ComprehensiveExtractor:
    """
    Multi-stage LLM extractor for comprehensive efficacy data.

    Stages:
    1. Trial Metadata - Extract trial info, arms, sample sizes
    2. Baseline Characteristics - Extract demographics, disease severity per arm
    3. Efficacy Endpoints - Extract ALL endpoints at ALL timepoints

    Uses Claude with extended thinking for complex extraction tasks.
    """

    def __init__(
        self,
        anthropic_client: Optional[anthropic.Anthropic] = None,
        model: str = EXTRACTION_MODEL,
    ):
        """
        Initialize the extractor.

        Args:
            anthropic_client: Optional Anthropic client
            model: Model to use for extraction
        """
        if anthropic_client:
            self.anthropic = anthropic_client
        else:
            settings = get_settings()
            self.anthropic = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.model = model

    async def extract_trial_data(
        self,
        data_source: ResolvedDataSource,
        trial: PivotalTrial,
        drug: ApprovedDrug,
        indication: str,
        expected_endpoints: Optional[List[str]] = None,
    ) -> TrialExtraction:
        """
        Extract comprehensive trial data using multi-stage pipeline.

        Args:
            data_source: Resolved data source with content
            trial: PivotalTrial being extracted
            drug: ApprovedDrug information
            indication: Disease/condition name
            expected_endpoints: Optional list of expected endpoint names

        Returns:
            TrialExtraction with all extracted data
        """
        logger.info(
            f"Starting extraction for {trial.trial_name or trial.nct_id} from {data_source.source_type}"
        )

        # Truncate content if needed
        content = self._truncate_content(data_source.content)

        # Stage 1: Extract trial metadata
        logger.debug("Stage 1: Extracting trial metadata")
        metadata = await self._extract_trial_metadata(
            content, drug, trial, indication
        )

        # Get arm names for subsequent stages
        arm_names = [arm.name for arm in metadata.arms] if metadata.arms else []
        if not arm_names:
            arm_names = ["Treatment", "Placebo"]  # Default arms

        # Stage 2: Extract baseline characteristics
        logger.debug("Stage 2: Extracting baseline characteristics")
        baseline = await self._extract_baseline(
            content, drug, arm_names, indication
        )

        # Stage 3: Extract all efficacy endpoints
        logger.debug("Stage 3: Extracting efficacy endpoints")
        endpoints = await self._extract_efficacy_endpoints(
            content, drug, arm_names, indication, expected_endpoints
        )

        # Create extraction result
        extraction = TrialExtraction(
            metadata=metadata,
            baseline=baseline,
            endpoints=endpoints,
            extraction_timestamp=datetime.now(),
            extraction_confidence=self._calculate_confidence(metadata, baseline, endpoints),
            data_source=data_source,
        )

        logger.info(
            f"Extraction complete: {len(baseline)} arms, {len(endpoints)} endpoints"
        )

        return extraction

    async def _extract_trial_metadata(
        self,
        content: str,
        drug: ApprovedDrug,
        trial: PivotalTrial,
        indication: str,
    ) -> TrialMetadata:
        """
        Stage 1: Extract trial metadata.
        """
        prompt = build_trial_metadata_prompt(
            content=content,
            drug_name=drug.drug_name,
            trial_name=trial.trial_name,
            indication=indication,
        )

        try:
            response = self.anthropic.messages.create(
                model=self.model,
                max_tokens=2000,
                system=TRIAL_METADATA_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

            result = self._parse_json_response(response.content[0].text)

            if not result:
                return self._create_default_metadata(drug, trial, indication)

            # Parse arms
            arms = []
            for arm_data in result.get("arms", []):
                arm = TrialArm(
                    name=arm_data.get("name", "Unknown"),
                    n=arm_data.get("n"),
                    is_active=arm_data.get("is_active", True),
                    dose=arm_data.get("dose"),
                    frequency=arm_data.get("frequency"),
                    route=arm_data.get("route"),
                )
                arms.append(arm)

            return TrialMetadata(
                nct_id=result.get("nct_id") or trial.nct_id,
                trial_name=result.get("trial_name") or trial.trial_name,
                phase=result.get("phase") or trial.phase,
                drug_name=drug.drug_name,
                generic_name=drug.generic_name,
                manufacturer=drug.manufacturer,
                indication_name=indication,
                arms=arms,
                total_enrollment=result.get("total_enrollment"),
                background_therapy=result.get("background_therapy"),
                background_therapy_required=result.get("background_therapy_required", False),
            )

        except Exception as e:
            logger.error(f"Error extracting trial metadata: {e}")
            return self._create_default_metadata(drug, trial, indication)

    async def _extract_baseline(
        self,
        content: str,
        drug: ApprovedDrug,
        arm_names: List[str],
        indication: str,
    ) -> List[BaselineCharacteristics]:
        """
        Stage 2: Extract baseline characteristics.
        """
        prompt = build_baseline_extraction_prompt(
            content=content,
            drug_name=drug.drug_name,
            arms=arm_names,
            indication=indication,
        )

        try:
            response = self.anthropic.messages.create(
                model=self.model,
                max_tokens=4000,
                system=BASELINE_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

            result = self._parse_json_response(response.content[0].text)

            if not result:
                return []

            baselines = []
            for arm_data in result.get("baseline_by_arm", []):
                demographics = arm_data.get("demographics", {})
                race_data = arm_data.get("race", {})
                disease = arm_data.get("disease_characteristics", {})
                prior = arm_data.get("prior_treatments", {})

                # Parse race breakdown
                race = RaceBreakdown(
                    white=race_data.get("white"),
                    black=race_data.get("black"),
                    asian=race_data.get("asian"),
                    hispanic=race_data.get("hispanic"),
                    other=race_data.get("other"),
                )

                # Parse severity scores
                severity_scores = []
                for score_data in arm_data.get("severity_scores", []):
                    score = SeverityScore(
                        name=score_data.get("name", "Unknown"),
                        mean=score_data.get("mean"),
                        median=score_data.get("median"),
                        sd=score_data.get("sd"),
                        distribution=score_data.get("distribution"),
                    )
                    severity_scores.append(score)

                # Parse prior treatments
                prior_treatments = []
                for pt_data in prior.get("details", []):
                    pt = PriorTreatment(
                        treatment=pt_data.get("treatment", "Unknown"),
                        percentage=pt_data.get("pct"),
                    )
                    prior_treatments.append(pt)

                baseline = BaselineCharacteristics(
                    arm_name=arm_data.get("arm_name", "Unknown"),
                    n=arm_data.get("n"),
                    age_mean=demographics.get("age_mean"),
                    age_median=demographics.get("age_median"),
                    age_sd=demographics.get("age_sd"),
                    age_range_min=demographics.get("age_range_min"),
                    age_range_max=demographics.get("age_range_max"),
                    male_pct=demographics.get("male_pct"),
                    female_pct=demographics.get("female_pct"),
                    race=race,
                    disease_duration_mean=disease.get("disease_duration_mean"),
                    disease_duration_median=disease.get("disease_duration_median"),
                    disease_duration_unit=disease.get("disease_duration_unit", "years"),
                    severity_scores=severity_scores,
                    prior_systemic_pct=prior.get("prior_systemic_pct"),
                    prior_biologic_pct=prior.get("prior_biologic_pct"),
                    prior_topical_pct=prior.get("prior_topical_pct"),
                    prior_treatments=prior_treatments,
                    source_table=arm_data.get("source_table"),
                )
                baselines.append(baseline)

            return baselines

        except Exception as e:
            logger.error(f"Error extracting baseline characteristics: {e}")
            return []

    async def _extract_efficacy_endpoints(
        self,
        content: str,
        drug: ApprovedDrug,
        arm_names: List[str],
        indication: str,
        expected_endpoints: Optional[List[str]] = None,
    ) -> List[EfficacyEndpoint]:
        """
        Stage 3: Extract all efficacy endpoints.
        """
        prompt = build_efficacy_extraction_prompt(
            content=content,
            drug_name=drug.drug_name,
            arms=arm_names,
            indication=indication,
            expected_endpoints=expected_endpoints,
        )

        try:
            response = self.anthropic.messages.create(
                model=self.model,
                max_tokens=16000,  # Increased for many endpoints
                system=EFFICACY_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

            result = self._parse_json_response(response.content[0].text)

            if not result:
                return []

            endpoints = []
            for ep_data in result.get("endpoints", []):
                # Parse endpoint category
                category_str = ep_data.get("endpoint_category", "")
                category = None
                if category_str:
                    category_map = {
                        "primary": EndpointCategory.PRIMARY,
                        "secondary": EndpointCategory.SECONDARY,
                        "exploratory": EndpointCategory.EXPLORATORY,
                        "pro": EndpointCategory.PRO,
                        "biomarker": EndpointCategory.BIOMARKER,
                    }
                    category = category_map.get(category_str.lower())

                # Parse p-value to numeric
                p_value_str = ep_data.get("p_value")
                p_value_numeric = self._parse_p_value(p_value_str)

                endpoint = EfficacyEndpoint(
                    endpoint_name_raw=ep_data.get("endpoint_name_raw", "Unknown"),
                    endpoint_category=category,
                    arm_name=ep_data.get("arm_name"),
                    timepoint=ep_data.get("timepoint"),
                    timepoint_weeks=ep_data.get("timepoint_weeks"),
                    n_evaluated=ep_data.get("n_evaluated"),
                    responders_n=ep_data.get("responders_n"),
                    responders_pct=ep_data.get("responders_pct"),
                    mean_value=ep_data.get("mean_value"),
                    median_value=ep_data.get("median_value"),
                    change_from_baseline=ep_data.get("change_from_baseline"),
                    change_from_baseline_pct=ep_data.get("change_from_baseline_pct"),
                    se=ep_data.get("se"),
                    sd=ep_data.get("sd"),
                    ci_lower=ep_data.get("ci_lower"),
                    ci_upper=ep_data.get("ci_upper"),
                    vs_comparator=ep_data.get("vs_comparator"),
                    p_value=p_value_str,
                    p_value_numeric=p_value_numeric,
                    is_statistically_significant=ep_data.get("is_statistically_significant"),
                    source_table=ep_data.get("source_table"),
                    source_text=ep_data.get("source_text"),
                )
                endpoints.append(endpoint)

            return endpoints

        except Exception as e:
            logger.error(f"Error extracting efficacy endpoints: {e}")
            return []

    def _parse_json_response(self, response_text: str) -> Optional[Dict[str, Any]]:
        """
        Parse JSON from LLM response.

        Handles:
        - Markdown code blocks
        - Trailing text
        - Truncated JSON
        """
        text = response_text.strip()

        # Remove markdown code blocks
        if text.startswith("```"):
            text = re.sub(r"```json?\n?", "", text)
            text = text.rstrip("`").strip()

        # Try to find JSON object
        try:
            # First try direct parse
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try to extract JSON object
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        # Try to repair truncated JSON
        try:
            repaired = self._repair_truncated_json(text)
            if repaired:
                return json.loads(repaired)
        except:
            pass

        logger.warning(f"Failed to parse JSON response: {text[:200]}...")
        return None

    def _repair_truncated_json(self, text: str) -> Optional[str]:
        """
        Attempt to repair truncated JSON by adding missing brackets.
        """
        # Count brackets
        open_braces = text.count('{')
        close_braces = text.count('}')
        open_brackets = text.count('[')
        close_brackets = text.count(']')

        # Add missing closing brackets/braces
        if open_braces > close_braces:
            text += '}' * (open_braces - close_braces)
        if open_brackets > close_brackets:
            text += ']' * (open_brackets - close_brackets)

        return text

    def _parse_p_value(self, p_value_str: Optional[str]) -> Optional[float]:
        """
        Parse p-value string to numeric.

        Handles formats like: "<0.001", "0.03", "NS", "p<0.05"
        """
        if not p_value_str:
            return None

        p_str = p_value_str.lower().strip()

        # Handle "NS" (not significant)
        if p_str in ["ns", "not significant", "n.s."]:
            return 0.999  # Represents not significant

        # Remove "p=" or "p<" prefix
        p_str = re.sub(r'^p\s*[=<>]\s*', '', p_str)

        # Handle "<" values
        if p_str.startswith('<'):
            try:
                return float(p_str[1:].strip())
            except:
                pass

        # Handle ">" values
        if p_str.startswith('>'):
            try:
                return float(p_str[1:].strip()) + 0.001
            except:
                pass

        # Direct numeric
        try:
            return float(p_str)
        except:
            pass

        return None

    def _truncate_content(self, content: str) -> str:
        """Truncate content to fit within token limits."""
        if len(content) <= MAX_CONTENT_LENGTH:
            return content

        logger.warning(f"Truncating content from {len(content)} to {MAX_CONTENT_LENGTH} chars")

        # Try to truncate at a reasonable point
        truncated = content[:MAX_CONTENT_LENGTH]

        # Find last complete paragraph or section
        last_para = truncated.rfind('\n\n')
        if last_para > MAX_CONTENT_LENGTH * 0.8:
            truncated = truncated[:last_para]

        return truncated + "\n\n[Content truncated]"

    def _calculate_confidence(
        self,
        metadata: TrialMetadata,
        baseline: List[BaselineCharacteristics],
        endpoints: List[EfficacyEndpoint],
    ) -> float:
        """Calculate overall extraction confidence."""
        score = 0.0
        max_score = 0.0

        # Metadata completeness
        max_score += 5
        if metadata.trial_name:
            score += 1
        if metadata.nct_id:
            score += 1
        if metadata.phase:
            score += 1
        if metadata.arms:
            score += 1
        if metadata.total_enrollment:
            score += 1

        # Baseline completeness
        max_score += 3
        if baseline:
            score += 1
            if any(b.age_mean or b.age_median for b in baseline):
                score += 1
            if any(b.severity_scores for b in baseline):
                score += 1

        # Endpoint completeness
        max_score += 4
        if endpoints:
            score += 1
            primary_endpoints = [e for e in endpoints if e.endpoint_category == EndpointCategory.PRIMARY]
            if primary_endpoints:
                score += 1
            if any(e.p_value for e in endpoints):
                score += 1
            if len(endpoints) >= 3:
                score += 1

        return score / max_score if max_score > 0 else 0.0

    def _create_default_metadata(
        self,
        drug: ApprovedDrug,
        trial: PivotalTrial,
        indication: str,
    ) -> TrialMetadata:
        """Create default metadata when extraction fails."""
        return TrialMetadata(
            nct_id=trial.nct_id,
            trial_name=trial.trial_name,
            phase=trial.phase,
            drug_name=drug.drug_name,
            generic_name=drug.generic_name,
            manufacturer=drug.manufacturer,
            indication_name=indication,
            arms=[],
            total_enrollment=trial.enrollment,
        )
