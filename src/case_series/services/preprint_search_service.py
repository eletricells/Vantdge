"""
Preprint Search Service

Searches for case series and case reports from preprint servers:
- bioRxiv (biology preprints)
- medRxiv (medical/clinical preprints)

Features:
- Searches limited to last 2 years by default
- Publication status checking and deduplication
- LLM-based relevance filtering (optional)
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Set
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.case_series.protocols.llm_protocol import LLMClient
from src.case_series.services.literature_search_service import Paper, SearchResult

logger = logging.getLogger(__name__)


def _safe_parse_json_list(response: str, context: str = "", list_key: str = None) -> Optional[List]:
    """
    Safely parse JSON list from LLM response.
    """
    if not response or not response.strip():
        return None

    text = response.strip()

    # Remove markdown code blocks if present
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    if not text:
        return None

    try:
        result = json.loads(text)
        if isinstance(result, dict) and list_key and list_key in result:
            return result[list_key] if isinstance(result[list_key], list) else None
        if isinstance(result, dict):
            for key in ['evaluations', 'papers', 'results', 'items']:
                if key in result and isinstance(result[key], list):
                    return result[key]
        if isinstance(result, list):
            return result
        return None
    except json.JSONDecodeError:
        array_match = re.search(r'\[[\s\S]*\]', text)
        if array_match:
            try:
                result = json.loads(array_match.group())
                if isinstance(result, list):
                    return result
            except json.JSONDecodeError:
                pass
        return None


class PreprintSearchService:
    """
    Service for searching preprint literature (bioRxiv/medRxiv).

    Implements:
    1. Multi-query search across both servers
    2. Publication status checking
    3. Deduplication with published papers
    4. Optional LLM-based filtering
    """

    # Search query templates for preprints
    PREPRINT_QUERY_TEMPLATES = [
        # Core clinical searches
        '{drug_term} case report',
        '{drug_term} case series',
        '{drug_term} clinical',

        # Treatment response searches
        '{drug_term} treatment response',
        '{drug_term} efficacy',
        '{drug_term} patient outcome',

        # Off-label and repurposing
        '{drug_term} off-label',
        '{drug_term} repurposing',

        # Disease-specific (autoimmune focus)
        '{drug_term} autoimmune',
        '{drug_term} inflammatory',
    ]

    def __init__(
        self,
        preprint_searcher=None,
        llm_client: Optional[LLMClient] = None,
        filter_llm_client: Optional[LLMClient] = None,
    ):
        """
        Initialize preprint search service.

        Args:
            preprint_searcher: PreprintSearchAPI instance
            llm_client: LLM client for extraction (Sonnet)
            filter_llm_client: LLM client for filtering (Haiku - faster/cheaper)
        """
        self.preprint_searcher = preprint_searcher
        self.llm_client = llm_client
        self.filter_llm_client = filter_llm_client or llm_client

    async def search(
        self,
        drug_name: str,
        generic_name: Optional[str] = None,
        approved_indications: Optional[List[str]] = None,
        max_results: int = 200,
        server: str = "both",
        years_back: int = 2,
        apply_llm_filter: bool = True,
    ) -> SearchResult:
        """
        Search preprint servers for case series papers.

        Args:
            drug_name: Brand name of drug
            generic_name: Generic name (if different from brand)
            approved_indications: List of approved indications to exclude
            max_results: Maximum papers to return
            server: "biorxiv", "medrxiv", or "both"
            years_back: Number of years back to search (default: 2)
            apply_llm_filter: Whether to apply LLM-based filtering

        Returns:
            SearchResult with preprint papers
        """
        if not self.preprint_searcher:
            logger.warning("No preprint searcher configured")
            return SearchResult(
                papers=[],
                queries_used=[],
                sources_searched=["bioRxiv", "medRxiv"],
                total_found=0,
                duplicates_removed=0
            )

        all_papers: List[Paper] = []
        queries_used: List[str] = []

        # Search with both drug names
        drug_names = [drug_name]
        if generic_name and generic_name.lower() != drug_name.lower():
            drug_names.append(generic_name)

        # Run searches for each query template
        for drug_term in drug_names:
            for template in self.PREPRINT_QUERY_TEMPLATES:
                query = template.format(drug_term=drug_term)
                queries_used.append(query)

                try:
                    results = self.preprint_searcher.search(
                        query=query,
                        server=server,
                        max_results=50,
                        years_back=years_back
                    )

                    for result in results:
                        paper = self._convert_to_paper(result)
                        all_papers.append(paper)

                except Exception as e:
                    logger.warning(f"Preprint search error for '{query}': {e}")
                    continue

        # Deduplicate
        original_count = len(all_papers)
        deduped_papers = self._deduplicate(all_papers)
        duplicates_removed = original_count - len(deduped_papers)

        logger.info(
            f"Preprint search: {len(deduped_papers)} unique papers "
            f"({duplicates_removed} duplicates removed)"
        )

        # Apply LLM filtering if requested
        if apply_llm_filter and self.filter_llm_client and deduped_papers:
            filtered_papers = await self._filter_with_llm(
                deduped_papers,
                drug_name,
                approved_indications or []
            )
        else:
            filtered_papers = deduped_papers

        # Limit results
        final_papers = filtered_papers[:max_results]

        sources = []
        if server in ["biorxiv", "both"]:
            sources.append("bioRxiv")
        if server in ["medrxiv", "both"]:
            sources.append("medRxiv")

        return SearchResult(
            papers=final_papers,
            queries_used=queries_used,
            sources_searched=sources,
            total_found=len(final_papers),
            duplicates_removed=duplicates_removed
        )

    def _convert_to_paper(self, preprint_data: Dict[str, Any]) -> Paper:
        """
        Convert preprint API response to Paper object.

        Args:
            preprint_data: Raw data from PreprintSearchAPI

        Returns:
            Paper object
        """
        return Paper(
            pmid=None,  # Preprints don't have PMIDs
            pmcid=None,
            doi=preprint_data.get("doi"),
            title=preprint_data.get("title", ""),
            abstract=preprint_data.get("abstract", ""),
            authors=preprint_data.get("authors", ""),
            journal=f"{preprint_data.get('source', 'Preprint')} (preprint)",
            year=preprint_data.get("year"),
            url=preprint_data.get("url"),
            source=preprint_data.get("source", "Preprint"),
            has_full_text=bool(preprint_data.get("jatsxml")),
            relevance_score=0.0,
            relevance_reason=None,
            extracted_disease=None,
            is_preprint=True,
            published_doi=preprint_data.get("published_doi"),
            preprint_server=preprint_data.get("preprint_server"),
        )

    def _deduplicate(self, papers: List[Paper]) -> List[Paper]:
        """
        Deduplicate papers by DOI and title.

        Args:
            papers: List of papers to deduplicate

        Returns:
            Deduplicated list
        """
        seen_dois: Set[str] = set()
        seen_titles: Set[str] = set()
        unique_papers = []

        for paper in papers:
            # Check DOI
            if paper.doi:
                normalized_doi = paper.doi.lower().strip()
                if normalized_doi in seen_dois:
                    continue
                seen_dois.add(normalized_doi)

            # Check title similarity
            if paper.title:
                normalized_title = re.sub(r'[^a-z0-9]', '', paper.title.lower())[:80]
                if normalized_title in seen_titles:
                    continue
                seen_titles.add(normalized_title)

            unique_papers.append(paper)

        return unique_papers

    def deduplicate_with_published(
        self,
        preprint_papers: List[Paper],
        standard_papers: List[Paper]
    ) -> List[Paper]:
        """
        Remove preprints that have published versions in standard results.

        Args:
            preprint_papers: List of preprint papers
            standard_papers: List of papers from standard sources

        Returns:
            Filtered preprint papers
        """
        # Collect DOIs from standard papers
        published_dois: Set[str] = set()
        for paper in standard_papers:
            if paper.doi:
                published_dois.add(paper.doi.lower().strip())

        # Filter preprints
        filtered = []
        removed_count = 0

        for paper in preprint_papers:
            # Check if this preprint's published version is in standard results
            if paper.published_doi:
                normalized_published = paper.published_doi.lower().strip()
                if normalized_published in published_dois:
                    logger.debug(
                        f"Removing preprint (published version found): {paper.title[:50]}"
                    )
                    removed_count += 1
                    continue

            # Also check if the preprint DOI appears (shouldn't, but safety check)
            if paper.doi:
                normalized_preprint = paper.doi.lower().strip()
                if normalized_preprint in published_dois:
                    removed_count += 1
                    continue

            filtered.append(paper)

        if removed_count > 0:
            logger.info(
                f"Removed {removed_count} preprints with published versions in standard results"
            )

        return filtered

    async def _filter_with_llm(
        self,
        papers: List[Paper],
        drug_name: str,
        approved_indications: List[str],
    ) -> List[Paper]:
        """
        Filter papers using LLM for relevance.

        Args:
            papers: Papers to filter
            drug_name: Drug name for context
            approved_indications: Indications to exclude

        Returns:
            Filtered papers
        """
        if not papers:
            return []

        # Pre-filter by keywords
        pre_filtered = self._pre_filter_by_keywords(papers)

        if not pre_filtered:
            return []

        # Build filtering prompt
        papers_text = []
        for i, paper in enumerate(pre_filtered[:30]):  # Limit batch size
            papers_text.append(
                f"{i+1}. Title: {paper.title}\n"
                f"   Abstract: {(paper.abstract or '')[:800]}\n"
            )

        approved_str = ", ".join(approved_indications) if approved_indications else "None specified"

        prompt = f"""Evaluate these PREPRINT papers for relevance to {drug_name} case series research.

