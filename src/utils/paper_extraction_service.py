"""
Paper Extraction Service

Unified service for extracting data from clinical papers.
Provides a simple interface for other workflows to extract structured data
from papers without worrying about the underlying extraction logic.

This service:
1. Handles paper content retrieval (from JSON files, PDFs, or abstracts)
2. Routes to appropriate extractor (clinical trial vs case study)
3. Returns standardized extraction results
"""
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Literal
from anthropic import Anthropic

from src.agents.clinical_data_extractor import ClinicalDataExtractorAgent
from src.models.clinical_extraction_schemas import ClinicalTrialExtraction, TrialDesignMetadata

logger = logging.getLogger(__name__)

# PyMuPDF for PDF extraction
try:
    from pymupdf4llm.helpers.pymupdf_rag import to_markdown
    import pymupdf
    PYMUPDF_AVAILABLE = True
except ImportError:
    logger.warning("pymupdf4llm not available. PDF extraction will be limited.")
    PYMUPDF_AVAILABLE = False


class PaperExtractionService:
    """
    Unified service for extracting data from clinical papers.
    
    Usage:
        service = PaperExtractionService(anthropic_client)
        
        # Extract from existing JSON file
        result = service.extract_from_paper(
            paper_path="data/clinical_papers/drug/indication/paper.json",
            drug_name="Tofacitinib",
            indication="Dermatomyositis"
        )
        
        # Extract from PDF
        result = service.extract_from_pdf(
            pdf_path="path/to/paper.pdf",
            drug_name="Tofacitinib",
            indication="Dermatomyositis"
        )
    """
    
    def __init__(
        self,
        client: Anthropic,
        model: str = "claude-sonnet-4-5-20250929"
    ):
        """
        Initialize paper extraction service.
        
        Args:
            client: Anthropic API client
            model: Claude model to use
        """
        self.client = client
        self.model = model
        self.clinical_extractor = ClinicalDataExtractorAgent(
            client=client,
            model=model
        )
    
    def extract_from_paper(
        self,
        paper_path: str | Path,
        drug_name: str,
        indication: str,
        nct_id: Optional[str] = None,
        standard_endpoints: Optional[List[str]] = None,
        extraction_type: Literal["clinical_trial", "case_study", "auto"] = "auto"
    ) -> Dict[str, Any]:
        """
        Extract data from a paper JSON file.
        
        Args:
            paper_path: Path to paper JSON file (from PaperScope/Clinical Data Collector)
            drug_name: Drug name
            indication: Disease indication
            nct_id: Optional NCT ID (will be extracted from paper if not provided)
            standard_endpoints: Optional list of standard endpoints for the indication
            extraction_type: Type of extraction ("clinical_trial", "case_study", or "auto")
        
        Returns:
            Dictionary containing:
                - extraction_type: "clinical_trial" or "case_study"
                - trial_design: TrialDesignMetadata (for clinical trials)
                - extractions: List of ClinicalTrialExtraction objects
                - paper_metadata: Paper metadata (title, authors, etc.)
        """
        paper_path = Path(paper_path)
        
        if not paper_path.exists():
            raise FileNotFoundError(f"Paper not found: {paper_path}")
        
        # Load paper JSON
        with open(paper_path, 'r', encoding='utf-8') as f:
            paper = json.load(f)
        
        logger.info(f"Extracting from paper: {paper.get('title', 'Unknown')}")
        
        # Auto-detect extraction type if needed
        if extraction_type == "auto":
            extraction_type = self._detect_extraction_type(paper)
            logger.info(f"Auto-detected extraction type: {extraction_type}")
        
        # Extract NCT ID if not provided
        if not nct_id and extraction_type == "clinical_trial":
            nct_id = self._extract_nct_id(paper)
            if not nct_id:
                logger.warning("No NCT ID found in paper. Extraction may be incomplete.")
        
        # Route to appropriate extractor
        if extraction_type == "clinical_trial":
            return self._extract_clinical_trial(
                paper=paper,
                nct_id=nct_id,
                drug_name=drug_name,
                indication=indication,
                standard_endpoints=standard_endpoints
            )
        else:
            # TODO: Add case study extraction when ready
            raise NotImplementedError("Case study extraction not yet implemented in service")
    
    def extract_from_pdf(
        self,
        pdf_path: str | Path,
        drug_name: str,
        indication: str,
        nct_id: Optional[str] = None,
        standard_endpoints: Optional[List[str]] = None,
        extraction_type: Literal["clinical_trial", "case_study", "auto"] = "auto"
    ) -> Dict[str, Any]:
        """
        Extract data from a PDF file.
        
        Args:
            pdf_path: Path to PDF file
            drug_name: Drug name
            indication: Disease indication
            nct_id: Optional NCT ID
            standard_endpoints: Optional list of standard endpoints
            extraction_type: Type of extraction
        
        Returns:
            Dictionary containing extraction results
        """
        if not PYMUPDF_AVAILABLE:
            raise ImportError("pymupdf4llm is required for PDF extraction. Install with: pip install pymupdf4llm")
        
        pdf_path = Path(pdf_path)
        
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
        
        logger.info(f"Extracting text from PDF: {pdf_path.name}")
        
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
            'source': 'pdf',
            'pdf_path': str(pdf_path)
        }
        
        # Auto-detect extraction type
        if extraction_type == "auto":
            extraction_type = self._detect_extraction_type(paper)
            logger.info(f"Auto-detected extraction type: {extraction_type}")
        
        # Extract NCT ID if not provided
        if not nct_id and extraction_type == "clinical_trial":
            nct_id = self._extract_nct_id(paper)
        
        # Route to appropriate extractor
        if extraction_type == "clinical_trial":
            return self._extract_clinical_trial(
                paper=paper,
                nct_id=nct_id,
                drug_name=drug_name,
                indication=indication,
                standard_endpoints=standard_endpoints
            )
        else:
            raise NotImplementedError("Case study extraction not yet implemented in service")
    
    def _extract_clinical_trial(
        self,
        paper: Dict[str, Any],
        nct_id: str,
        drug_name: str,
        indication: str,
        standard_endpoints: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Extract clinical trial data using ClinicalDataExtractorAgent."""
        trial_design, extractions = self.clinical_extractor.extract_trial_data(
            paper=paper,
            nct_id=nct_id,
            drug_name=drug_name,
            indication=indication,
            standard_endpoints=standard_endpoints
        )
        
        return {
            'extraction_type': 'clinical_trial',
            'trial_design': trial_design,
            'extractions': extractions,
            'paper_metadata': {
                'title': paper.get('title'),
                'pmid': paper.get('pmid'),
                'doi': paper.get('doi'),
                'authors': paper.get('authors'),
                'journal': paper.get('journal'),
                'year': paper.get('year')
            }
        }
    
    def _detect_extraction_type(self, paper: Dict[str, Any]) -> str:
        """
        Auto-detect whether paper is a clinical trial or case study.
        
        Args:
            paper: Paper content dict
        
        Returns:
            "clinical_trial" or "case_study"
        """
        content = paper.get('content', '') + ' ' + paper.get('abstract', '')
        title = paper.get('title', '').lower()
        
        # Check for NCT ID (strong indicator of clinical trial)
        if self._extract_nct_id(paper):
            return "clinical_trial"
        
        # Check title for case study indicators
        case_study_keywords = [
            'case report', 'case series', 'case study',
            'pilot study', 'open-label', 'open label',
            'retrospective', 'real-world', 'expanded access'
        ]
        
        for keyword in case_study_keywords:
            if keyword in title:
                return "case_study"
        
        # Check content for clinical trial indicators
        trial_keywords = ['randomized', 'placebo', 'double-blind', 'phase 2', 'phase 3', 'phase ii', 'phase iii']
        trial_count = sum(1 for keyword in trial_keywords if keyword in content.lower()[:5000])
        
        if trial_count >= 2:
            return "clinical_trial"
        
        # Default to case study if uncertain
        return "case_study"
    
    def _extract_nct_id(self, paper: Dict[str, Any]) -> Optional[str]:
        """
        Extract NCT ID from paper content.
        
        Args:
            paper: Paper content dict
        
        Returns:
            NCT ID or None
        """
        import re
        
        content = paper.get('content', '') + ' ' + paper.get('abstract', '')
        
        # Search for NCT IDs in first 5000 characters
        nct_pattern = r'NCT\d{8}'
        matches = re.findall(nct_pattern, content[:5000])
        
        if matches:
            return matches[0]
        
        return None

