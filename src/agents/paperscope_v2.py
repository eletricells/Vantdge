"""
PaperScope 2.0 - Universal Drug Literature Search and Categorization Agent

Takes a single drug name and comprehensively searches, categorizes, and organizes
all papers from the literature. Works across any therapeutic area without disease-specific
assumptions.
"""
import logging
import re
import time
from typing import List, Dict, Set, Optional, Tuple, Any
from datetime import datetime
from collections import defaultdict
from pathlib import Path
import json

from src.tools.pubmed import PubMedAPI
from src.tools.clinicaltrials import ClinicalTrialsAPI
from src.tools.web_search import WebSearchTool
from anthropic import Anthropic

# Import new utility classes
from src.agents.paperscope_v2_utils import (
    PaperScopeConfig,
    ClaudeResponseParser,
    PromptBuilder,
    APIClient,
    ResponseCache,
    ProgressTracker,
    StructuredLogger,
    ParallelProcessor,
    SearchRequest,
    PYDANTIC_AVAILABLE
)
from src.agents.trial_name_extractor import TrialNameExtractor

logger = logging.getLogger(__name__)


class PaperScopeV2Agent:
    """
    Universal drug literature searcher and categorizer.

    Performs comprehensive literature search for any drug, automatically detects
    disease context, and categorizes papers into 18+ categories.

    Uses Claude for intelligent classification and context detection.
    """

    # Generic trial name patterns (no drug-specific names)
    TRIAL_PATTERNS = [
        r'\b([A-Z]{3,}-\d+[A-Z]?)\b',           # TULIP-1, EXTEND-2A
        r'\b([A-Z]{3,}\d+[A-Z]?)\b',            # MUSE2, REACH3
        r'\b([A-Z]{4,})\s+(?:trial|study)\b',   # BLOSSOM trial
    ]
    
    # Paper categories - comprehensive coverage of all development stages
    CATEGORIES = [
        'Preclinical/Mechanistic',
        'Phase 1',
        'Phase 1/2',
        'Phase 2',
        'Phase 2 - Extensions',
        'Phase 2/3',
        'Phase 3 - Primary Trials',
        'Phase 3 - Long-term Extensions',
        'Phase 3 - Pooled/Post-hoc Analyses',
        'Phase 4',
        'Biomarker Studies',
        'Subgroup Analyses - Demographics',
        'Subgroup Analyses - Disease Characteristics',
        'Subgroup Analyses - Concomitant Medications',
        'Special Populations',
        'Pharmacokinetics/Pharmacodynamics',
        'Drug Interactions',
        'Post-marketing/Real-world',
        'Safety/Pharmacovigilance',
        'Systematic Reviews/Meta-analyses',
        'Economic/Cost-effectiveness',
        'Ongoing Studies',
        'Other'
    ]
    
    def __init__(
        self,
        pubmed_api: PubMedAPI,
        anthropic_client: Anthropic,
        web_search_tool: Optional[WebSearchTool] = None,
        clinicaltrials_api: Optional[ClinicalTrialsAPI] = None,
        config: Optional[PaperScopeConfig] = None,
        **kwargs
    ):
        """
        Initialize PaperScope 2.0 agent.

        Args:
            pubmed_api: PubMed API client
            anthropic_client: Anthropic API client for Claude
            web_search_tool: Optional web search tool for finding papers beyond PubMed
            clinicaltrials_api: Optional ClinicalTrials.gov API client
            config: Optional configuration object (PaperScopeConfig)
            **kwargs: Additional config overrides (output_dir, model, batch_size, etc.)
        """
        # Initialize configuration
        self.config = config or PaperScopeConfig()

        # Apply any kwargs overrides
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)

        # Set up APIs
        self.pubmed = pubmed_api
        self.web_search = web_search_tool
        self.ct_api = clinicaltrials_api

        # Set up output directory
        self.output_dir = Path(self.config.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Initialize utility classes
        cache_dir = self.output_dir / 'cache'
        self.cache = ResponseCache(cache_dir, default_ttl_hours=self.config.cache_ttl_hours) if self.config.enable_cache else None
        self.api_client = APIClient(anthropic_client, self.config, self.cache)
        self.json_parser = ClaudeResponseParser(save_failures=True)
        self.prompt_builder = PromptBuilder()
        self.trial_extractor = TrialNameExtractor()

        # Legacy attributes for backward compatibility
        self.anthropic = anthropic_client
        self.model = self.config.model
        self.batch_size = self.config.batch_size
        self.CATEGORIES = self.config.categories

        # State tracking
        self.all_pmids: Set[str] = set()
        self.search_log: List[Dict] = []
        self.drug_context: Dict[str, Any] = {}

        # Track paper sources for metrics
        self.paper_sources: Dict[str, int] = defaultdict(int)
        
    def search_and_categorize(
        self,
        drug_name: str,
        disease_indication: Optional[str] = None,
        drug_class: Optional[str] = None,
        max_results_per_search: int = 100
    ) -> Dict[str, Any]:
        """
        Main workflow: search for all papers and categorize them.

        Args:
            drug_name: Generic drug name
            disease_indication: Optional disease/indication
            drug_class: Optional drug class
            max_results_per_search: Max results per individual search

        Returns:
            Dictionary with categorized papers and metadata
        """
        # Validate inputs if Pydantic is available
        if PYDANTIC_AVAILABLE and SearchRequest:
            try:
                request = SearchRequest(
                    drug_name=drug_name,
                    disease_indication=disease_indication,
                    drug_class=drug_class,
                    max_results_per_search=max_results_per_search
                )
                # Use validated inputs
                drug_name = request.drug_name
                disease_indication = request.disease_indication
                drug_class = request.drug_class
                max_results_per_search = request.max_results_per_search
            except ValueError as e:
                logger.error(f"Invalid input: {e}")
                raise ValueError(f"Invalid search parameters: {e}")

        logger.info(f"Starting PaperScope 2.0 for: {drug_name}")
        start_time = time.time()

        # Initialize progress tracking and logging
        progress = ProgressTracker()
        structured_log = StructuredLogger(
            name='paperscope_v2',
            log_dir=self.output_dir / 'logs'
        )

        # Log start
        structured_log.log_event('workflow_start', {
            'drug_name': drug_name,
            'disease_indication': disease_indication,
            'drug_class': drug_class
        })

        # Auto-detect context if not provided
        progress.start_phase('context_detection', 'Auto-detecting drug context')
        if not disease_indication or not drug_class:
            logger.info("Auto-detecting drug context...")
            detected = self._detect_drug_context(drug_name)
            disease_indication = disease_indication or detected.get('disease')
            drug_class = drug_class or detected.get('drug_class')
            logger.info(f"Detected - Disease: {disease_indication}, Class: {drug_class}")
            structured_log.log_event('context_detected', {
                'disease': disease_indication,
                'drug_class': drug_class
            })
        progress.complete_phase('context_detection')

        self.drug_context = {
            'drug_name': drug_name,
            'disease': disease_indication,
            'drug_class': drug_class
        }

        # Phase 0: Discover all trial names for this drug using web search
        progress.start_phase('trial_discovery', 'Discovering trial names via web search')
        logger.info("Phase 0: Discovering trial names via web search...")
        known_trial_names = self._discover_trial_names_via_web(drug_name, disease_indication)
        logger.info(f"Discovered {len(known_trial_names)} trial names: {known_trial_names}")
        self.known_trial_names = known_trial_names
        structured_log.log_event('trials_discovered', {
            'count': len(known_trial_names),
            'trial_names': list(known_trial_names)
        })
        progress.complete_phase('trial_discovery')

        # Phase 0b: Discover all indications from ClinicalTrials.gov
        progress.start_phase('indication_discovery', 'Discovering indications from ClinicalTrials.gov')
        logger.info("Phase 0b: Discovering indications from ClinicalTrials.gov...")
        discovered_indications = self._discover_indications_from_ctgov(drug_name)
        logger.info(f"Discovered {len(discovered_indications)} indications: {discovered_indications}")
        self.discovered_indications = discovered_indications
        structured_log.log_event('indications_discovered', {
            'count': len(discovered_indications),
            'indications': discovered_indications
        })
        progress.complete_phase('indication_discovery')

        # Phase 1: Comprehensive search
        progress.start_phase('literature_search', 'Comprehensive literature search')
        logger.info("Phase 1: Comprehensive literature search...")
        search_sequence = self._build_search_sequence(
            drug_name, disease_indication, drug_class
        )
        
        for i, search in enumerate(search_sequence, 1):
            progress.update_progress(i, len(search_sequence), f"Search: {search['purpose']}")
            logger.info(f"Search #{search['id']}: {search['purpose']}")
            pmids = self.pubmed.search(
                search['query'],
                max_results=search['max_results']
            )

            self.search_log.append({
                'id': search['id'],
                'query': search['query'],
                'purpose': search['purpose'],
                'pmids_found': len(pmids),
                'timestamp': datetime.now().isoformat()
            })

            self.all_pmids.update(pmids)
            logger.info(f"  Found {len(pmids)} papers")
            # Note: Rate limiting handled by PubMedAPI._rate_limit()

        logger.info(f"Total unique PMIDs found: {len(self.all_pmids)}")
        structured_log.log_event('literature_search_complete', {
            'total_searches': len(search_sequence),
            'unique_pmids': len(self.all_pmids)
        })
        progress.complete_phase('literature_search')

        # Phase 2: Extract trial names and search for trial families
        progress.start_phase('trial_family_search', 'Extracting trial names and searching families')
        logger.info("Phase 2: Extracting trial names...")
        trial_names = self._extract_trial_names_from_sample(list(self.all_pmids)[:50])
        logger.info(f"Identified {len(trial_names)} trial names: {trial_names}")
        
        for i, trial_name in enumerate(trial_names, 1):
            progress.update_progress(i, len(trial_names), f"Trial family: {trial_name}")
            logger.info(f"Searching for trial family: {trial_name}")
            pmids = self.pubmed.search(
                f"{drug_name} {trial_name}",
                max_results=30
            )
            self.all_pmids.update(pmids)

            # Search for extensions
            ext_pmids = self.pubmed.search(
                f"{drug_name} {trial_name} extension",
                max_results=20
            )
            self.all_pmids.update(ext_pmids)
            # Note: Rate limiting handled by PubMedAPI._rate_limit()

        logger.info(f"After trial family search: {len(self.all_pmids)} unique PMIDs")
        progress.complete_phase('trial_family_search')

        # Phase 3: Web search for additional papers (if available)
        web_papers = []
        if self.web_search:
            progress.start_phase('web_search', 'Searching web for additional papers')
            logger.info("Phase 3: Searching web for additional papers...")
            web_papers = self._search_with_web(drug_name, disease_indication)
            logger.info(f"  Found {len(web_papers)} additional papers from web search")
            structured_log.log_event('web_search_complete', {'papers_found': len(web_papers)})
            progress.complete_phase('web_search')

        # Phase 4: Fetch all article details
        progress.start_phase('fetch_articles', 'Fetching article details')
        logger.info("Phase 4: Fetching article details...")
        articles = self._fetch_all_articles(list(self.all_pmids))
        logger.info(f"Retrieved details for {len(articles)} articles")

        # Add web papers to articles
        articles.extend(web_papers)
        logger.info(f"  Total papers: {len(articles)}")
        structured_log.log_event('articles_fetched', {'total_articles': len(articles)})
        progress.complete_phase('fetch_articles')

        # Phase 4.5: Filter for drug relevance
        progress.start_phase('filter_relevance', 'Filtering for drug relevance')
        logger.info("Phase 4.5: Filtering for drug relevance...")
        articles_before_filter = len(articles)
        articles = self._filter_drug_relevant_papers(articles, drug_name)
        filtered_count = articles_before_filter - len(articles)
        logger.info(f"  Filtered out {filtered_count} irrelevant papers, {len(articles)} remaining")
        structured_log.log_event('relevance_filter_complete', {
            'filtered_out': filtered_count,
            'remaining': len(articles)
        })
        progress.complete_phase('filter_relevance')

        # Phase 5: Match papers to known trials
        progress.start_phase('match_trials', 'Matching papers to trials')
        logger.info("Phase 5: Matching papers to trials...")
        self._match_papers_to_trials(articles, known_trial_names)
        progress.complete_phase('match_trials')

        # Phase 6: Enrich with links
        progress.start_phase('enrich_links', 'Enriching papers with links')
        logger.info("Phase 6: Enriching papers with links...")
        articles = self._enrich_with_links(articles)
        progress.complete_phase('enrich_links')

        # Phase 7: Categorize papers
        progress.start_phase('categorize', 'Categorizing papers')
        logger.info("Phase 7: Categorizing papers...")
        categorized = self._categorize_papers(articles)
        progress.complete_phase('categorize')

        # Phase 8: Generate detailed summaries
        progress.start_phase('generate_summaries', 'Generating detailed summaries')
        logger.info("Phase 8: Generating detailed summaries...")
        self._add_detailed_summaries(articles)

        # Re-categorize with summaries
        categorized = self._categorize_papers(articles)
        structured_log.log_event('summaries_generated', {'total_articles': len(articles)})
        progress.complete_phase('generate_summaries')

        # Phase 9: Build cross-references and trial families
        progress.start_phase('cross_references', 'Building cross-references')
        logger.info("Phase 9: Building cross-references...")
        cross_refs, trial_families = self._build_cross_references(articles)
        progress.complete_phase('cross_references')

        # Phase 10: Search ClinicalTrials.gov for ongoing trials
        ct_trials = []
        ongoing_trials = []
        if self.ct_api:
            progress.start_phase('clinicaltrials_search', 'Searching ClinicalTrials.gov')
            logger.info("Phase 10: Searching ClinicalTrials.gov...")
            ct_trials = self._search_clinicaltrials(drug_name)
            ongoing_trials = self._find_ongoing_trials(drug_name)
            logger.info(f"  Found {len(ongoing_trials)} ongoing trials")
            structured_log.log_event('clinicaltrials_search_complete', {
                'trials_found': len(ct_trials),
                'ongoing_trials': len(ongoing_trials)
            })
            progress.complete_phase('clinicaltrials_search')

        # Phase 11: Organize papers by disease
        progress.start_phase('organize_by_disease', 'Organizing papers by disease')
        logger.info("Phase 11: Organizing papers by disease...")
        by_disease, disease_agnostic = self._categorize_by_disease(articles)
        progress.complete_phase('organize_by_disease')

        # Compile results
        elapsed = time.time() - start_time

        # Get token usage statistics
        token_stats = self.api_client.token_tracker.get_summary()
        parse_stats = self.json_parser.get_stats()

        results = {
            'metadata': {
                'drug_name': drug_name,
                'disease_indication': disease_indication,
                'drug_class': drug_class,
                'search_date': datetime.now().isoformat(),
                'total_unique_papers': len(articles),
                'total_searches': len(self.search_log),
                'elapsed_seconds': round(elapsed, 2),
                'paper_sources': dict(self.paper_sources),
                'ongoing_trials_count': len(ongoing_trials),
                'filtered_papers_count': filtered_count,
                'token_usage': token_stats,
                'parse_statistics': parse_stats
            },
            'search_log': self.search_log,
            'discovered_trial_names': list(known_trial_names),
            'discovered_indications': discovered_indications,
            'categorized_papers': categorized,
            'papers_by_disease': by_disease,
            'disease_agnostic_papers': disease_agnostic,
            'trial_families': trial_families,
            'cross_references': cross_refs,
            'clinicaltrials_gov': ct_trials,
            'ongoing_trials': ongoing_trials
        }

        # Save results
        progress.start_phase('save_results', 'Saving results')
        logger.info("Saving results...")
        self._save_results(results, drug_name)
        progress.complete_phase('save_results')

        # Log completion
        structured_log.log_event('workflow_complete', {
            'elapsed_seconds': elapsed,
            'total_papers': len(articles),
            'token_usage': token_stats,
            'parse_success_rate': parse_stats.get('success_rate', 0)
        })

        # Print summary
        logger.info(f"\n{'='*80}")
        logger.info(f"PaperScope 2.0 Complete!")
        logger.info(f"{'='*80}")
        logger.info(f"Time elapsed: {elapsed:.1f}s")
        logger.info(f"Papers found: {len(articles)}")
        # token_stats is a formatted string from TokenUsageTracker.get_summary()
        logger.info(f"Token usage:\n{token_stats}")
        logger.info(f"Parse success rate: {parse_stats.get('success_rate', 0):.1%}")
        logger.info(f"{'='*80}\n")

        return results
    
    def _detect_drug_context(self, drug_name: str) -> Dict[str, Optional[str]]:
        """
        Auto-detect disease indication and drug class using Claude.

        Args:
            drug_name: Drug name

        Returns:
            Dictionary with 'disease' and 'drug_class' keys
        """
        logger.info("Auto-detecting drug context using Claude...")

        # Quick search to get context
        pmids = self.pubmed.search(
            f"{drug_name} clinical trial",
            max_results=20
        )

        if not pmids:
            return {'disease': None, 'drug_class': None}

        # Fetch sample articles
        articles = self.pubmed.fetch_abstracts(pmids[:5])

        # Format papers for prompt
        papers_text = self._format_papers_for_prompt(articles, max_abstract_length=500)

        # Use PromptBuilder for consistent prompts
        prompt = self.prompt_builder.build_prompt(
            'detect_context',
            drug_name=drug_name,
            papers_text=papers_text
        )

        # Fallback to legacy prompt if PromptBuilder doesn't have this template yet
        if not prompt or 'detect_context' not in self.prompt_builder.templates:
            prompt = f"""Analyze these papers about {drug_name} and extract:

1. Primary disease indication (be specific, e.g., "Rheumatoid Arthritis", "Non-Small Cell Lung Cancer")
2. Drug class/modality (e.g., "Monoclonal Antibody", "JAK Inhibitor", "Small Molecule")

Papers:
{papers_text}

Respond in JSON format:
{{
    "disease": "disease name or null",
    "drug_class": "drug class or null"
}}"""

        try:
            # Use APIClient for robust API calls
            response_text = self.api_client.call_claude(
                prompt=prompt,
                max_tokens=200,
                timeout=self.config.api_timeout
            )

            # Use ClaudeResponseParser for robust JSON parsing
            try:
                data = self.json_parser.parse_json_response(
                    response_text,
                    expected_type=dict
                )
                return {
                    'disease': data.get('disease'),
                    'drug_class': data.get('drug_class')
                }
            except Exception as e:
                logger.error(f"Failed to parse context from Claude response: {e}")

        except Exception as e:
            logger.error(f"Error detecting context with Claude: {e}")

        return {'disease': None, 'drug_class': None}

    def _search_with_web(
        self,
        drug_name: str,
        disease_indication: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Use web search to find papers not in PubMed.

        Searches for:
        - Preprints (bioRxiv, medRxiv)
        - Conference abstracts
        - Journal articles not yet indexed
        - Real-world registries

        Args:
            drug_name: Drug name
            disease_indication: Optional disease indication

        Returns:
            List of paper dictionaries
        """
        if not self.web_search:
            return []

        logger.info("  Searching web for additional papers...")

        # Build search queries
        queries = [
            f"{drug_name} clinical trial results publication",
            f"{drug_name} phase 3 trial publication",
            f"{drug_name} bioRxiv medRxiv preprint",
            f"{drug_name} conference abstract ACR EULAR",
            f"{drug_name} real-world evidence study",
        ]

        if disease_indication:
            queries.extend([
                f"{drug_name} {disease_indication} clinical trial",
                f"{drug_name} {disease_indication} real-world",
            ])

        all_results = []
        for query in queries:
            try:
                results = self.web_search.search(
                    query,
                    max_results=10,
                    search_depth="advanced"
                )
                all_results.extend(results)
                time.sleep(0.5)  # Rate limiting
            except Exception as e:
                logger.error(f"Web search error for '{query}': {e}")

        if not all_results:
            return []

        # Use Claude to extract paper information
        papers = self._extract_papers_from_web_results(all_results, drug_name)

        # Track sources
        for paper in papers:
            source = paper.get('source', 'web_search')
            self.paper_sources[source] += 1

        return papers

    def _extract_papers_from_web_results(
        self,
        results: List[Dict],
        drug_name: str
    ) -> List[Dict[str, Any]]:
        """
        Extract paper information from web search results using Claude.

        Args:
            results: Web search results
            drug_name: Drug name for filtering

        Returns:
            List of paper dictionaries
        """
        # Format results for Claude
        formatted_results = self.web_search.format_for_llm(results)

        prompt = f"""Extract information about scientific papers related to {drug_name} from these search results.

Search Results:
{formatted_results}

For each relevant paper, extract:
- title: Paper title
- authors: Author list (if available)
- journal: Journal or source name
- year: Publication year
- url: Direct link to paper
- pmid: PubMed ID (if mentioned)
- doi: DOI (if available)
- source: Source type (e.g., "bioRxiv", "medRxiv", "conference_abstract", "journal", "registry")
- abstract: Brief description or abstract snippet (if available)

Only include papers that are:
1. Directly about {drug_name}
2. Scientific/clinical in nature (not news articles or press releases)
3. Have sufficient information to be useful

Return as JSON array:
[
  {{
    "title": "...",
    "authors": "...",
    "journal": "...",
    "year": "2024",
    "url": "...",
    "pmid": "...",
    "doi": "...",
    "source": "bioRxiv",
    "abstract": "..."
  }},
  ...
]

If no relevant papers found, return empty array: []
"""

        try:
            # Use APIClient for robust API calls
            response_text = self.api_client.call_claude(
                prompt=prompt,
                max_tokens=4000,
                timeout=self.config.api_timeout
            )

            # Use ClaudeResponseParser for robust JSON parsing
            try:
                papers = self.json_parser.parse_json_response(
                    response_text,
                    expected_type=list
                )
                logger.info(f"  Extracted {len(papers)} papers from web results")
                return papers
            except Exception as e:
                logger.error(f"Failed to parse papers from web results: {e}")

        except Exception as e:
            logger.error(f"Error extracting papers from web results: {e}")

        return []

    def _find_ongoing_trials(self, drug_name: str) -> List[Dict[str, Any]]:
        """
        Find ongoing trials from ClinicalTrials.gov.

        Args:
            drug_name: Drug name

        Returns:
            List of ongoing trial dictionaries
        """
        if not self.ct_api:
            return []

        logger.info("  Searching for ongoing trials...")

        try:
            # Search for recruiting/active trials
            trials = self.ct_api.search_studies(
                query=drug_name,
                max_results=50
            )

            ongoing = []
            for trial in trials:
                status = trial.get('status', '').upper()

                # Filter for ongoing trials
                if status in ['RECRUITING', 'ACTIVE_NOT_RECRUITING', 'ENROLLING_BY_INVITATION', 'NOT_YET_RECRUITING']:
                    ongoing.append({
                        'nct_id': trial.get('nct_id'),
                        'title': trial.get('title'),
                        'phase': trial.get('phase'),
                        'status': trial.get('status'),
                        'enrollment': trial.get('enrollment'),
                        'start_date': trial.get('start_date'),
                        'completion_date': trial.get('completion_date'),
                        'primary_completion_date': trial.get('primary_completion_date'),
                        'conditions': trial.get('conditions', []),
                        'interventions': trial.get('interventions', []),
                        'url': f"https://clinicaltrials.gov/study/{trial.get('nct_id')}"
                    })

            logger.info(f"  Found {len(ongoing)} ongoing trials")
            return ongoing

        except Exception as e:
            logger.error(f"Error finding ongoing trials: {e}")
            return []

    def _enrich_with_links(self, articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Add direct links to papers.

        Args:
            articles: List of article dictionaries

        Returns:
            Enriched articles with links
        """
        for article in articles:
            pmid = article.get('pmid')
            doi = article.get('doi')
            pmc = article.get('pmc')
            url = article.get('url')  # From web search

            # Build links
            links = []

            if url:
                links.append(url)

            if pmid:
                links.append(f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/")

            if pmc:
                links.append(f"https://pmc.ncbi.nlm.nih.gov/articles/{pmc}/")

            if doi:
                links.append(f"https://doi.org/{doi}")

            article['links'] = links
            article['primary_link'] = links[0] if links else None

            # Track source
            if not article.get('source'):
                if pmid:
                    article['source'] = 'pubmed'
                    self.paper_sources['pubmed'] += 1

        return articles

    def _build_search_sequence(
        self,
        drug_name: str,
        disease: Optional[str],
        drug_class: Optional[str]
    ) -> List[Dict[str, Any]]:
        """
        Build adaptive search sequence based on drug context.

        Args:
            drug_name: Drug name
            disease: Disease indication
            drug_class: Drug class

        Returns:
            List of search dictionaries
        """
        searches = []
        search_id = 1

        # Core discovery
        searches.append({
            'id': search_id,
            'query': f'{drug_name} clinical trials published',
            'purpose': 'initial_discovery',
            'max_results': 100
        })
        search_id += 1

        # Disease-specific if available
        if disease:
            searches.append({
                'id': search_id,
                'query': f'{drug_name} {disease} clinical trial',
                'purpose': 'disease_specific',
                'max_results': 50
            })
            search_id += 1

        # Phase-specific searches
        for phase in ['phase 3', 'phase 2', 'phase 1']:
            searches.append({
                'id': search_id,
                'query': f'{drug_name} {phase} trial',
                'purpose': f'{phase.replace(" ", "_")}_identification',
                'max_results': 50 if phase == 'phase 3' else 40
            })
            search_id += 1

        # Extensions and pooled analyses
        searches.extend([
            {
                'id': search_id,
                'query': f'{drug_name} phase 3 extension long-term',
                'purpose': 'phase_3_extensions',
                'max_results': 30
            },
            {
                'id': search_id + 1,
                'query': f'{drug_name} pooled analysis post-hoc',
                'purpose': 'pooled_posthoc_analyses',
                'max_results': 30
            }
        ])
        search_id += 2

        # Preclinical/mechanistic
        searches.append({
            'id': search_id,
            'query': f'{drug_name} preclinical mechanism action',
            'purpose': 'preclinical_mechanism',
            'max_results': 30
        })
        search_id += 1

        # Biomarker studies
        searches.extend([
            {
                'id': search_id,
                'query': f'{drug_name} biomarker predictive',
                'purpose': 'biomarker_studies',
                'max_results': 30
            },
            {
                'id': search_id + 1,
                'query': f'{drug_name} pharmacodynamics gene expression',
                'purpose': 'biomarker_validation',
                'max_results': 30
            }
        ])
        search_id += 2

        # Subgroup analyses
        searches.extend([
            {
                'id': search_id,
                'query': f'{drug_name} subgroup analysis ethnicity race',
                'purpose': 'subgroup_ethnicity',
                'max_results': 30
            },
            {
                'id': search_id + 1,
                'query': f'{drug_name} subgroup disease severity baseline',
                'purpose': 'subgroup_disease_characteristics',
                'max_results': 30
            },
            {
                'id': search_id + 2,
                'query': f'{drug_name} concomitant medication combination therapy',
                'purpose': 'subgroup_concomitant',
                'max_results': 30
            }
        ])
        search_id += 3

        # Real-world and safety
        searches.extend([
            {
                'id': search_id,
                'query': f'{drug_name} real-world evidence observational',
                'purpose': 'real_world_data',
                'max_results': 50
            },
            {
                'id': search_id + 1,
                'query': f'{drug_name} meta-analysis systematic review',
                'purpose': 'reviews',
                'max_results': 30
            },
            {
                'id': search_id + 2,
                'query': f'{drug_name} safety adverse events pharmacovigilance',
                'purpose': 'safety_focused',
                'max_results': 30
            }
        ])
        search_id += 3

        # Special populations
        searches.extend([
            {
                'id': search_id,
                'query': f'{drug_name} elderly aged geriatric',
                'purpose': 'special_population_elderly',
                'max_results': 20
            },
            {
                'id': search_id + 1,
                'query': f'{drug_name} pediatric children adolescent',
                'purpose': 'special_population_pediatric',
                'max_results': 20
            },
            {
                'id': search_id + 2,
                'query': f'{drug_name} renal impairment hepatic impairment',
                'purpose': 'special_population_organ_impairment',
                'max_results': 20
            }
        ])
        search_id += 3

        # PK/PD and drug interactions
        searches.extend([
            {
                'id': search_id,
                'query': f'{drug_name} pharmacokinetics pharmacodynamics',
                'purpose': 'pk_pd_studies',
                'max_results': 30
            },
            {
                'id': search_id + 1,
                'query': f'{drug_name} drug interaction',
                'purpose': 'drug_interactions',
                'max_results': 20
            }
        ])

        return searches

    def _fetch_all_articles(self, pmids: List[str]) -> List[Dict[str, Any]]:
        """
        Fetch article details for all PMIDs in batches.

        Args:
            pmids: List of PMIDs

        Returns:
            List of article dictionaries
        """
        articles = []
        batch_size = 50

        for i in range(0, len(pmids), batch_size):
            batch = pmids[i:i+batch_size]
            logger.info(f"  Fetching batch {i//batch_size + 1} ({len(batch)} articles)...")

            batch_articles = self.pubmed.fetch_abstracts(batch)

            # Add trial names and phase classification
            for article in batch_articles:
                text = f"{article.get('title', '')} {article.get('abstract', '')}".lower()
                article['trial_names'] = self._extract_trial_names_from_text(text)
                article['phase'] = self._classify_phase(text)
                article['study_type'] = self._classify_study_type(text)

            articles.extend(batch_articles)
            # Note: Rate limiting handled by PubMedAPI._rate_limit()

        return articles

    def _extract_trial_names_from_sample(self, pmids: List[str]) -> Set[str]:
        """
        Extract trial names from a sample of articles.

        Args:
            pmids: List of PMIDs to sample

        Returns:
            Set of trial names
        """
        articles = self.pubmed.fetch_abstracts(pmids[:20])

        all_trial_names = set()
        for article in articles:
            text = f"{article.get('title', '')} {article.get('abstract', '')}".lower()
            trial_names = self._extract_trial_names_from_text(text)
            all_trial_names.update(trial_names)

        return all_trial_names

    def _extract_trial_names_from_text(self, text: str) -> List[str]:
        """
        Extract trial names from text using generic patterns.

        Args:
            text: Text to search

        Returns:
            List of trial names
        """
        trial_names = set()
        text_upper = text.upper()

        # Apply all generic patterns
        for pattern in self.TRIAL_PATTERNS:
            matches = re.findall(pattern, text_upper)
            trial_names.update(matches)

        # Filter out common false positives
        exclude = {
            'THE', 'AND', 'FOR', 'WITH', 'FROM', 'THAT', 'THIS',
            'ALL', 'ARE', 'WAS', 'HAD', 'NOT', 'BUT', 'WHO', 'CAN',
            'RCT', 'FDA', 'EMA', 'USA', 'COVID', 'HIV', 'AIDS',
            'DNA', 'RNA', 'METHODS', 'RESULTS', 'BACKGROUND',
            'CONCLUSIONS', 'OBJECTIVE', 'DESIGN', 'SETTING'
        }

        filtered = []
        for name in trial_names:
            if len(name) >= 3 and name not in exclude and not name.isdigit():
                filtered.append(name)

        return filtered

    def _classify_phase(self, text: str) -> str:
        """Classify clinical trial phase from text."""
        if re.search(r'preclinical|in vitro|animal model|mechanism of action', text):
            return 'Preclinical'
        elif re.search(r'phase\s*i\b|phase\s*1\b|first.in.human', text):
            return 'Phase 1'
        elif re.search(r'phase\s*iib|phase\s*2b', text):
            return 'Phase 2b'
        elif re.search(r'phase\s*ii\b|phase\s*2\b', text):
            return 'Phase 2'
        elif re.search(r'phase\s*iii\b|phase\s*3\b', text):
            return 'Phase 3'
        elif re.search(r'real.world|post.marketing|observational|registry', text):
            return 'Post-marketing'
        elif re.search(r'extension|long.term', text):
            return 'Extension'
        elif re.search(r'meta.analysis|systematic review', text):
            return 'Review/Meta-analysis'
        else:
            return 'Other'

    def _classify_study_type(self, text: str) -> str:
        """Classify study type from text."""
        if re.search(r'randomized|randomised|rct|placebo.controlled', text):
            return 'RCT'
        elif re.search(r'open.label', text):
            return 'Open-label'
        elif re.search(r'observational|cohort|case.control', text):
            return 'Observational'
        elif re.search(r'case report|case series', text):
            return 'Case series'
        elif re.search(r'meta.analysis', text):
            return 'Meta-analysis'
        elif re.search(r'systematic review|review', text):
            return 'Review'
        else:
            return 'Other'

    def _categorize_papers(self, articles: List[Dict[str, Any]]) -> Dict[str, List[Dict]]:
        """
        Categorize papers using Claude in batches for efficiency.

        Args:
            articles: List of article dictionaries

        Returns:
            Dictionary mapping category names to lists of articles
        """
        logger.info(f"Categorizing {len(articles)} papers using Claude...")
        categorized = {category: [] for category in self.CATEGORIES}

        # Split into batches
        batches = [articles[i:i+self.batch_size] for i in range(0, len(articles), self.batch_size)]

        # Use parallel processing if enabled and multiple batches
        if self.config.enable_parallel and len(batches) > 1:
            logger.info(f"  Processing {len(batches)} batches in parallel (max {self.config.max_workers} workers)...")
            parallel = ParallelProcessor(max_workers=self.config.max_workers)
            batch_results = parallel.map(self._classify_batch_with_claude, batches)

            # Assign to categories
            for batch, batch_classifications in zip(batches, batch_results):
                for article, categories in zip(batch, batch_classifications):
                    article['categories'] = categories  # Store for reference
                    for category in categories:
                        if category in categorized:
                            categorized[category].append(article)
        else:
            # Sequential processing
            for i, batch in enumerate(batches, 1):
                logger.info(f"  Processing batch {i}/{len(batches)}")
                batch_classifications = self._classify_batch_with_claude(batch)

                # Assign to categories
                for article, categories in zip(batch, batch_classifications):
                    article['categories'] = categories  # Store for reference
                    for category in categories:
                        if category in categorized:
                            categorized[category].append(article)

        # Sort each category by year (descending)
        for category in categorized:
            categorized[category].sort(
                key=lambda x: x.get('year', '0'),
                reverse=True
            )

        return categorized

    def _categorize_by_disease(
        self,
        papers: List[Dict[str, Any]]
    ) -> tuple[Dict[str, Dict[str, List[Dict]]], Dict[str, List[Dict]]]:
        """
        Categorize papers by disease first, then by phase/category.

        Args:
            papers: List of paper dictionaries with 'categories' and 'indication' fields

        Returns:
            Tuple of (by_disease, disease_agnostic)
            - by_disease: Dict[disease][category] = [papers]
            - disease_agnostic: Dict[category] = [papers]
        """
        # Define disease-agnostic categories
        disease_agnostic_categories = {
            'Preclinical/Mechanistic Studies',
            'Pharmacokinetics/Pharmacodynamics',
            'Drug Interactions',
            'Systematic Reviews/Meta-analyses',
            'Economic/Cost-effectiveness Studies',
            'Other'
        }

        by_disease = defaultdict(lambda: defaultdict(list))
        disease_agnostic = defaultdict(list)

        for paper in papers:
            # Get indication from structured_summary
            indication = None
            structured_summary = paper.get('structured_summary', {})
            if isinstance(structured_summary, dict):
                indication = structured_summary.get('indication')

            # Fallback to 'Unknown Indication' if not found
            if not indication or indication == 'Unknown':
                indication = 'Unknown Indication'

            # Get categories
            categories = paper.get('categories', [])
            if isinstance(categories, str):
                try:
                    categories = json.loads(categories)
                except:
                    categories = [categories]

            # Categorize each paper by its categories
            for category in categories:
                if category in disease_agnostic_categories:
                    # Disease-agnostic paper
                    disease_agnostic[category].append(paper)
                else:
                    # Disease-specific paper
                    by_disease[indication][category].append(paper)

        # Convert defaultdicts to regular dicts for JSON serialization
        by_disease_dict = {
            disease: dict(categories)
            for disease, categories in by_disease.items()
        }
        disease_agnostic_dict = dict(disease_agnostic)

        # Log summary
        logger.info(f"Disease-based categorization:")
        logger.info(f"  Disease-specific: {len(by_disease_dict)} diseases")
        for disease in sorted(by_disease_dict.keys()):
            total_papers = sum(len(papers) for papers in by_disease_dict[disease].values())
            logger.info(f"    {disease}: {total_papers} papers across {len(by_disease_dict[disease])} categories")
        logger.info(f"  Disease-agnostic: {sum(len(papers) for papers in disease_agnostic_dict.values())} papers across {len(disease_agnostic_dict)} categories")

        return by_disease_dict, disease_agnostic_dict

    def _classify_batch_with_claude(self, batch: List[Dict[str, Any]]) -> List[List[str]]:
        """
        Classify a batch of articles using Claude.

        Args:
            batch: List of article dictionaries

        Returns:
            List of category lists (one per article)
        """
        # Format papers for prompt
        papers_text = self._format_papers_for_prompt(batch, max_abstract_length=800)

        # Build classification rules
        classification_rules = """
CRITICAL CLASSIFICATION RULES:

1. **Phase 1/2/3 - Primary Trials**: ONLY for papers reporting PRIMARY results of a clinical trial
   - Must be the FIRST publication of trial results
   - Must report prospectively defined primary/secondary endpoints
   - Examples: "Phase 3 trial of X", "Randomized controlled trial", "Efficacy and safety of X: results from Y trial"
   - NOT for: reviews, subanalyses, post-hoc analyses, pooled analyses

2. **Phase 3 - Pooled/Post-hoc Analyses**: For secondary analyses of completed trials
   - Pooled analyses combining multiple trials
   - Post-hoc analyses (not pre-specified)
   - Examples: "Pooled analysis of X trials", "Post-hoc analysis of Y"

3. **Subgroup Analyses**: For analyses focusing on specific patient subgroups
   - Must explicitly analyze a subgroup (e.g., "in Japanese patients", "in elderly patients")
   - Examples: "Efficacy in Japanese patients: TULIP-2 subanalysis"
   - Use appropriate subcategory: Demographics, Disease Characteristics, or Concomitant Medications

4. **Systematic Reviews/Meta-analyses**: For review papers
   - Systematic reviews, meta-analyses, narrative reviews
   - Papers that REVIEW or SUMMARIZE multiple studies
   - Examples: "An overview from clinical trials", "Current knowledge and future considerations"
   - Keywords: "review", "overview", "meta-analysis", "systematic review"

5. **Phase 3 - Long-term Extensions**: For open-label extension studies
   - Long-term follow-up beyond primary trial period
   - Open-label extensions (OLE)
   - Examples: "Long-term safety", "52-week extension", "Open-label extension"

6. **Biomarker Studies**: For studies examining biomarkers/predictive factors
   - Must focus on biomarkers, gene expression, predictive factors
   - Examples: "Biomarker analysis", "Gene signature", "Predictive factors"

7. **Post-marketing/Real-world**: For observational studies after drug approval
   - Real-world evidence, registry studies, observational cohorts
   - NOT randomized controlled trials
   - Examples: "Real-world effectiveness", "Registry study", "Observational cohort"

IMPORTANT:
- Reviews and subanalyses should NEVER be classified as "Phase 1/2/3 - Primary Trials"
- Only the FIRST publication of trial results goes in "Primary Trials"
- Subanalyses go in "Subgroup Analyses" categories
- Reviews go in "Systematic Reviews/Meta-analyses"
"""

        # Use PromptBuilder for consistent prompts
        prompt = self.prompt_builder.build_prompt(
            'categorize',
            papers_text=papers_text,
            categories_list='\n'.join([f"- {cat}" for cat in self.CATEGORIES]),
            num_papers=len(batch),
            classification_rules=classification_rules
        )

        try:
            # Use APIClient for robust API calls
            response_text = self.api_client.call_claude(
                prompt=prompt,
                max_tokens=self.config.max_tokens_categorize,
                timeout=self.config.api_timeout
            )

            # Use ClaudeResponseParser for robust JSON parsing
            classifications = self.json_parser.parse_json_response(
                response_text,
                expected_type=list
            )

            # Build result list
            result = []
            for item in classifications:
                categories = item.get('categories', ['Other'])
                result.append(categories)

            # Pad with 'Other' if needed
            while len(result) < len(batch):
                result.append(['Other'])

            return result[:len(batch)]

        except Exception as e:
            logger.error(f"Error classifying batch with Claude: {e}")

        # Fallback: use regex-based classification
        return [self._classify_article_regex(article) for article in batch]

    def _classify_article_regex(self, article: Dict[str, Any]) -> List[str]:
        """
        Fallback regex-based classification.

        Args:
            article: Article dictionary

        Returns:
            List of category names
        """
        text = f"{article.get('title', '')} {article.get('abstract', '')}".lower()
        categories = []

        # Basic phase detection
        if re.search(r'preclinical|animal model', text):
            categories.append('Preclinical/Mechanistic')
        elif re.search(r'phase\s*i\b|phase\s*1\b', text):
            categories.append('Phase 1')
        elif re.search(r'phase\s*ii\b|phase\s*2\b', text):
            categories.append('Phase 2')
        elif re.search(r'phase\s*iii\b|phase\s*3\b', text):
            categories.append('Phase 3 - Primary Trials')
        elif re.search(r'real.world|observational', text):
            categories.append('Post-marketing/Real-world')
        elif re.search(r'meta.analysis|systematic review', text):
            categories.append('Systematic Reviews/Meta-analyses')

        if not categories:
            categories.append('Other')

        return categories

    def _add_detailed_summaries(self, articles: List[Dict[str, Any]]):
        """
        Generate detailed summaries using Claude in batches.

        Args:
            articles: List of article dictionaries (modified in place)
        """
        logger.info(f"Generating detailed summaries for {len(articles)} papers using Claude...")

        # Split into batches
        batches = [articles[i:i+self.batch_size] for i in range(0, len(articles), self.batch_size)]

        # Use parallel processing if enabled and multiple batches
        if self.config.enable_parallel and len(batches) > 1:
            logger.info(f"  Processing {len(batches)} batches in parallel (max {self.config.max_workers} workers)...")
            parallel = ParallelProcessor(max_workers=self.config.max_workers)
            batch_results = parallel.map(self._generate_detailed_summaries_batch, batches)

            # Assign summaries
            for batch, batch_summaries in zip(batches, batch_results):
                for article, summary_data in zip(batch, batch_summaries):
                    article['detailed_summary'] = summary_data.get('summary', '')
                    article['key_takeaways'] = summary_data.get('takeaways', [])
                    article['structured_summary'] = summary_data.get('structured_summary', {})
        else:
            # Sequential processing
            for i, batch in enumerate(batches, 1):
                logger.info(f"  Processing batch {i}/{len(batches)}")
                batch_summaries = self._generate_detailed_summaries_batch(batch)

                for article, summary_data in zip(batch, batch_summaries):
                    article['detailed_summary'] = summary_data.get('summary', '')
                    article['key_takeaways'] = summary_data.get('takeaways', [])
                    article['structured_summary'] = summary_data.get('structured_summary', {})

        # NEW: Download full-text content for papers with PMIDs
        logger.info(f"Downloading full-text content for papers with PMIDs...")
        self._download_full_text_content(articles)

    def _format_papers_for_prompt(
        self,
        batch: List[Dict[str, Any]],
        max_abstract_length: int = 2000
    ) -> str:
        """
        Format papers for inclusion in prompts.

        Args:
            batch: List of article dictionaries
            max_abstract_length: Maximum length for abstracts

        Returns:
            Formatted string with papers
        """
        papers_text = []
        for i, article in enumerate(batch, 1):
            title = article.get('title') or 'N/A'
            abstract = article.get('abstract') or 'N/A'
            # Limit abstract length (handle None case)
            if abstract != 'N/A':
                abstract = abstract[:max_abstract_length]
            papers_text.append(f"{i}. Title: {title}")
            papers_text.append(f"   Abstract: {abstract}")
            papers_text.append("")

        return '\n'.join(papers_text)

    def _generate_detailed_summaries_batch(self, batch: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Generate detailed summaries and takeaways for a batch of articles using Claude.

        Args:
            batch: List of article dictionaries

        Returns:
            List of dictionaries with 'summary' and 'takeaways' keys
        """
        # Build papers text
        papers_text = self._format_papers_for_prompt(batch, max_abstract_length=self.config.max_abstract_length_prompt)

        # Get discovered indications for context
        discovered_indications = getattr(self, 'discovered_indications', [])
        indications_context = ""
        if discovered_indications:
            indications_context = f"\n\nKNOWN INDICATIONS (use these when possible):\n{', '.join(discovered_indications[:10])}"
            if len(discovered_indications) > 10:
                indications_context += f", and {len(discovered_indications) - 10} more"

        # Use PromptBuilder for consistent prompts
        prompt = self.prompt_builder.build_prompt(
            'summarize',
            papers_text=papers_text,
            indications_context=indications_context
        )

        try:
            # Use APIClient for robust API calls with retry logic
            response_text = self.api_client.call_claude(
                prompt=prompt,
                max_tokens=self.config.max_tokens_summary,
                timeout=self.config.api_timeout
            )

            # Use ClaudeResponseParser for robust JSON parsing
            try:
                summaries_data = self.json_parser.parse_json_response(
                    response_text,
                    expected_type=list
                )
            except Exception as e:
                logger.error(f"Failed to parse summaries: {e}")
                # Return empty summaries for this batch
                return [{'summary': '', 'takeaways': [], 'structured_summary': {}} for _ in batch]

            # Process parsed data
            result = []
            for item in summaries_data:
                # Normalize indication against discovered indications
                raw_indication = item.get('indication', 'Unknown')
                discovered_indications = getattr(self, 'discovered_indications', [])

                logger.debug(f"Raw indication: '{raw_indication}', Discovered indications: {discovered_indications[:5]}")

                normalized_indication = self._normalize_indication(
                    raw_indication,
                    discovered_indications
                )

                logger.debug(f"Normalized indication: '{normalized_indication}'")

                # Build structured summary
                structured_summary = {
                    'phase': item.get('phase', 'Unknown'),
                    'trial_name': item.get('trial_name'),
                    'indication': normalized_indication,
                    'patient_population': item.get('patient_population', 'Not specified'),
                    'study_design': item.get('study_design', 'Not specified'),
                    'key_results': item.get('key_results', {}),
                    'safety': item.get('safety', 'Not reported')
                }

                result.append({
                    'summary': item.get('narrative_summary', item.get('summary', 'Study contributed to evidence base.')),
                    'takeaways': item.get('takeaways', ['Study contributed to evidence base']),
                    'structured_summary': structured_summary
                })

            # Pad if needed
            while len(result) < len(batch):
                result.append({
                    'summary': 'Study contributed to evidence base.',
                    'takeaways': ['Study contributed to evidence base'],
                    'structured_summary': {}
                })

            return result[:len(batch)]

        except Exception as e:
            logger.error(f"Error generating detailed summaries with Claude: {e}")

        # Fallback: generate simple summaries
        return [
            {
                'summary': f"Study: {article.get('title') or 'N/A'}",
                'takeaways': [f"Study: {(article.get('title') or 'N/A')[:100]}..."]
            }
            for article in batch
        ]

    def _download_full_text_content(self, articles: List[Dict[str, Any]]):
        """
        Download full-text content for papers with PMIDs.

        This standardizes PaperScope v2 papers with PaperScope v1 format by adding
        'content', 'tables', 'sections', and 'metadata' fields.

        Args:
            articles: List of article dictionaries (modified in place)
        """
        papers_with_pmid = [a for a in articles if a.get('pmid')]

        if not papers_with_pmid:
            logger.info("  No papers with PMIDs to download")
            return

        logger.info(f"  Attempting to download full text for {len(papers_with_pmid)} papers...")

        success_count = 0
        failed_count = 0

        for article in papers_with_pmid:
            pmid = article.get('pmid')

            try:
                # Check PMC availability
                pmc_map = self.pubmed.check_pmc_availability([pmid])
                pmcid = pmc_map.get(pmid)

                if pmcid:
                    # Download full text from PMC
                    fulltext_xml = self.pubmed.fetch_pmc_fulltext(pmcid)

                    if fulltext_xml:
                        # Parse full text
                        parsed = self.pubmed._parse_pmc_fulltext(fulltext_xml, pmid, pmcid)

                        if parsed and parsed.get('content'):
                            # Add full-text fields to article
                            article['content'] = parsed.get('content')
                            article['tables'] = parsed.get('tables', [])
                            article['sections'] = parsed.get('sections', {})
                            article['metadata'] = parsed.get('metadata', {})

                            success_count += 1
                            logger.debug(f"    ✓ Downloaded full text for PMID {pmid}")
                        else:
                            failed_count += 1
                            logger.debug(f"    ✗ Failed to parse full text for PMID {pmid}")
                    else:
                        failed_count += 1
                        logger.debug(f"    ✗ Failed to fetch full text for PMID {pmid}")
                else:
                    failed_count += 1
                    logger.debug(f"    ✗ No PMC ID available for PMID {pmid}")

            except Exception as e:
                failed_count += 1
                logger.debug(f"    ✗ Error downloading PMID {pmid}: {e}")

        logger.info(f"  Full-text download complete: {success_count} successful, {failed_count} failed/unavailable")

    def _build_cross_references(
        self,
        articles: List[Dict[str, Any]]
    ) -> Tuple[Dict[str, Dict], Dict[str, Dict]]:
        """
        Build cross-reference system and trial families.

        Args:
            articles: List of article dictionaries

        Returns:
            Tuple of (cross_references, trial_families)
        """
        cross_references = {}
        trial_families = defaultdict(lambda: {
            'primary': [],
            'extensions': [],
            'post_hoc': [],
            'subgroup': [],
            'related': []
        })

        # Group articles by trial name
        trial_name_to_articles = defaultdict(list)

        for article in articles:
            pmid = article.get('pmid')
            trial_names = article.get('trial_names', [])

            for trial_name in trial_names:
                trial_name_to_articles[trial_name].append(article)

        # Build trial families
        for trial_name, trial_articles in trial_name_to_articles.items():
            for article in trial_articles:
                pmid = article.get('pmid')
                text = f"{article.get('title', '')} {article.get('abstract', '')}".lower()

                if re.search(r'extension|long.term', text):
                    trial_families[trial_name]['extensions'].append(pmid)
                    article_type = 'extension'
                elif re.search(r'pooled|post.hoc|post hoc|combined analysis', text):
                    trial_families[trial_name]['post_hoc'].append(pmid)
                    article_type = 'post_hoc'
                elif re.search(r'subgroup|subset', text):
                    trial_families[trial_name]['subgroup'].append(pmid)
                    article_type = 'subgroup'
                elif re.search(r'phase\s*(?:iii|3|ii|2)', text):
                    trial_families[trial_name]['primary'].append(pmid)
                    article_type = 'primary'
                else:
                    trial_families[trial_name]['related'].append(pmid)
                    article_type = 'related'

                if pmid not in cross_references:
                    cross_references[pmid] = {
                        'trial_family': trial_name,
                        'article_type': article_type,
                        'related_articles': [],
                        'parent_article': None,
                        'child_articles': []
                    }

        # Link parent-child relationships
        for trial_name, family in trial_families.items():
            for primary_pmid in family['primary']:
                if primary_pmid in cross_references:
                    cross_references[primary_pmid]['child_articles'].extend(
                        [{'pmid': ext, 'type': 'extension'} for ext in family['extensions']]
                    )
                    cross_references[primary_pmid]['child_articles'].extend(
                        [{'pmid': ph, 'type': 'post_hoc'} for ph in family['post_hoc']]
                    )
                    cross_references[primary_pmid]['child_articles'].extend(
                        [{'pmid': sg, 'type': 'subgroup'} for sg in family['subgroup']]
                    )

            # Set parent for extensions/post-hoc/subgroups
            for ext_pmid in family['extensions']:
                if ext_pmid in cross_references and family['primary']:
                    cross_references[ext_pmid]['parent_article'] = family['primary'][0]

            for ph_pmid in family['post_hoc']:
                if ph_pmid in cross_references and family['primary']:
                    cross_references[ph_pmid]['parent_article'] = family['primary']

            for sg_pmid in family['subgroup']:
                if sg_pmid in cross_references and family['primary']:
                    cross_references[sg_pmid]['parent_article'] = family['primary']

            # Set related articles
            all_pmids = (family['primary'] + family['extensions'] +
                        family['post_hoc'] + family['subgroup'] + family['related'])

            for pmid in all_pmids:
                if pmid in cross_references:
                    cross_references[pmid]['related_articles'] = [
                        p for p in all_pmids if p != pmid
                    ]

        return dict(cross_references), dict(trial_families)

    def _search_clinicaltrials(self, drug_name: str) -> List[Dict[str, Any]]:
        """
        Search ClinicalTrials.gov for trials.

        Args:
            drug_name: Drug name

        Returns:
            List of trial dictionaries
        """
        if not self.ct_api:
            return []

        try:
            trials = self.ct_api.search_studies(drug_name, max_results=100)
            logger.info(f"Found {len(trials)} trials on ClinicalTrials.gov")
            return trials
        except Exception as e:
            logger.error(f"Error searching ClinicalTrials.gov: {e}")
            return []

    def _save_results(self, results: Dict[str, Any], drug_name: str):
        """
        Save results to JSON file.

        Args:
            results: Results dictionary
            drug_name: Drug name for filename
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{drug_name}_{timestamp}.json"
        filepath = self.output_dir / filename

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        logger.info(f"Results saved to: {filepath}")

        # Also save a summary
        self._save_summary(results, drug_name, timestamp)

    def _save_summary(self, results: Dict[str, Any], drug_name: str, timestamp: str):
        """
        Save a human-readable summary.

        Args:
            results: Results dictionary
            drug_name: Drug name
            timestamp: Timestamp string
        """
        filename = f"{drug_name}_{timestamp}_summary.txt"
        filepath = self.output_dir / filename

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f"PaperScope 2.0 Summary\n")
            f.write(f"{'=' * 80}\n\n")

            metadata = results['metadata']
            f.write(f"Drug: {metadata['drug_name']}\n")
            f.write(f"Disease: {metadata.get('disease_indication', 'N/A')}\n")
            f.write(f"Drug Class: {metadata.get('drug_class', 'N/A')}\n")
            f.write(f"Search Date: {metadata['search_date']}\n")
            f.write(f"Total Papers: {metadata['total_unique_papers']}\n")
            f.write(f"Total Searches: {metadata['total_searches']}\n")
            f.write(f"Elapsed Time: {metadata['elapsed_seconds']}s\n\n")

            f.write(f"Papers by Category\n")
            f.write(f"{'-' * 80}\n")

            categorized = results['categorized_papers']
            for category in self.CATEGORIES:
                count = len(categorized.get(category, []))
                if count > 0:
                    f.write(f"{category}: {count}\n")

            f.write(f"\n")
            f.write(f"Trial Families\n")
            f.write(f"{'-' * 80}\n")

            trial_families = results.get('trial_families', {})
            for trial_name, family in trial_families.items():
                total = (len(family['primary']) + len(family['extensions']) +
                        len(family['post_hoc']) + len(family['subgroup']))
                f.write(f"{trial_name}: {total} papers ")
                f.write(f"(Primary: {len(family['primary'])}, ")
                f.write(f"Extensions: {len(family['extensions'])}, ")
                f.write(f"Post-hoc: {len(family['post_hoc'])}, ")
                f.write(f"Subgroup: {len(family['subgroup'])})\n")

        logger.info(f"Summary saved to: {filepath}")

        # Also save to Excel if pandas is available
        try:
            self._save_to_excel(results, drug_name, timestamp)
        except ImportError:
            logger.warning("pandas not available, skipping Excel export")
        except Exception as e:
            logger.error(f"Error saving to Excel: {e}")

    def _save_to_excel(self, results: Dict[str, Any], drug_name: str, timestamp: str):
        """
        Save results to Excel file.

        Args:
            results: Results dictionary
            drug_name: Drug name
            timestamp: Timestamp string
        """
        import pandas as pd

        filename = f"{drug_name}_{timestamp}.xlsx"
        filepath = self.output_dir / filename

        with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
            # Summary sheet
            summary_data = {
                'Category': [],
                'Count': []
            }
            for category, papers in results['categorized_papers'].items():
                summary_data['Category'].append(category)
                summary_data['Count'].append(len(papers))

            df_summary = pd.DataFrame(summary_data)
            df_summary.to_excel(writer, sheet_name='Summary', index=False)

            # Individual category sheets
            for category, papers in results['categorized_papers'].items():
                if papers:
                    df_data = []
                    for paper in papers:
                        row = {
                            'PMID': paper.get('pmid'),
                            'Title': paper.get('title'),
                            'Journal': paper.get('journal'),
                            'Year': paper.get('year'),
                            'Authors': '; '.join(paper.get('authors', [])) if isinstance(paper.get('authors'), list) else paper.get('authors', ''),
                            'Study Type': paper.get('study_type'),
                            'Phase': paper.get('phase'),
                            'Trial Names': '; '.join(paper.get('trial_names', [])),
                            'Key Takeaway 1': paper.get('key_takeaways', [''])[0] if paper.get('key_takeaways') else '',
                            'Key Takeaway 2': paper.get('key_takeaways', ['', ''])[1] if len(paper.get('key_takeaways', [])) > 1 else '',
                            'Key Takeaway 3': paper.get('key_takeaways', ['', '', ''])[2] if len(paper.get('key_takeaways', [])) > 2 else '',
                            'PubMed URL': f"https://pubmed.ncbi.nlm.nih.gov/{paper.get('pmid')}/" if paper.get('pmid') else ''
                        }
                        df_data.append(row)

                    df = pd.DataFrame(df_data)
                    # Clean sheet name: remove invalid characters and truncate to 31 chars (Excel limit)
                    sheet_name = category.replace('/', '-').replace('\\', '-').replace('*', '').replace('?', '').replace('[', '').replace(']', '')
                    sheet_name = sheet_name[:31]
                    df.to_excel(writer, sheet_name=sheet_name, index=False)

            # Trial Families sheet
            if results.get('trial_families'):
                family_data = []
                for trial_name, family in results['trial_families'].items():
                    family_data.append({
                        'Trial Name': trial_name,
                        'Primary Trials': len(family.get('primary', [])),
                        'Extensions': len(family.get('extensions', [])),
                        'Post-hoc': len(family.get('post_hoc', [])),
                        'Subgroup': len(family.get('subgroup', [])),
                        'Total Papers': sum([
                            len(family.get('primary', [])),
                            len(family.get('extensions', [])),
                            len(family.get('post_hoc', [])),
                            len(family.get('subgroup', []))
                        ])
                    })

                df_families = pd.DataFrame(family_data)
                df_families.to_excel(writer, sheet_name='Trial Families', index=False)

        logger.info(f"Excel file saved to: {filepath}")

    def _normalize_indication(
        self,
        indication: str,
        discovered_indications: List[str]
    ) -> str:
        """
        Normalize an indication name against discovered indications.

        Args:
            indication: Raw indication string from paper
            discovered_indications: List of known indications from ClinicalTrials.gov

        Returns:
            Normalized indication name or original if no match
        """
        if not indication or not discovered_indications:
            return indication

        # Clean up the indication
        indication_clean = indication.strip().lower()

        # Try exact match (case-insensitive)
        for discovered in discovered_indications:
            if discovered.lower() == indication_clean:
                return discovered

        # Try partial match (indication contains discovered or vice versa)
        for discovered in discovered_indications:
            discovered_lower = discovered.lower()
            if discovered_lower in indication_clean or indication_clean in discovered_lower:
                # Prefer the shorter, more canonical name
                if len(discovered) < len(indication):
                    return discovered
                else:
                    return indication.strip()

        # No match found, return original (capitalized)
        return ' '.join(word.capitalize() for word in indication.split())

    def _discover_indications_from_ctgov(
        self,
        drug_name: str
    ) -> List[str]:
        """
        Discover all indications/diseases for a drug from ClinicalTrials.gov.

        Args:
            drug_name: Drug name to search for

        Returns:
            List of normalized indication names
        """
        if not self.ct_api:
            logger.info("ClinicalTrials.gov API not available, skipping indication discovery")
            return []

        try:
            logger.info(f"Discovering indications from ClinicalTrials.gov for {drug_name}...")

            # Search for trials
            trials = self.ct_api.search_trials(
                drug_name=drug_name,
                condition=None,  # Get all conditions
                max_results=100  # Get more trials for comprehensive coverage
            )

            logger.info(f"  Found {len(trials)} trials on ClinicalTrials.gov")

            if not trials:
                logger.warning(f"No trials found on ClinicalTrials.gov for {drug_name}")
                return []

            # Extract all unique conditions
            # Note: search_trials() returns simplified format, not raw API format
            # Conditions are already at trial['conditions']
            all_conditions = set()
            for i, trial in enumerate(trials):
                conditions = trial.get('conditions', [])
                logger.debug(f"  Trial {i+1}: {len(conditions)} conditions - {conditions[:3]}")
                for condition in conditions:
                    if condition:
                        all_conditions.add(condition)

            logger.info(f"  Extracted {len(all_conditions)} unique conditions from trials")

            # Normalize condition names
            normalized_indications = []
            for condition in sorted(all_conditions):
                # Basic normalization
                normalized = condition.strip()
                # Capitalize first letter of each word
                normalized = ' '.join(word.capitalize() for word in normalized.split())
                normalized_indications.append(normalized)

            logger.info(f"Discovered {len(normalized_indications)} indications: {normalized_indications[:10]}")
            if len(normalized_indications) > 10:
                logger.info(f"  ... and {len(normalized_indications) - 10} more")

            return normalized_indications

        except Exception as e:
            logger.error(f"Error discovering indications from ClinicalTrials.gov: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return []

    def _validate_trial_names(
        self,
        trial_data: List[Dict[str, Any]],
        drug_name: str
    ) -> Set[str]:
        """
        Validate trial names and filter out false positives.

        Args:
            trial_data: List of trial dicts with acronym, confidence, etc.
            drug_name: Drug name for context

        Returns:
            Set of validated trial acronyms
        """
        from collections import defaultdict

        validated_trials = set()

        # Generic terms to skip
        GENERIC_TERMS = ['STUDY', 'TRIAL', 'PHASE', 'OPEN', 'LABEL',
                         'EXTENSION', 'FOLLOWUP', 'CONTINUATION', 'LONG', 'TERM']

        # Common medical/regulatory abbreviations to skip
        COMMON_ABBREVS = ['SLE', 'RA', 'MS', 'FDA', 'EMA', 'NEJM', 'BMJ', 'JAMA',
                          'ITT', 'PP', 'MITT', 'AE', 'SAE', 'TEAE', 'CI', 'HR']

        # Group by base name for family analysis
        trial_families = defaultdict(list)

        for trial in trial_data:
            acronym = trial.get('acronym', '')
            if not acronym:
                continue

            # Skip if too generic
            if acronym.upper() in GENERIC_TERMS:
                logger.debug(f"  Skipping generic term: {acronym}")
                continue

            # Skip common abbreviations
            if acronym.upper() in COMMON_ABBREVS:
                logger.debug(f"  Skipping common abbreviation: {acronym}")
                continue

            # Skip if looks like a company code without strong context
            # But allow if it has high confidence or NCT number
            if (re.match(r'^[A-Z]{1,2}-\d+$', acronym) and
                trial.get('confidence') == 'low' and
                not trial.get('nct_number')):
                logger.debug(f"  Skipping low-confidence company code: {acronym}")
                continue

            # Extract base name (preserve delivery method suffixes)
            # VICTORY-1 -> VICTORY
            # VICTORY-SC -> VICTORY (but keep VICTORY-SC in results)
            # VICTORY-LTE -> VICTORY
            base_name = re.sub(r'-(\d+[A-Z]?|LTE|OLE|EXTEND|SC|IV|PO|IM|TD|SubQ)$', '', acronym)
            trial_families[base_name].append(trial)

            # High confidence trials always included
            if trial.get('confidence') == 'high' or trial.get('source_count', 0) >= 3:
                validated_trials.add(acronym)
                logger.info(f"    High-confidence trial: {acronym} (Phase: {trial.get('phase', 'N/A')}, NCT: {trial.get('nct_number', 'N/A')})")

            # Medium confidence if has NCT number or phase or 2+ sources
            elif (trial.get('confidence') == 'medium' and
                  (trial.get('nct_number') or
                   trial.get('phase') or
                   trial.get('source_count', 0) >= 2)):
                validated_trials.add(acronym)
                logger.info(f"    Medium-confidence trial: {acronym} (Phase: {trial.get('phase', 'N/A')})")

            # Low confidence but appears in trial family
            elif trial.get('confidence') == 'low' and len(trial_families[base_name]) >= 2:
                validated_trials.add(acronym)
                logger.info(f"    Low-confidence trial (in family): {acronym}")

        # If we found a trial family (e.g., VICTORY-1, VICTORY-2, VICTORY-SC),
        # include base name too for comprehensive searching
        for base_name, family_members in trial_families.items():
            if len(family_members) >= 2 and base_name not in validated_trials:
                validated_trials.add(base_name)
                logger.info(f"    Added base trial name: {base_name} (family of {len(family_members)})")

        return validated_trials

    def _discover_trial_names_via_web(
        self,
        drug_name: str,
        disease_indication: Optional[str]
    ) -> Set[str]:
        """
        Discover all known trial names for a drug using web search + Claude.

        Strategy:
        1. Web search: "{drug_name} clinical trials"
        2. Web search: "{drug_name} {indication} phase 3 trials"
        3. Web search: "{drug_name} trial names acronyms"
        4. Use Claude to extract trial names from search results
        5. Cross-reference with ClinicalTrials.gov if available

        Args:
            drug_name: Drug name
            disease_indication: Disease indication (optional)

        Returns:
            Set of trial names (e.g., {"PSOARING 1", "PSOARING 2", "PSOARING 3"})
        """
        if not self.web_search:
            logger.warning("Web search not available, skipping trial name discovery")
            return set()

        trial_names = set()

        try:
            # Search 1: Target FDA approval documents (always mention trial acronyms)
            query1 = f"{drug_name} FDA approval clinical trial names"
            logger.info(f"  Web search 1: '{query1}'")
            results1 = self.web_search.search(query1, max_results=10)
            logger.info(f"    Found {len(results1)} results")

            # Search 2: Disease-specific trials with acronym focus
            results2 = []
            if disease_indication:
                query2 = f"{drug_name} {disease_indication} phase 3 study acronym names"
            else:
                query2 = f"{drug_name} phase 3 study acronym names"
            logger.info(f"  Web search 2: '{query2}'")
            results2 = self.web_search.search(query2, max_results=10)
            logger.info(f"    Found {len(results2)} results")

            # Search 3: Target press releases (pharma companies always use trial acronyms)
            query3 = f"{drug_name} trial results press release"
            logger.info(f"  Web search 3: '{query3}'")
            results3 = self.web_search.search(query3, max_results=10)
            logger.info(f"    Found {len(results3)} results")

            # Search 4: Target EMA regulatory documents
            query4 = f"{drug_name} EMA clinical trial acronym"
            logger.info(f"  Web search 4: '{query4}'")
            results4 = self.web_search.search(query4, max_results=10)
            logger.info(f"    Found {len(results4)} results")

            # Search 5: Target scientific publications
            query5 = f'"{drug_name}" randomized controlled trial acronym'
            logger.info(f"  Web search 5: '{query5}'")
            results5 = self.web_search.search(query5, max_results=10)
            logger.info(f"    Found {len(results5)} results")

            # Combine all search results
            all_results = results1 + results2 + results3 + results4 + results5

        except Exception as e:
            logger.error(f"Error during web searches for trial names: {e}")
            return set()

        if not all_results:
            logger.warning("No web search results found for trial name discovery")
            return set()

        # Prioritize high-value sources
        HIGH_VALUE_DOMAINS = [
            'fda.gov',           # FDA approvals always list trials
            'ema.europa.eu',     # European regulator
            'clinicaltrials.gov', # Official registry
            'pubmed.ncbi.nlm.nih.gov',  # Scientific papers
            'thelancet.com',     # Top journals
            'nejm.org',
            'bmj.com',
            'nature.com',
            'pharmaceutical-technology.com',  # Industry news
            'biopharmadive.com',
            'fiercepharma.com',
            'biospace.com',
            'prnewswire.com',    # Press releases
            'businesswire.com',
        ]

        prioritized_results = []
        other_results = []

        for result in all_results:
            url = result.get('url', '')
            if any(domain in url.lower() for domain in HIGH_VALUE_DOMAINS):
                prioritized_results.append(result)
            else:
                other_results.append(result)

        # Send top 15 prioritized + top 5 others to Claude
        final_results = prioritized_results[:15] + other_results[:5]

        logger.info(f"  Prioritized {len(prioritized_results)} high-value sources, {len(other_results)} other sources")
        logger.info(f"  Sending {len(final_results)} results to Claude for extraction")

        # Combine all text from search results
        combined_text = []
        for result in final_results:
            combined_text.append(result.get('title', ''))
            combined_text.append(result.get('snippet', ''))

        full_text = '\n'.join(combined_text)

        # Use TrialNameExtractor for sophisticated extraction
        logger.info("  Using TrialNameExtractor to extract trial names...")
        extracted_trials = self.trial_extractor.extract_from_text(
            full_text,
            min_confidence=self.config.trial_name_min_confidence
        )

        # Add high-confidence trials (extract_from_text returns a Set[str], not objects)
        trial_names.update(extracted_trials)
        logger.info(f"    Extracted {len(extracted_trials)} trial names from web search")

        # Also use Claude for additional extraction with structured prompt
        results_text = []
        for i, result in enumerate(final_results, 1):
            results_text.append(f"{i}. {result.get('title', 'N/A')}")
            results_text.append(f"   {result.get('snippet', 'N/A')}")
            if result.get('url'):
                results_text.append(f"   URL: {result.get('url')}")
            results_text.append("")

        # Use PromptBuilder for consistent prompts
        prompt = self.prompt_builder.build_prompt(
            'extract_trials',
            drug_name=drug_name,
            results_text='\n'.join(results_text)
        )

        # Fallback to legacy prompt if PromptBuilder doesn't have this template yet
        if not prompt or 'extract_trials' not in self.prompt_builder.templates:
            prompt = f"""Extract ALL clinical trial names/acronyms for the drug "{drug_name}" from the search results below.

TRIAL NAME PATTERNS TO LOOK FOR:

1. **All-caps acronyms**: Common formats include:
   - Single word: VICTORY, EVOLVE, ADVANCE, SUMMIT, PIONEER, MUSE, DAISY
   - Multi-word: CLEAR OUTCOMES, CARE MS-1
   - With numbers: STEP-1, STEP-2, ASCEND-NHQ, TULIP-1, TULIP-2
   - With hyphens: MONARCH-2, ELOQUENT-1

2. **Delivery method variants**: INCLUDE these as separate entries:
   - Subcutaneous: TRIAL-SC, TRIAL-SubQ
   - Intravenous: TRIAL-IV
   - Oral: TRIAL-PO, TRIAL-Oral
   - Other routes: TRIAL-IM, TRIAL-TD (transdermal)

3. **Disease/indication variants**: INCLUDE these:
   - Disease-specific: TRIAL-LN (lupus nephritis), TRIAL-RA (rheumatoid arthritis)
   - Population-specific: TRIAL-PED (pediatric), TRIAL-ADO (adolescent)

4. **Extension/continuation studies**: INCLUDE these:
   - Long-term extensions: TRIAL-LTE, TRIAL-OLE
   - Continuation: TRIAL-EXTEND
   - With phases: TRIAL-2A, TRIAL-2B

5. **Context clues where trial names appear**:
   - "in the [NAME] trial"
   - "the [NAME] study demonstrated"
   - "results from [NAME] showed"
   - "[NAME] (NCT12345678)"
   - "the Phase 3 [NAME] study"
   - "data from [NAME] and [NAME] trials"

EXTRACTION RULES:

✅ DO EXTRACT (as separate entries):
- Base trial names: VICTORY, EVOLVE, SUMMIT, MUSE, DAISY
- ALL numbered variants: STEP-1, STEP-2, STEP-3 (each as separate entry)
- ALL delivery method variants: TRIAL-SC, TRIAL-IV (each as separate entry)
- ALL disease variants: TRIAL-LN, TRIAL-RA (each as separate entry)
- Extension studies: TRIAL-LTE, TRIAL-OLE
- Phase variants: TRIAL-2A, TRIAL-2B

❌ DO NOT EXTRACT:
- Generic descriptive terms alone: "Phase 3", "Extension Study", "Open-Label"
- Common English words that happen to be capitalized
- Company internal codes without context: ABC-123
- Journal abbreviations: NEJM, BMJ, JAMA
- Regulatory abbreviations: FDA, EMA, ICH
- Statistical terms: ITT, PP, mITT
- Medical abbreviations: SLE, RA, MS (unless part of trial name like CARE-MS-1)

VERIFICATION CHECKLIST for each potential trial name:
- ✓ Is it mentioned in context of clinical trial results or data?
- ✓ Is it associated with specific phases, patient numbers, or NCT numbers?
- ✓ Does it appear multiple times or across multiple sources?
- ✓ Is it clearly linked to {drug_name}?

For each trial name found, extract:
- **acronym**: The trial acronym/name
- **full_name**: Full trial name if mentioned (e.g., "Study of Treatment In..." for VICTORY)
- **phase**: Phase 1/2/3/4 if mentioned
- **nct_number**: NCT number if mentioned (format: NCT########)
- **indication**: Disease/condition if mentioned
- **source_count**: Count how many different search results mention this trial
- **confidence**:
  - "high" = Multiple sources (3+), has NCT number or phase, appears in regulatory/journal context
  - "medium" = 2+ sources OR has NCT/phase OR appears in credible context
  - "low" = Single mention without strong context

Search Results:
{chr(10).join(results_text)}

Respond ONLY with valid JSON in this exact format:
{{
  "trial_names": [
    {{
      "acronym": "TULIP-1",
      "full_name": "Type I Interferon Inhibition in Lupus",
      "phase": "Phase 3",
      "nct_number": "NCT02446912",
      "indication": "systemic lupus erythematosus",
      "source_count": 3,
      "confidence": "high"
    }},
    {{
      "acronym": "MUSE-1",
      "full_name": null,
      "phase": "Phase 2",
      "nct_number": null,
      "indication": "systemic lupus erythematosus",
      "source_count": 2,
      "confidence": "medium"
    }}
  ]
}}

CRITICAL: Only include trial names that are clearly associated with {drug_name}. Do not include trials for other drugs.
"""

        try:
            # Use APIClient for robust API calls
            response_text = self.api_client.call_claude(
                prompt=prompt,
                max_tokens=3000,
                timeout=self.config.api_timeout
            )

            # Use ClaudeResponseParser for robust JSON parsing
            try:
                data = self.json_parser.parse_json_response(
                    response_text,
                    expected_type=dict
                )
                trial_data = data.get('trial_names', [])

                # Validate and filter trial names
                validated_trials = self._validate_trial_names(trial_data, drug_name)
                trial_names.update(validated_trials)

                logger.info(f"Extracted {len(trial_names)} validated trial names from web search")
            except Exception as e:
                logger.error(f"Failed to parse trial names from Claude response: {e}")

        except Exception as e:
            logger.error(f"Error extracting trial names with Claude: {e}")

        # Supplement with ClinicalTrials.gov API if available
        if self.ct_api:
            try:
                logger.info("  Supplementing with ClinicalTrials.gov API...")
                ct_trials = self.ct_api.search_trials(
                    drug_name=drug_name,
                    condition=disease_indication if disease_indication else None,
                    max_results=50
                )

                # Extract trial acronyms from official titles
                for trial in ct_trials:
                    title = trial.get('official_title', '') or trial.get('brief_title', '')

                    # Look for acronyms in parentheses or after colons
                    # Examples: "Study of X (TULIP-1)", "Study of X: MUSE trial"
                    import re

                    # Pattern 1: Acronym in parentheses
                    matches = re.findall(r'\(([A-Z][A-Z0-9\-]+(?:\s+\d+)?)\)', title)
                    for match in matches:
                        if len(match) >= 3:  # At least 3 chars
                            trial_names.add(match)

                    # Pattern 2: Acronym after colon
                    if ':' in title:
                        after_colon = title.split(':')[-1].strip()
                        # Extract first all-caps word
                        words = after_colon.split()
                        for word in words[:3]:  # Check first 3 words
                            # Remove "trial", "study", etc.
                            word = word.replace('trial', '').replace('study', '').strip()
                            if word.isupper() and len(word) >= 3:
                                trial_names.add(word)

                logger.info(f"  Found {len(trial_names)} total trial names (including ClinicalTrials.gov)")

            except Exception as e:
                logger.warning(f"  Could not search ClinicalTrials.gov: {e}")

        return trial_names

    def _filter_drug_relevant_papers(
        self,
        articles: List[Dict[str, Any]],
        drug_name: str
    ) -> List[Dict[str, Any]]:
        """
        Filter papers to only include those actually about the searched drug.

        Uses Claude to verify each paper is about the correct drug.
        Threshold: 0.6 (moderate - balance between precision and recall)

        Args:
            articles: List of papers
            drug_name: Drug being searched

        Returns:
            Filtered list of relevant papers
        """
        logger.info(f"Filtering {len(articles)} papers for drug relevance...")

        # Process in batches
        batch_size = 20
        filtered_articles = []

        for i in range(0, len(articles), batch_size):
            batch = articles[i:i+batch_size]
            logger.info(f"  Processing batch {i//batch_size + 1}/{(len(articles)-1)//batch_size + 1}")

            # Build prompt
            papers_text = []
            for j, article in enumerate(batch, 1):
                title = article.get('title') or 'N/A'
                abstract = article.get('abstract') or 'N/A'
                if abstract != 'N/A':
                    abstract = abstract[:500]  # Limit length
                papers_text.append(f"{j}. Title: {title}")
                papers_text.append(f"   Abstract: {abstract}")
                papers_text.append("")

            prompt = f"""For each paper below, determine if it is about the drug "{drug_name}".

Score each paper from 0.0 to 1.0:
- 1.0: Definitely about {drug_name}
- 0.8: Probably about {drug_name}
- 0.6: Possibly about {drug_name} (mentions it but may focus on other drugs)
- 0.4: Mentions {drug_name} but primarily about other drugs
- 0.2: Barely mentions {drug_name}
- 0.0: Not about {drug_name} at all

Papers:
{chr(10).join(papers_text)}

Respond in JSON format:
[
  {{"paper": 1, "score": 0.9, "reason": "Primary focus on {drug_name}"}},
  {{"paper": 2, "score": 0.3, "reason": "Primarily about benvitimod, not {drug_name}"}},
  ...
]
"""

            try:
                # Use APIClient for robust API calls
                response_text = self.api_client.call_claude(
                    prompt=prompt,
                    max_tokens=3000,
                    timeout=self.config.api_timeout
                )

                # Use ClaudeResponseParser for robust JSON parsing
                try:
                    scores = self.json_parser.parse_json_response(
                        response_text,
                        expected_type=list
                    )

                    # Filter papers with score >= 0.6 (moderate threshold)
                    for article, score_data in zip(batch, scores):
                        score = score_data.get('score', 0.0)
                        article['drug_relevance_score'] = score

                        if score >= 0.6:
                            filtered_articles.append(article)
                        else:
                            logger.debug(f"Filtered out: {article.get('title', 'N/A')[:80]} (score: {score})")

                except Exception as e:
                    logger.error(f"Failed to parse relevance scores: {e}")
                    # On error, keep all papers in batch (conservative)
                    for article in batch:
                        article['drug_relevance_score'] = None
                        filtered_articles.append(article)

            except Exception as e:
                logger.error(f"Error filtering batch with Claude: {e}")
                # On error, keep all papers in batch (conservative)
                for article in batch:
                    article['drug_relevance_score'] = None
                    filtered_articles.append(article)

        logger.info(f"Kept {len(filtered_articles)}/{len(articles)} papers after relevance filtering")
        return filtered_articles

    def _match_papers_to_trials(
        self,
        articles: List[Dict[str, Any]],
        known_trial_names: Set[str]
    ) -> None:
        """
        Match papers to trial names using Claude (not just regex).

        For each paper:
        1. Check if title/abstract mentions any known trial names
        2. Use Claude to confirm trial association
        3. Store trial_name in article dict

        Modifies articles in place.

        Args:
            articles: List of papers
            known_trial_names: Set of known trial names from Phase 0
        """
        if not known_trial_names:
            logger.info("No known trial names to match against")
            return

        logger.info(f"Matching {len(articles)} papers to {len(known_trial_names)} known trials...")

        # First pass: Quick regex matching
        for article in articles:
            text = f"{article.get('title', '')} {article.get('abstract', '')}".upper()

            # Check if any known trial name appears in text
            for trial_name in known_trial_names:
                if trial_name.upper() in text:
                    article['trial_name'] = trial_name
                    break

        # Second pass: Use Claude for papers without matches
        unmatched = [a for a in articles if not a.get('trial_name')]

        if not unmatched:
            logger.info("All papers matched to trials via regex")
            return

        logger.info(f"Using Claude to match {len(unmatched)} unmatched papers...")

        # Process in batches
        batch_size = 10
        for i in range(0, len(unmatched), batch_size):
            batch = unmatched[i:i+batch_size]

            # Build prompt
            papers_text = []
            for j, article in enumerate(batch, 1):
                title = article.get('title') or 'N/A'
                abstract = article.get('abstract') or 'N/A'
                if abstract != 'N/A':
                    abstract = abstract[:500]
                papers_text.append(f"{j}. Title: {title}")
                papers_text.append(f"   Abstract: {abstract}")
                papers_text.append("")

            trial_names_list = ', '.join(sorted(known_trial_names))

            prompt = f"""For each paper below, determine which trial (if any) it belongs to.

Known trial names: {trial_names_list}

IMPORTANT:
1. First check if the paper mentions any of the known trial names
2. If not, check if the title/abstract contains OTHER trial acronyms (e.g., DAISY, MUSE, EXTEND, etc.)
3. Extract the trial name EXACTLY as it appears (e.g., "TULIP-2" not "TULIP-SC", "DAISY" not "DAISY study")
4. Trial names are typically ALL-CAPS acronyms, may include numbers/hyphens

Papers:
{chr(10).join(papers_text)}

Respond in JSON format:
[
  {{"paper": 1, "trial_name": "PSOARING 3", "confidence": "high"}},
  {{"paper": 2, "trial_name": "DAISY", "confidence": "high"}},
  {{"paper": 3, "trial_name": null, "confidence": "none"}},
  ...
]

Use null if the paper doesn't clearly belong to any trial.
"""

            try:
                # Use APIClient for robust API calls
                response_text = self.api_client.call_claude(
                    prompt=prompt,
                    max_tokens=2000,
                    timeout=self.config.api_timeout
                )

                # Use ClaudeResponseParser for robust JSON parsing
                try:
                    matches = self.json_parser.parse_json_response(
                        response_text,
                        expected_type=list
                    )

                    # Apply matches
                    for article, match_data in zip(batch, matches):
                        trial_name = match_data.get('trial_name')
                        if trial_name:
                            article['trial_name'] = trial_name
                            logger.debug(f"Matched: {article.get('title', 'N/A')[:60]} -> {trial_name}")

                except Exception as e:
                    logger.error(f"Failed to parse trial matches: {e}")

            except Exception as e:
                logger.error(f"Error matching batch with Claude: {e}")

        matched_count = sum(1 for a in articles if a.get('trial_name'))
        logger.info(f"Matched {matched_count}/{len(articles)} papers to trials")

