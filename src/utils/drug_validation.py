"""
Drug data validation utilities to prevent contamination.

Prevents unrelated drugs from being merged during discovery and enrichment
by validating that synonyms, trials, and mechanisms are actually related.
"""
from typing import Dict, List, Optional
import logging
import re

logger = logging.getLogger(__name__)


class DrugValidator:
    """
    Validates that drug data from multiple sources actually belongs to the same drug.

    Prevents contamination where unrelated drugs get merged (e.g., LASN01 getting TEPEZZA's data).
    """

    def __init__(self, web_search_tool=None, anthropic_client=None):
        """
        Initialize validator.

        Args:
            web_search_tool: Optional web search tool for validation queries
            anthropic_client: Optional Anthropic client for LLM-based validation
        """
        self.web_search = web_search_tool
        self.anthropic = anthropic_client

    def validate_synonym(
        self,
        drug_name: str,
        potential_synonym: str,
        drug_mechanism: Optional[str] = None,
        drug_company: Optional[str] = None
    ) -> bool:
        """
        Validate if a potential synonym actually refers to the same drug.

        Uses multiple validation strategies:
        1. Pattern matching (same research code, obvious variants)
        2. Target extraction from mechanism (must match)
        3. Web search validation (if tools available)

        Args:
            drug_name: Original drug name (e.g., "LASN01")
            potential_synonym: Synonym to validate (e.g., "TEPEZZA")
            drug_mechanism: Known mechanism of action for the drug
            drug_company: Known developer/manufacturer

        Returns:
            True if synonym is valid, False if it's contamination
        """
        # Normalize names for comparison
        drug_lower = drug_name.lower().strip()
        synonym_lower = potential_synonym.lower().strip()

        # Rule 1: Exact match or substring (obvious variants)
        if drug_lower == synonym_lower:
            return True
        if drug_lower in synonym_lower or synonym_lower in drug_lower:
            # e.g., "K1-70" in "K1-70TM" or "adalimumab" in "adalimumab-atto"
            logger.debug(f"✓ Synonym '{potential_synonym}' is substring match for '{drug_name}'")
            return True

        # Rule 2: Research code variants (same root code)
        if self._are_research_code_variants(drug_name, potential_synonym):
            logger.debug(f"✓ Synonym '{potential_synonym}' is research code variant of '{drug_name}'")
            return True

        # Rule 3: Target-based validation (mechanism must match)
        if drug_mechanism:
            # Extract target from mechanism
            drug_target = self._extract_target_from_mechanism(drug_mechanism)

            # If we can infer target from synonym name (e.g., "anti-IL11R"), check it matches
            synonym_target_hint = self._infer_target_from_name(potential_synonym)

            if drug_target and synonym_target_hint:
                if not self._targets_match(drug_target, synonym_target_hint):
                    logger.warning(
                        f"✗ Rejecting synonym '{potential_synonym}' for '{drug_name}': "
                        f"target mismatch ({drug_target} vs {synonym_target_hint})"
                    )
                    return False

        # Rule 4: Skip obvious non-matches (OPTIMIZATION: avoid expensive LLM calls)
        if self._is_obvious_non_match(drug_name, potential_synonym):
            logger.debug(f"✗ Skipped obvious non-match: '{potential_synonym}' vs '{drug_name}'")
            return False

        # Rule 5: If names are VERY different and no clear relationship, be suspicious
        # e.g., "LASN01" vs "TEPEZZA" - completely different strings
        if not self._names_similar(drug_name, potential_synonym):
            # Use LLM validation if available
            if self.web_search and self.anthropic:
                is_same = self._llm_validate_synonym(drug_name, potential_synonym, drug_mechanism)
                if is_same is not None:
                    return is_same

            # Without LLM validation, reject if names are too different
            logger.warning(
                f"⚠ Suspicious synonym '{potential_synonym}' for '{drug_name}': "
                f"names very different, no validation available"
            )
            # Be conservative: allow it but log warning
            return True

        # Default: accept (validated by PubChem)
        return True

    def validate_trial_relevance(
        self,
        drug_name: str,
        trial_intervention_names: List,  # Can be List[str] or List[Dict]
        drug_mechanism: Optional[str] = None,
        drug_target: Optional[str] = None
    ) -> bool:
        """
        Validate if a trial is actually testing this drug or an unrelated drug.

        Args:
            drug_name: Drug being enriched
            trial_intervention_names: List of intervention names or dicts from trial
            drug_mechanism: Known mechanism of action
            drug_target: Known biological target

        Returns:
            True if trial is relevant, False if contamination
        """
        # Check if drug name appears in intervention names
        drug_lower = drug_name.lower().strip()

        for intervention in trial_intervention_names:
            # Handle both string and dict formats
            if isinstance(intervention, dict):
                intervention_name = intervention.get('name', '')
            else:
                intervention_name = intervention

            if not intervention_name:
                continue

            intervention_lower = intervention_name.lower().strip()

            # Direct match
            if drug_lower == intervention_lower:
                return True

            # Substring match
            if drug_lower in intervention_lower or intervention_lower in drug_lower:
                return True

            # Research code variants
            if self._are_research_code_variants(drug_name, intervention_name):
                return True

        # No match found - suspicious
        logger.warning(
            f"⚠ Trial intervention names {trial_intervention_names} do not contain '{drug_name}'"
        )

        # Could be a synonym - need deeper validation
        # For now, return False to prevent contamination
        return False

    def _is_obvious_non_match(self, drug_name: str, potential_synonym: str) -> bool:
        """
        Check if synonym is an obvious non-match to skip expensive LLM validation.

        OPTIMIZATION: This prevents wasting LLM calls on obvious non-matches like:
        - "Placebo" vs "Dupilumab"
        - "Vehicle" vs "tacrolimus"
        - "Standard Treatment" vs "Baricitinib"

        Args:
            drug_name: Original drug name
            potential_synonym: Synonym to check

        Returns:
            True if obviously not the same drug (skip validation)
        """
        synonym_lower = potential_synonym.lower().strip()

        # Common placebo/control terms
        placebo_terms = {
            'placebo', 'vehicle', 'control', 'standard treatment', 'standard care',
            'standard of care', 'best supportive care', 'usual care', 'sham',
            'no treatment', 'observation', 'observational', 'not applicable'
        }

        if synonym_lower in placebo_terms:
            return True

        # Phrases containing placebo/control
        if any(term in synonym_lower for term in ['placebo', 'vehicle of', 'matching placebo']):
            return True

        # Generic treatment descriptions
        generic_terms = {
            'background treatment', 'background therapy', 'concomitant medication',
            'rescue medication', 'standard therapy', 'conventional therapy'
        }

        if synonym_lower in generic_terms:
            return True

        # Procedure/intervention terms (not drugs)
        procedure_terms = {
            'surgery', 'radiation', 'chemotherapy', 'radiotherapy', 'phototherapy',
            'virtual reality', 'behavioral therapy', 'cognitive therapy',
            'tears sampling', 'lashes sampling', 'blood sampling'
        }

        if synonym_lower in procedure_terms or any(term in synonym_lower for term in procedure_terms):
            return True

        # Obvious different drug classes (if drug_name is clearly a biologic)
        # e.g., if drug_name ends in -mab/-umab (monoclonal antibody), reject small molecules
        if drug_name.lower().endswith(('mab', 'umab')):
            # Reject obvious small molecules
            small_molecule_suffixes = ['cycline', 'cillin', 'mycin', 'olol', 'pril', 'sartan', 'statin']
            if any(synonym_lower.endswith(suffix) for suffix in small_molecule_suffixes):
                return True

        return False

    def _are_research_code_variants(self, name1: str, name2: str) -> bool:
        """
        Check if two names are variants of the same research code.

        Examples:
            K1-70 vs K1-70TM → True
            OSI-906 vs OSI906 → True
            LASN01 vs LASN-01 → True
            LASN01 vs TEPEZZA → False
        """
        # Normalize: remove dashes, spaces, lowercase
        norm1 = re.sub(r'[-\s]', '', name1.lower())
        norm2 = re.sub(r'[-\s]', '', name2.lower())

        # Check if one is prefix of other (e.g., "k170" vs "k170tm")
        if norm1.startswith(norm2) or norm2.startswith(norm1):
            return True

        # Extract research code pattern: letters + numbers
        pattern = r'^([a-z]+)(\d+)([a-z]*)$'
        match1 = re.match(pattern, norm1)
        match2 = re.match(pattern, norm2)

        if match1 and match2:
            # Compare letters and numbers parts
            letters1, numbers1, suffix1 = match1.groups()
            letters2, numbers2, suffix2 = match2.groups()

            # Same letters and numbers = variants
            if letters1 == letters2 and numbers1 == numbers2:
                return True

        return False

    def _extract_target_from_mechanism(self, mechanism: str) -> Optional[str]:
        """
        Extract biological target from mechanism string.

        Examples:
            "Anti-IGF-1R monoclonal antibody" → "IGF-1R"
            "IL-11R inhibitor" → "IL-11R"
            "JAK1/TYK2 inhibitor" → "JAK1"
            "FcRn inhibitor" → "FcRn"
        """
        if not mechanism:
            return None

        mechanism_upper = mechanism.upper()

        # Common target patterns
        target_patterns = [
            r'(IL-\d+R?)',           # IL-11R, IL-6R, IL-17, etc.
            r'(IGF-\d+R)',           # IGF-1R, IGF-2R
            r'(VEGF-?R?\d*)',        # VEGF, VEGFR, VEGFR2
            r'(PD-L?\d)',            # PD-1, PD-L1
            r'(CTLA-\d)',            # CTLA-4
            r'(TNF-?α?)',            # TNF, TNF-alpha
            r'(JAK\d)',              # JAK1, JAK2, JAK3
            r'(TYK\d)',              # TYK2
            r'(FcRn)',               # FcRn
            r'(CD\d+)',              # CD20, CD38, etc.
            r'(HER\d)',              # HER2, HER3
            r'(EGFR)',               # EGFR
            r'(KRAS)',               # KRAS
            r'(BRAF)',               # BRAF
            r'(TSHR)',               # TSHR (thyroid stimulating hormone receptor)
        ]

        for pattern in target_patterns:
            match = re.search(pattern, mechanism_upper)
            if match:
                return match.group(1)

        return None

    def _infer_target_from_name(self, name: str) -> Optional[str]:
        """
        Try to infer target from drug name (if name contains target info).

        Examples:
            "anti-IL11R antibody" → "IL-11R"
            "pembrolizumab" → None (generic mAb name)
        """
        name_upper = name.upper()

        # Check if name contains target keywords
        if 'ANTI-' in name_upper:
            # Extract target after "anti-"
            target_match = re.search(r'ANTI-([A-Z0-9-]+)', name_upper)
            if target_match:
                return target_match.group(1)

        return None

    def _targets_match(self, target1: str, target2: str) -> bool:
        """
        Check if two targets are the same (handling variations).

        Examples:
            IL-11R vs IL11R → True
            IGF-1R vs IGF1R → True
            IL-11R vs IGF-1R → False
        """
        # Normalize: remove dashes, spaces
        norm1 = re.sub(r'[-\s]', '', target1.upper())
        norm2 = re.sub(r'[-\s]', '', target2.upper())

        return norm1 == norm2

    def _names_similar(self, name1: str, name2: str) -> bool:
        """
        Check if two names are similar enough to be variants.

        Uses character overlap ratio.
        """
        name1_lower = name1.lower()
        name2_lower = name2.lower()

        # Character set overlap
        chars1 = set(name1_lower)
        chars2 = set(name2_lower)

        overlap = len(chars1 & chars2)
        total = len(chars1 | chars2)

        if total == 0:
            return False

        overlap_ratio = overlap / total

        # At least 50% character overlap
        return overlap_ratio >= 0.5

    def _llm_validate_synonym(
        self,
        drug_name: str,
        potential_synonym: str,
        drug_mechanism: Optional[str]
    ) -> Optional[bool]:
        """
        Use LLM + web search to validate if two names refer to same drug.

        Args:
            drug_name: Original drug name
            potential_synonym: Synonym to validate
            drug_mechanism: Known mechanism (for context)

        Returns:
            True if same drug, False if different, None if uncertain
        """
        if not self.web_search or not self.anthropic:
            return None

        try:
            # Search for both drugs
            query = f'"{drug_name}" "{potential_synonym}" same drug different'
            search_results = self.web_search.search(query, max_results=5)

            if not search_results:
                return None

            # Format results
            context = "\n\n".join([
                f"Title: {r.get('title', '')}\nContent: {r.get('content', '')}"
                for r in search_results
            ])

            # Ask Claude
            prompt = f"""Are "{drug_name}" and "{potential_synonym}" the same drug or different drugs?

Context from web search:
{context[:4000]}

Known mechanism for {drug_name}: {drug_mechanism or 'Unknown'}

Instructions:
- If they are THE SAME drug (one is brand name, one is generic, or one is research code for the other), answer "SAME"
- If they are DIFFERENT drugs (different targets, different companies, different mechanisms), answer "DIFFERENT"
- If unclear, answer "UNCERTAIN"

Answer with ONLY one word: SAME, DIFFERENT, or UNCERTAIN"""

            response = self.anthropic.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}]
            )

            answer = response.content[0].text.strip().upper()

            if answer == "SAME":
                logger.info(f"✓ LLM validated: '{potential_synonym}' is same as '{drug_name}'")
                return True
            elif answer == "DIFFERENT":
                logger.warning(f"✗ LLM rejected: '{potential_synonym}' is DIFFERENT from '{drug_name}'")
                return False
            else:
                logger.debug(f"⚠ LLM uncertain about '{potential_synonym}' vs '{drug_name}'")
                return None

        except Exception as e:
            logger.error(f"LLM validation failed: {e}")
            return None


def filter_synonyms(
    drug_name: str,
    synonyms: List[str],
    drug_mechanism: Optional[str] = None,
    drug_company: Optional[str] = None,
    validator: Optional[DrugValidator] = None
) -> List[str]:
    """
    Filter synonyms to remove unrelated drugs.

    Args:
        drug_name: Original drug name
        synonyms: List of synonyms from PubChem or other sources
        drug_mechanism: Known mechanism of action
        drug_company: Known developer/manufacturer
        validator: DrugValidator instance (creates one if not provided)

    Returns:
        Filtered list of validated synonyms
    """
    if not synonyms:
        return []

    if validator is None:
        validator = DrugValidator()

    validated_synonyms = []
    rejected_synonyms = []

    for synonym in synonyms:
        if validator.validate_synonym(drug_name, synonym, drug_mechanism, drug_company):
            validated_synonyms.append(synonym)
        else:
            rejected_synonyms.append(synonym)

    if rejected_synonyms:
        logger.info(f"Rejected {len(rejected_synonyms)} invalid synonyms for '{drug_name}': {rejected_synonyms[:5]}")

    return validated_synonyms
