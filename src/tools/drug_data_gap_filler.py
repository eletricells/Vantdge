"""
Unified Drug Data Gap Filler

Makes ONE AI agent call to fill ALL data gaps after exhausting API/scraping sources.

Fills gaps for:
- Mechanism of action (when NULL)
- Approval years for indications (when missing from Drugs.com)
- Complex dosing interpretations (when regex parsing fails)
- Any other structured data that couldn't be extracted

NEW: Web search fallback when label extraction fails
"""
import json
import logging
import re
from typing import Dict, List, Optional
from anthropic import Anthropic

from src.utils.config import get_settings

logger = logging.getLogger(__name__)


class DrugDataGapFiller:
    """
    Unified AI agent for filling all drug data gaps in one call.

    Philosophy:
    1. APIs and scraping FIRST (DailyMed, Drugs.com, etc.)
    2. Identify ALL gaps
    3. ONE AI call to fill all gaps from label
    4. If extraction fails, fallback to web search
    5. More efficient, lower cost, better context
    """

    def __init__(self, api_key: Optional[str] = None, enable_web_search: bool = True):
        """
        Initialize gap filler.

        Args:
            api_key: Anthropic API key (defaults to settings)
            enable_web_search: Enable web search fallback when label extraction fails
        """
        if not api_key:
            settings = get_settings()
            api_key = settings.anthropic_api_key

        self.client = Anthropic(api_key=api_key)
        self.model = "claude-sonnet-4-5-20250929"
        self.enable_web_search = enable_web_search

        # Initialize web search if enabled
        self.web_search = None
        if enable_web_search:
            settings = get_settings()
            if settings.tavily_api_key:
                from src.tools.web_search import WebSearchTool
                self.web_search = WebSearchTool(settings.tavily_api_key)
                logger.info("Web search fallback enabled for gap filling")
            else:
                logger.warning("Web search enabled but no Tavily API key found")
                self.enable_web_search = False

    def fill_all_gaps(
        self,
        drug_data: Dict,
        label_xml: str,
        scraped_approval_data: Optional[Dict] = None
    ) -> Dict:
        """
        Fill ALL data gaps in one AI agent call.

        Args:
            drug_data: Extracted drug data from DailyMed
            label_xml: Full DailyMed label XML
            scraped_approval_data: Results from Drugs.com scraper (if available)

        Returns:
            Dictionary with filled gaps:
            {
                "mechanism_of_action": "IL-17A inhibitor",
                "approval_years": {
                    "plaque psoriasis": {"year": 2015, "date": "2015-01-21", "confidence": "high"},
                    ...
                },
                "dosing_regimens": [...],  # Indication-specific dosing
                "metadata": {...}  # Future: other metadata
            }
        """
        logger.info(f"Analyzing data gaps for {drug_data.get('brand_name')}")

        # Step 1: Identify gaps
        gaps = self._identify_gaps(drug_data, scraped_approval_data)

        if not gaps["has_gaps"]:
            logger.info("No data gaps found - skipping AI agent")
            return {
                "mechanism_of_action": drug_data.get("mechanism_of_action"),
                "approval_years": {},
                "dosing_regimens": [],
                "gaps_filled": False
            }

        # Step 2: Build unified prompt
        prompt = self._build_gap_filling_prompt(
            drug_data=drug_data,
            label_xml=label_xml,
            gaps=gaps
        )

        # Step 3: Call Claude ONCE to fill ALL gaps from label
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=8000,  # Increased for complex dosing extraction
                temperature=0,  # Deterministic for extraction
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )

            # Step 4: Parse response
            filled_data = self._parse_gap_filling_response(
                response.content[0].text,
                gaps
            )

            logger.info(
                f"AI gap filler (label): filled {filled_data['gaps_filled_count']} gaps "
                f"({', '.join(filled_data['gaps_filled_types'])})"
            )

            # Step 5: Check if web search fallback is needed
            if self.enable_web_search and self.web_search:
                unfilled_gaps = self._identify_unfilled_gaps(filled_data, gaps)

                if unfilled_gaps["has_gaps"]:
                    logger.info(
                        f"Label extraction incomplete. Falling back to web search for: "
                        f"{', '.join(unfilled_gaps['gap_types'])}"
                    )

                    # Use web search to fill remaining gaps
                    web_filled_data = self._fill_gaps_from_web(
                        drug_data=drug_data,
                        unfilled_gaps=unfilled_gaps,
                        label_filled_data=filled_data
                    )

                    # Merge web search results with label results
                    filled_data = self._merge_filled_data(filled_data, web_filled_data)

                    logger.info(
                        f"AI gap filler (web): filled {web_filled_data['gaps_filled_count']} additional gaps "
                        f"({', '.join(web_filled_data['gaps_filled_types'])})"
                    )

            return filled_data

        except Exception as e:
            logger.error(f"AI gap filling failed: {e}")
            return {
                "mechanism_of_action": None,
                "approval_years": {},
                "dosing_regimens": [],
                "gaps_filled": False,
                "error": str(e)
            }

    def _identify_gaps(
        self,
        drug_data: Dict,
        scraped_approval_data: Optional[Dict]
    ) -> Dict:
        """
        Identify what data is missing.

        Args:
            drug_data: Extracted drug data
            scraped_approval_data: Scraped approval dates (if available)

        Returns:
            Gap analysis:
            {
                "has_gaps": True,
                "needs_mechanism": True,
                "needs_approval_years": ["plaque psoriasis", "psoriatic arthritis"],
                "needs_complex_dosing": False
            }
        """
        gaps = {
            "has_gaps": False,
            "needs_mechanism": False,
            "needs_approval_years": [],
            "needs_dosing_linkage": False
        }

        # Check mechanism
        if not drug_data.get("mechanism_of_action"):
            gaps["needs_mechanism"] = True
            gaps["has_gaps"] = True

        # Skip approval years - Drugs.com already provides 100% coverage
        # The AI should focus entirely on dosing-indication linkage

        # Check dosing-indication linkage
        # If we have dosing regimens but many are unlinked (showing as "General"),
        # we need AI to extract indication-specific dosing
        dosing_regimens = drug_data.get("dosing_regimens", [])
        if dosing_regimens:
            unlinked_count = sum(1 for d in dosing_regimens if not d.get("indication_id"))
            total_count = len(dosing_regimens)
            indications_count = len(drug_data.get("indications", []))

            # Trigger AI if:
            # 1. We have 3+ indications AND >30% dosing is unlinked (multi-indication drugs need better linkage)
            # 2. OR we have ANY indications AND all dosing is unlinked (complete failure to link)
            should_use_ai = (
                (indications_count >= 3 and unlinked_count > total_count * 0.3) or
                (indications_count > 0 and unlinked_count == total_count)
            )

            if should_use_ai:
                gaps["needs_dosing_linkage"] = True
                gaps["has_gaps"] = True
                logger.info(
                    f"Detected dosing linkage gap: {unlinked_count}/{total_count} dosing regimens unlinked, "
                    f"{indications_count} indications - triggering AI extraction"
                )

        return gaps

    def _build_gap_filling_prompt(
        self,
        drug_data: Dict,
        label_xml: str,
        gaps: Dict
    ) -> str:
        """
        Build unified prompt to fill all gaps.

        Args:
            drug_data: Drug data
            label_xml: Label XML
            gaps: Identified gaps

        Returns:
            Prompt string
        """
        # Limit label size
        label_excerpt = self._extract_relevant_sections(label_xml)

        tasks = []

        # Task 1: Mechanism of action
        if gaps["needs_mechanism"]:
            tasks.append({
                "field": "mechanism_of_action",
                "instructions": (
                    f"Extract the mechanism of action for {drug_data['brand_name']} "
                    f"({drug_data['generic_name']}). Look in:\n"
                    "  - 'Clinical Pharmacology' section\n"
                    "  - 'Mechanism of Action' section\n"
                    "  - 'Description' section\n"
                    "Return a concise description (max 100 chars), e.g., 'IL-17A inhibitor', 'PD-1 inhibitor', etc."
                )
            })

        # Task 2: Dosing-indication linkage (PRIORITY - Drugs.com handles approval years)
        if gaps["needs_dosing_linkage"]:
            indications_json = json.dumps([ind.lower() for ind in drug_data.get("indications", [])], indent=2)
            tasks.append({
                "field": "dosing_regimens",
                "instructions": (
                    f"Extract ALL indication-specific dosing regimens from Section 2 (Dosage and Administration).\n\n"
                    f"**Available Indications (from Section 1):**\n{indications_json}\n\n"
                    "**YOUR TASK:**\n"
                    "1. Read through Section 2 carefully, including ALL tables and subsections\n"
                    "2. For EACH subsection (e.g., '2.2 Rheumatoid Arthritis', '2.4 Crohn's Disease'), extract ALL dosing\n"
                    "3. Match the subsection title to indication names from Section 1 (case-insensitive, fuzzy match okay)\n"
                    "4. For EACH dose mentioned (in text OR tables), create a complete entry\n\n"
                    "**CRITICAL RULES FOR MULTIPLE INDICATIONS:**\n"
                    "- If a subsection title uses commas or 'and' (e.g., '2.2 Rheumatoid Arthritis, Psoriatic Arthritis, and Ankylosing Spondylitis'),\n"
                    "  you MUST create SEPARATE dosing entries for EACH indication with the same dosing values\n"
                    "- If a subsection title uses 'or' (e.g., '2.3 Juvenile Idiopathic Arthritis or Pediatric Patients with Uveitis'),\n"
                    "  you MUST create SEPARATE dosing entries for EACH indication mentioned\n"
                    "- Do NOT skip any indications - extract for ALL mentioned diseases\n\n"
                    "**CRITICAL RULES FOR WEIGHT-BASED/TABULAR DOSING:**\n"
                    "- If you see a dosing TABLE with multiple weight ranges or patient categories,\n"
                    "  you MUST extract EACH row as a separate dosing entry\n"
                    "- Example: If the table shows:\n"
                    "    10-15 kg: 10 mg Q2W\n"
                    "    15-30 kg: 20 mg Q2W\n"
                    "    30+ kg: 40 mg Q2W\n"
                    "  You MUST create 3 separate dosing entries (10mg, 20mg, 40mg), one for each weight range\n"
                    "- If this table applies to multiple indications (e.g., 'JIA or Pediatric Uveitis'),\n"
                    "  multiply: 3 doses × 2 indications = 6 total entries\n\n"
                    "**OTHER RULES:**\n"
                    "- Extract BOTH loading AND maintenance doses\n"
                    "- Use lowercase for indication_name to match Section 1 names\n"
                    "- For 'every other week' use frequency_standard='Q2W', for 'every 4 weeks' use 'Q4W'\n"
                    "- sequence_order: 1, 2, 3... (loading doses first, then maintenance)\n\n"
                    "**Example 1 - Comma-separated indications:**\n"
                    "If Section 2.2 says 'Rheumatoid Arthritis, Psoriatic Arthritis: 40 mg every other week',\n"
                    "you should create TWO entries:\n"
                    "  1. {{indication_name: 'rheumatoid arthritis', dose_amount: 40, frequency_standard: 'Q2W', ...}}\n"
                    "  2. {{indication_name: 'psoriatic arthritis', dose_amount: 40, frequency_standard: 'Q2W', ...}}\n\n"
                    "**Example 2 - 'Or' between indications with weight table:**\n"
                    "If Section 2.3 says 'Juvenile Idiopathic Arthritis or Pediatric Uveitis' with table:\n"
                    "  10-15 kg: 10 mg Q2W\n"
                    "  15-30 kg: 20 mg Q2W\n"
                    "  30+ kg: 40 mg Q2W\n"
                    "you should create SIX entries:\n"
                    "  1. {{indication_name: 'polyarticular juvenile idiopathic arthritis', dose_amount: 10, frequency_standard: 'Q2W', ...}}\n"
                    "  2. {{indication_name: 'polyarticular juvenile idiopathic arthritis', dose_amount: 20, frequency_standard: 'Q2W', ...}}\n"
                    "  3. {{indication_name: 'polyarticular juvenile idiopathic arthritis', dose_amount: 40, frequency_standard: 'Q2W', ...}}\n"
                    "  4. {{indication_name: 'non-infectious intermediate, posterior and panuveitis', dose_amount: 10, frequency_standard: 'Q2W', ...}}\n"
                    "  5. {{indication_name: 'non-infectious intermediate, posterior and panuveitis', dose_amount: 20, frequency_standard: 'Q2W', ...}}\n"
                    "  6. {{indication_name: 'non-infectious intermediate, posterior and panuveitis', dose_amount: 40, frequency_standard: 'Q2W', ...}}\n\n"
                    "**Fields to extract:**\n"
                    "  - indication_name: lowercase disease name from Section 1\n"
                    "  - regimen_phase: 'loading' (initial doses) or 'maintenance' (recurring doses) or null\n"
                    "  - dose_amount: Numeric value (e.g., 40, 80, 160)\n"
                    "  - dose_unit: 'mg', 'g', 'mL', 'mg/kg', etc.\n"
                    "  - frequency_standard: 'Q2W', 'Q4W', 'QW', 'QM', 'Day 1', 'Day 15', etc.\n"
                    "  - frequency_raw: Original text from label\n"
                    "  - route_standard: 'SC', 'IV', 'oral', 'IM'\n"
                    "  - route_raw: Original text\n"
                    "  - sequence_order: 1, 2, 3...\n"
                    "  - weight_based: true if dose varies by weight/age, false otherwise\n"
                    "  - dosing_notes: Optional. Include weight range ('10-15 kg'), age range ('≥6 years'), or patient population ('pediatric', 'adults')\n"
                )
            })

        # Build final prompt
        tasks_text = "\n\n".join([
            f"**{i+1}. {task['field']}**\n{task['instructions']}"
            for i, task in enumerate(tasks)
        ])

        prompt = f"""Analyze this FDA drug label for {drug_data['brand_name']} and fill in missing data.

**Drug Information:**
- Brand Name: {drug_data['brand_name']}
- Generic Name: {drug_data['generic_name']}
- Drug Type: {drug_data.get('drug_type', 'Unknown')}

**Tasks:**
{tasks_text}

**Label Excerpt:**
<label>
{label_excerpt}
</label>

**Output Format:**
Return ONLY valid JSON (no markdown, no code blocks):

{{
  "mechanism_of_action": "string or null",
  "dosing_regimens": [
    {{
      "indication_name": "lowercase disease name matching Section 1",
      "regimen_phase": "loading|maintenance|null",
      "dose_amount": 40,
      "dose_unit": "mg",
      "frequency_standard": "Q2W",
      "frequency_raw": "every other week",
      "route_standard": "SC",
      "route_raw": "subcutaneous",
      "sequence_order": 1
    }}
  ]
}}

CRITICAL: For dosing_regimens, extract ALL dosing information from Section 2, ensuring each regimen is linked to the correct indication name from Section 1. If a subsection covers multiple indications (e.g., "Rheumatoid Arthritis, Psoriatic Arthritis, and Ankylosing Spondylitis"), create separate entries for EACH indication with the same dosing.

Return your analysis as JSON now:"""

        return prompt

    def _extract_relevant_sections(self, label_xml: str, max_chars: int = 40000) -> str:
        """
        Extract relevant sections from label.

        Args:
            label_xml: Full label XML
            max_chars: Max characters to extract

        Returns:
            Relevant label excerpt
        """
        # Extract key sections using regex (prioritize Indications and Dosing)
        sections_to_extract = [
            r'<section>.*?<code code="34067-9".*?</section>',  # Indications (Section 1)
            r'<section>.*?<code code="34068-7".*?</section>',  # Dosage and Administration (Section 2) - PRIORITY
            r'<section>.*?<code code="34090-1".*?</section>',  # Clinical Pharmacology
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

    def _parse_gap_filling_response(self, response_text: str, gaps: Dict) -> Dict:
        """
        Parse AI response.

        Args:
            response_text: Raw response from Claude
            gaps: Original gaps

        Returns:
            Filled data
        """
        # Remove markdown code blocks
        response_text = re.sub(r'```json\s*', '', response_text)
        response_text = re.sub(r'```\s*$', '', response_text)
        response_text = response_text.strip()

        # Try to extract JSON object if there's extra text
        # Look for the first { and last } to extract just the JSON portion
        json_start = response_text.find('{')
        json_end = response_text.rfind('}')

        if json_start != -1 and json_end != -1 and json_end > json_start:
            response_text = response_text[json_start:json_end+1]

        try:
            data = json.loads(response_text)

            filled_count = 0
            filled_types = []

            # Extract mechanism
            mechanism = data.get("mechanism_of_action")
            if mechanism:
                filled_count += 1
                filled_types.append("mechanism")

            # Extract dosing regimens (PRIMARY FOCUS)
            dosing_regimens = data.get("dosing_regimens", [])
            if dosing_regimens:
                filled_count += len(dosing_regimens)
                filled_types.append("dosing_regimens")
                logger.info(f"AI extracted {len(dosing_regimens)} dosing regimens")

            return {
                "mechanism_of_action": mechanism,
                "approval_years": {},  # No longer extracted by AI - use Drugs.com data
                "dosing_regimens": dosing_regimens,
                "gaps_filled": filled_count > 0,
                "gaps_filled_count": filled_count,
                "gaps_filled_types": filled_types
            }

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response as JSON: {e}")
            logger.debug(f"Response text: {response_text[:500]}")

            return {
                "mechanism_of_action": None,
                "approval_years": {},
                "dosing_regimens": [],
                "gaps_filled": False,
                "gaps_filled_count": 0,
                "gaps_filled_types": [],
                "error": f"JSON parse error: {e}"
            }

    def _identify_unfilled_gaps(self, filled_data: Dict, original_gaps: Dict) -> Dict:
        """
        Identify which gaps remain unfilled after label extraction.

        Args:
            filled_data: Data filled from label
            original_gaps: Original gaps identified

        Returns:
            Dictionary of remaining gaps
        """
        unfilled_gaps = {
            "has_gaps": False,
            "gap_types": [],
            "needs_mechanism": False,
            "needs_approval_years": []
        }

        # Check if mechanism is still missing
        if original_gaps["needs_mechanism"] and not filled_data.get("mechanism_of_action"):
            unfilled_gaps["needs_mechanism"] = True
            unfilled_gaps["gap_types"].append("mechanism")
            unfilled_gaps["has_gaps"] = True

        # Check which approval years are still missing
        approval_years = filled_data.get("approval_years", {})
        for indication in original_gaps["needs_approval_years"]:
            indication_lower = indication.lower()
            # Check if this indication has no year or low confidence
            ind_data = approval_years.get(indication_lower, {})
            if not ind_data.get("year") or ind_data.get("confidence") == "low":
                unfilled_gaps["needs_approval_years"].append(indication)

        if unfilled_gaps["needs_approval_years"]:
            unfilled_gaps["gap_types"].append("approval_years")
            unfilled_gaps["has_gaps"] = True

        return unfilled_gaps

    def _fill_gaps_from_web(
        self,
        drug_data: Dict,
        unfilled_gaps: Dict,
        label_filled_data: Dict
    ) -> Dict:
        """
        Fill remaining gaps using web search.

        Args:
            drug_data: Drug data
            unfilled_gaps: Gaps that need filling
            label_filled_data: Data already filled from label

        Returns:
            Additional filled data from web
        """
        web_results = []

        # Search for mechanism if needed
        if unfilled_gaps["needs_mechanism"]:
            query = f"{drug_data['brand_name']} {drug_data['generic_name']} mechanism of action"
            logger.info(f"Web search: {query}")
            results = self.web_search.search(query, max_results=3)
            if results:
                web_results.append({
                    "gap_type": "mechanism",
                    "query": query,
                    "results": self.web_search.format_for_llm(results)
                })

        # Search for approval years if needed
        if unfilled_gaps["needs_approval_years"]:
            for indication in unfilled_gaps["needs_approval_years"]:
                query = f"{drug_data['brand_name']} FDA approval {indication}"
                logger.info(f"Web search: {query}")
                results = self.web_search.search(query, max_results=3)
                if results:
                    web_results.append({
                        "gap_type": "approval_year",
                        "indication": indication,
                        "query": query,
                        "results": self.web_search.format_for_llm(results)
                    })

        if not web_results:
            return {
                "mechanism_of_action": None,
                "approval_years": {},
                "dosing_regimens": [],
                "gaps_filled": False,
                "gaps_filled_count": 0,
                "gaps_filled_types": []
            }

        # Build prompt with web search results
        web_prompt = self._build_web_search_prompt(drug_data, web_results, unfilled_gaps)

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4000,
                temperature=0,
                messages=[{
                    "role": "user",
                    "content": web_prompt
                }]
            )

            web_filled_data = self._parse_gap_filling_response(
                response.content[0].text,
                unfilled_gaps
            )

            return web_filled_data

        except Exception as e:
            logger.error(f"Web search gap filling failed: {e}")
            return {
                "mechanism_of_action": None,
                "approval_years": {},
                "dosing_regimens": [],
                "gaps_filled": False,
                "gaps_filled_count": 0,
                "gaps_filled_types": [],
                "error": str(e)
            }

    def _build_web_search_prompt(
        self,
        drug_data: Dict,
        web_results: List[Dict],
        unfilled_gaps: Dict
    ) -> str:
        """
        Build prompt using web search results.

        Args:
            drug_data: Drug data
            web_results: Web search results
            unfilled_gaps: Gaps to fill

        Returns:
            Prompt string
        """
        # Format web results
        web_results_text = []
        for result in web_results:
            web_results_text.append(f"""
Gap Type: {result['gap_type']}
Query: {result['query']}
{result.get('indication', '')}

Web Search Results:
{result['results']}
""")

        web_results_formatted = "\n\n---\n\n".join(web_results_text)

        # Build tasks
        tasks = []
        if unfilled_gaps["needs_mechanism"]:
            tasks.append({
                "field": "mechanism_of_action",
                "instructions": (
                    f"Extract the mechanism of action for {drug_data['brand_name']} "
                    f"({drug_data['generic_name']}) from the web search results. "
                    "Return a concise description (max 100 chars), e.g., 'IL-17A inhibitor', 'PD-1 inhibitor'."
                )
            })

        if unfilled_gaps["needs_approval_years"]:
            indications_json = json.dumps(unfilled_gaps["needs_approval_years"], indent=2)
            tasks.append({
                "field": "approval_years",
                "instructions": (
                    f"Extract FDA approval years for these indications:\n{indications_json}\n\n"
                    "Look for explicit approval dates in the web search results.\n"
                    "For EACH indication, provide:\n"
                    "  - year: YYYY (integer) or null\n"
                    "  - date: 'YYYY-MM-DD' or null\n"
                    "  - confidence: 'high', 'medium', or 'low'\n"
                    "  - source_text: Brief snippet (max 100 chars)"
                )
            })

        tasks_text = "\n\n".join([
            f"**{i+1}. {task['field']}**\n{task['instructions']}"
            for i, task in enumerate(tasks)
        ])

        prompt = f"""Extract drug information from web search results for {drug_data['brand_name']}.

**Drug Information:**
- Brand Name: {drug_data['brand_name']}
- Generic Name: {drug_data['generic_name']}
- Drug Type: {drug_data.get('drug_type', 'Unknown')}

**Tasks:**
{tasks_text}

**Web Search Results:**
{web_results_formatted}

**Output Format:**
Return ONLY valid JSON (no markdown, no code blocks):

{{
  "mechanism_of_action": "string or null",
  "approval_years": {{
    "indication_name": {{
      "year": YYYY or null,
      "date": "YYYY-MM-DD" or null,
      "confidence": "high|medium|low",
      "source_text": "snippet"
    }}
  }}
}}

Return your analysis as JSON now:"""

        return prompt

    def _merge_filled_data(self, label_data: Dict, web_data: Dict) -> Dict:
        """
        Merge data from label and web sources.

        Web data takes precedence for missing fields only.

        Args:
            label_data: Data filled from label
            web_data: Data filled from web

        Returns:
            Merged data
        """
        merged = label_data.copy()

        # Merge mechanism (web overrides only if label is null)
        if not merged.get("mechanism_of_action") and web_data.get("mechanism_of_action"):
            merged["mechanism_of_action"] = web_data["mechanism_of_action"]
            logger.info(f"Filled mechanism from web: {web_data['mechanism_of_action']}")

        # Merge approval years (web adds missing or low-confidence entries)
        label_approvals = merged.get("approval_years", {})
        web_approvals = web_data.get("approval_years", {})

        for indication, web_data_entry in web_approvals.items():
            label_data_entry = label_approvals.get(indication, {})

            # Use web data if:
            # 1. No label data exists
            # 2. Label data has low confidence
            # 3. Label data has no year
            should_use_web = (
                not label_data_entry or
                label_data_entry.get("confidence") == "low" or
                not label_data_entry.get("year")
            )

            if should_use_web and web_data_entry.get("year"):
                label_approvals[indication] = web_data_entry
                logger.info(f"Filled approval year from web for {indication}: {web_data_entry.get('year')}")

        merged["approval_years"] = label_approvals

        # Update counts
        total_filled = 0
        filled_types = set()

        if merged.get("mechanism_of_action"):
            total_filled += 1
            filled_types.add("mechanism")

        for approval_data in merged.get("approval_years", {}).values():
            if approval_data.get("year"):
                total_filled += 1
                filled_types.add("approval_years")

        merged["gaps_filled"] = total_filled > 0
        merged["gaps_filled_count"] = total_filled
        merged["gaps_filled_types"] = list(filled_types)

        return merged


# Convenience function
def fill_drug_data_gaps(
    drug_data: Dict,
    label_xml: str,
    scraped_approval_data: Optional[Dict] = None
) -> Dict:
    """
    Convenience function to fill drug data gaps.

    Args:
        drug_data: Extracted drug data
        label_xml: DailyMed label XML
        scraped_approval_data: Scraped approval dates

    Returns:
        Filled gap data
    """
    filler = DrugDataGapFiller()
    return filler.fill_all_gaps(drug_data, label_xml, scraped_approval_data)
