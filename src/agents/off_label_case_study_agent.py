"""
Off-Label Case Study Agent

Discovers and analyzes clinical evidence of off-label drug use including:
- Case reports and case series
- Clinical trials (prospective and retrospective)
- Real-world evidence studies
- Expanded access programs

Workflow:
1. Drug Input & Mechanism Extraction
2. Direct Off-Label Literature Search
3. Mechanism Expansion & Related Drug Discovery
4. Mechanism-Based Literature Search (user-selected mechanisms)
5. Data Extraction, Classification & Cross-Referencing
"""

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from anthropic import Anthropic

from src.models.off_label_schemas import (
    OffLabelCaseStudy,
    OffLabelBaseline,
    OffLabelOutcome,
    OffLabelSafetyEvent,
    StudyClassification,
    OffLabelValidationResult
)
from src.tools.off_label_database import OffLabelDatabase
from src.tools.pubmed import PubMedAPI
from src.tools.web_search import WebSearchTool
from src.tools.clinicaltrials import ClinicalTrialsAPI
from src.utils.paper_extraction_service import PaperExtractionService

logger = logging.getLogger(__name__)

# PyMuPDF for PDF extraction
try:
    from pymupdf4llm.helpers.pymupdf_rag import to_markdown
    import pymupdf
    PYMUPDF_AVAILABLE = True
except ImportError:
    logger.warning("pymupdf4llm not available. PDF extraction will be limited to abstracts.")
    PYMUPDF_AVAILABLE = False


