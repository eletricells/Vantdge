"""
Indication Parser - Extracts structured indication data from raw text.
"""

import json
import re
from typing import List, Dict, Optional
from dataclasses import dataclass
import logging

from anthropic import Anthropic

from src.drug_extraction_system.config import get_config
from src.drug_extraction_system.api_clients.mesh_client import MeSHClient

logger = logging.getLogger(__name__)


@dataclass
class ParsedIndication:
    """Structured indication data."""
    disease_name: str
    population: Optional[str] = None
    severity: Optional[str] = None
    line_of_therapy: Optional[str] = None
    combination_therapy: Optional[str] = None
    special_conditions: Optional[str] = None
    mesh_id: Optional[str] = None
    confidence_score: float = 0.0


class IndicationParser:
    """Parse raw indication text into structured records using Claude."""

    SYSTEM_PROMPT = """You are a pharmaceutical data extraction specialist. Extract indication data from FDA label text and return ONLY valid JSON.

CRITICAL RULES:
1. Return ONLY a JSON array - no text before or after
2. Use double quotes for all strings
3. Use null for missing values (not empty strings)
4. No trailing commas
5. Maximum 15 indications

EXACT FORMAT - copy this structure:
[
  {
    "disease_name": "rheumatoid arthritis",
    "population": "adults",
    "severity": "moderate to severe",
    "line_of_therapy": null,
    "combination_therapy": null,
    "special_conditions": null
  }
]

Extract these fields (use null if not found):
- disease_name: full disease name (not abbreviations)
- population: patient group (adults, pediatric, etc.)
- severity: disease severity level
- line_of_therapy: first-line, second-line, etc.
- combination_therapy: monotherapy or combination details
- special_conditions: requirements or limitations

Start your response with [ and end with ]"""
    
    def __init__(self, mesh_client: Optional[MeSHClient] = None):
        self.config = get_config()
        self.client = Anthropic()
        self.mesh_client = mesh_client or MeSHClient()

    def _clean_json_response(self, text: str) -> str:
        """Clean and extract JSON from Claude response."""
        text = text.strip()

        # Remove markdown code blocks
        if "```" in text:
            match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
            if match:
                text = match.group(1).strip()

        # Find JSON array boundaries
        start_idx = text.find('[')
        end_idx = text.rfind(']')

        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            text = text[start_idx:end_idx + 1]

        # Fix common JSON issues
        text = re.sub(r',\s*]', ']', text)  # Remove trailing commas before ]
        text = re.sub(r',\s*}', '}', text)  # Remove trailing commas before }

        return text

    def parse(self, raw_text: str, drug_name: str) -> List[ParsedIndication]:
        """Parse raw indication text into structured records."""
        if not raw_text or len(raw_text.strip()) < 10:
            logger.warning(f"Empty or too short indication text for {drug_name}")
            return []

        # Truncate if too long
        max_chars = 8000
        if len(raw_text) > max_chars:
            raw_text = raw_text[:max_chars] + "..."
            logger.info(f"Truncated indication text for {drug_name}")

        try:
            logger.info(f"Calling Claude to parse indications for {drug_name}")
            response = self.client.messages.create(
                model=self.config.api.claude_model,
                max_tokens=2000,
                system=self.SYSTEM_PROMPT,
                messages=[{
                    "role": "user",
                    "content": f"Drug: {drug_name}\n\nIndications text:\n{raw_text}"
                }]
            )

            if not response.content:
                logger.warning(f"Empty response from Claude for {drug_name}")
                return []

            result_text = self._clean_json_response(response.content[0].text)
            logger.debug(f"Cleaned JSON for {drug_name}: {result_text[:300]}...")

            try:
                parsed_data = json.loads(result_text)
            except json.JSONDecodeError as e:
                logger.warning(f"JSON decode error for {drug_name}: {e}")
                logger.debug(f"Failed JSON: {result_text[:500]}...")
                return []
            
            if not isinstance(parsed_data, list):
                parsed_data = [parsed_data]
            
            # Convert to dataclass objects and enrich with MeSH IDs
            indications = []
            for item in parsed_data:
                indication = ParsedIndication(
                    disease_name=item.get('disease_name', '').strip(),
                    population=item.get('population'),
                    severity=item.get('severity'),
                    line_of_therapy=item.get('line_of_therapy'),
                    combination_therapy=item.get('combination_therapy'),
                    special_conditions=item.get('special_conditions'),
                    confidence_score=0.85  # Default confidence for Claude parsing
                )
                
                # Skip empty disease names
                if not indication.disease_name:
                    continue
                
                # Enrich with MeSH ID
                mesh_result = self.mesh_client.standardize_disease_name(indication.disease_name)
                if mesh_result:
                    indication.mesh_id = mesh_result.get('mesh_id')
                    indication.confidence_score = 0.95  # Higher confidence with MeSH match
                
                indications.append(indication)
            
            # Deduplicate
            indications = self._deduplicate(indications)
            
            logger.info(f"Parsed {len(indications)} indications for {drug_name}")
            return indications
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Claude response as JSON for {drug_name}: {e}")
            return []
        except Exception as e:
            logger.error(f"Indication parsing failed for {drug_name}: {e}")
            return []
    
    def _deduplicate(self, indications: List[ParsedIndication]) -> List[ParsedIndication]:
        """Remove duplicate indications based on disease + population."""
        seen = set()
        unique = []
        for ind in indications:
            key = (ind.disease_name.lower(), (ind.population or '').lower())
            if key not in seen:
                seen.add(key)
                unique.append(ind)
        return unique