APPROVED INDICATIONS (exclude these): {approved_str}

CRITERIA for inclusion:
1. Contains patient data (case report, case series, clinical study)
2. Reports clinical outcomes or efficacy data
3. Discusses off-label use, repurposing, or novel indications
4. Is NOT about approved indications listed above
5. Is NOT a review, meta-analysis, or protocol paper

PREPRINT PAPERS:
{"".join(papers_text)}

Return a JSON array with evaluations:
[
  {{"paper_num": 1, "include": true/false, "reason": "brief reason", "patient_count": estimated_count_or_null, "disease": "disease name or null"}}
]

Only include papers that clearly meet the criteria. Respond with only the JSON array."""

        try:
            response = await self.filter_llm_client.complete(
                prompt=prompt,
                max_tokens=2000
            )

            evaluations = _safe_parse_json_list(response, "preprint filter")

            if not evaluations:
                logger.warning("Failed to parse LLM filter response, returning all papers")
                return pre_filtered

            # Apply evaluations
            filtered = []
            for eval_item in evaluations:
                if not isinstance(eval_item, dict):
                    continue

                paper_num = eval_item.get("paper_num")
                include = eval_item.get("include", False)

                if include and paper_num and 1 <= paper_num <= len(pre_filtered):
                    paper = pre_filtered[paper_num - 1]
                    paper.relevance_reason = eval_item.get("reason")
                    paper.extracted_disease = eval_item.get("disease")

                    patient_count = eval_item.get("patient_count")
                    if patient_count:
                        paper.relevance_score = min(1.0, patient_count / 100)

                    filtered.append(paper)

            logger.info(f"LLM filter: {len(filtered)}/{len(pre_filtered)} preprints passed")
            return filtered

        except Exception as e:
            logger.error(f"LLM filtering error: {e}")
            return pre_filtered

    def _pre_filter_by_keywords(self, papers: List[Paper]) -> List[Paper]:
        """
        Quick pre-filter by clinical keywords.

        Args:
            papers: Papers to filter

        Returns:
            Pre-filtered papers
        """
        clinical_keywords = {
            'patient', 'patients', 'case', 'clinical', 'treatment', 'treated',
            'trial', 'study', 'response', 'efficacy', 'outcome', 'therapy',
            'remission', 'improvement', 'adverse', 'tolerability', 'safety'
        }

        exclude_keywords = {
            'in vitro', 'cell line', 'mouse model', 'rat model', 'animal model',
            'molecular mechanism', 'computational', 'simulation', 'docking',
            'structure prediction', 'phylogenetic'
        }

        filtered = []
        for paper in papers:
            text = f"{paper.title} {paper.abstract}".lower()

            # Check for exclusion keywords
            if any(kw in text for kw in exclude_keywords):
                continue

            # Check for at least one clinical keyword
            if any(kw in text for kw in clinical_keywords):
                filtered.append(paper)

        logger.debug(f"Pre-filter: {len(filtered)}/{len(papers)} passed keyword check")
        return filtered
