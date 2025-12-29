"""
Data Enricher

Uses Claude API and Tavily Search to fill gaps in drug data.
"""

import os
import json
import logging
from typing import Dict, List, Optional, Any

from src.drug_extraction_system.extractors.approved_drug_extractor import ExtractedDrugData

logger = logging.getLogger(__name__)


class DataEnricher:
    """
    Enriches drug data using AI and web search.
    
    Uses:
    - Claude API: Parse unstructured label text, extract structured data
    - Tavily Search: Fill gaps with web search
    """

    def __init__(
        self,
        claude_model: str = "claude-sonnet-4-5-20250929",
        max_tokens: int = 4000
    ):
        """
        Initialize enricher.

        Args:
            claude_model: Claude model to use
            max_tokens: Max tokens for Claude responses
        """
        self.claude_model = claude_model
        self.max_tokens = max_tokens
        self.anthropic_client = None
        self.tavily_client = None

        # Lazy initialization of clients
        self._init_clients()

    def _init_clients(self):
        """Initialize API clients if keys are available."""
        # Initialize Anthropic client
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        if anthropic_key:
            try:
                import anthropic
                self.anthropic_client = anthropic.Anthropic(api_key=anthropic_key)
                logger.info("Anthropic client initialized")
            except ImportError:
                logger.warning("anthropic package not installed")
            except Exception as e:
                logger.warning(f"Failed to initialize Anthropic client: {e}")

        # Initialize Tavily client
        tavily_key = os.getenv("TAVILY_API_KEY")
        if tavily_key:
            try:
                from tavily import TavilyClient
                self.tavily_client = TavilyClient(api_key=tavily_key)
                logger.info("Tavily client initialized")
            except ImportError:
                logger.warning("tavily package not installed")
            except Exception as e:
                logger.warning(f"Failed to initialize Tavily client: {e}")

    def enrich(self, data: ExtractedDrugData) -> ExtractedDrugData:
        """
        Enrich drug data by filling gaps.

        Args:
            data: ExtractedDrugData to enrich

        Returns:
            Enriched ExtractedDrugData
        """
        logger.info(f"Enriching data for '{data.drug_key}'")

        # Parse indications if we have raw text
        if data.indications and self.anthropic_client:
            for ind in data.indications:
                if "raw_text" in ind and "parsed_indications" not in ind:
                    parsed = self._parse_indications_text(ind["raw_text"])
                    if parsed:
                        ind["parsed_indications"] = parsed

        # Parse dosing if we have raw text
        if data.dosing_regimens and self.anthropic_client:
            for dosing in data.dosing_regimens:
                if "raw_text" in dosing and "parsed_dosing" not in dosing:
                    parsed = self._parse_dosing_text(dosing["raw_text"])
                    if parsed:
                        dosing["parsed_dosing"] = parsed

        # Fill gaps with web search
        if self.tavily_client:
            data = self._fill_gaps_with_search(data)

        # Recalculate completeness
        data.completeness_score = self._recalculate_completeness(data)

        if "enrichment" not in data.data_sources:
            data.data_sources.append("enrichment")

        return data

    def _clean_json_response(self, text: str) -> str:
        """Clean and extract JSON from Claude response."""
        text = text.strip()

        # Remove markdown code blocks
        if "```" in text:
            import re
            match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
            if match:
                text = match.group(1).strip()

        # Find JSON array boundaries
        start_idx = text.find('[')
        end_idx = text.rfind(']')

        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            text = text[start_idx:end_idx + 1]

        return text

    def _parse_indications_text(self, text: str) -> Optional[List[Dict]]:
        """Parse indications from raw label text using Claude."""
        if not self.anthropic_client:
            return None

        prompt = f"""Extract structured indication data from this FDA label text.
Return ONLY a JSON array (start with [ and end with ]).
Each object should have: disease_name, patient_population, line_of_therapy.
Use null for missing values.

Text:
{text[:4000]}"""

        try:
            response = self.anthropic_client.messages.create(
                model=self.claude_model,
                max_tokens=self.max_tokens,
                messages=[{"role": "user", "content": prompt}]
            )
            result = self._clean_json_response(response.content[0].text)
            return json.loads(result)
        except Exception as e:
            logger.warning(f"Failed to parse indications: {e}")
            return None

    def _parse_dosing_text(self, text: str) -> Optional[List[Dict]]:
        """Parse dosing information from raw label text using Claude."""
        if not self.anthropic_client:
            return None

        prompt = f"""Extract structured dosing data from this FDA label text.
Return ONLY a JSON array (start with [ and end with ]).
Each object should have: dose, frequency, route, indication.
Use null for missing values.

Text:
{text[:4000]}"""

        try:
            response = self.anthropic_client.messages.create(
                model=self.claude_model,
                max_tokens=self.max_tokens,
                messages=[{"role": "user", "content": prompt}]
            )
            result = self._clean_json_response(response.content[0].text)
            return json.loads(result)
        except Exception as e:
            logger.warning(f"Failed to parse dosing: {e}")
            return None

    def _fill_gaps_with_search(self, data: ExtractedDrugData) -> ExtractedDrugData:
        """Use Tavily search to fill data gaps."""
        if not self.tavily_client:
            return data

        # Only search if we're missing key data
        missing = []
        if not data.mechanism_of_action:
            missing.append("mechanism of action")
        if not data.manufacturer:
            missing.append("manufacturer")

        if not missing:
            return data

        try:
            query = f"{data.generic_name} drug {' '.join(missing)}"
            results = self.tavily_client.search(query, max_results=3)

            # Extract information from search results using Claude
            if results and self.anthropic_client:
                search_text = "\n\n".join([
                    f"Source: {r.get('url', 'N/A')}\n{r.get('content', '')}"
                    for r in results.get('results', [])
                ])[:4000]

                extracted = self._extract_from_search_results(data.generic_name, search_text, missing)
                if extracted:
                    if not data.mechanism_of_action and extracted.get("mechanism_of_action"):
                        data.mechanism_of_action = extracted["mechanism_of_action"]
                        logger.info(f"Filled mechanism of action from web search: {data.mechanism_of_action}")
                    if not data.manufacturer and extracted.get("manufacturer"):
                        data.manufacturer = extracted["manufacturer"]
                        logger.info(f"Filled manufacturer from web search: {data.manufacturer}")
            else:
                logger.info(f"Tavily search completed for '{data.generic_name}' but no results or Claude unavailable")

        except Exception as e:
            logger.warning(f"Tavily search failed: {e}")

        return data

    def _extract_from_search_results(self, drug_name: str, search_text: str, missing_fields: List[str]) -> Optional[Dict]:
        """Extract missing drug information from search results using Claude."""
        if not self.anthropic_client or not search_text:
            return None

        prompt = f"""Extract the following information about the drug "{drug_name}" from these search results:

Missing fields: {', '.join(missing_fields)}

Search results:
{search_text}

Return ONLY a JSON object (start with {{ and end with }}) with these fields:
- mechanism_of_action: Brief description (1-2 sentences) or null
- manufacturer: Company name or null

Example:
{{"mechanism_of_action": "FcRn inhibitor that reduces pathogenic IgG antibodies", "manufacturer": "Immunovant Sciences GmbH"}}

JSON:"""

        try:
            response = self.anthropic_client.messages.create(
                model=self.claude_model,
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}]
            )
            result = self._clean_json_response(response.content[0].text)
            return json.loads(result)
        except Exception as e:
            logger.warning(f"Failed to extract from search results: {e}")
            return None

    def _recalculate_completeness(self, data: ExtractedDrugData) -> float:
        """Recalculate completeness after enrichment."""
        is_pipeline = data.approval_status in ("pipeline", "investigational")

        # For pipeline drugs, use different weights since dosing data isn't available
        if is_pipeline:
            # Pipeline drugs: core (35%), indications (35%), trials (20%), identifiers (10%)
            scores = {"core": 0.0, "indications": 0.0, "trials": 0.0, "identifiers": 0.0}

            # Core fields (don't penalize for missing brand_name which pipeline drugs rarely have)
            core_fields = ["generic_name", "manufacturer", "mechanism_of_action", "highest_phase"]
            scores["core"] = sum(1 for f in core_fields if getattr(data, f, None)) / len(core_fields)

            # Indications from trials
            has_parsed_ind = any("parsed_indications" in ind for ind in data.indications)
            ind_count = len(data.indications)
            if has_parsed_ind:
                scores["indications"] = 1.0
            elif ind_count >= 3:
                scores["indications"] = 0.8
            elif ind_count >= 1:
                scores["indications"] = 0.6
            else:
                scores["indications"] = 0.0

            # Clinical trials data
            has_trials = bool(data.clinical_trials)
            scores["trials"] = 1.0 if has_trials else 0.0

            # Identifiers (less important for pipeline drugs)
            id_fields = ["rxcui", "unii", "chembl_id", "cas_number"]
            scores["identifiers"] = sum(1 for f in id_fields if getattr(data, f, None)) / len(id_fields)

            return round(scores["core"] * 0.35 + scores["indications"] * 0.35 +
                         scores["trials"] * 0.20 + scores["identifiers"] * 0.10, 4)
        else:
            # Approved drugs: original scoring
            scores = {"core": 0.0, "indications": 0.0, "dosing": 0.0, "identifiers": 0.0}

            core_fields = ["generic_name", "brand_name", "manufacturer", "mechanism_of_action"]
            scores["core"] = sum(1 for f in core_fields if getattr(data, f, None)) / len(core_fields)

            # Check for parsed indications
            has_parsed_ind = any("parsed_indications" in ind for ind in data.indications)
            scores["indications"] = 1.0 if has_parsed_ind else (0.5 if data.indications else 0.0)

            has_parsed_dos = any("parsed_dosing" in d for d in data.dosing_regimens)
            scores["dosing"] = 1.0 if has_parsed_dos else (0.5 if data.dosing_regimens else 0.0)

            id_fields = ["rxcui", "unii", "chembl_id", "cas_number"]
            scores["identifiers"] = sum(1 for f in id_fields if getattr(data, f, None)) / len(id_fields)

            return round(scores["core"] * 0.30 + scores["indications"] * 0.25 +
                         scores["dosing"] * 0.25 + scores["identifiers"] * 0.20, 4)

