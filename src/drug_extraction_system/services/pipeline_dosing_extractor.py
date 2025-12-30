"""
Pipeline Drug Dosing Extractor

Extracts dosing information for investigational drugs using:
1. ClinicalTrials.gov trial details (API)
2. Tavily web search + Claude extraction
3. Trial publication search
"""

import logging
from typing import List, Dict, Optional
from anthropic import Anthropic
import os
import json

logger = logging.getLogger(__name__)


class PipelineDosingExtractor:
    """Extract dosing regimens for pipeline drugs from various sources."""

    def __init__(self):
        """Initialize with Anthropic client."""
        self.anthropic = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    def extract_dosing_for_indication(
        self,
        drug_name: str,
        indication_name: str,
        nct_ids: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        Extract dosing information for a specific drug-indication pair.

        Args:
            drug_name: Generic or brand name of the drug
            indication_name: Disease/condition name
            nct_ids: Optional list of NCT IDs for this indication

        Returns:
            List of dosing regimen dictionaries with structure:
            {
                'dose_amount': '680',
                'dose_unit': 'mg',
                'frequency_raw': 'every 4 weeks',
                'route_raw': 'subcutaneous',
                'population': 'adults',
                'indication_name': indication_name,
                'source': 'web_search',
                'confidence': 0.8
            }
        """
        logger.info(f"Extracting dosing for {drug_name} - {indication_name}")

        dosing_regimens = []

        # Strategy 1: Try ClinicalTrials.gov first if we have NCT IDs
        if nct_ids:
            trial_dosing = self._extract_from_trials(drug_name, indication_name, nct_ids)
            dosing_regimens.extend(trial_dosing)

        # Strategy 2: Tavily web search
        if not dosing_regimens:  # Only if trial search didn't find anything
            web_dosing = self._extract_from_web_search(drug_name, indication_name)
            dosing_regimens.extend(web_dosing)

        return dosing_regimens

    def _extract_from_trials(
        self,
        drug_name: str,
        indication_name: str,
        nct_ids: List[str]
    ) -> List[Dict]:
        """Extract dosing from ClinicalTrials.gov trial details."""
        # TODO: Implement ClinicalTrials.gov detailed extraction
        # This would use the existing ClinicalTrialsClient to get full trial details
        logger.info(f"Searching {len(nct_ids)} trials for dosing information")
        return []

    def _extract_from_web_search(
        self,
        drug_name: str,
        indication_name: str
    ) -> List[Dict]:
        """
        Extract dosing from web search using Tavily + Claude.

        Uses Claude's built-in web search capability (via Tavily).
        """
        search_query = f"{drug_name} {indication_name} dosing clinical trial"

        logger.info(f"Web searching: {search_query}")

        try:
            # Use Claude with web search
            message = self.anthropic.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2000,
                tools=[{
                    "type": "web_search_20250305",
                    "name": "web_search"
                }],
                messages=[{
                    "role": "user",
                    "content": f"""Search the web to find dosing information for {drug_name}
used to treat {indication_name}.

Look for:
- Dose amount and unit (e.g., 680 mg, 200 mg)
- Frequency (e.g., once daily, every 4 weeks, twice daily)
- Route of administration (e.g., subcutaneous, oral, intravenous)
- Population (e.g., adults, pediatric)
- Loading dose vs maintenance dose

Search for clinical trial results, press releases, FDA briefing documents,
or published papers that mention specific dosing regimens.

After searching, extract the dosing information and return it as a JSON array with this structure:
[
  {{
    "dose_amount": "680",
    "dose_unit": "mg",
    "frequency_raw": "every 4 weeks",
    "route_raw": "subcutaneous",
    "population": "adults",
    "regimen_phase": "maintenance",
    "source": "URL or source",
    "confidence": 0.9
  }}
]

If you find multiple dosing regimens (e.g., loading dose and maintenance dose,
or different doses for different populations), include all of them.

Return ONLY the JSON array, no additional text."""
                }]
            )

            # Parse Claude's response
            dosing_regimens = self._parse_claude_response(message, indication_name)
            return dosing_regimens

        except Exception as e:
            logger.error(f"Web search failed: {e}")
            return []

    def _parse_claude_response(
        self,
        message,
        indication_name: str
    ) -> List[Dict]:
        """Parse Claude's response to extract dosing regimens."""
        try:
            # Get the final text response from Claude
            final_text = None
            for block in message.content:
                if block.type == "text":
                    final_text = block.text
                    break

            if not final_text:
                logger.warning("No text response from Claude")
                return []

            # Try to extract JSON from the response
            # Claude might wrap it in markdown code blocks
            json_str = final_text.strip()
            if json_str.startswith("```"):
                # Remove markdown code blocks
                lines = json_str.split("\n")
                json_str = "\n".join(lines[1:-1])  # Remove first and last lines
                json_str = json_str.replace("```json", "").replace("```", "")

            # Parse JSON
            dosing_list = json.loads(json_str)

            # Add indication name to each regimen
            for regimen in dosing_list:
                regimen['indication_name'] = indication_name

            logger.info(f"Extracted {len(dosing_list)} dosing regimens from web search")
            return dosing_list

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from Claude response: {e}")
            logger.debug(f"Response text: {final_text}")
            return []
        except Exception as e:
            logger.error(f"Error parsing Claude response: {e}")
            return []

    def _deduplicate_dosing(self, dosing_regimens: List[Dict]) -> List[Dict]:
        """
        Deduplicate dosing regimens based on key attributes.

        Two regimens are considered duplicates if they have the same:
        - indication_name
        - dose_amount
        - dose_unit
        - route_raw
        - population
        - regimen_phase

        Keeps the regimen with higher confidence.
        """
        if not dosing_regimens:
            return []

        # Group by deduplication key
        from collections import defaultdict
        grouped = defaultdict(list)

        for regimen in dosing_regimens:
            # Create deduplication key
            key = (
                regimen.get('indication_name', ''),
                regimen.get('dose_amount', ''),
                regimen.get('dose_unit', ''),
                regimen.get('route_raw', ''),
                regimen.get('population', ''),
                regimen.get('regimen_phase', '')
            )
            grouped[key].append(regimen)

        # Keep the one with highest confidence from each group
        deduplicated = []
        for key, regimens in grouped.items():
            # Sort by confidence (descending)
            sorted_regimens = sorted(
                regimens,
                key=lambda r: r.get('confidence', 0),
                reverse=True
            )
            # Keep the highest confidence one
            best = sorted_regimens[0]
            deduplicated.append(best)

        logger.info(f"Deduplicated {len(dosing_regimens)} regimens to {len(deduplicated)}")
        return deduplicated

    def extract_all_dosing(
        self,
        drug_name: str,
        indications: List[Dict],
        trials_by_indication: Optional[Dict[str, List[str]]] = None,
        deduplicate: bool = True
    ) -> List[Dict]:
        """
        Extract dosing for all indications of a drug.

        Args:
            drug_name: Drug name
            indications: List of indication dictionaries with 'disease_name'
            trials_by_indication: Optional mapping of indication name to NCT IDs
            deduplicate: If True, remove duplicate regimens (default: True)

        Returns:
            List of all dosing regimens found
        """
        all_dosing = []

        for indication in indications:
            indication_name = indication.get('disease_name')
            if not indication_name:
                continue

            # Get NCT IDs for this indication if available
            nct_ids = None
            if trials_by_indication:
                nct_ids = trials_by_indication.get(indication_name, [])

            # Extract dosing
            dosing_regimens = self.extract_dosing_for_indication(
                drug_name=drug_name,
                indication_name=indication_name,
                nct_ids=nct_ids
            )

            all_dosing.extend(dosing_regimens)

        # Deduplicate if requested
        if deduplicate:
            all_dosing = self._deduplicate_dosing(all_dosing)

        return all_dosing
