"""
Efficacy and Safety Data Extractor

Extracts structured efficacy and safety data from OpenFDA drug labels using Claude API.
"""

import logging
import json
import re
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Any
from anthropic import Anthropic
import os

logger = logging.getLogger(__name__)


@dataclass
class EfficacyResult:
    """Structured efficacy endpoint result."""
    trial_name: str
    endpoint_name: str
    endpoint_type: Optional[str] = None
    drug_arm_name: Optional[str] = None
    drug_arm_n: Optional[int] = None
    drug_arm_result: Optional[float] = None
    drug_arm_result_unit: Optional[str] = None
    comparator_arm_name: Optional[str] = None
    comparator_arm_n: Optional[int] = None
    comparator_arm_result: Optional[float] = None
    p_value: Optional[float] = None
    confidence_interval: Optional[str] = None
    timepoint: Optional[str] = None
    trial_phase: Optional[str] = None
    nct_id: Optional[str] = None
    population: Optional[str] = None
    indication_name: Optional[str] = None
    confidence_score: float = 0.85


@dataclass
class SafetyResult:
    """Structured adverse event result."""
    adverse_event: str
    system_organ_class: Optional[str] = None
    severity: Optional[str] = None
    is_serious: bool = False
    drug_arm_name: Optional[str] = None
    drug_arm_n: Optional[int] = None
    drug_arm_count: Optional[int] = None
    drug_arm_rate: Optional[float] = None
    drug_arm_rate_unit: str = "%"
    comparator_arm_name: Optional[str] = None
    comparator_arm_n: Optional[int] = None
    comparator_arm_count: Optional[int] = None
    comparator_arm_rate: Optional[float] = None
    timepoint: Optional[str] = None
    trial_context: Optional[str] = None
    is_boxed_warning: bool = False
    warning_category: Optional[str] = None
    population: Optional[str] = None
    indication_name: Optional[str] = None
    confidence_score: float = 0.85


