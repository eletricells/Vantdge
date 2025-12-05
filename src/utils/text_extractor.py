"""
Text extraction from PDFs with multiple fallback strategies.

Provides a robust text extraction pipeline with quality assessment.
"""

import logging
from dataclasses import dataclass
from typing import Optional
from pathlib import Path

from src.utils.extraction_config import TextExtractionConfig


logger = logging.getLogger(__name__)


@dataclass
class TextExtractionResult:
    """Result of text extraction."""
    content: str
    method: str
    quality_score: float
    page_count: int = 0
    error: Optional[str] = None


class TextExtractor:
    """
    Text extraction with multiple fallback strategies.
    
    Strategy order:
    1. pymupdf4llm (best for LLM consumption)
    2. pdfplumber (good balance of accuracy and formatting)
    3. PyPDF2 (basic fallback)
    4. OCR (for scanned documents, if enabled)
    """
    
    def __init__(self, config: Optional[TextExtractionConfig] = None):
        self.config = config or TextExtractionConfig()
        self.logger = logging.getLogger(__name__)
    
    def extract(self, pdf_path: str) -> TextExtractionResult:
        """Extract text using best available method."""
        
        strategies = [
            ('pymupdf4llm', self._extract_pymupdf4llm),
            ('pdfplumber', self._extract_pdfplumber),
            ('pypdf2', self._extract_pypdf2),
        ]
        
        if self.config.enable_ocr_fallback:
            strategies.append(('ocr', self._extract_ocr))
        
        for method_name, extractor in strategies:
            try:
                result = extractor(pdf_path)
                
                # Validate extraction quality
                if self._is_quality_acceptable(result):
                    self.logger.info(
                        f"Text extracted with {method_name}: "
                        f"{len(result.content)} chars, quality={result.quality_score:.2f}"
                    )
                    return result
                else:
                    self.logger.warning(
                        f"{method_name} extraction quality too low "
                        f"({result.quality_score:.2f}), trying next method"
                    )
                    
            except Exception as e:
                self.logger.warning(f"{method_name} extraction failed: {e}")
                continue
        
        # All methods failed
        return TextExtractionResult(
            content="",
            method="failed",
            quality_score=0.0,
            error="All extraction methods failed"
        )
    
    def _extract_pymupdf4llm(self, pdf_path: str) -> TextExtractionResult:
        """Extract using pymupdf4llm."""
        from pymupdf4llm.helpers.pymupdf_rag import to_markdown
        import pymupdf
        
        doc = pymupdf.open(pdf_path)
        try:
            content = to_markdown(
                doc,
                pages=None,
                page_chunks=False,
                table_strategy=self.config.table_strategy,
                force_text=True,
                show_progress=False
            )
            
            quality = self._assess_quality(content)
            
            return TextExtractionResult(
                content=content,
                method='pymupdf4llm',
                quality_score=quality,
                page_count=len(doc)
            )
        finally:
            doc.close()
    
    def _extract_pdfplumber(self, pdf_path: str) -> TextExtractionResult:
        """Extract using pdfplumber."""
        import pdfplumber
        
        content_parts = []
        page_count = 0
        
        with pdfplumber.open(pdf_path) as pdf:
            page_count = len(pdf.pages)
            for page in pdf.pages:
                text = page.extract_text() or ''
                content_parts.append(text)
        
        content = '\n\n'.join(content_parts)
        quality = self._assess_quality(content)
        
        return TextExtractionResult(
            content=content,
            method='pdfplumber',
            quality_score=quality,
            page_count=page_count
        )
    
    def _extract_pypdf2(self, pdf_path: str) -> TextExtractionResult:
        """Extract using PyPDF2 (basic fallback)."""
        import PyPDF2

        content_parts = []

        with open(pdf_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            page_count = len(reader.pages)

            for page in reader.pages:
                text = page.extract_text() or ''
                content_parts.append(text)

        content = '\n'.join(content_parts)
        quality = self._assess_quality(content)

        return TextExtractionResult(
            content=content,
            method='pypdf2',
            quality_score=quality,
            page_count=page_count
        )

    def _extract_ocr(self, pdf_path: str) -> TextExtractionResult:
        """Extract using OCR (for scanned documents)."""
        try:
            import pytesseract
            from pdf2image import convert_from_path

            images = convert_from_path(pdf_path)
            content_parts = []

            for image in images:
                text = pytesseract.image_to_string(image)
                content_parts.append(text)

            content = '\n\n'.join(content_parts)
            quality = self._assess_quality(content)

            return TextExtractionResult(
                content=content,
                method='ocr',
                quality_score=quality * 0.8,  # OCR typically lower quality
                page_count=len(images)
            )
        except ImportError:
            raise RuntimeError("OCR dependencies not installed (pytesseract, pdf2image)")

    def _assess_quality(self, content: str) -> float:
        """
        Assess text extraction quality.

        Metrics:
        - Word count
        - Average word length (detects garbled text)
        - Whitespace ratio
        - Common word presence
        - Scientific paper indicators
        """
        if not content:
            return 0.0

        # Word analysis
        words = content.split()
        word_count = len(words)

        if word_count < 100:
            return 0.2  # Too little text

        # Average word length (should be 4-8 for English)
        avg_word_len = sum(len(w) for w in words) / word_count
        word_len_score = 1.0 if 4 <= avg_word_len <= 8 else 0.5

        # Whitespace ratio (too high suggests extraction issues)
        whitespace_ratio = content.count(' ') / len(content)
        whitespace_score = 1.0 if 0.1 <= whitespace_ratio <= 0.3 else 0.7

        # Common words check
        common_words = {'the', 'and', 'of', 'to', 'in', 'a', 'is', 'that', 'for', 'with'}
        words_lower = set(w.lower() for w in words)
        common_found = len(common_words & words_lower)
        common_score = common_found / len(common_words)

        # Scientific paper indicators
        scientific_terms = {'study', 'patients', 'results', 'methods', 'clinical', 'trial'}
        scientific_found = len(scientific_terms & words_lower)
        scientific_score = min(scientific_found / 3, 1.0)

        # Combine scores
        quality = (
            word_len_score * 0.25 +
            whitespace_score * 0.25 +
            common_score * 0.25 +
            scientific_score * 0.25
        )

        return quality

    def _is_quality_acceptable(self, result: TextExtractionResult) -> bool:
        """Check if extraction quality is acceptable."""
        return (
            result.quality_score >= self.config.min_quality_score and
            len(result.content) >= self.config.min_content_length
        )

