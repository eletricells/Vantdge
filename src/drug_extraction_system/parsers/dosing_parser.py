"""
Dosing Parser - Extracts structured dosing regimen data from raw text.
"""

import json
import re
from typing import List, Optional
from dataclasses import dataclass
import logging

from anthropic import Anthropic

from src.drug_extraction_system.config import get_config

logger = logging.getLogger(__name__)


@dataclass
class ParsedDosingRegimen:
    """Structured dosing regimen data."""
    indication_name: str
    dose_amount: Optional[float] = None
    dose_unit: Optional[str] = None
    dose_range_min: Optional[float] = None
    dose_range_max: Optional[float] = None
    frequency: Optional[str] = None
    route: Optional[str] = None
    duration: Optional[str] = None
    max_daily_dose: Optional[float] = None
    max_daily_dose_unit: Optional[str] = None
    population: Optional[str] = None
    titration_schedule: Optional[str] = None
    special_instructions: Optional[str] = None
    formulation: Optional[str] = None
    confidence_score: float = 0.0


class DosingParser:
    """Parse raw dosing text into structured regimens using Claude."""

    SYSTEM_PROMPT = """You are a pharmaceutical data extraction specialist. Extract dosing regimen data from FDA label text and return ONLY valid JSON.

CRITICAL RULES:
1. Return ONLY a JSON array - no text before or after
2. Use double quotes for all strings
3. Use null for missing values (not empty strings)
4. Numbers should be unquoted
5. No trailing commas
6. IMPORTANT: Create a SEPARATE entry for EACH indication/disease, even if the dosing is the same
   - If a drug has 3 approved indications and uses the same dose for all, return 3 entries (one per indication)
   - Each indication must have its own dosing entry

EXACT FORMAT - copy this structure:
[
  {
    "indication_name": "condition name",
    "dose_amount": 15,
    "dose_unit": "mg",
    "frequency": "once daily",
    "route": "oral",
    "population": "adults",
    "formulation": "tablet",
    "special_instructions": null
  }
]

Extract these fields (use null if not found):
- indication_name: the specific condition/disease being treated (e.g., "plaque psoriasis", "rheumatoid arthritis")
- dose_amount: numeric dose value
- dose_unit: mg, mcg, mL, units
- frequency: once daily, twice daily, every 12 hours
- route: oral, IV, subcutaneous
- population: adults, pediatric, etc.
- formulation: tablet, capsule, solution
- special_instructions: food/timing requirements

Start your response with [ and end with ]"""
    
    def __init__(self):
        self.config = get_config()
        self.client = Anthropic()

    def _clean_json_response(self, text: str) -> str:
        """Clean and extract JSON from Claude response."""
        text = text.strip()

        # Remove markdown code blocks - handle various formats
        # First try to extract content between code fences
        if "```" in text:
            # Try to find json code block first
            match = re.search(r'```json\s*([\s\S]*?)\s*```', text, re.IGNORECASE)
            if match:
                text = match.group(1).strip()
            else:
                # Try generic code block
                match = re.search(r'```\s*([\s\S]*?)\s*```', text)
                if match:
                    text = match.group(1).strip()
                else:
                    # Just strip the backticks if they exist at start/end
                    text = re.sub(r'^```(?:json)?\s*', '', text)
                    text = re.sub(r'\s*```$', '', text)

        # Find JSON array boundaries
        start_idx = text.find('[')
        end_idx = text.rfind(']')

        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            text = text[start_idx:end_idx + 1]

        # Fix common JSON issues
        text = re.sub(r',\s*]', ']', text)  # Remove trailing commas before ]
        text = re.sub(r',\s*}', '}', text)  # Remove trailing commas before }

        return text

    def parse(self, raw_text: str, drug_name: str) -> List[ParsedDosingRegimen]:
        """Parse raw dosing text into structured regimens."""
        if not raw_text or len(raw_text.strip()) < 10:
            return []

        # Truncate if needed
        max_chars = 10000
        if len(raw_text) > max_chars:
            raw_text = raw_text[:max_chars] + "..."

        try:
            logger.info(f"Calling Claude to parse dosing for {drug_name}")
            response = self.client.messages.create(
                model=self.config.api.claude_model,
                max_tokens=4000,
                system=self.SYSTEM_PROMPT,
                messages=[{
                    "role": "user",
                    "content": f"Drug: {drug_name}\n\nDosing text:\n{raw_text}"
                }]
            )

            if not response.content:
                logger.warning(f"Empty response from Claude for {drug_name}")
                return []

            # Check for truncation
            if response.stop_reason == "max_tokens":
                logger.warning(f"Response truncated for {drug_name} - trying to recover")

            result_text = self._clean_json_response(response.content[0].text)
            logger.debug(f"Cleaned JSON for {drug_name}: {result_text[:300]}...")

            try:
                parsed_data = json.loads(result_text)
            except json.JSONDecodeError as e:
                logger.warning(f"JSON decode error for {drug_name}: {e}")
                # Try to recover partial JSON by finding valid complete entries
                parsed_data = self._recover_partial_json(result_text)
                if not parsed_data:
                    logger.debug(f"Failed JSON: {result_text[:500]}...")
                    return []
                logger.info(f"Recovered {len(parsed_data)} dosing entries from partial JSON")
            
            if not isinstance(parsed_data, list):
                parsed_data = [parsed_data]
            
            regimens = []
            for item in parsed_data:
                regimen = ParsedDosingRegimen(
                    indication_name=item.get('indication_name', 'General'),
                    dose_amount=self._safe_float(item.get('dose_amount')),
                    dose_unit=item.get('dose_unit'),
                    dose_range_min=self._safe_float(item.get('dose_range_min')),
                    dose_range_max=self._safe_float(item.get('dose_range_max')),
                    frequency=item.get('frequency'),
                    route=item.get('route'),
                    duration=item.get('duration'),
                    max_daily_dose=self._safe_float(item.get('max_daily_dose')),
                    max_daily_dose_unit=item.get('max_daily_dose_unit'),
                    population=item.get('population'),
                    titration_schedule=item.get('titration_schedule'),
                    special_instructions=item.get('special_instructions'),
                    formulation=item.get('formulation'),
                    confidence_score=0.85
                )
                regimens.append(regimen)
            
            logger.info(f"Parsed {len(regimens)} dosing regimens for {drug_name}")
            return regimens
            
        except Exception as e:
            logger.error(f"Dosing parsing failed for {drug_name}: {e}")
            return []
    
    def _safe_float(self, value) -> Optional[float]:
        """Safely convert value to float."""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _recover_partial_json(self, text: str) -> List[dict]:
        """Try to recover valid entries from truncated or malformed JSON array."""
        results = []

        # Find all complete JSON objects in the text
        # Look for pattern: { ... }
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

        return results