class EfficacySafetyExtractor:
    """
    Extract structured efficacy and safety data from FDA drug labels.

    Uses Claude API to parse clinical studies and adverse reactions sections
    into structured data.
    """

    EFFICACY_SYSTEM_PROMPT = """You are a pharmaceutical data extraction specialist.
Extract clinical trial efficacy data from FDA label text and return ONLY valid JSON.

CRITICAL RULES:
1. Return ONLY a JSON array - no text before or after
2. Use double quotes for all strings
3. Use null for missing values (not empty strings or "N/A")
4. Numbers should be unquoted
5. No trailing commas

EXTRACT THESE FIELDS for each efficacy endpoint:
- trial_name: Name of the trial (e.g., "Trial PsO1", "MEASURE 1")
- endpoint_name: Primary/secondary endpoint (e.g., "PASI 75", "ACR20", "IGA 0/1")
- endpoint_type: "primary", "secondary", or "exploratory"
- drug_arm_name: Drug group name (e.g., "COSENTYX 300 mg")
- drug_arm_n: Sample size for drug group
- drug_arm_result: Numeric result (e.g., 81.6 for 81.6%)
- drug_arm_result_unit: Unit (usually "%")
- comparator_arm_name: Comparator group (e.g., "Placebo", "Adalimumab")
- comparator_arm_n: Sample size for comparator
- comparator_arm_result: Numeric result for comparator
- p_value: P-value if available (e.g., 0.001)
- timepoint: Assessment timepoint (e.g., "Week 12", "Week 52")
- trial_phase: Phase of trial (e.g., "Phase 3")
- nct_id: ClinicalTrials.gov ID if mentioned (e.g., "NCT01365455")
- indication_name: Disease/condition being treated

EXACT FORMAT:
[
  {
    "trial_name": "Trial PsO1",
    "endpoint_name": "PASI 75",
    "endpoint_type": "primary",
    "drug_arm_name": "COSENTYX 300 mg",
    "drug_arm_n": 245,
    "drug_arm_result": 81.6,
    "drug_arm_result_unit": "%",
    "comparator_arm_name": "Placebo",
    "comparator_arm_n": 248,
    "comparator_arm_result": 4.5,
    "p_value": null,
    "timepoint": "Week 12",
    "trial_phase": "Phase 3",
    "nct_id": "NCT01365455",
    "indication_name": "Plaque Psoriasis"
  }
]

Extract ALL efficacy endpoints from the text. If a table shows multiple doses and comparators, create separate entries for each."""

    SAFETY_SYSTEM_PROMPT = """You are a pharmaceutical data extraction specialist.
Extract adverse event safety data from FDA label text and return ONLY valid JSON.

CRITICAL RULES:
1. Return ONLY a JSON array - no text before or after
2. Use double quotes for all strings
3. Use null for missing values (not empty strings or "N/A")
4. Numbers should be unquoted
5. No trailing commas

EXTRACT THESE FIELDS for each adverse event:
- adverse_event: Name of adverse event (e.g., "Nasopharyngitis", "Diarrhea")
- system_organ_class: MedDRA SOC if available (e.g., "Infections and infestations")
- severity: "mild", "moderate", "severe", or null
- is_serious: true if listed as serious adverse event, false otherwise
- drug_arm_name: Drug group name (e.g., "COSENTYX 300 mg")
- drug_arm_n: Sample size for drug group
- drug_arm_count: Number of events in drug group
- drug_arm_rate: Incidence rate (e.g., 11.4 for 11.4%)
- drug_arm_rate_unit: Usually "%"
- comparator_arm_name: Comparator group (e.g., "Placebo")
- comparator_arm_n: Sample size for comparator
- comparator_arm_count: Number of events in comparator
- comparator_arm_rate: Incidence rate for comparator
- timepoint: Observation period (e.g., "Week 12", "1 year")
- trial_context: Which trials data is from (e.g., "Pooled from PsO1-PsO4")
- is_boxed_warning: true if part of boxed warning
- warning_category: Category if boxed warning (e.g., "Infections")
- indication_name: Disease/condition

EXACT FORMAT:
[
  {
    "adverse_event": "Nasopharyngitis",
    "system_organ_class": "Infections and infestations",
    "severity": null,
    "is_serious": false,
    "drug_arm_name": "COSENTYX 300 mg",
    "drug_arm_n": 691,
    "drug_arm_count": 79,
    "drug_arm_rate": 11.4,
    "drug_arm_rate_unit": "%",
    "comparator_arm_name": "Placebo",
    "comparator_arm_n": 694,
    "comparator_arm_count": 60,
    "comparator_arm_rate": 8.6,
    "timepoint": "Week 12",
    "trial_context": "Pooled from PsO1, PsO2, PsO3, PsO4",
    "is_boxed_warning": false,
    "warning_category": null,
    "indication_name": "Plaque Psoriasis"
  }
]

Extract ALL adverse events reported in the text. Focus on those with >1% incidence."""

    def __init__(self, anthropic_client: Optional[Anthropic] = None):
        """Initialize with Anthropic client."""
        self.anthropic = anthropic_client or Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    def extract_efficacy(
        self,
        drug_name: str,
        clinical_studies_text: str,
        clinical_studies_tables: Optional[List[str]] = None
    ) -> List[EfficacyResult]:
        """
        Extract efficacy data from clinical studies section.

        Args:
            drug_name: Name of the drug
            clinical_studies_text: Text from clinical_studies field
            clinical_studies_tables: Optional HTML tables from clinical_studies_table field

        Returns:
            List of EfficacyResult dataclasses
        """
        if not clinical_studies_text:
            logger.warning(f"No clinical studies text for {drug_name}")
            return []

        logger.info(f"Extracting efficacy data for {drug_name}")

        # Combine text and tables
        combined_text = clinical_studies_text
        if clinical_studies_tables:
            combined_text += "\n\nCLINICAL STUDIES TABLES:\n"
            for i, table in enumerate(clinical_studies_tables[:5]):  # Limit to first 5 tables
                combined_text += f"\nTable {i+1}:\n{table}\n"

        # Truncate if too long (Claude has context limits)
        max_chars = 25000
        if len(combined_text) > max_chars:
            combined_text = combined_text[:max_chars] + "\n... [truncated]"

        try:
            response = self.anthropic.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4000,
                system=self.EFFICACY_SYSTEM_PROMPT,
                messages=[{
                    "role": "user",
                    "content": f"Drug: {drug_name}\n\nClinical Studies Section:\n{combined_text}"
                }]
            )

            result_text = self._clean_json_response(response.content[0].text)
            parsed_data = self._parse_json_safely(result_text)

            results = []
            for item in parsed_data:
                result = EfficacyResult(
                    trial_name=item.get('trial_name', 'Unknown'),
                    endpoint_name=item.get('endpoint_name', 'Unknown'),
                    endpoint_type=item.get('endpoint_type'),
                    drug_arm_name=item.get('drug_arm_name'),
                    drug_arm_n=self._safe_int(item.get('drug_arm_n')),
                    drug_arm_result=self._safe_float(item.get('drug_arm_result')),
                    drug_arm_result_unit=item.get('drug_arm_result_unit', '%'),
                    comparator_arm_name=item.get('comparator_arm_name'),
                    comparator_arm_n=self._safe_int(item.get('comparator_arm_n')),
                    comparator_arm_result=self._safe_float(item.get('comparator_arm_result')),
                    p_value=self._safe_float(item.get('p_value')),
                    confidence_interval=item.get('confidence_interval'),
                    timepoint=item.get('timepoint'),
                    trial_phase=item.get('trial_phase'),
                    nct_id=item.get('nct_id'),
                    population=item.get('population'),
                    indication_name=item.get('indication_name'),
                    confidence_score=0.85
                )
                results.append(result)

            logger.info(f"Extracted {len(results)} efficacy endpoints for {drug_name}")
            return results

        except Exception as e:
            logger.error(f"Efficacy extraction failed for {drug_name}: {e}")
            return []

    def extract_safety(
        self,
        drug_name: str,
        adverse_reactions_text: str,
        adverse_reactions_tables: Optional[List[str]] = None,
        boxed_warning: Optional[str] = None,
        warnings_and_cautions: Optional[str] = None
    ) -> List[SafetyResult]:
        """
        Extract safety data from adverse reactions section.

        Args:
            drug_name: Name of the drug
            adverse_reactions_text: Text from adverse_reactions field
            adverse_reactions_tables: Optional HTML tables
            boxed_warning: Optional boxed warning text
            warnings_and_cautions: Optional warnings section

        Returns:
            List of SafetyResult dataclasses
        """
        if not adverse_reactions_text:
            logger.warning(f"No adverse reactions text for {drug_name}")
            return []

        logger.info(f"Extracting safety data for {drug_name}")

        # Combine all safety-related text
        combined_text = adverse_reactions_text

        if boxed_warning:
            combined_text = f"BOXED WARNING:\n{boxed_warning}\n\n" + combined_text

        if warnings_and_cautions:
            combined_text += f"\n\nWARNINGS AND PRECAUTIONS:\n{warnings_and_cautions[:3000]}"

        if adverse_reactions_tables:
            combined_text += "\n\nADVERSE REACTIONS TABLES:\n"
            for i, table in enumerate(adverse_reactions_tables[:3]):
                combined_text += f"\nTable {i+1}:\n{table}\n"

        # Truncate if too long
        max_chars = 20000
        if len(combined_text) > max_chars:
            combined_text = combined_text[:max_chars] + "\n... [truncated]"

        try:
            response = self.anthropic.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4000,
                system=self.SAFETY_SYSTEM_PROMPT,
                messages=[{
                    "role": "user",
                    "content": f"Drug: {drug_name}\n\nSafety Information:\n{combined_text}"
                }]
            )

            result_text = self._clean_json_response(response.content[0].text)
            parsed_data = self._parse_json_safely(result_text)

            results = []
            for item in parsed_data:
                result = SafetyResult(
                    adverse_event=item.get('adverse_event', 'Unknown'),
                    system_organ_class=item.get('system_organ_class'),
                    severity=item.get('severity'),
                    is_serious=bool(item.get('is_serious', False)),
                    drug_arm_name=item.get('drug_arm_name'),
                    drug_arm_n=self._safe_int(item.get('drug_arm_n')),
                    drug_arm_count=self._safe_int(item.get('drug_arm_count')),
                    drug_arm_rate=self._safe_float(item.get('drug_arm_rate')),
                    drug_arm_rate_unit=item.get('drug_arm_rate_unit', '%'),
                    comparator_arm_name=item.get('comparator_arm_name'),
                    comparator_arm_n=self._safe_int(item.get('comparator_arm_n')),
                    comparator_arm_count=self._safe_int(item.get('comparator_arm_count')),
                    comparator_arm_rate=self._safe_float(item.get('comparator_arm_rate')),
                    timepoint=item.get('timepoint'),
                    trial_context=item.get('trial_context'),
                    is_boxed_warning=bool(item.get('is_boxed_warning', False)),
                    warning_category=item.get('warning_category'),
                    population=item.get('population'),
                    indication_name=item.get('indication_name'),
                    confidence_score=0.85
                )
                results.append(result)

            logger.info(f"Extracted {len(results)} adverse events for {drug_name}")
            return results

        except Exception as e:
            logger.error(f"Safety extraction failed for {drug_name}: {e}")
            return []

    def extract_from_label(
        self,
        drug_name: str,
        label: Dict[str, Any]
    ) -> tuple[List[EfficacyResult], List[SafetyResult]]:
        """
        Extract both efficacy and safety data from an OpenFDA label.

        Args:
            drug_name: Name of the drug
            label: OpenFDA label dictionary

        Returns:
            Tuple of (efficacy_results, safety_results)
        """
        # Extract efficacy
        clinical_studies = self._get_first(label.get('clinical_studies'))
        clinical_studies_tables = label.get('clinical_studies_table', [])

        efficacy_results = self.extract_efficacy(
            drug_name,
            clinical_studies,
            clinical_studies_tables
        )

        # Extract safety
        adverse_reactions = self._get_first(label.get('adverse_reactions'))
        adverse_reactions_tables = label.get('adverse_reactions_table', [])
        boxed_warning = self._get_first(label.get('boxed_warning'))
        warnings_and_cautions = self._get_first(label.get('warnings_and_cautions'))

        safety_results = self.extract_safety(
            drug_name,
            adverse_reactions,
            adverse_reactions_tables,
            boxed_warning,
            warnings_and_cautions
        )

        return efficacy_results, safety_results

    def _clean_json_response(self, text: str) -> str:
        """Clean JSON response from Claude."""
        text = text.strip()

        # Handle markdown code blocks
        if "```" in text:
            match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text, re.IGNORECASE)
            if match:
                text = match.group(1).strip()

        # Find JSON array boundaries
        start_idx = text.find('[')
        end_idx = text.rfind(']')
        if start_idx != -1 and end_idx != -1:
            text = text[start_idx:end_idx + 1]

        # Fix trailing commas
        text = re.sub(r',\s*]', ']', text)
        text = re.sub(r',\s*}', '}', text)

        return text

    def _parse_json_safely(self, text: str) -> List[Dict]:
        """Parse JSON with error recovery."""
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, list) else [parsed]
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse error: {e}")
            # Try to recover partial JSON
            return self._recover_partial_json(text)

    def _recover_partial_json(self, text: str) -> List[Dict]:
        """Try to recover valid entries from truncated JSON."""
        results = []
        depth = 0
        start_idx = None

        for i, char in enumerate(text):
            if char == '{':
                if depth == 0:
                    start_idx = i
                depth += 1
            elif char == '}':
                depth -= 1
                if depth == 0 and start_idx is not None:
                    try:
                        obj_text = text[start_idx:i+1]
                        obj = json.loads(obj_text)
                        results.append(obj)
                    except json.JSONDecodeError:
                        pass
                    start_idx = None

        logger.info(f"Recovered {len(results)} entries from partial JSON")
        return results

    def _get_first(self, value: Any) -> Optional[str]:
        """Get first element from list or return value as-is."""
        if isinstance(value, list) and value:
            return value[0]
        return value if value else None

    def _safe_float(self, value: Any) -> Optional[float]:
        """Safely convert to float."""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _safe_int(self, value: Any) -> Optional[int]:
        """Safely convert to int."""
        if value is None:
            return None
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return None
