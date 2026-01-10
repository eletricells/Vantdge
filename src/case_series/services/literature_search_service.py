"""
Literature Search Service

Searches for case series and case reports from multiple sources:
- PubMed (biomedical literature)
- Semantic Scholar (citation network + citation mining)
- Citation snowballing (mine review article references)
- Web search (grey literature)
"""

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Set
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.case_series.protocols.llm_protocol import LLMClient
from src.case_series.protocols.search_protocol import (
    PubMedSearcher,
    SemanticScholarSearcher,
    WebSearcher,
)

logger = logging.getLogger(__name__)


def _safe_parse_json_list(response: str, context: str = "", list_key: str = None) -> Optional[List]:
    """
    Safely parse JSON list from LLM response.

    Args:
        response: Raw LLM response text
        context: Description of what we're parsing (for logging)
        list_key: If provided, extract the list from this key in a JSON object
                  e.g., list_key="evaluations" extracts from {"evaluations": [...]}
    """
    if not response or not response.strip():
        logger.warning(f"Empty LLM response{f' for {context}' if context else ''}")
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
        # If result is a dict and we have a key, extract the list
        if isinstance(result, dict) and list_key and list_key in result:
            return result[list_key] if isinstance(result[list_key], list) else None
        # If result is a dict, try common list keys
        if isinstance(result, dict):
            for key in ['evaluations', 'papers', 'results', 'items']:
                if key in result and isinstance(result[key], list):
                    return result[key]
        if isinstance(result, list):
            return result
        return None
    except json.JSONDecodeError:
        # Try to extract array from within the text
        array_match = re.search(r'\[[\s\S]*\]', text)
        if array_match:
            try:
                result = json.loads(array_match.group())
                if isinstance(result, list):
                    return result
            except json.JSONDecodeError:
                pass
        logger.warning(f"Failed to parse JSON list{f' for {context}' if context else ''}")
        return None


@dataclass
class Paper:
    """Paper metadata."""
    pmid: Optional[str] = None
    pmcid: Optional[str] = None
    doi: Optional[str] = None
    title: str = ""
    abstract: str = ""
    authors: Optional[str] = None  # Always stored as string
    journal: Optional[str] = None
    year: Optional[int] = None
    url: Optional[str] = None
    source: str = "Unknown"  # PubMed, Semantic Scholar, Web, Citation Mining
    has_full_text: bool = False
    relevance_score: float = 0.0
    relevance_reason: Optional[str] = None
    extracted_disease: Optional[str] = None

    def __post_init__(self):
        """Ensure authors is always a string and pmcid is valid."""
        # Validate pmcid is a string, not a dict (can happen with API bugs)
        if self.pmcid is not None and not isinstance(self.pmcid, str):
            logger.warning(f"Invalid pmcid type {type(self.pmcid)}, setting to None")
            self.pmcid = None

        if self.authors is not None and not isinstance(self.authors, str):
            # Convert list of author dicts to string
            if isinstance(self.authors, list):
                author_names = []
                for author in self.authors:
                    if isinstance(author, dict):
                        name = author.get('name', '')
                        if name:
                            author_names.append(name)
                    elif isinstance(author, str):
                        author_names.append(author)
                if len(author_names) > 5:
                    self.authors = ", ".join(author_names[:5]) + " et al."
                else:
                    self.authors = ", ".join(author_names)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'pmid': self.pmid,
            'pmcid': self.pmcid,
            'doi': self.doi,
            'title': self.title,
            'abstract': self.abstract,
            'authors': self.authors,
            'journal': self.journal,
            'year': self.year,
            'url': self.url,
            'source': self.source,
            'has_full_text': self.has_full_text,
            'relevance_score': self.relevance_score,
            'relevance_reason': self.relevance_reason,
            'extracted_disease': self.extracted_disease,
        }


@dataclass
class SearchResult:
    """Search result with metadata."""
    papers: List[Paper] = field(default_factory=list)
    queries_used: List[str] = field(default_factory=list)
    sources_searched: List[str] = field(default_factory=list)
    total_found: int = 0
    duplicates_removed: int = 0