class OffLabelCaseStudyAgent:
    """
    Agent for discovering and analyzing off-label case studies.
    
    Main workflow:
    1. Extract mechanism from drug
    2. Search for off-label case studies
    3. Expand to related mechanisms (user-selected)
    4. Extract structured data
    5. Validate and save to database
    """
    
    def __init__(
        self,
        anthropic_api_key: str,
        database_url: str,
        pubmed_email: str,
        tavily_api_key: Optional[str] = None
    ):
        """
        Initialize agent.

        Args:
            anthropic_api_key: Anthropic API key
            database_url: PostgreSQL database URL
            pubmed_email: Email for PubMed API
            tavily_api_key: Tavily API key for web search
        """
        self.client = Anthropic(api_key=anthropic_api_key)
        self.db = OffLabelDatabase(database_url)
        self.pubmed = PubMedAPI(email=pubmed_email)
        self.web_search = WebSearchTool(api_key=tavily_api_key) if tavily_api_key else None
        self.ct_api = ClinicalTrialsAPI()

        # Model configuration
        self.model = "claude-sonnet-4-20250514"
        self.max_tokens = 16000

        # Initialize paper extraction service for reusing clinical data extractor
        self.paper_service = PaperExtractionService(
            client=self.client,
            model=self.model
        )
    
    # =====================================================
    # STAGE 1: DRUG INPUT & MECHANISM EXTRACTION
    # =====================================================
    
    def extract_mechanism(self, drug_name: str) -> Dict[str, Any]:
        """
        Extract mechanism of action for a drug.
        
        Args:
            drug_name: Name of drug
            
        Returns:
            Dict with mechanism, target, and approved indications
        """
        logger.info(f"Extracting mechanism for {drug_name}")
        
        # First check database for existing drug info
        drug_info = self._get_drug_from_database(drug_name)
        if drug_info:
            logger.info(f"Found drug in database: {drug_info}")
            return drug_info
        
        # If not in database, use Claude to extract
        prompt = f"""Extract the mechanism of action and molecular target for the drug: {drug_name}

Return JSON with:
{{
    "drug_name": "Official drug name",
    "generic_name": "Generic name if different",
    "mechanism": "Brief mechanism description (e.g., 'JAK1/JAK3 inhibitor')",
    "target": "Molecular target (e.g., 'JAK1/JAK3')",
    "approved_indications": ["List of FDA-approved indications"]
}}

Be concise and accurate. Use your knowledge of approved drugs."""
        
        response = self.client.messages.create(
            model=self.model,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )
        
        text = self._extract_text_response(response)

        try:
            # Strip markdown code blocks if present
            text = text.strip()
            if text.startswith("```json"):
                text = text[7:]  # Remove ```json
            if text.startswith("```"):
                text = text[3:]  # Remove ```
            if text.endswith("```"):
                text = text[:-3]  # Remove trailing ```
            text = text.strip()

            data = json.loads(text)
            logger.info(f"Extracted mechanism: {data.get('mechanism')}")
            return data
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse mechanism response: {text[:200]}... Error: {e}")
            return {
                "drug_name": drug_name,
                "mechanism": None,
                "target": None,
                "approved_indications": []
            }
    
    def _get_drug_from_database(self, drug_name: str) -> Optional[Dict[str, Any]]:
        """Get drug info from database."""
        import psycopg2
        from psycopg2.extras import RealDictCursor

        try:
            conn = psycopg2.connect(self.db.database_url)
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    query = """
                        SELECT
                            d.drug_id,
                            d.brand_name,
                            d.generic_name,
                            d.mechanism_of_action,
                            d.drug_type,
                            COALESCE(
                                (SELECT json_agg(dis.disease_name_standard)
                                 FROM drug_indications di
                                 JOIN diseases dis ON di.disease_id = dis.disease_id
                                 WHERE di.drug_id = d.drug_id
                                 AND di.approval_status = 'Approved'),
                                '[]'::json
                            ) as approved_indications
                        FROM drugs d
                        WHERE d.brand_name ILIKE %s OR d.generic_name ILIKE %s
                        LIMIT 1
                    """
                    cur.execute(query, (f"%{drug_name}%", f"%{drug_name}%"))
                    result = cur.fetchone()

                    if result:
                        # Map database fields to expected format
                        drug_dict = dict(result)
                        return {
                            'drug_id': drug_dict.get('drug_id'),
                            'drug_name': drug_dict.get('brand_name'),
                            'generic_name': drug_dict.get('generic_name'),
                            'mechanism': drug_dict.get('mechanism_of_action'),
                            'target': drug_dict.get('drug_type'),  # Using drug_type as target
                            'approved_indications': drug_dict.get('approved_indications', [])
                        }
                    return None
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Error querying database for drug: {e}")
            return None
    
    # =====================================================
    # STAGE 2: DIRECT OFF-LABEL LITERATURE SEARCH
    # =====================================================
    
    def search_off_label_literature(
        self,
        drug_name: str,
        max_results: int = 50,
        incremental: bool = False,
        save_to_disk: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Search for off-label case studies for a drug.

        Args:
            drug_name: Name of drug
            max_results: Maximum number of results
            incremental: If True, only search for papers published after last search.
                        If False, search all papers (default).
            save_to_disk: If True, save discovered papers to disk for caching

        Returns:
            List of paper metadata dicts
        """
        logger.info(f"Searching for off-label case studies: {drug_name}")

        # Check for existing papers on disk first
        storage_path = self._get_storage_path(drug_name)
        existing_papers = self._load_existing_papers(storage_path)

        if existing_papers:
            logger.info(f"Found {len(existing_papers)} existing papers for {drug_name}")
            return existing_papers

        # Check for incremental update (only if enabled)
        last_search = self.db.get_last_search_date(drug_name) if incremental else None

        papers = []
        seen_pmids = set()

        # PubMed search - Multiple strategies to capture different study types
        # Enhanced with repurposing-specific queries
        pubmed_queries = [
            # Strategy 1: Case reports and series (explicit)
            f'"{drug_name}"[Title/Abstract] AND ("case report"[Publication Type] OR "case series"[Title/Abstract])',

            # Strategy 2: Off-label mentions
            f'"{drug_name}"[Title/Abstract] AND ("off-label"[Title/Abstract] OR "off label"[Title/Abstract])',

            # Strategy 3: Expanded access programs
            f'"{drug_name}"[Title/Abstract] AND ("expanded access"[Title/Abstract] OR "compassionate use"[Title/Abstract])',

            # Strategy 4: Pilot studies and open-label trials (often off-label)
            f'"{drug_name}"[Title/Abstract] AND ("pilot study"[Title/Abstract] OR "open-label"[Title/Abstract] OR "open label"[Title/Abstract])',

            # Strategy 5: Retrospective studies and case series
            f'"{drug_name}"[Title/Abstract] AND ("retrospective"[Title/Abstract] OR "case series"[Title/Abstract] OR "case study"[Title/Abstract])',

            # Strategy 6: Refractory/resistant conditions (often off-label)
            f'"{drug_name}"[Title/Abstract] AND ("refractory"[Title/Abstract] OR "resistant"[Title/Abstract] OR "treatment"[Title/Abstract])',

            # Strategy 7: Novel/alternative indications (NEW)
            f'"{drug_name}"[Title/Abstract] AND ("novel indication"[Title/Abstract] OR "alternative indication"[Title/Abstract])',

            # Strategy 8: Drug repurposing (NEW)
            f'"{drug_name}"[Title/Abstract] AND ("repurposing"[Title/Abstract] OR "repositioning"[Title/Abstract] OR "repurposed"[Title/Abstract])',

            # Strategy 9: Rare diseases (NEW)
            f'"{drug_name}"[Title/Abstract] AND ("rare disease"[Title/Abstract] OR "orphan"[Title/Abstract] OR "ultra-rare"[Title/Abstract])',

            # Strategy 10: Real-world evidence (NEW)
            f'"{drug_name}"[Title/Abstract] AND ("real-world"[Title/Abstract] OR "registry"[Title/Abstract] OR "observational"[Title/Abstract])',

            # Strategy 11: Investigator-initiated studies (NEW)
            f'"{drug_name}"[Title/Abstract] AND ("investigator initiated"[Title/Abstract] OR "investigator-initiated"[Title/Abstract])',

            # Strategy 12: Unapproved/unlabeled use (NEW)
            f'"{drug_name}"[Title/Abstract] AND ("unapproved indication"[Title/Abstract] OR "unlabeled use"[Title/Abstract])',
        ]

        for i, query in enumerate(pubmed_queries):
            # Add date filter if incremental
            if last_search:
                date_str = last_search.strftime("%Y/%m/%d")
                query += f' AND ("{date_str}"[PDAT] : "3000"[PDAT])'

            try:
                # Search with smaller batch size per query
                pmids = self.pubmed.search(query, max_results=max_results // len(pubmed_queries))
                if pmids:
                    # Deduplicate PMIDs
                    new_pmids = [pmid for pmid in pmids if pmid not in seen_pmids]
                    if new_pmids:
                        seen_pmids.update(new_pmids)

                        # Add delay between queries to avoid rate limiting
                        if i > 0:
                            import time
                            time.sleep(0.5)  # 500ms delay between queries

                        paper_infos = self.pubmed.fetch_abstracts(new_pmids)
                        for paper_info in paper_infos:
                            paper_info['search_query'] = query
                            paper_info['search_source'] = 'PubMed'
                            papers.append(paper_info)
                        logger.info(f"Query found {len(new_pmids)} new papers (total: {len(papers)})")
            except Exception as e:
                logger.error(f"PubMed search error for query '{query[:50]}...': {e}")

        # Web search (if available) - Multiple queries for better coverage
        if self.web_search:
            web_queries = [
                f"{drug_name} off-label case study",
                f"{drug_name} pilot study treatment",
                f"{drug_name} refractory case report",
            ]

            for web_query in web_queries:
                try:
                    web_results = self.web_search.search(web_query, max_results=5)
                    for result in web_results:
                        # Try to extract PMID from URL
                        pmid = self._extract_pmid_from_url(result.get('url', ''))
                        if pmid and pmid not in seen_pmids:
                            seen_pmids.add(pmid)
                            paper_infos = self.pubmed.fetch_abstracts([pmid])
                            if paper_infos:
                                paper_info = paper_infos[0]
                                paper_info['search_query'] = web_query
                                paper_info['search_source'] = 'Web Search'
                                papers.append(paper_info)
                except Exception as e:
                    logger.error(f"Web search error for query '{web_query}': {e}")

        logger.info(f"Found {len(papers)} unique papers for {drug_name}")

        # Save papers to disk for caching
        if save_to_disk and papers:
            self._save_papers_to_disk(papers, storage_path, drug_name)

        return papers
    
    def _extract_pmid_from_url(self, url: str) -> Optional[str]:
        """Extract PMID from PubMed URL."""
        match = re.search(r'pubmed\.ncbi\.nlm\.nih\.gov/(\d+)', url)
        if match:
            return match.group(1)
        match = re.search(r'ncbi\.nlm\.nih\.gov/pubmed/(\d+)', url)
        if match:
            return match.group(1)
        return None

    def _get_storage_path(self, drug_name: str) -> Path:
        """Get storage path for discovered papers."""
        # Sanitize drug name for filesystem
        safe_drug_name = re.sub(r'[^\w\s-]', '', drug_name).strip().replace(' ', '_')
        storage_path = Path("data/off_label_papers") / safe_drug_name
        storage_path.mkdir(parents=True, exist_ok=True)

        return storage_path

    def _load_existing_papers(self, storage_path: Path) -> List[Dict[str, Any]]:
        """Load existing papers from disk."""
        papers_file = storage_path / "discovered_papers.json"

        if not papers_file.exists():
            return []

        try:
            with open(papers_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                papers = data.get('papers', [])
                logger.info(f"Loaded {len(papers)} papers from cache: {papers_file}")
                return papers
        except Exception as e:
            logger.error(f"Error loading papers from {papers_file}: {e}")
            return []

    def _save_papers_to_disk(
        self,
        papers: List[Dict[str, Any]],
        storage_path: Path,
        drug_name: str
    ):
        """Save discovered papers to disk."""
        papers_file = storage_path / "discovered_papers.json"

        try:
            # Download full text for open access papers AND classify to extract indication
            papers_with_content = []
            for paper in papers:
                pmid = paper.get('pmid')

                # Try to download full text
                if pmid:
                    try:
                        file_path, is_cached = self.pubmed.download_paper(pmid)
                        if file_path and os.path.exists(file_path):
                            # Read content
                            with open(file_path, 'r', encoding='utf-8') as f:
                                content_data = json.load(f)
                                full_text = content_data.get('full_text', '')

                                # Only mark as open access if we actually have full text content
                                # (not just abstract)
                                if full_text and len(full_text) > 500:  # Arbitrary threshold to distinguish from abstract-only
                                    paper['full_text'] = full_text
                                    paper['is_open_access'] = True
                                    paper['cached_path'] = str(file_path)
                                    logger.info(f"Downloaded full text for PMID {pmid} ({len(full_text)} chars)")
                                else:
                                    paper['is_open_access'] = False
                                    logger.info(f"PMID {pmid} has no full text (only abstract)")
                        else:
                            paper['is_open_access'] = False
                    except Exception as e:
                        logger.error(f"Error downloading PMID {pmid}: {e}")
                        paper['is_open_access'] = False

                # Classify paper to extract indication (for disease grouping)
                if not paper.get('indication'):
                    try:
                        classification = self.classify_paper(paper, drug_name)
                        if classification and classification.indication:
                            paper['indication'] = classification.indication
                            paper['study_type'] = classification.study_type
                            paper['n_patients'] = classification.n_patients
                            paper['relevance_score'] = classification.relevance_score
                            logger.info(f"Classified: {classification.indication} ({classification.study_type})")
                    except Exception as e:
                        logger.warning(f"Could not classify paper {pmid}: {e}")

                papers_with_content.append(paper)

            # Save to JSON
            data = {
                'drug_name': drug_name,
                'search_date': datetime.now().isoformat(),
                'total_papers': len(papers_with_content),
                'papers': papers_with_content
            }

            with open(papers_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            logger.info(f"Saved {len(papers_with_content)} papers to {papers_file}")

        except Exception as e:
            logger.error(f"Error saving papers to disk: {e}")
    
    # =====================================================
    # STAGE 3: MECHANISM EXPANSION
    # =====================================================
    
    def expand_mechanisms(
        self,
        mechanism: str,
        target: str
    ) -> List[Dict[str, str]]:
        """
        Find related mechanisms for expansion.
        
        This returns a list of related mechanisms that the USER can select from.
        
        Args:
            mechanism: Primary mechanism
            target: Primary target
            
        Returns:
            List of dicts with mechanism, target, similarity_score, rationale
        """
        logger.info(f"Expanding mechanisms for: {mechanism}")
        
        prompt = f"""Given this drug mechanism: {mechanism} (Target: {target})

Identify 5-10 related mechanisms that might have similar off-label uses.

Consider:
1. Same target family (e.g., JAK1/3 → JAK1/2, JAK2)
2. Same pathway (e.g., JAK → STAT, BTK → B cell signaling)
3. Similar pharmacology (e.g., TNF inhibitor → IL-6 inhibitor)

For each related mechanism, provide:
- mechanism: Brief description
- target: Molecular target
- similarity_score: 0.0-1.0 (1.0 = very similar)
- rationale: Why this mechanism is related

Return JSON array:
[
    {{
        "mechanism": "JAK1/JAK2 inhibitor",
        "target": "JAK1/JAK2",
        "similarity_score": 0.85,
        "rationale": "Overlapping JAK1 inhibition, similar immunomodulatory effects"
    }},
    ...
]"""
        
        response = self._call_claude_with_thinking(prompt, thinking_budget=3000)
        text = self._extract_text_response(response)
        
        try:
            related_mechanisms = json.loads(text)
            logger.info(f"Found {len(related_mechanisms)} related mechanisms")
            return related_mechanisms
        except json.JSONDecodeError:
            logger.error(f"Failed to parse mechanism expansion: {text}")
            return []
    
    def _extract_text_response(self, response) -> str:
        """Extract text from Claude response."""
        for block in response.content:
            if block.type == "text":
                return block.text
        return ""
    
    def _call_claude_with_thinking(self, prompt: str, thinking_budget: int = 5000):
        """Call Claude with extended thinking."""
        import time
        
        max_tokens = max(thinking_budget + 5000, 16000)
        
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                thinking={
                    "type": "enabled",
                    "budget_tokens": thinking_budget
                },
                messages=[{"role": "user", "content": prompt}]
            )
            return response
        except Exception as e:
            logger.error(f"Error calling Claude with thinking: {e}")
            # Fallback without thinking
            time.sleep(1)
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[{"role": "user", "content": prompt}]
            )
            return response

    # =====================================================
    # STAGE 4: PAPER CLASSIFICATION
    # =====================================================

    def classify_paper(
        self,
        paper: Dict[str, Any],
        drug_name: str
    ) -> Optional[StudyClassification]:
        """
        Classify paper as case report, case series, etc.

        Args:
            paper: Paper metadata dict (must have 'abstract' or 'content')
            drug_name: Drug name to check for

        Returns:
            StudyClassification or None if not relevant
        """
        title = paper.get('title', '')
        abstract = paper.get('abstract', '')
        content = paper.get('content', '')

        # Use abstract if available, otherwise use first 3000 chars of content
        # (for PDF uploads that don't have abstracts)
        text_for_classification = abstract
        if not text_for_classification and content:
            # Use first 3000 characters of full text for classification
            text_for_classification = content[:3000]
            logger.info(f"Using content excerpt for classification (no abstract available)")

        if not text_for_classification:
            logger.warning(f"No abstract or content for {paper.get('pmid')}, skipping classification")
            return None

        prompt = f"""Classify this paper for off-label drug use analysis.

Drug: {drug_name}

Title: {title}

Text: {text_for_classification}

Determine:
1. Study type: Choose from:
   - "Case Report" - Single patient case
   - "Case Series" - Multiple patients, descriptive
   - "Retrospective Cohort" - Retrospective analysis of patient cohort
   - "Prospective Cohort" - Prospective observational study
   - "Clinical Trial" - Prospective interventional trial (randomized or non-randomized)
   - "Expanded Access Program" - Compassionate use program
   - "Real-World Evidence" - Real-world data analysis
   - "N-of-1 Trial" - Single patient trial
   - "Not Relevant" - Review, preclinical, mechanism only, etc.

2. Number of patients (if mentioned)
3. Whether this describes off-label use (use for non-approved indication)
4. Indication/disease being treated (extract the specific disease/condition)
5. Relevance score (0.0-1.0):
   - 1.0 = Direct clinical evidence of off-label use (case study, trial, cohort)
   - 0.8 = Clinical evidence with mechanism match
   - 0.6 = Mentions off-label use or clinical experience
   - 0.4 = Tangentially related
   - 0.0 = Not relevant (review, preclinical, mechanism only)

IMPORTANT: Clinical trials testing off-label indications are HIGHLY RELEVANT (score 0.9-1.0).
Prospective studies of off-label use are valuable evidence.

Return JSON:
{{
    "study_type": "Clinical Trial",
    "n_patients": 30,
    "is_off_label": true,
    "indication": "Systemic Sclerosis",
    "relevance_score": 1.0,
    "rationale": "Prospective randomized trial of off-label use for systemic sclerosis"
}}

If not relevant (review article, preclinical, mechanism only), return relevance_score < 0.5."""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )

        text = self._extract_text_response(response)

        try:
            # Strip markdown code blocks if present
            text = text.strip()
            if text.startswith("```json"):
                text = text[7:]
            if text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

            data = json.loads(text)
            classification = StudyClassification(**data)

            # Filter out low relevance
            if classification.relevance_score < 0.5:
                logger.info(f"Low relevance ({classification.relevance_score}): {title}")
                return None

            logger.info(f"Classified as {classification.study_type} (relevance: {classification.relevance_score})")
            return classification

        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Failed to classify paper: {e}. Text: {text[:200]}...")
            return None

    # =====================================================
    # STAGE 5: DATA EXTRACTION
    # =====================================================

    def extract_case_study_data(
        self,
        paper: Dict[str, Any],
        drug_name: str,
        drug_info: Dict[str, Any],
        classification: StudyClassification
    ) -> Optional[OffLabelCaseStudy]:
        """
        Extract structured data from case study.

        Args:
            paper: Paper metadata and content
            drug_name: Drug name
            drug_info: Drug mechanism/target info
            classification: Study classification

        Returns:
            OffLabelCaseStudy or None if extraction fails
        """
        logger.info(f"Extracting data from: {paper.get('title')}")

        # Download full text if available
        paper_content = self._get_paper_content(paper)

        if not paper_content:
            logger.warning(f"No content available for {paper.get('pmid')}")
            return None

        # Extract with extended thinking
        extraction = self._extract_with_thinking(
            paper, paper_content, drug_name, drug_info, classification
        )

        if not extraction:
            return None

        # Validate extraction
        validation = self._validate_extraction(extraction)

        # Calculate confidence
        confidence = self._calculate_confidence(validation)
        extraction.extraction_confidence = confidence

        # Calculate evidence quality (NEW)
        evidence_quality = self._calculate_evidence_quality(extraction)
        extraction.evidence_quality = evidence_quality
        extraction.evidence_grade = evidence_quality['overall_grade']

        logger.info(f"Extraction complete. Confidence: {confidence:.2f}, Quality: {evidence_quality['overall_grade']}")
        logger.info(validation.summary())

        return extraction

    def _get_paper_content(self, paper: Dict[str, Any]) -> Optional[str]:
        """
        Get full paper content with intelligent handling of long papers.

        Tries multiple sources in order:
        0. Direct content from PDF upload (paper['content'])
        1. Cached full text from discovery (paper['full_text'])
        2. Existing papers from Clinical Data Collector (data/clinical_papers/)
        3. PMC download (auto-download if open access)
        4. Abstract only (fallback)

        For long papers (>20k chars), extract key sections instead of truncating.
        """
        pmid = paper.get('pmid')
        pmc = paper.get('pmc')

        # Strategy -1: Check if content was provided directly (e.g., from PDF upload)
        if paper.get('content'):
            content = paper['content']
            logger.info(f"Using provided content (e.g., from PDF upload)")

            # Handle long papers
            if len(content) > 20000:
                logger.info(f"Content is long ({len(content)} chars), extracting key sections")
                paper['needs_chunking'] = True
                paper['full_content'] = content
                return self._extract_key_sections(content)

            return content

        # Strategy 0: Check if full text was cached during discovery
        if paper.get('full_text'):
            content = paper['full_text']
            logger.info(f"Using cached full text from discovery: PMID {pmid}")

            # Handle long papers
            if len(content) > 20000:
                logger.info(f"Content is long ({len(content)} chars), extracting key sections")
                paper['needs_chunking'] = True
                paper['full_content'] = content
                return self._extract_key_sections(content)

            return content

        # Strategy 1: Check if paper exists in Clinical Data Collector storage
        if pmid:
            existing_content = self._find_existing_paper(pmid)
            if existing_content:
                logger.info(f"Found existing paper in Clinical Data Collector storage: PMID {pmid}")

                # Handle long papers
                if len(existing_content) > 20000:
                    logger.info(f"Content is long ({len(existing_content)} chars), extracting key sections")
                    paper['needs_chunking'] = True
                    paper['full_content'] = existing_content
                    return self._extract_key_sections(existing_content)

                return existing_content

        # Strategy 2: Try to download from PMC (auto-download if open access)
        # Note: download_paper() expects PMID, not PMC ID
        # It will check PMC availability internally
        if pmid:
            try:
                file_path, is_cached = self.pubmed.download_paper(pmid)
                if file_path and os.path.exists(file_path):
                    # Read JSON content
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content_data = json.load(f)
                        full_text = content_data.get('full_text', '')
                        if full_text:
                            action = "Using cached" if is_cached else "Downloaded"
                            logger.info(f"{action} paper from PMC: PMID {pmid}")

                            # Handle long papers
                            if len(full_text) > 20000:
                                logger.info(f"Content is long ({len(full_text)} chars), extracting key sections")
                                paper['needs_chunking'] = True
                                paper['full_content'] = full_text
                                return self._extract_key_sections(full_text)

                            return full_text
            except Exception as e:
                logger.error(f"Error downloading paper PMID {pmid}: {e}")

        # Strategy 3: Fallback to abstract
        logger.warning(f"No full text available for PMID {pmid}. Using abstract only.")
        return paper.get('abstract', '')

    def _find_existing_paper(self, pmid: str) -> Optional[str]:
        """
        Find existing paper in Clinical Data Collector storage.

        Searches data/clinical_papers/ for JSON files containing this PMID.

        Args:
            pmid: PubMed ID

        Returns:
            Full text content if found, None otherwise
        """
        from pathlib import Path

        clinical_papers_dir = Path("data/clinical_papers")

        if not clinical_papers_dir.exists():
            return None

        # Search for JSON files containing this PMID
        for json_file in clinical_papers_dir.rglob("*.json"):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                    # Check if this is the right paper
                    if data.get('pmid') == pmid or data.get('metadata', {}).get('pmid') == pmid:
                        # Return full text content
                        content = data.get('content') or data.get('full_text')
                        if content:
                            logger.info(f"Found paper in: {json_file}")
                            return content
            except Exception as e:
                # Skip files that can't be read
                continue

        return None

    def _extract_key_sections(self, content: str) -> str:
        """
        Extract key sections from long paper using Claude.

        This preserves the most relevant content for case study extraction:
        - Methods (patient selection, dosing, duration)
        - Results (efficacy outcomes, response rates, time to response)
        - Safety (adverse events, discontinuations)
        - Discussion (mechanism rationale, clinical implications)

        Args:
            content: Full paper content

        Returns:
            Structured text with key sections (typically 8-12k chars)
        """
        logger.info("Extracting key sections from long paper...")

        # Take first 30k chars for section extraction
        # (Claude needs to see enough to identify section boundaries)
        content_excerpt = content[:30000]

        prompt = f"""Extract the following sections from this research paper:

1. **Methods** - Patient selection, inclusion/exclusion criteria, dosing regimen, treatment duration
2. **Results** - Efficacy outcomes, response rates, time to response, duration of response
3. **Safety** - Adverse events, serious adverse events, discontinuations due to AEs
4. **Discussion** - Mechanism rationale, clinical implications, comparison to standard treatments

Paper content:
{content_excerpt}

Return the extracted sections in this format:

## METHODS
[extracted methods text]

## RESULTS
[extracted results text]

## SAFETY
[extracted safety text]

## DISCUSSION
[extracted discussion text]

Focus on extracting complete information. If a section is not found, write "Section not found."
"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=8000,
                messages=[{"role": "user", "content": prompt}]
            )

            extracted = self._extract_text_response(response)
            logger.info(f"Extracted key sections ({len(extracted)} chars)")
            return extracted

        except Exception as e:
            logger.error(f"Error extracting sections: {e}")
            # Fallback to simple truncation
            return content[:20000] + "\n\n[Content truncated...]"

    def extract_from_pdf(
        self,
        pdf_path: str,
        drug_name: str,
        drug_info: Dict[str, Any],
        pmid: Optional[str] = None
    ) -> Optional[OffLabelCaseStudy]:
        """
        Extract case study data from a PDF file.

        This method allows users to upload PDFs for papers that don't have
        full text available through PMC.

        Args:
            pdf_path: Path to PDF file
            drug_name: Drug name
            drug_info: Drug information dict
            pmid: Optional PMID to associate with this paper

        Returns:
            OffLabelCaseStudy object or None if extraction fails
        """
        if not PYMUPDF_AVAILABLE:
            logger.error("pymupdf4llm not available. Cannot extract from PDF.")
            return None

        from pathlib import Path

        pdf_path = Path(pdf_path)

        if not pdf_path.exists():
            logger.error(f"PDF not found: {pdf_path}")
            return None

        logger.info(f"Extracting text from PDF: {pdf_path.name}")

        try:
            # Extract text from PDF
            doc = pymupdf.open(str(pdf_path))
            text_content = to_markdown(
                doc,
                pages=None,
                page_chunks=False,
                table_strategy='lines_strict',
                force_text=True,
                show_progress=False
            )
            doc.close()

            logger.info(f"Extracted {len(text_content)} characters from PDF")

            # Create paper dict
            paper = {
                'content': text_content,
                'title': pdf_path.stem,
                'pmid': pmid,
                'source': 'pdf_upload',
                'pdf_path': str(pdf_path)
            }

            # Classify paper
            classification = self.classify_paper(paper, drug_name)

            if not classification:
                logger.warning(f"Paper not classified as relevant: {pdf_path.name}")
                return None

            # Extract case study data
            case_study = self.extract_case_study_data(paper, drug_name, drug_info, classification)

            return case_study

        except Exception as e:
            logger.error(f"Error extracting from PDF {pdf_path}: {e}")
            return None

    def _extract_with_thinking(
        self,
        paper: Dict[str, Any],
        paper_content: str,
        drug_name: str,
        drug_info: Dict[str, Any],
        classification: StudyClassification
    ) -> Optional[OffLabelCaseStudy]:
        """Extract data using Claude with extended thinking."""

        prompt = self._get_extraction_prompt(
            paper_content, drug_name, drug_info, classification
        )

        response = self._call_claude_with_thinking(prompt, thinking_budget=8000)
        text = self._extract_text_response(response)

        try:
            # Parse JSON
            json_str = self._extract_json_from_text(text)
            data = json.loads(json_str)

            # Add paper metadata
            data['pmid'] = paper.get('pmid')
            data['doi'] = paper.get('doi')
            data['pmc'] = paper.get('pmc')
            data['title'] = paper.get('title')

            # Convert authors list to comma-separated string
            authors = paper.get('authors')
            if isinstance(authors, list):
                data['authors'] = ', '.join(authors)
            else:
                data['authors'] = authors

            data['journal'] = paper.get('journal')
            data['year'] = paper.get('year')
            data['abstract'] = paper.get('abstract')
            data['study_type'] = classification.study_type
            data['relevance_score'] = classification.relevance_score
            data['drug_name'] = drug_name
            data['generic_name'] = drug_info.get('generic_name')
            data['mechanism'] = drug_info.get('mechanism')
            data['target'] = drug_info.get('target')
            data['approved_indications'] = drug_info.get('approved_indications', [])
            data['search_query'] = paper.get('search_query')
            data['search_source'] = paper.get('search_source')

            # Ensure outcomes and safety_events are lists, not None
            if data.get('outcomes') is None:
                data['outcomes'] = []
            if data.get('safety_events') is None:
                data['safety_events'] = []

            # Convert to Pydantic model
            case_study = OffLabelCaseStudy(**data)
            return case_study

        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Failed to parse extraction: {e}")
            logger.error(f"Response text: {text[:500]}")
            return None

    def _extract_json_from_text(self, text: str) -> str:
        """Extract JSON from text that might have markdown formatting."""
        # Remove markdown code blocks
        text = re.sub(r'```json\s*', '', text)
        text = re.sub(r'```\s*', '', text)

        # Find JSON object
        start = text.find('{')
        if start == -1:
            return text

        # Find matching closing brace
        open_braces = 0
        for i in range(start, len(text)):
            if text[i] == '{':
                open_braces += 1
            elif text[i] == '}':
                open_braces -= 1
                if open_braces == 0:
                    return text[start:i+1]

        return text[start:]

    def _get_extraction_prompt(
        self,
        paper_content: str,
        drug_name: str,
        drug_info: Dict[str, Any],
        classification: StudyClassification
    ) -> str:
        """Generate extraction prompt."""

        # Truncate content if too long
        max_content_length = 20000
        if len(paper_content) > max_content_length:
            paper_content = paper_content[:max_content_length] + "\n\n[Content truncated...]"

        return f"""Extract structured data from this case study.

Drug: {drug_name}
Mechanism: {drug_info.get('mechanism', 'Unknown')}
Study Type: {classification.study_type}
N Patients: {classification.n_patients}

Paper Content:
{paper_content}

Extract ALL available information and return as JSON matching this schema:

{{
    "indication_treated": "The indication/disease being treated (off-label)",
    "is_off_label": true,
    "n_patients": {classification.n_patients or 'null'},
    "dosing_regimen": "Dosing regimen (e.g., '5mg BID', '300mg Q2W')",
    "treatment_duration": "Treatment duration (e.g., '6 months', '12 weeks')",
    "concomitant_medications": ["List of other medications"],

    "response_rate": "Response rate description (e.g., '75% (9/12)')",
    "responders_n": 9,
    "responders_pct": 75.0,
    "time_to_response": "Time to response (e.g., '4-8 weeks')",
    "duration_of_response": "Duration of response (e.g., 'Sustained at 12 months')",

    "serious_adverse_events_n": 0,
    "discontinuations_n": 0,

    "efficacy_signal": "Strong/Moderate/Weak/None",
    "safety_profile": "Acceptable/Concerning/Unknown",
    "mechanism_rationale": "Why this mechanism makes sense for this indication",
    "development_potential": "High/Medium/Low",
    "key_findings": "1-2 sentence summary",

    "baseline_characteristics": {{
        "n": {classification.n_patients or 'null'},
        "median_age": 45.0,
        "mean_age": 47.2,
        "male_pct": 33.3,
        "female_pct": 66.7,
        "disease_severity": "Moderate to severe",
        "prior_medications_detail": [
            {{"medication": "Prednisone", "n_patients": 12, "outcome": "Failed or intolerable"}},
            {{"medication": "Methotrexate", "n_patients": 8, "outcome": "Inadequate response"}}
        ],
        "comorbidities": ["List of comorbidities"],
        "biomarkers": {{"biomarker_name": "value"}}
    }},

    "outcomes": [
        {{
            "outcome_name": "Skin rash improvement",
            "outcome_category": "Primary",
            "timepoint": "Week 12",
            "responders_n": 9,
            "responders_pct": 75.0,
            "notes": "Complete or near-complete resolution"
        }}
    ],

    "safety_events": [
        {{
            "event_name": "Upper respiratory infection",
            "event_category": "Adverse Event",
            "severity": "Mild",
            "n_patients": 3,
            "incidence_pct": 25.0,
            "event_outcome": "Resolved without intervention"
        }}
    ]
}}

IMPORTANT:
- Extract EVERY piece of clinical data available
- For baseline characteristics, extract ALL demographics and disease characteristics
- For outcomes, extract ALL efficacy endpoints mentioned
- For safety, extract ALL adverse events mentioned
- Use null for missing data
- Be thorough and accurate"""

        return prompt

    # =====================================================
    # VALIDATION
    # =====================================================

    def _validate_extraction(
        self,
        extraction: OffLabelCaseStudy
    ) -> OffLabelValidationResult:
        """
        Validate extraction quality.

        Checks clinical plausibility and data completeness.
        """
        prompt = self._get_validation_prompt(extraction)

        response = self._call_claude_with_thinking(prompt, thinking_budget=2000)
        text = self._extract_text_response(response)

        # Parse validation result
        try:
            data = json.loads(text)
            return OffLabelValidationResult(**data)
        except json.JSONDecodeError:
            json_str = self._extract_json_from_text(text)
            if json_str:
                try:
                    data = json.loads(json_str)
                    return OffLabelValidationResult(**data)
                except:
                    pass

            logger.error(f"Failed to parse validation response: {text[:500]}")
            return OffLabelValidationResult(
                is_valid=False,
                issues=["Validation parsing failed"],
                warnings=[]
            )

    def _get_validation_prompt(self, extraction: OffLabelCaseStudy) -> str:
        """Generate validation prompt."""
        extraction_json = extraction.model_dump_json(indent=2)

        return f"""Validate the case study data extraction for quality and plausibility.

Extraction:
{extraction_json}

Check:
1. Data completeness (baseline, outcomes, safety)
2. Clinical plausibility (demographics, response rates, adverse events)
3. Internal consistency

Return JSON:
{{
    "is_valid": true,
    "issues": ["List of critical issues"],
    "warnings": ["List of non-critical warnings"],
    "has_baseline_data": true,
    "has_outcome_data": true,
    "has_safety_data": true,
    "baseline_completeness_pct": 75.0,
    "outcome_count": 3,
    "safety_event_count": 2,
    "demographics_plausible": true,
    "outcomes_plausible": true
}}

Set is_valid=false if there are critical issues."""

    def _calculate_confidence(self, validation: OffLabelValidationResult) -> float:
        """Calculate overall confidence score from validation."""
        if not validation.is_valid:
            return 0.5

        # Start with baseline
        confidence = 0.7

        # Boost for data completeness
        if validation.has_baseline_data:
            confidence += 0.05
        if validation.has_outcome_data:
            confidence += 0.10
        if validation.has_safety_data:
            confidence += 0.05

        # Boost for plausibility
        if validation.demographics_plausible and validation.outcomes_plausible:
            confidence += 0.05

        # Penalize for issues
        confidence -= len(validation.issues) * 0.05

        return min(max(confidence, 0.0), 1.0)

    def _calculate_evidence_quality(self, case_study: OffLabelCaseStudy) -> Dict[str, Any]:
        """
        Assess evidence quality using modified GRADE criteria.

        Criteria:
        - Sample size adequacy (n≥10 for case series)
        - Study design (prospective > retrospective)
        - Control group presence
        - Outcome measurement quality (objective measures)
        - Follow-up duration adequacy
        - Safety reporting completeness
        - Potential for bias

        Returns:
            Dict with quality assessment and grade (A/B/C/D)
        """
        quality = {
            'overall_grade': 'C',  # Default
            'score': 0,
            'max_score': 10,

            # Individual criteria
            'sample_size_adequate': False,
            'sample_size_score': 0,

            'study_design_quality': 'Low',
            'study_design_score': 0,

            'has_control_group': False,
            'control_group_score': 0,

            'outcome_quality': 'Low',
            'outcome_score': 0,

            'followup_adequate': False,
            'followup_score': 0,

            'safety_reporting': 'Poor',
            'safety_score': 0,

            'bias_risk': 'High',

            'limitations': [],
            'strengths': []
        }

        # 1. Sample size (0-2 points)
        n = case_study.n_patients or 0
        if n >= 50:
            quality['sample_size_adequate'] = True
            quality['sample_size_score'] = 2
            quality['strengths'].append(f"Large sample size (n={n})")
        elif n >= 10:
            quality['sample_size_adequate'] = True
            quality['sample_size_score'] = 1
        else:
            quality['limitations'].append(f"Small sample size (n={n})")

        # 2. Study design (0-3 points)
        study_type = case_study.study_type
        if study_type in ['Clinical Trial', 'Prospective Cohort', 'Pilot Study', 'Open-Label Trial', 'N-of-1 Trial']:
            quality['study_design_quality'] = 'High'
            quality['study_design_score'] = 3
            quality['strengths'].append(f"Prospective design ({study_type})")
        elif study_type in ['Case Series', 'Retrospective Cohort', 'Real-World Evidence']:
            quality['study_design_quality'] = 'Moderate'
            quality['study_design_score'] = 2
        elif study_type == 'Case Report':
            quality['study_design_quality'] = 'Low'
            quality['study_design_score'] = 1
            quality['limitations'].append("Case report (lowest evidence level)")
        else:
            # Default for other types
            quality['study_design_quality'] = 'Moderate'
            quality['study_design_score'] = 2

        # 3. Control group (0-2 points)
        # Assume no control for now (would need to be extracted)
        quality['has_control_group'] = False
        quality['control_group_score'] = 0
        quality['limitations'].append("No control group")

        # 4. Outcome measurement (0-2 points)
        n_outcomes = len(case_study.outcomes)
        if n_outcomes >= 3:
            quality['outcome_quality'] = 'High'
            quality['outcome_score'] = 2
            quality['strengths'].append(f"Multiple outcomes measured (n={n_outcomes})")
        elif n_outcomes >= 1:
            quality['outcome_quality'] = 'Moderate'
            quality['outcome_score'] = 1
        else:
            quality['outcome_quality'] = 'Low'
            quality['outcome_score'] = 0
            quality['limitations'].append("Outcomes poorly defined")

        # 5. Follow-up duration (0-1 point)
        duration = case_study.treatment_duration or ""
        if "month" in duration.lower() or "year" in duration.lower():
            quality['followup_adequate'] = True
            quality['followup_score'] = 1
            quality['strengths'].append(f"Adequate follow-up ({duration})")
        else:
            quality['limitations'].append("Short follow-up or not reported")

        # 6. Safety reporting (0-1 point)
        n_safety = len(case_study.safety_events)
        if n_safety >= 2 or case_study.serious_adverse_events_n is not None:
            quality['safety_reporting'] = 'Good'
            quality['safety_score'] = 1
            quality['strengths'].append("Comprehensive safety reporting")
        elif n_safety == 1:
            quality['safety_reporting'] = 'Fair'
            quality['safety_score'] = 0.5
        else:
            quality['safety_reporting'] = 'Poor'
            quality['safety_score'] = 0
            quality['limitations'].append("Limited safety data")

        # Calculate total score
        quality['score'] = (
            quality['sample_size_score'] +
            quality['study_design_score'] +
            quality['control_group_score'] +
            quality['outcome_score'] +
            quality['followup_score'] +
            quality['safety_score']
        )

        # Assign grade
        score_pct = (quality['score'] / quality['max_score']) * 100
        if score_pct >= 80:
            quality['overall_grade'] = 'A'
        elif score_pct >= 65:
            quality['overall_grade'] = 'B'
        elif score_pct >= 50:
            quality['overall_grade'] = 'C'
        else:
            quality['overall_grade'] = 'D'

        # Assess bias risk
        if quality['score'] >= 7:
            quality['bias_risk'] = 'Low'
        elif quality['score'] >= 5:
            quality['bias_risk'] = 'Moderate'
        else:
            quality['bias_risk'] = 'High'

        return quality

    # =====================================================
    # MAIN ORCHESTRATION
    # =====================================================

    def analyze_drug(
        self,
        drug_name: str,
        max_papers: int = 50,
        max_workers: int = 5,
        progress_callback=None,
        use_parallel: bool = True
    ) -> Dict[str, Any]:
        """
        Main workflow: Analyze off-label use for a drug with parallel processing.

        Args:
            drug_name: Name of drug
            max_papers: Maximum papers to process
            max_workers: Number of concurrent workers (default: 5)
            progress_callback: Optional callback for progress updates
            use_parallel: Whether to use parallel processing (default: True)

        Returns:
            Dict with results summary
        """
        logger.info(f"=" * 80)
        logger.info(f"Starting off-label analysis for: {drug_name}")
        logger.info(f"=" * 80)

        results = {
            'drug_name': drug_name,
            'drug_info': None,
            'papers_found': 0,
            'papers_classified': 0,
            'case_studies_extracted': 0,
            'case_studies': [],
            'related_mechanisms': [],
            'errors': []
        }

        try:
            # Stage 1: Extract mechanism
            logger.info("\n[Stage 1] Extracting mechanism...")
            drug_info = self.extract_mechanism(drug_name)
            results['drug_info'] = drug_info

            # Stage 2: Search for off-label literature
            logger.info("\n[Stage 2] Searching for off-label literature...")
            papers = self.search_off_label_literature(drug_name, max_results=max_papers)
            results['papers_found'] = len(papers)

            if not papers:
                logger.warning("No papers found")
                return results

            # Stage 3: Classify and extract (with optional parallel processing)
            if use_parallel and len(papers) > 3:
                logger.info(f"\n[Stage 3] Processing {len(papers)} papers with {max_workers} workers...")

                from concurrent.futures import ThreadPoolExecutor, as_completed
                import threading

                # Thread-safe counter for progress
                processed_count = [0]
                lock = threading.Lock()

                def update_progress(message):
                    with lock:
                        processed_count[0] += 1
                        current = processed_count[0]

                    if progress_callback:
                        progress_callback(current, len(papers), message)
                    logger.info(f"[{current}/{len(papers)}] {message}")

                # Submit all papers for processing
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = {
                        executor.submit(
                            self._process_single_paper,
                            paper,
                            drug_name,
                            drug_info,
                            update_progress
                        ): paper
                        for paper in papers
                    }

                    # Collect results as they complete
                    for future in as_completed(futures):
                        paper = futures[future]
                        try:
                            result = future.result()

                            if result:
                                with lock:
                                    results['case_studies_extracted'] += 1
                                    results['case_studies'].append(result)

                                logger.info(f"✓ Saved: {result['indication']} (PMID: {result.get('pmid')})")

                        except Exception as e:
                            logger.error(f"Error processing paper {paper.get('pmid')}: {e}")
                            with lock:
                                results['errors'].append({
                                    'pmid': paper.get('pmid'),
                                    'title': paper.get('title', '')[:100],
                                    'error': str(e)
                                })

                # Update classified count
                results['papers_classified'] = len([cs for cs in results['case_studies'] if cs])

            else:
                # Sequential processing (original logic)
                logger.info("\n[Stage 3] Classifying and extracting papers (sequential)...")
                for i, paper in enumerate(papers, 1):
                    logger.info(f"\nProcessing paper {i}/{len(papers)}: {paper.get('title', 'Unknown')[:80]}...")

                    if progress_callback:
                        progress_callback(i, len(papers), f"Processing {paper.get('title', 'Unknown')[:50]}")

                    try:
                        # Check if already extracted
                        if self.db.check_paper_exists(
                            paper.get('pmid'),
                            drug_name,
                            paper.get('indication_treated', '')
                        ):
                            logger.info("Paper already extracted, skipping")
                            continue

                        # Classify
                        classification = self.classify_paper(paper, drug_name)
                        if not classification:
                            continue

                        results['papers_classified'] += 1

                        # Extract
                        case_study = self.extract_case_study_data(
                            paper, drug_name, drug_info, classification
                        )

                        if case_study:
                            # Save to database
                            case_study_id = self.db.save_case_study(case_study)
                            logger.info(f"✓ Saved case study {case_study_id}")

                            results['case_studies_extracted'] += 1
                            results['case_studies'].append({
                                'case_study_id': case_study_id,
                                'title': case_study.title,
                                'indication': case_study.indication_treated,
                                'n_patients': case_study.n_patients,
                                'efficacy_signal': case_study.efficacy_signal,
                                'development_potential': case_study.development_potential
                            })

                    except Exception as e:
                        logger.error(f"Error processing paper: {e}")
                        results['errors'].append(str(e))
                        continue

            # Stage 4: Mechanism expansion (for user selection)
            logger.info("\n[Stage 4] Expanding mechanisms...")
            if drug_info.get('mechanism'):
                related_mechanisms = self.expand_mechanisms(
                    drug_info['mechanism'],
                    drug_info.get('target', '')
                )
                results['related_mechanisms'] = related_mechanisms

            logger.info("\n" + "=" * 80)
            logger.info("Analysis complete!")
            logger.info(f"Papers found: {results['papers_found']}")
            logger.info(f"Papers classified: {results['papers_classified']}")
            logger.info(f"Case studies extracted: {results['case_studies_extracted']}")
            logger.info("=" * 80)

        except Exception as e:
            logger.error(f"Error in analysis: {e}")
            results['errors'].append(str(e))

        return results

    def _process_single_paper(
        self,
        paper: Dict[str, Any],
        drug_name: str,
        drug_info: Dict[str, Any],
        progress_callback=None
    ) -> Optional[Dict[str, Any]]:
        """
        Process a single paper (designed for parallel execution).

        This is thread-safe and can be run concurrently.

        Args:
            paper: Paper metadata
            drug_name: Drug name
            drug_info: Drug information
            progress_callback: Optional callback for progress updates

        Returns:
            Dict with case study summary or None if not relevant
        """
        pmid = paper.get('pmid')
        title = paper.get('title', 'Unknown')[:80]

        try:
            # Check if already extracted
            if self.db.check_paper_exists(
                pmid,
                drug_name,
                paper.get('indication_treated', '')
            ):
                if progress_callback:
                    progress_callback(f"Already extracted: {title}")
                return None

            # Classify
            classification = self.classify_paper(paper, drug_name)
            if not classification:
                if progress_callback:
                    progress_callback(f"Not relevant: {title}")
                return None

            # Extract
            case_study = self.extract_case_study_data(
                paper, drug_name, drug_info, classification
            )

            if not case_study:
                if progress_callback:
                    progress_callback(f"Extraction failed: {title}")
                return None

            # Save to database (database operations should be thread-safe)
            case_study_id = self.db.save_case_study(case_study)

            if progress_callback:
                progress_callback(f"Extracted: {case_study.indication_treated}")

            return {
                'case_study_id': case_study_id,
                'pmid': case_study.pmid,
                'title': case_study.title,
                'indication': case_study.indication_treated,
                'n_patients': case_study.n_patients,
                'efficacy_signal': case_study.efficacy_signal,
                'development_potential': case_study.development_potential,
                'response_rate': case_study.response_rate
            }

        except Exception as e:
            logger.error(f"Error processing paper {pmid}: {e}")
            if progress_callback:
                progress_callback(f"Error: {title}")
            raise  # Re-raise so it's captured by future.result()

    def analyze_mechanism(
        self,
        mechanism: str,
        target: str,
        max_papers: int = 50
    ) -> Dict[str, Any]:
        """
        Analyze off-label use for drugs with a specific mechanism.

        Args:
            mechanism: Mechanism of action
            target: Molecular target
            max_papers: Maximum papers per drug

        Returns:
            Dict with results summary
        """
        logger.info(f"Analyzing mechanism: {mechanism}")

        # Find drugs with this mechanism from database
        drugs = self._find_drugs_by_mechanism(mechanism, target)

        if not drugs:
            logger.warning(f"No drugs found with mechanism: {mechanism}")
            return {
                'mechanism': mechanism,
                'target': target,
                'drugs_found': 0,
                'results': []
            }

        logger.info(f"Found {len(drugs)} drugs with mechanism: {mechanism}")

        results = {
            'mechanism': mechanism,
            'target': target,
            'drugs_found': len(drugs),
            'results': []
        }

        # Analyze each drug
        for drug in drugs:
            drug_name = drug.get('drug_name')
            logger.info(f"\nAnalyzing {drug_name}...")

            drug_results = self.analyze_drug(drug_name, max_papers=max_papers)
            results['results'].append(drug_results)

        return results

    def _find_drugs_by_mechanism(
        self,
        mechanism: str,
        target: str
    ) -> List[Dict[str, Any]]:
        """Find drugs with similar mechanism from database."""
        import psycopg2
        from psycopg2.extras import RealDictCursor

        conn = psycopg2.connect(self.db.database_url)
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = """
                    SELECT drug_id, drug_name, generic_name, mechanism, target
                    FROM drugs
                    WHERE mechanism ILIKE %s OR target ILIKE %s
                    LIMIT 10
                """
                cur.execute(query, (f"%{mechanism}%", f"%{target}%"))
                return [dict(row) for row in cur.fetchall()]
        finally:
            conn.close()

    def aggregate_indication_evidence(self, drug_name: str) -> List[Dict[str, Any]]:
        """
        Aggregate all case studies for a drug and rank indications by evidence strength.

        Returns ranked list of indications with:
        - Total patients treated
        - Response rate (weighted average)
        - Number of independent reports
        - Evidence quality score
        - Development potential

        Args:
            drug_name: Name of drug to analyze

        Returns:
            List of dicts with indication evidence, sorted by evidence score (highest first)
        """
        logger.info(f"Aggregating evidence for {drug_name}")

        # Query database for all case studies
        case_studies = self.db.get_case_studies_by_drug(drug_name)

        if not case_studies:
            logger.warning(f"No case studies found for {drug_name}")
            return []

        # Group by indication
        indication_groups = {}
        for study in case_studies:
            indication = study.indication_treated
            if indication not in indication_groups:
                indication_groups[indication] = []
            indication_groups[indication].append(study)

        logger.info(f"Found {len(indication_groups)} unique indications")

        # Score each indication
        scored_indications = []
        for indication, studies in indication_groups.items():
            score_details = self._calculate_indication_score(studies)

            scored_indications.append({
                'indication': indication,
                'n_studies': len(studies),
                'total_patients': sum(s.n_patients or 0 for s in studies),
                'avg_response_rate': self._calculate_weighted_response_rate(studies),
                'evidence_score': score_details['total_score'],
                'score_breakdown': score_details,
                'avg_confidence': sum(s.extraction_confidence for s in studies) / len(studies),
                'development_potential': self._aggregate_development_potential(studies),
                'safety_profile': self._aggregate_safety_profile(studies),
                'studies': [
                    {
                        'pmid': s.pmid,
                        'title': s.title,
                        'year': s.year,
                        'n_patients': s.n_patients,
                        'efficacy_signal': s.efficacy_signal,
                        'response_rate': s.response_rate
                    }
                    for s in studies
                ]
            })

        # Rank by evidence score
        scored_indications.sort(key=lambda x: x['evidence_score'], reverse=True)

        logger.info(f"Top indication: {scored_indications[0]['indication']} (score: {scored_indications[0]['evidence_score']:.1f})")

        return scored_indications

    def _calculate_indication_score(self, studies: List[OffLabelCaseStudy]) -> Dict[str, float]:
        """
        Score indication based on multiple evidence dimensions.

        Scoring criteria:
        - Replication: Independent reports (max 30 points)
        - Sample size: Total patients treated (max 25 points)
        - Efficacy: Response rates (max 30 points)
        - Quality: Study quality/confidence (max 10 points)
        - Potential: Development potential (max 5 points)

        Total possible: 100 points

        Args:
            studies: List of case studies for this indication

        Returns:
            Dict with score breakdown
        """
        # 1. Replication bonus (diminishing returns)
        n_studies = len(studies)
        replication_score = min(n_studies * 10, 30)  # Cap at 30 points

        # 2. Sample size
        total_patients = sum(s.n_patients or 0 for s in studies)
        sample_size_score = min(total_patients / 10, 25)  # Cap at 25 points

        # 3. Response rate
        avg_response = self._calculate_weighted_response_rate(studies)
        efficacy_score = avg_response * 0.3  # 0-30 points (assuming response is 0-100%)

        # 4. Study quality (avg extraction confidence)
        avg_confidence = sum(s.extraction_confidence for s in studies) / len(studies)
        quality_score = avg_confidence * 10  # 0-10 points

        # 5. Development potential
        high_potential = sum(1 for s in studies if s.development_potential == 'High')
        medium_potential = sum(1 for s in studies if s.development_potential == 'Medium')
        potential_score = ((high_potential * 1.0 + medium_potential * 0.5) / len(studies)) * 5  # 0-5 points

        total_score = (
            replication_score +
            sample_size_score +
            efficacy_score +
            quality_score +
            potential_score
        )

        return {
            'total_score': total_score,
            'replication_score': replication_score,
            'sample_size_score': sample_size_score,
            'efficacy_score': efficacy_score,
            'quality_score': quality_score,
            'potential_score': potential_score
        }

    def _calculate_weighted_response_rate(self, studies: List[OffLabelCaseStudy]) -> float:
        """
        Calculate weighted average response rate.

        Weights by sample size to give more weight to larger studies.

        Args:
            studies: List of case studies

        Returns:
            Weighted average response rate (0-100)
        """
        total_weight = 0
        weighted_sum = 0

        for study in studies:
            if study.responders_pct is not None and study.n_patients:
                weight = study.n_patients
                weighted_sum += study.responders_pct * weight
                total_weight += weight

        if total_weight == 0:
            return 0.0

        return weighted_sum / total_weight

    def _aggregate_development_potential(self, studies: List[OffLabelCaseStudy]) -> str:
        """Aggregate development potential across studies."""
        potential_counts = {
            'High': sum(1 for s in studies if s.development_potential == 'High'),
            'Medium': sum(1 for s in studies if s.development_potential == 'Medium'),
            'Low': sum(1 for s in studies if s.development_potential == 'Low')
        }

        # Majority vote
        max_count = max(potential_counts.values())
        for potential, count in potential_counts.items():
            if count == max_count:
                return potential

        return 'Medium'

    def _aggregate_safety_profile(self, studies: List[OffLabelCaseStudy]) -> str:
        """Aggregate safety profile across studies."""
        safety_counts = {
            'Acceptable': sum(1 for s in studies if s.safety_profile == 'Acceptable'),
            'Concerning': sum(1 for s in studies if s.safety_profile == 'Concerning'),
            'Unknown': sum(1 for s in studies if s.safety_profile == 'Unknown')
        }

        # If any study shows concerning safety, flag as concerning
        if safety_counts['Concerning'] > 0:
            return 'Concerning'

        # If majority is acceptable, return acceptable
        if safety_counts['Acceptable'] > len(studies) / 2:
            return 'Acceptable'

        return 'Unknown'

    # =====================================================
    # CITATION NETWORK ANALYSIS
    # =====================================================

    def find_related_papers_by_citations(
        self,
        pmid: str,
        max_related: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Find related papers using PubMed citation network (eLink API).

        This follows:
        - Papers that cite this paper (cited by)
        - Papers cited by this paper (references)
        - Papers similar to this paper (related)

        Args:
            pmid: PubMed ID of seed paper
            max_related: Maximum related papers to return

        Returns:
            List of related papers with metadata
        """
        logger.info(f"Finding related papers for PMID: {pmid}")

        related_papers = []

        try:
            # Use PubMed eLink API to find related papers
            from Bio import Entrez
            Entrez.email = "your_email@example.com"  # Required by NCBI

            # Get papers that cite this paper
            logger.info("Finding citing papers...")
            handle = Entrez.elink(dbfrom="pubmed", id=pmid, linkname="pubmed_pubmed_citedin")
            citing_record = Entrez.read(handle)
            handle.close()

            citing_pmids = []
            if citing_record and citing_record[0].get('LinkSetDb'):
                for link in citing_record[0]['LinkSetDb']:
                    if link['LinkName'] == 'pubmed_pubmed_citedin':
                        citing_pmids = [link_item['Id'] for link_item in link['Link']]
                        break

            logger.info(f"Found {len(citing_pmids)} citing papers")

            # Get papers cited by this paper (references)
            logger.info("Finding referenced papers...")
            handle = Entrez.elink(dbfrom="pubmed", id=pmid, linkname="pubmed_pubmed_refs")
            refs_record = Entrez.read(handle)
            handle.close()

            ref_pmids = []
            if refs_record and refs_record[0].get('LinkSetDb'):
                for link in refs_record[0]['LinkSetDb']:
                    if link['LinkName'] == 'pubmed_pubmed_refs':
                        ref_pmids = [link_item['Id'] for link_item in link['Link']]
                        break

            logger.info(f"Found {len(ref_pmids)} referenced papers")

            # Get similar papers
            logger.info("Finding similar papers...")
            handle = Entrez.elink(dbfrom="pubmed", id=pmid, linkname="pubmed_pubmed")
            similar_record = Entrez.read(handle)
            handle.close()

            similar_pmids = []
            if similar_record and similar_record[0].get('LinkSetDb'):
                for link in similar_record[0]['LinkSetDb']:
                    if link['LinkName'] == 'pubmed_pubmed':
                        similar_pmids = [link_item['Id'] for link_item in link['Link']]
                        break

            logger.info(f"Found {len(similar_pmids)} similar papers")

            # Combine and deduplicate
            all_related_pmids = list(set(citing_pmids + ref_pmids + similar_pmids))

            # Limit to max_related
            all_related_pmids = all_related_pmids[:max_related]

            logger.info(f"Total unique related papers: {len(all_related_pmids)}")

            # Fetch metadata for related papers
            if all_related_pmids:
                logger.info("Fetching metadata for related papers...")
                papers = self.pubmed.search_papers_by_pmids(all_related_pmids)

                # Add relationship type
                for paper in papers:
                    paper_pmid = paper.get('pmid')
                    relationships = []

                    if paper_pmid in citing_pmids:
                        relationships.append('cites_seed')
                    if paper_pmid in ref_pmids:
                        relationships.append('cited_by_seed')
                    if paper_pmid in similar_pmids:
                        relationships.append('similar_to_seed')

                    paper['relationship_to_seed'] = relationships
                    paper['seed_pmid'] = pmid

                related_papers = papers

            logger.info(f"Returning {len(related_papers)} related papers")

        except Exception as e:
            logger.error(f"Error finding related papers: {e}")

        return related_papers

    def expand_search_via_citations(
        self,
        drug_name: str,
        seed_papers: List[Dict[str, Any]],
        max_related_per_paper: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Expand paper search by following citation networks from seed papers.

        This is useful for finding additional case studies that may not appear
        in direct keyword searches.

        Args:
            drug_name: Drug name
            seed_papers: Initial set of papers
            max_related_per_paper: Max related papers to fetch per seed

        Returns:
            List of newly discovered papers
        """
        logger.info(f"Expanding search via citations for {drug_name}")
        logger.info(f"Starting with {len(seed_papers)} seed papers")

        all_related = []
        seen_pmids = {p.get('pmid') for p in seed_papers if p.get('pmid')}

        for i, seed_paper in enumerate(seed_papers, 1):
            pmid = seed_paper.get('pmid')
            if not pmid:
                continue

            logger.info(f"[{i}/{len(seed_papers)}] Finding related papers for PMID: {pmid}")

            related = self.find_related_papers_by_citations(pmid, max_related_per_paper)

            # Filter out duplicates
            new_papers = [p for p in related if p.get('pmid') not in seen_pmids]

            logger.info(f"Found {len(new_papers)} new papers")

            all_related.extend(new_papers)
            seen_pmids.update(p.get('pmid') for p in new_papers if p.get('pmid'))

        logger.info(f"Citation expansion complete. Found {len(all_related)} new papers")

        return all_related

    # =====================================================
    # COMPARATIVE ANALYSIS
    # =====================================================

    def compare_to_approved_drugs(
        self,
        drug_name: str,
        indication: str
    ) -> Dict[str, Any]:
        """
        Compare off-label candidate to approved drugs for the indication.

        This helps assess:
        - How the off-label drug compares to standard of care
        - Whether there's an unmet need
        - Competitive landscape

        Args:
            drug_name: Off-label drug name
            indication: Target indication

        Returns:
            Dict with comparative analysis
        """
        logger.info(f"Comparing {drug_name} to approved drugs for {indication}")

        comparison = {
            'off_label_drug': drug_name,
            'indication': indication,
            'approved_drugs': [],
            'off_label_data': None,
            'comparative_summary': None,
            'unmet_need_assessment': None
        }

        try:
            # 1. Get off-label case study data
            logger.info("Fetching off-label case study data...")
            case_studies = self.db.get_case_studies_by_drug_and_indication(drug_name, indication)

            if not case_studies:
                logger.warning(f"No case studies found for {drug_name} in {indication}")
                return comparison

            # Aggregate off-label data
            comparison['off_label_data'] = {
                'n_studies': len(case_studies),
                'total_patients': sum(s.n_patients or 0 for s in case_studies),
                'avg_response_rate': self._calculate_weighted_response_rate(case_studies),
                'efficacy_signals': [s.efficacy_signal for s in case_studies],
                'safety_profiles': [s.safety_profile for s in case_studies],
                'development_potential': self._aggregate_development_potential(case_studies)
            }

            # 2. Find approved drugs for this indication
            logger.info(f"Finding approved drugs for {indication}...")
            approved_drugs = self._find_approved_drugs_for_indication(indication)

            if not approved_drugs:
                logger.warning(f"No approved drugs found for {indication}")
                comparison['unmet_need_assessment'] = "High - No approved therapies found"
                return comparison

            logger.info(f"Found {len(approved_drugs)} approved drugs")

            # 3. Get clinical data for approved drugs
            for approved_drug in approved_drugs:
                drug_id = approved_drug.get('drug_id')
                drug_name_approved = approved_drug.get('drug_name')

                logger.info(f"Fetching clinical data for {drug_name_approved}...")

                # Get clinical trial data from database
                clinical_data = self.db.get_clinical_data_for_drug_indication(drug_id, indication)

                comparison['approved_drugs'].append({
                    'drug_name': drug_name_approved,
                    'drug_id': drug_id,
                    'approval_status': approved_drug.get('status'),
                    'mechanism': approved_drug.get('mechanism'),
                    'clinical_data': clinical_data
                })

            # 4. Generate comparative summary using Claude
            logger.info("Generating comparative summary...")
            comparison['comparative_summary'] = self._generate_comparative_summary(comparison)
            comparison['unmet_need_assessment'] = self._assess_unmet_need(comparison)

        except Exception as e:
            logger.error(f"Error in comparative analysis: {e}")
            comparison['error'] = str(e)

        return comparison

    def _find_approved_drugs_for_indication(self, indication: str) -> List[Dict[str, Any]]:
        """Find approved drugs for a specific indication from database."""
        # Query drugs database for approved drugs with this indication
        query = """
        SELECT DISTINCT
            d.drug_id,
            d.drug_name,
            d.generic_name,
            d.mechanism,
            d.target,
            d.status,
            di.indication_name
        FROM drugs d
        JOIN drug_indications di ON d.drug_id = di.drug_id
        WHERE di.indication_name ILIKE %s
        AND d.status = 'Approved'
        ORDER BY d.drug_name
        """

        try:
            with self.db.conn.cursor() as cur:
                cur.execute(query, (f'%{indication}%',))
                results = cur.fetchall()
                return results
        except Exception as e:
            logger.error(f"Error finding approved drugs: {e}")
            return []

    def _generate_comparative_summary(self, comparison: Dict[str, Any]) -> str:
        """Generate comparative summary using Claude."""
        prompt = f"""Compare the off-label drug to approved therapies for this indication.

Off-label Drug: {comparison['off_label_drug']}
Indication: {comparison['indication']}

Off-label Data:
{json.dumps(comparison['off_label_data'], indent=2)}

Approved Drugs:
{json.dumps(comparison['approved_drugs'], indent=2)}

Provide a concise comparative summary (3-5 sentences) addressing:
1. How does the off-label drug's efficacy compare to approved therapies?
2. How does the safety profile compare?
3. What are the key advantages/disadvantages?
4. Is there a potential role for this drug in the treatment landscape?
"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}]
            )

            return self._extract_text_response(response)
        except Exception as e:
            logger.error(f"Error generating comparative summary: {e}")
            return "Error generating summary"

    def _assess_unmet_need(self, comparison: Dict[str, Any]) -> str:
        """Assess unmet need based on comparative analysis."""
        n_approved = len(comparison['approved_drugs'])

        if n_approved == 0:
            return "High - No approved therapies available"
        elif n_approved <= 2:
            return "Moderate - Limited treatment options available"
        else:
            # Check if off-label drug shows advantages
            off_label_data = comparison.get('off_label_data', {})
            dev_potential = off_label_data.get('development_potential', 'Low')

            if dev_potential == 'High':
                return "Moderate - Multiple approved therapies exist, but off-label drug shows promise"
            else:
                return "Low - Multiple approved therapies available"

