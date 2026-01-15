"""
AI Agent for Approval Date Extraction

Uses Claude to extract FDA approval years from drug labels when
Drugs.com scraping fails or returns incomplete data.
"""
import json
import logging
import os
import re
from typing import Dict, List, Optional
from anthropic import Anthropic

logger = logging.getLogger(__name__)


class ApprovalDateAgent:
    """
    AI agent for extracting approval dates from FDA drug labels.

    Uses Claude to analyze label XML and extract approval years
    for each indication when structured data is not available.
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize approval date agent.

        Args:
            api_key: Anthropic API key (defaults to environment variable)
        """
        if not api_key:
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY environment variable not set")

        self.client = Anthropic(api_key=api_key)
        self.model = "claude-sonnet-4-20250514"

    def extract_approval_dates(
        self,
        label_xml: str,
        indications: List[str],
        drug_name: str
    ) -> Dict[str, Dict]:
        """
        Extract approval dates for indications from label XML.

        Args:
            label_xml: Full DailyMed label XML content
            indications: List of indication names to find dates for
            drug_name: Drug brand name

        Returns:
            Dictionary mapping indication names to approval data:
            {
                "rheumatoid arthritis": {
                    "year": 2002,
                    "date": "2002-12-31",  # If available
                    "confidence": "high",
                    "source_text": "snippet from label"
                },
                ...
            }
        """
        logger.info(f"Extracting approval dates for {drug_name} using AI agent")

        # Limit label size to avoid token limits
        label_excerpt = self._extract_relevant_sections(label_xml)

        # Create prompt
        prompt = self._create_extraction_prompt(
            drug_name=drug_name,
            label_excerpt=label_excerpt,
            indications=indications
        )

        try:
            # Call Claude
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4000,
                temperature=0,  # Deterministic for extraction
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )

            # Parse response
            result = self._parse_response(response.content[0].text, indications)

            logger.info(f"AI agent extracted dates for {len(result)} indications")
            return result

        except Exception as e:
            logger.error(f"AI agent extraction failed: {e}")
            return {}

    def _extract_relevant_sections(self, label_xml: str, max_chars: int = 20000) -> str:
        """
        Extract relevant sections from label to stay within token limits.

        Prioritizes:
        1. Indications and Usage section
        2. Clinical Studies section
        3. Description section

        Args:
            label_xml: Full label XML
            max_chars: Maximum characters to extract

        Returns:
            Relevant label excerpt
        """
        # Extract key sections using regex
        sections_to_extract = [
            r'<section>.*?<code code="34067-9".*?</section>',  # Indications and Usage
            r'<section>.*?<code code="34092-7".*?</section>',  # Clinical Studies
            r'<section>.*?<code code="34089-3".*?</section>',  # Description
        ]

        excerpts = []
        total_length = 0

        for section_pattern in sections_to_extract:
            matches = re.findall(section_pattern, label_xml, re.DOTALL | re.IGNORECASE)

            for match in matches:
                if total_length + len(match) > max_chars:
                    break
                excerpts.append(match)
                total_length += len(match)

            if total_length >= max_chars:
                break

        if not excerpts:
            # Fallback: take first max_chars
            return label_xml[:max_chars]

        return '\n\n'.join(excerpts)

    def _create_extraction_prompt(
        self,
        drug_name: str,
        label_excerpt: str,
        indications: List[str]
    ) -> str:
        """
        Create extraction prompt for Claude.

        Args:
            drug_name: Drug brand name
            label_excerpt: Relevant label sections
            indications: List of indications to find dates for

        Returns:
            Prompt string
        """
        indications_json = json.dumps(indications, indent=2)

        prompt = f"""Analyze this FDA drug label for {drug_name} and extract approval years for each indication.

**Task:** Find the FDA approval year for each of these indications. Look for:
- Explicit approval dates ("FDA approved on [date]", "approved in [year]")
- Clinical study dates (studies typically complete 1-2 years before approval)
- Indication addition dates (supplemental approvals)
- Any temporal references to when each indication was approved

**Indications to find dates for:**
{indications_json}

**Label excerpt:**
<label>
{label_excerpt}
</label>

**Output format:** Return ONLY valid JSON (no markdown, no code blocks). For each indication, provide:
- "year": YYYY as integer (or null if not found)
- "date": "YYYY-MM-DD" as string (or null if exact date not available)
- "confidence": "high", "medium", or "low"
- "source_text": Brief snippet showing where you found the year (max 100 chars)

**Example output:**
{{
  "rheumatoid arthritis": {{
    "year": 2002,
    "date": "2002-12-31",
    "confidence": "high",
    "source_text": "FDA approved Humira for rheumatoid arthritis in December 2002"
  }},
  "psoriasis": {{
    "year": 2008,
    "date": null,
    "confidence": "medium",
    "source_text": "Plaque psoriasis clinical studies completed in 2007"
  }},
  "unknown indication": {{
    "year": null,
    "date": null,
    "confidence": "low",
    "source_text": "No approval date found in label"
  }}
}}

Return your analysis as JSON now:"""

        return prompt

    def _parse_response(self, response_text: str, indications: List[str]) -> Dict[str, Dict]:
        """
        Parse Claude's JSON response.

        Args:
            response_text: Raw response from Claude
            indications: Original indication list

        Returns:
            Parsed approval date data
        """
        # Remove markdown code blocks if present
        response_text = re.sub(r'```json\s*', '', response_text)
        response_text = re.sub(r'```\s*$', '', response_text)
        response_text = response_text.strip()

        try:
            data = json.loads(response_text)

            # Validate structure
            result = {}
            for indication in indications:
                # Try exact match first
                indication_lower = indication.lower()

                if indication_lower in data:
                    approval_data = data[indication_lower]
                else:
                    # Try fuzzy match
                    matched = False
                    for key in data.keys():
                        if indication_lower in key.lower() or key.lower() in indication_lower:
                            approval_data = data[key]
                            matched = True
                            break

                    if not matched:
                        # Not found, create empty entry
                        approval_data = {
                            "year": None,
                            "date": None,
                            "confidence": "low",
                            "source_text": "AI agent: no data found"
                        }

                # Validate and clean data
                result[indication_lower] = {
                    "year": approval_data.get("year"),
                    "date": approval_data.get("date"),
                    "confidence": approval_data.get("confidence", "low"),
                    "source_text": approval_data.get("source_text", "")[:100]  # Limit length
                }

            return result

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response as JSON: {e}")
            logger.debug(f"Response text: {response_text[:500]}")

            # Return empty results for all indications
            return {
                indication.lower(): {
                    "year": None,
                    "date": None,
                    "confidence": "low",
                    "source_text": f"AI agent: JSON parse error - {e}"
                }
                for indication in indications
            }


# Convenience function
def extract_approval_dates_with_ai(
    label_xml: str,
    indications: List[str],
    drug_name: str
) -> Dict[str, Dict]:
    """
    Convenience function to extract approval dates using AI.

    Args:
        label_xml: DailyMed label XML
        indications: List of indication names
        drug_name: Drug brand name

    Returns:
        Approval date dictionary
    """
    agent = ApprovalDateAgent()
    return agent.extract_approval_dates(label_xml, indications, drug_name)