class LiteratureSearchService:
    """
    Service for searching biomedical literature.

    Implements a multi-layer search strategy:
    1. Enhanced PubMed search
    2. Semantic Scholar search
    3. Citation snowballing
    4. Web search (grey literature)
    5. LLM-based relevance filtering
    """

    # Search query templates - Enhanced with clinical indicators from v2 agent
    # {drug_term} will be replaced with brand name OR generic name search
    PUBMED_QUERY_TEMPLATES = [
        # Core case report/series searches
        '{drug_term} AND ("Case Reports"[Publication Type] OR "Clinical Study"[Publication Type] OR "Observational Study"[Publication Type]) {exclusions}',
        '{drug_term} AND (case report[pt] OR case series) {exclusions}',

        # Clinical indicator searches - finds papers with patient data even without "case" in title
        '{drug_term} AND ("patients treated" OR "treated with" OR "received treatment" OR "treatment response" OR "clinical response" OR "our experience") {exclusions}',

        # Off-label and compassionate use
        '{drug_term} AND ("off-label" OR "off label") {exclusions}',
        '{drug_term} AND ("expanded access" OR "compassionate use") {exclusions}',
        '{drug_term} AND "repurpos"[Title/Abstract] {exclusions}',

        # Pediatric/juvenile (catches JDM and other pediatric cases)
        '{drug_term} AND (pediatric OR juvenile OR children) AND (treated OR response OR outcome OR patients) {exclusions}',

        # Retrospective and observational studies
        '{drug_term} AND (retrospective OR "cohort study" OR observational) AND (efficacy OR outcome OR response) {exclusions}',

        # Novel indication searches
        '{drug_term} AND (novel indication OR new indication) {exclusions}',

        # AUTOIMMUNE/INFLAMMATORY disease-specific searches (from v2)
        '{drug_term} AND (dermatomyositis OR myositis OR lupus OR vasculitis OR scleroderma) AND (patients OR treated OR response) {exclusions}',
        '{drug_term} AND (rheumatoid OR psoriatic OR ankylosing OR arthritis) AND (patients OR treated OR response) {exclusions}',
        '{drug_term} AND (inflammatory OR autoimmune) AND (patients OR treated OR outcome OR response) {exclusions}',

        # Refractory/resistant disease searches
        '{drug_term} AND (refractory OR resistant OR recalcitrant OR treatment-resistant) AND (patients OR treated OR response) {exclusions}',
    ]

    # Exclusion terms - filter out non-clinical papers
    PUBMED_EXCLUSIONS = 'NOT ("Review"[Publication Type] OR "Systematic Review"[Publication Type] OR "Meta-Analysis"[Publication Type] OR "Guideline"[Publication Type] OR "Editorial"[Publication Type] OR "Clinical Trial, Phase III"[Publication Type])'

    def __init__(
        self,
        pubmed_searcher: Optional[PubMedSearcher] = None,
        semantic_scholar_searcher: Optional[SemanticScholarSearcher] = None,
        web_searcher: Optional[WebSearcher] = None,
        llm_client: Optional[LLMClient] = None,
        filter_llm_client: Optional[LLMClient] = None,
        semantic_scholar_api_key: Optional[str] = None,
    ):
        """
        Initialize the literature search service.

        Args:
            pubmed_searcher: PubMed search implementation
            semantic_scholar_searcher: Semantic Scholar search implementation
            web_searcher: Web search implementation
            llm_client: LLM client for general tasks
            filter_llm_client: Optional separate LLM client for filtering (e.g., Haiku for speed/cost)
            semantic_scholar_api_key: API key for Semantic Scholar (for citation mining)
        """
        self._pubmed = pubmed_searcher
        self._semantic_scholar = semantic_scholar_searcher
        self._web_searcher = web_searcher
        self._llm_client = llm_client
        # Use separate filter client if provided, otherwise fall back to main client
        self._filter_llm_client = filter_llm_client or llm_client

        # Initialize Semantic Scholar API directly for citation mining
        self._semantic_scholar_api = None
        try:
            from src.tools.semantic_scholar import SemanticScholarAPI
            self._semantic_scholar_api = SemanticScholarAPI(api_key=semantic_scholar_api_key)
            logger.info("Semantic Scholar API initialized for citation mining")
        except Exception as e:
            logger.warning(f"Could not initialize Semantic Scholar API: {e}")

    async def search(
        self,
        drug_name: str,
        exclude_indications: List[str] = None,
        max_results_per_source: int = 100,
        max_total_papers: Optional[int] = None,
        filter_with_llm: bool = True,
        include_citation_mining: bool = True,
        generic_name: Optional[str] = None,
        use_pubmed: bool = True,
        use_semantic_scholar: bool = True,
        use_web_search: bool = True,
    ) -> SearchResult:
        """
        Search for case series across all sources.

        Multi-layer search strategy:
        1. Enhanced PubMed search - clinical data indicators
        2. Semantic Scholar search - semantic relevance ranking
        3. Citation snowballing - mine references from review articles
        4. Web search - grey literature
        5. LLM filtering - Claude validates clinical data presence

        Args:
            drug_name: Name of the drug
            exclude_indications: List of approved indications to exclude
            max_results_per_source: Max results from each source
            max_total_papers: Limit total papers before filtering (for testing)
            filter_with_llm: Whether to use LLM for relevance filtering
            include_citation_mining: Whether to mine review article references
            generic_name: Optional generic name (searches both if different from drug_name)
            use_pubmed: Whether to search PubMed
            use_semantic_scholar: Whether to search Semantic Scholar
            use_web_search: Whether to search web sources

        Returns:
            SearchResult with deduplicated, filtered papers
        """
        exclude_indications = exclude_indications or []
        result = SearchResult()

        # Run all searches in parallel for speed (like old agent implementation)
        import asyncio

        search_tasks = []
        task_names = []

        # 1. PubMed search (with generic name for better coverage)
        if use_pubmed and self._pubmed:
            search_tasks.append(self._search_pubmed(drug_name, max_results_per_source, generic_name))
            task_names.append('PubMed')

        # 2. Semantic Scholar search (with generic name)
        if use_semantic_scholar and self._semantic_scholar:
            search_tasks.append(self._search_semantic_scholar(drug_name, max_results_per_source, generic_name))
            task_names.append('Semantic Scholar')

        # 3. Citation snowballing (sync function, run in thread)
        if include_citation_mining and use_semantic_scholar and self._semantic_scholar_api:
            search_tasks.append(
                asyncio.to_thread(self._mine_review_citations, drug_name, generic_name)
            )
            task_names.append('Citation Mining')

        # 4. Web search (grey literature, with generic name)
        if use_web_search and self._web_searcher:
            search_tasks.append(self._search_web(drug_name, generic_name))
            task_names.append('Web')

        # Execute all searches in parallel
        logger.info(f"Running {len(search_tasks)} search sources in parallel...")
        start_time = time.time()

        search_results = await asyncio.gather(*search_tasks, return_exceptions=True)

        # Collect results
        all_papers: List[Paper] = []
        for name, papers_or_error in zip(task_names, search_results):
            if isinstance(papers_or_error, Exception):
                logger.error(f"{name} search failed: {papers_or_error}")
            elif papers_or_error:
                all_papers.extend(papers_or_error)
                result.sources_searched.append(name)
                logger.info(f"{name} returned {len(papers_or_error)} papers")

        elapsed = time.time() - start_time
        logger.info(f"Parallel search completed in {elapsed:.1f}s")

        total_raw = len(all_papers)

        # Deduplicate by PMID/DOI/title
        deduped_papers = self._deduplicate(all_papers)
        result.duplicates_removed = total_raw - len(deduped_papers)

        # Truncate to max_total_papers if specified (for testing)
        truncated_count = 0
        if max_total_papers and len(deduped_papers) > max_total_papers:
            truncated_count = len(deduped_papers) - max_total_papers
            logger.info(f"Truncating {len(deduped_papers)} papers to {max_total_papers} (testing limit)")
            deduped_papers = deduped_papers[:max_total_papers]

        # Set total_found to reflect papers actually sent to filtering (after dedup and truncation)
        result.total_found = len(deduped_papers)
        logger.info(f"Papers to filter: {result.total_found} (raw: {total_raw}, deduped: {total_raw - result.duplicates_removed}, truncated: {truncated_count})")

        # Check PMC availability
        if self._pubmed:
            deduped_papers = await self._check_pmc_availability(deduped_papers)

        # Filter with LLM (uses separate filter client if available, e.g., Haiku)
        if filter_with_llm and self._filter_llm_client:
            filtered_papers = await self._filter_with_llm(
                deduped_papers, drug_name, exclude_indications
            )
            result.papers = filtered_papers
        else:
            result.papers = deduped_papers

        logger.info(f"Search complete: {len(result.papers)} papers after filtering")
        return result

    async def _search_pubmed(
        self,
        drug_name: str,
        max_results: int,
        generic_name: Optional[str] = None,
    ) -> List[Paper]:
        """
        Enhanced PubMed search with multiple queries.

        Searches for BOTH brand name and generic name to maximize recall.
        Uses clinical data indicators to find papers with patient outcomes
        even if they don't use "case report" terminology.
        """
        papers = []
        queries_used = []

        # Build drug name search term (brand name OR generic name)
        # This ensures we find papers indexed under either name
        if generic_name and generic_name.lower() != drug_name.lower():
            drug_term = f'("{drug_name}"[Title/Abstract] OR "{generic_name}"[Title/Abstract])'
            logger.info(f"PubMed: Searching for both brand name '{drug_name}' and generic name '{generic_name}'")
        else:
            drug_term = f'"{drug_name}"[Title/Abstract]'
            logger.info(f"PubMed: Searching for drug name '{drug_name}'")

        # Papers per query: use max_results directly for each query to avoid missing papers
        # Each query searches a different aspect, so we want full coverage from each
        # The deduplication step will remove overlaps
        papers_per_query = max(50, max_results)

        total_before_dedup = 0
        for i, template in enumerate(self.PUBMED_QUERY_TEMPLATES):
            query = template.format(drug_term=drug_term, exclusions=self.PUBMED_EXCLUSIONS)
            queries_used.append(query)

            try:
                logger.info(f"PubMed query {i+1}/{len(self.PUBMED_QUERY_TEMPLATES)}: {query[:100]}...")
                results = await self._pubmed.search(query, max_results=papers_per_query)
                logger.info(f"  -> Returned {len(results)} results")

                new_papers = 0
                for r in results:
                    papers.append(Paper(
                        pmid=r.get('pmid'),
                        title=r.get('title', ''),
                        abstract=r.get('abstract', ''),
                        authors=r.get('authors'),
                        journal=r.get('journal'),
                        year=r.get('year'),
                        doi=r.get('doi'),
                        source='PubMed',
                    ))
                    new_papers += 1

                if new_papers > 0:
                    logger.info(f"  Found {new_papers} papers")

            except Exception as e:
                logger.warning(f"PubMed query failed: {query[:60]}..., error: {e}")

            # Rate limiting between queries (0.3s like original agent)
            if i < len(self.PUBMED_QUERY_TEMPLATES) - 1:
                time.sleep(0.3)

        # Add a broad catch-all query to ensure we don't miss papers
        broad_query = f'{drug_term} {self.PUBMED_EXCLUSIONS}'
        try:
            logger.info(f"PubMed broad catch-all query: {broad_query[:80]}...")
            results = await self._pubmed.search(broad_query, max_results=papers_per_query)
            logger.info(f"  -> Returned {len(results)} results")
            for r in results:
                papers.append(Paper(
                    pmid=r.get('pmid'),
                    title=r.get('title', ''),
                    abstract=r.get('abstract', ''),
                    authors=r.get('authors'),
                    journal=r.get('journal'),
                    year=r.get('year'),
                    doi=r.get('doi'),
                    source='PubMed',
                ))
        except Exception as e:
            logger.warning(f"PubMed broad query failed: {e}")

        logger.info(f"PubMed enhanced search: {len(papers)} total papers from {len(self.PUBMED_QUERY_TEMPLATES) + 1} queries (before dedup)")
        return papers

    async def _search_semantic_scholar(
        self,
        drug_name: str,
        max_results: int,
        generic_name: Optional[str] = None,
    ) -> List[Paper]:
        """Search Semantic Scholar with comprehensive queries matching v2 agent."""
        papers = []

        # Build comprehensive queries for each drug name (3 queries per name like v2)
        drug_names = [drug_name]
        if generic_name and generic_name.lower() != drug_name.lower():
            drug_names.append(generic_name)

        queries = []
        for name in drug_names:
            # Query 1: Case reports and treatment outcomes
            queries.append(f"{name} case report case series treatment outcomes patients")
            # Query 2: Off-label and compassionate use
            queries.append(f"{name} off-label compassionate use clinical efficacy")
            # Query 3: Refractory/resistant disease treatment
            queries.append(f"{name} refractory resistant disease treatment response")

        logger.info(f"Semantic Scholar: Running {len(queries)} queries for {drug_names}")

        results_per_query = max(20, max_results // len(queries))

        for query in queries:
            try:
                results = await self._semantic_scholar.search(query, limit=results_per_query)

                for r in results:
                    papers.append(Paper(
                        title=r.get('title', ''),
                        abstract=r.get('abstract', ''),
                        authors=r.get('authors'),
                        year=r.get('year'),
                        doi=r.get('doi') or r.get('externalIds', {}).get('DOI'),
                        url=r.get('url'),
                        source='Semantic Scholar',
                    ))

            except Exception as e:
                logger.warning(f"Semantic Scholar search failed for '{query}': {e}")

        return papers

    async def _search_web(self, drug_name: str, generic_name: Optional[str] = None) -> List[Paper]:
        """Search web for grey literature with comprehensive queries matching v2."""
        papers = []

        # Build comprehensive search queries (matching v2 agent's 3 queries per drug name)
        drug_names = [drug_name]
        if generic_name and generic_name.lower() != drug_name.lower():
            drug_names.append(generic_name)

        queries = []
        for name in drug_names:
            queries.append(f"{name} case report")
            queries.append(f"{name} case series patient outcomes")
            queries.append(f"{name} off-label treatment efficacy")

        logger.info(f"Web search: Running {len(queries)} queries for {drug_names}")

        for query in queries:
            try:
                results = await self._web_searcher.search(
                    query,
                    max_results=15,  # Split across queries
                    search_depth="advanced",
                )

                for r in results:
                    # Only include results that look like papers
                    url = r.get('url', '')
                    if any(domain in url for domain in ['pubmed', 'ncbi', 'doi.org', 'springer', 'wiley', 'elsevier', 'nature', 'bmj', 'thelancet']):
                        papers.append(Paper(
                            title=r.get('title', ''),
                            abstract=r.get('content', '')[:1000],
                            url=url,
                            source='Web',
                        ))

            except Exception as e:
                logger.warning(f"Web search failed for '{query}': {e}")

        return papers

    def _mine_review_citations(
        self,
        drug_name: str,
        generic_name: Optional[str] = None,
        max_reviews: int = 3,
        max_refs_per_review: int = 50,
    ) -> List[Paper]:
        """
        Citation snowballing: find review articles and extract their references.

        Reviews aggregate all case studies in a field - mining their references
        gives comprehensive coverage even for papers that don't match our queries.

        Args:
            drug_name: Drug name (brand or generic)
            generic_name: Optional generic name (searches both if different)
            max_reviews: Number of reviews to mine
            max_refs_per_review: Max references to extract per review

        Returns:
            List of papers extracted from review references
        """
        if not self._semantic_scholar_api:
            return []

        papers = []
        seen_ids: Set[str] = set()

        # Build list of drug names to search
        drug_names = [drug_name]
        if generic_name and generic_name.lower() != drug_name.lower():
            drug_names.append(generic_name)
            logger.info(f"Citation mining: searching for both '{drug_name}' and '{generic_name}'")

        for name in drug_names:
            try:
                logger.info(f"Mining citations from review articles for '{name}'...")

                # Get references from review articles
                review_refs = self._semantic_scholar_api.mine_review_references(
                    name,
                    disease_area=None,  # Search broadly
                    max_reviews=max_reviews,
                    max_refs_per_review=max_refs_per_review,
                )

                for ref in review_refs:
                    # Skip if already seen (by Semantic Scholar ID)
                    s2_id = ref.get('paperId')
                    if s2_id and s2_id in seen_ids:
                        continue
                    if s2_id:
                        seen_ids.add(s2_id)

                    # Extract external IDs
                    external_ids = ref.get('externalIds') or {}

                    # Format authors (handle None entries in list)
                    authors = ref.get('authors') or []
                    author_names = [
                        a.get('name', '') for a in authors[:5]
                        if a is not None and isinstance(a, dict)
                    ]
                    author_str = ", ".join(author_names)
                    if len(authors) > 5:
                        author_str += " et al."

                    papers.append(Paper(
                        pmid=external_ids.get('PubMed'),
                        doi=external_ids.get('DOI'),
                        title=ref.get('title', ''),
                        abstract=ref.get('abstract', ''),
                        authors=author_str,
                        journal=ref.get('venue', ''),
                        year=ref.get('year'),
                        url=f"https://www.semanticscholar.org/paper/{s2_id}" if s2_id else None,
                        source='Citation Mining',
                        relevance_reason=f"Referenced by review: {ref.get('_mined_from_review', 'Unknown')[:100]}",
                    ))

                logger.info(f"Citation mining for '{name}': {len(review_refs)} papers from review references")

            except Exception as e:
                logger.error(f"Citation mining error for '{name}': {e}")

        logger.info(f"Citation mining total: {len(papers)} papers")
        return papers

    def _deduplicate(self, papers: List[Paper]) -> List[Paper]:
        """Deduplicate papers by PMID, DOI, or title similarity."""
        seen_pmids: Set[str] = set()
        seen_dois: Set[str] = set()
        seen_titles: Set[str] = set()
        unique_papers = []

        def normalize_title(title: str) -> str:
            """Normalize title for comparison: lowercase, remove punctuation, collapse spaces."""
            if not title:
                return ""
            import re
            # Lowercase and remove punctuation
            normalized = re.sub(r'[^\w\s]', '', title.lower())
            # Collapse multiple spaces
            normalized = re.sub(r'\s+', ' ', normalized).strip()
            # Take first 80 chars to handle slight variations at the end
            return normalized[:80]

        for paper in papers:
            is_duplicate = False

            # Check PMID
            if paper.pmid:
                if paper.pmid in seen_pmids:
                    is_duplicate = True
                else:
                    seen_pmids.add(paper.pmid)

            # Check DOI (if not already marked as duplicate)
            if not is_duplicate and paper.doi:
                doi_lower = paper.doi.lower().strip()
                # Normalize DOI format
                if doi_lower.startswith('https://doi.org/'):
                    doi_lower = doi_lower[16:]
                elif doi_lower.startswith('http://doi.org/'):
                    doi_lower = doi_lower[15:]
                elif doi_lower.startswith('doi:'):
                    doi_lower = doi_lower[4:]

                if doi_lower in seen_dois:
                    is_duplicate = True
                else:
                    seen_dois.add(doi_lower)

            # Check title similarity (if not already marked as duplicate)
            if not is_duplicate:
                title_key = normalize_title(paper.title)
                if title_key and title_key in seen_titles:
                    is_duplicate = True
                elif title_key:
                    seen_titles.add(title_key)

            if not is_duplicate:
                unique_papers.append(paper)

        logger.info(f"Deduplication: {len(papers)} -> {len(unique_papers)} papers ({len(papers) - len(unique_papers)} duplicates removed)")
        return unique_papers

    async def _check_pmc_availability(self, papers: List[Paper]) -> List[Paper]:
        """Check PMC full text availability for papers with PMIDs (batched for efficiency)."""
        # Collect all PMIDs that need checking
        pmids_to_check = [p.pmid for p in papers if p.pmid and not p.pmcid]

        if not pmids_to_check:
            return papers

        try:
            # Chunk PMIDs to avoid 414 URI Too Long errors (max ~100 per request)
            PMC_BATCH_SIZE = 100
            pmc_map = {}

            for i in range(0, len(pmids_to_check), PMC_BATCH_SIZE):
                batch = pmids_to_check[i:i + PMC_BATCH_SIZE]
                try:
                    batch_results = await self._pubmed.check_pmc_availability_batch(batch)
                    pmc_map.update(batch_results)
                except Exception as e:
                    logger.warning(f"PMC batch {i//PMC_BATCH_SIZE + 1} failed: {e}")
                    # Continue with other batches

            # Apply results to papers
            for paper in papers:
                if paper.pmid and paper.pmid in pmc_map:
                    pmcid = pmc_map[paper.pmid]
                    if pmcid:
                        paper.pmcid = pmcid
                        paper.has_full_text = True

            available_count = sum(1 for v in pmc_map.values() if v)
            logger.info(f"PMC availability: {available_count}/{len(pmids_to_check)} papers have full text")

        except Exception as e:
            logger.warning(f"PMC availability check error: {e}")

        return papers

    def _pre_filter_by_keywords(
        self,
        papers: List[Paper],
        drug_name: str,
    ) -> tuple[List[Paper], int]:
        """
        Quick keyword-based pre-filter before LLM filtering.

        Removes papers that clearly don't contain clinical data based on
        title/abstract keywords. This reduces LLM API calls.

        NOTE: Papers from citation mining are treated more leniently since they
        are contextually relevant (cited by reviews about the drug) even if they
        don't explicitly mention the drug name.

        Returns:
            Tuple of (filtered_papers, num_removed)
        """
        # Keywords indicating clinical outcomes (must have at least one)
        clinical_keywords = [
            'patient', 'case', 'treatment', 'therapy', 'efficacy', 'outcome',
            'response', 'improvement', 'remission', 'clinical', 'trial',
            'study', 'retrospective', 'prospective', 'cohort', 'series',
            'report', 'experience', 'safety', 'adverse', 'tolerability',
        ]

        # Keywords indicating non-clinical papers (exclude if present without clinical keywords)
        exclude_keywords = [
            'in vitro', 'cell line', 'mouse model', 'rat model', 'animal',
            'molecular', 'mechanism', 'pathway', 'binding', 'receptor',
            'pharmacokinetic', 'pk study', 'bioavailability',
        ]

        filtered = []
        drug_lower = drug_name.lower()

        for paper in papers:
            text = f"{paper.title or ''} {paper.abstract or ''}".lower()

            # Citation mining papers are contextually relevant (from reviews about the drug)
            # Don't require drug name in text - let LLM filter decide
            is_citation_mining = paper.source == 'Citation Mining'

            # For non-citation-mining papers, must mention the drug
            if not is_citation_mining and drug_lower not in text:
                continue

            # Check for clinical keywords
            has_clinical = any(kw in text for kw in clinical_keywords)

            # Check for exclude keywords
            has_exclude = any(kw in text for kw in exclude_keywords)

            # Include if has clinical keywords, or doesn't have exclude keywords
            # (be conservative - if unclear, send to LLM)
            if has_clinical or not has_exclude:
                filtered.append(paper)

        removed = len(papers) - len(filtered)
        if removed > 0:
            logger.info(f"Pre-filter removed {removed} papers (no clinical keywords)")

        return filtered, removed

    async def _filter_with_llm(
        self,
        papers: List[Paper],
        drug_name: str,
        exclude_indications: List[str],
    ) -> List[Paper]:
        """Use LLM to filter papers for relevance."""
        if not papers:
            return []

        # Quick pre-filter by keywords to reduce LLM calls
        papers, pre_filtered_count = self._pre_filter_by_keywords(papers, drug_name)
        if not papers:
            logger.info("No papers remaining after pre-filter")
            return []

        # Build filter prompt
        from src.case_series.prompts.filtering_prompts import build_paper_filter_prompt
        import asyncio

        # Process in batches (10 papers per batch for precision)
        # Run up to 5 batches concurrently (Haiku has high rate limits)
        batch_size = 10
        max_concurrent_filter_batches = 5

        # Create batches
        batches = []
        for i in range(0, len(papers), batch_size):
            batches.append((i, papers[i:i + batch_size]))

        logger.info(f"Filtering {len(papers)} papers in {len(batches)} batches ({max_concurrent_filter_batches} concurrent)")

        # Semaphore to limit concurrency
        semaphore = asyncio.Semaphore(max_concurrent_filter_batches)

        async def process_batch(batch_idx: int, batch: List[Paper]) -> List[Paper]:
            """Process a single batch of papers."""
            async with semaphore:
                paper_dicts = [
                    {
                        'pmid': p.pmid or p.doi or f"paper_{j}",
                        'title': p.title or '',
                        'abstract': (p.abstract or '')[:1500],
                    }
                    for j, p in enumerate(batch)
                ]

                prompt = build_paper_filter_prompt(
                    drug_name=drug_name,
                    papers=paper_dicts,
                    approved_indications=exclude_indications,
                )

                try:
                    response = await self._filter_llm_client.complete(prompt, max_tokens=4000)

                    # Parse JSON response safely (template returns {"evaluations": [...]})
                    results = _safe_parse_json_list(response, f"filter batch {batch_idx}", list_key="evaluations")
                    if results is None:
                        logger.warning(f"No valid JSON in filter response for batch {batch_idx}, including all papers")
                        return batch

                    # Build index map for matching (template uses 1-based paper_index)
                    result_by_index = {}
                    for result in results:
                        idx = result.get('paper_index', 0)
                        if idx > 0:
                            result_by_index[idx - 1] = result  # Convert to 0-based

                    # Match results back to papers
                    passed_papers = []
                    excluded_count = 0
                    for j, paper in enumerate(batch):
                        result = result_by_index.get(j, {})
                        # Template uses 'include', not 'is_relevant'
                        if result.get('include', False):
                            paper.relevance_score = result.get('patient_count', 0) / 100.0 if result.get('patient_count') else 0.5
                            paper.relevance_reason = result.get('reason', '')
                            paper.extracted_disease = result.get('disease', '')
                            passed_papers.append(paper)
                        else:
                            excluded_count += 1
                            # Log exclusion reason for debugging
                            reason = result.get('reason', 'No reason given')
                            logger.debug(f"Excluded paper {paper.pmid or paper.title[:30]}: {reason[:100]}")

                    logger.info(f"Batch {batch_idx}: {len(passed_papers)} passed, {excluded_count} excluded")
                    return passed_papers

                except Exception as e:
                    logger.warning(f"LLM filtering failed for batch {batch_idx}: {e}")
                    # Include all papers from failed batch
                    return batch

        # Process all batches concurrently (limited by semaphore)
        batch_results = await asyncio.gather(
            *[process_batch(i, batch) for i, batch in batches],
            return_exceptions=True
        )

        # Collect results
        filtered_papers = []
        for i, result in enumerate(batch_results):
            if isinstance(result, Exception):
                logger.warning(f"Batch {i} raised exception: {result}")
                # Include all papers from failed batch
                filtered_papers.extend(batches[i][1])
            else:
                filtered_papers.extend(result)

        # Log filtering summary
        pass_rate = len(filtered_papers) / len(papers) * 100 if papers else 0
        logger.info(f"LLM filtering complete: {len(filtered_papers)}/{len(papers)} papers passed ({pass_rate:.1f}%)")

        return filtered_papers
