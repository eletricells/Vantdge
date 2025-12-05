"""
Adapter to convert PaperScope v2 papers to Clinical Extractor format.

PaperScope v2 papers from the database have metadata (title, authors, abstract, etc.)
but may not have full-text content. This adapter:
1. Accepts PaperScope v2 papers (from database or JSON)
2. Downloads full text if needed (using PMID via PubMed)
3. Converts to the format expected by ClinicalDataExtractorAgent
"""
import logging
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class PaperScopeV2Adapter:
    """
    Adapter to convert PaperScope v2 papers to Clinical Extractor format.
    """
    
    def __init__(self, pubmed_api=None):
        """
        Initialize adapter.
        
        Args:
            pubmed_api: Optional PubMedAPI instance for downloading full text
        """
        self.pubmed_api = pubmed_api
    
    def convert_paper(
        self,
        paperscope_paper: Dict[str, Any],
        download_full_text: bool = True
    ) -> Dict[str, Any]:
        """
        Convert PaperScope v2 paper to Clinical Extractor format.
        
        Args:
            paperscope_paper: Paper from PaperScope v2 (database or JSON)
            download_full_text: Whether to download full text if missing
            
        Returns:
            Paper dict compatible with ClinicalDataExtractorAgent
            
        Raises:
            ValueError: If paper cannot be converted
        """
        # Check if paper already has full content (from PaperScope v1 or uploaded PDFs)
        if paperscope_paper.get('content'):
            logger.info("Paper already has full content, using as-is")
            return self._normalize_paper(paperscope_paper)
        
        # Check if we have PMID for downloading
        pmid = paperscope_paper.get('pmid')
        if not pmid:
            logger.warning("Paper has no PMID and no content - using abstract only")
            return self._create_paper_from_abstract(paperscope_paper)
        
        # Try to download full text
        if download_full_text and self.pubmed_api:
            logger.info(f"Downloading full text for PMID: {pmid}")
            full_paper = self._download_full_text(pmid, paperscope_paper)
            if full_paper:
                return full_paper
        
        # Fallback to abstract-only paper
        logger.warning(f"Could not download full text for PMID {pmid}, using abstract only")
        return self._create_paper_from_abstract(paperscope_paper)
    
    def _download_full_text(
        self,
        pmid: str,
        paperscope_paper: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Download full text from PubMed Central.
        
        Args:
            pmid: PubMed ID
            paperscope_paper: Original PaperScope v2 paper
            
        Returns:
            Paper dict with full content, or None if download failed
        """
        try:
            # Try to get full text from PMC
            full_paper = self.pubmed_api.download_full_text(pmid)
            
            if full_paper and full_paper.get('content'):
                logger.info(f"Successfully downloaded full text for PMID {pmid}")
                # Merge with PaperScope v2 metadata
                return self._merge_papers(paperscope_paper, full_paper)
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to download full text for PMID {pmid}: {e}")
            return None
    
    def _merge_papers(
        self,
        paperscope_paper: Dict[str, Any],
        full_paper: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Merge PaperScope v2 metadata with downloaded full text.
        
        Args:
            paperscope_paper: Paper from PaperScope v2
            full_paper: Downloaded paper with full content
            
        Returns:
            Merged paper dict
        """
        # Start with full paper (has content and tables)
        merged = full_paper.copy()
        
        # Override with PaperScope v2 metadata (more reliable)
        merged.update({
            'title': paperscope_paper.get('title') or full_paper.get('title'),
            'authors': paperscope_paper.get('authors') or full_paper.get('authors'),
            'journal': paperscope_paper.get('journal') or full_paper.get('journal'),
            'year': paperscope_paper.get('year') or full_paper.get('year'),
            'pmid': paperscope_paper.get('pmid') or full_paper.get('pmid'),
            'doi': paperscope_paper.get('doi') or full_paper.get('doi'),
            'pmc': paperscope_paper.get('pmc') or full_paper.get('pmc'),
        })
        
        # Add PaperScope v2 specific fields
        if paperscope_paper.get('trial_name'):
            merged['trial_name'] = paperscope_paper['trial_name']
        if paperscope_paper.get('detailed_summary'):
            merged['detailed_summary'] = paperscope_paper['detailed_summary']
        if paperscope_paper.get('categories'):
            merged['categories'] = paperscope_paper['categories']
        
        # Update metadata
        if 'metadata' not in merged:
            merged['metadata'] = {}
        merged['metadata']['source'] = 'PaperScope V2 + PubMed Central'
        
        return merged
    
    def _create_paper_from_abstract(
        self,
        paperscope_paper: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create paper dict using only abstract (fallback when full text unavailable).
        
        Args:
            paperscope_paper: Paper from PaperScope v2
            
        Returns:
            Paper dict with abstract as content
        """
        abstract = paperscope_paper.get('abstract', '')
        detailed_summary = paperscope_paper.get('detailed_summary', '')
        
        # Use abstract + detailed summary as content
        content = f"{abstract}\n\n{detailed_summary}".strip()
        
        if not content:
            raise ValueError("Paper has no content, abstract, or detailed summary")
        
        return self._normalize_paper({
            **paperscope_paper,
            'content': content,
            'metadata': {
                'source': 'PaperScope V2 (Abstract Only)',
                'warning': 'Full text not available - using abstract only'
            }
        })

    def _normalize_paper(self, paper: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize paper to Clinical Extractor format.

        Ensures all required fields are present and in the correct format.

        Args:
            paper: Paper dict

        Returns:
            Normalized paper dict
        """
        # Ensure authors is a list
        authors = paper.get('authors', [])
        if isinstance(authors, str):
            # Split by semicolon or comma
            authors = [a.strip() for a in authors.replace(';', ',').split(',')]

        # Ensure tables is a list
        tables = paper.get('tables', [])
        if not isinstance(tables, list):
            tables = []

        # Ensure metadata is a dict
        metadata = paper.get('metadata', {})
        if not isinstance(metadata, dict):
            metadata = {}

        return {
            'pmid': paper.get('pmid'),
            'pmc': paper.get('pmc'),
            'title': paper.get('title', 'Unknown'),
            'authors': authors,
            'journal': paper.get('journal', 'Unknown'),
            'year': paper.get('year'),
            'doi': paper.get('doi'),
            'content': paper.get('content', ''),
            'tables': tables,
            'sections': paper.get('sections', {}),
            'metadata': metadata,
            # PaperScope v2 specific fields (optional)
            'trial_name': paper.get('trial_name'),
            'detailed_summary': paper.get('detailed_summary'),
            'categories': paper.get('categories'),
            'structured_summary': paper.get('structured_summary'),
        }

