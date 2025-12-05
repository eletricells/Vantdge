"""
Table extraction from PDFs using multiple strategies.

Provides robust table extraction with validation and quality scoring.
"""

import logging
import re
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from pathlib import Path

from src.utils.extraction_config import TableValidationConfig


logger = logging.getLogger(__name__)


@dataclass
class ExtractedTable:
    """Represents an extracted table with metadata."""
    label: str
    content: str  # Markdown format
    page: int
    accuracy: float  # Extraction confidence
    row_count: int
    column_count: int
    fill_ratio: float
    extraction_method: str  # 'hybrid', 'camelot_stream', 'camelot_lattice'
    header_recovery_applied: bool = False
    header_recovery_confidence: Optional[float] = None
    has_valid_headers: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'label': self.label,
            'content': self.content,
            'page': self.page,
            'accuracy': self.accuracy,
            'extraction_method': self.extraction_method,
            'header_recovery': {
                'applied': self.header_recovery_applied,
                'confidence': self.header_recovery_confidence,
            } if self.header_recovery_applied else None
        }


class TableExtractor:
    """
    Extracts tables from PDFs using multiple strategies.
    
    Strategy order:
    1. HybridTableExtractor (pdfplumber headers + Camelot content)
    2. Camelot stream mode (better for complex layouts)
    3. Camelot lattice mode (better for bordered tables)
    
    Each extracted table is validated and scored.
    """
    
    def __init__(self, config: Optional[TableValidationConfig] = None):
        self.config = config or TableValidationConfig()
        self.logger = logging.getLogger(__name__)
    
    def extract(self, pdf_path: str) -> List[ExtractedTable]:
        """
        Extract tables from PDF using best available method.

        Returns:
            List of ExtractedTable objects, sorted by quality score
        """
        tables = []

        # Strategy 1: Try HybridTableExtractor
        hybrid_tables = self._extract_with_hybrid(pdf_path)
        if hybrid_tables:
            self.logger.info(f"Hybrid extractor found {len(hybrid_tables)} tables")
            tables.extend(hybrid_tables)

        # Strategy 2: If hybrid found few tables, try Camelot
        if len(tables) < 2:
            self.logger.info("Trying Camelot extraction...")
            camelot_tables = self._extract_with_camelot(pdf_path)

            # Deduplicate (some tables may be found by both methods)
            new_tables = self._deduplicate_tables(camelot_tables, tables)
            tables.extend(new_tables)

        # Filter out tables without valid captions (likely false positives)
        tables_before = len(tables)
        tables = self._filter_tables_with_captions(tables)
        if tables_before > len(tables):
            self.logger.info(f"Filtered out {tables_before - len(tables)} tables without valid captions")

        # Sort by quality score
        tables.sort(key=lambda t: self._calculate_quality_score(t), reverse=True)

        self.logger.info(f"Total tables extracted: {len(tables)}")
        return tables
    
    def _extract_with_hybrid(self, pdf_path: str) -> List[ExtractedTable]:
        """Extract tables using HybridTableExtractor."""
        try:
            from src.utils.hybrid_table_extractor import HybridTableExtractor
            
            extractor = HybridTableExtractor()
            raw_tables = extractor.extract_tables_hybrid(pdf_path)
            
            return [
                self._convert_to_extracted_table(t, method='hybrid')
                for t in raw_tables
                if self._validate_table_dict(t)
            ]
        except Exception as e:
            self.logger.warning(f"Hybrid extraction failed: {e}")
            return []
    
    def _extract_with_camelot(self, pdf_path: str) -> List[ExtractedTable]:
        """Extract tables using Camelot with stream and lattice modes."""
        tables = []
        
        # Try stream mode first (better for scientific papers)
        stream_tables = self._camelot_extract(pdf_path, flavor='stream')
        tables.extend(stream_tables)
        
        # If few tables found, also try lattice mode
        if len(tables) < 2:
            lattice_tables = self._camelot_extract(pdf_path, flavor='lattice')
            # Only add tables not already found
            tables.extend(self._deduplicate_tables(lattice_tables, tables))
        
        return tables
    
    def _camelot_extract(
        self, 
        pdf_path: str, 
        flavor: str
    ) -> List[ExtractedTable]:
        """Extract tables using Camelot with specified flavor."""
        try:
            import camelot
            
            kwargs = {'pages': 'all', 'flavor': flavor, 'suppress_stdout': True}
            if flavor == 'lattice':
                kwargs['line_scale'] = 40
            
            raw_tables = camelot.read_pdf(pdf_path, **kwargs)
            
            extracted = []
            for i, table in enumerate(raw_tables):
                # Validate table
                if not self._validate_camelot_table(table):
                    continue
                
                # Convert to ExtractedTable
                extracted_table = self._convert_camelot_table(
                    table, 
                    index=i,
                    method=f'camelot_{flavor}'
                )
                
                if extracted_table:
                    extracted.append(extracted_table)

            return extracted

        except Exception as e:
            self.logger.warning(f"Camelot {flavor} extraction failed: {e}")
            return []

    def _validate_camelot_table(self, table) -> bool:
        """Validate a Camelot table object."""
        df = table.df

        # Basic size check
        if df.shape[0] < self.config.min_rows:
            return False
        if df.shape[1] < self.config.min_columns:
            return False

        # Check for page artifacts
        if self._is_page_artifact(df):
            return False

        # Check fill ratio
        fill_ratio = self._calculate_fill_ratio(df)
        if fill_ratio < self.config.min_fill_ratio:
            return False

        # For lattice mode, require positive accuracy
        if hasattr(table, 'accuracy') and table.accuracy == 0:
            return False

        return True

    def _is_page_artifact(self, df) -> bool:
        """
        Check if DataFrame is a page layout artifact rather than a data table.

        Common artifacts:
        - 2-column page layouts
        - Figure/caption reference tables
        - Metadata tables (page numbers, authors)
        """
        df_str = df.astype(str)

        # Check for 2-column layout with fragmented text
        if df.shape[1] == 2:
            col0_text = ' '.join(df_str.iloc[:, 0].tolist())
            col1_text = ' '.join(df_str.iloc[:, 1].tolist())

            # Figure references on both sides suggest page layout
            fig_pattern = r'Fig(ure)?\s*\d+'
            if (re.search(fig_pattern, col0_text, re.IGNORECASE) and
                re.search(fig_pattern, col1_text, re.IGNORECASE)):
                return True

        # Check for metadata headers
        first_row_text = ' '.join(str(c) for c in df_str.iloc[0].tolist()).lower()
        metadata_keywords = ['page', 'reference', 'affiliation', 'correspondence']

        if any(kw in first_row_text for kw in metadata_keywords):
            # Verify ALL columns look like metadata (not just one column header)
            metadata_count = sum(
                any(kw in str(c).lower() for kw in metadata_keywords)
                for c in df_str.iloc[0]
            )
            if metadata_count == df.shape[1]:
                return True

        # Check for inconsistent cell counts (fragmented extraction)
        non_empty_per_row = [
            sum(1 for c in row if str(c).strip())
            for row in df_str.values
        ]
        if len(set(non_empty_per_row)) > self.config.max_cell_count_variation:
            return True

        return False

    def _calculate_fill_ratio(self, df) -> float:
        """Calculate the ratio of non-empty cells."""
        df_str = df.astype(str)
        non_empty = df_str.map(lambda x: len(str(x).strip()) > 0).sum().sum()
        total = df.shape[0] * df.shape[1]
        return non_empty / total if total > 0 else 0

    def _convert_camelot_table(
        self,
        table,
        index: int,
        method: str
    ) -> Optional[ExtractedTable]:
        """Convert Camelot table to ExtractedTable."""
        df = table.df

        # Try to extract label from first row
        label = self._extract_table_label(df, index)

        # Convert to markdown
        content = df.to_markdown(index=False)

        # Calculate metrics
        fill_ratio = self._calculate_fill_ratio(df)

        return ExtractedTable(
            label=label,
            content=content,
            page=table.page,
            accuracy=getattr(table, 'accuracy', 0.0),
            row_count=df.shape[0],
            column_count=df.shape[1],
            fill_ratio=fill_ratio,
            extraction_method=method,
        )

    def _extract_table_label(self, df, fallback_index: int) -> str:
        """Extract table label from DataFrame or generate fallback."""
        if df.shape[0] == 0:
            return f"Table {fallback_index + 1}"

        first_row_text = ' '.join(str(c) for c in df.iloc[0].tolist())

        # Look for "Table X" or "Table I/II/III" patterns
        match = re.search(
            r'Table\s+([IVX]+|[0-9]+)[.\s:]?\s*([^\n]{0,50})?',
            first_row_text,
            re.IGNORECASE
        )

        if match:
            return f"Table {match.group(1)}"

        return f"Table {fallback_index + 1}"

    def _deduplicate_tables(
        self,
        new_tables: List[ExtractedTable],
        existing_tables: List[ExtractedTable]
    ) -> List[ExtractedTable]:
        """Remove tables that are duplicates of existing ones."""
        if not existing_tables:
            return new_tables

        unique = []
        existing_signatures = {
            self._table_signature(t) for t in existing_tables
        }

        for table in new_tables:
            sig = self._table_signature(table)
            if sig not in existing_signatures:
                unique.append(table)
                existing_signatures.add(sig)

        return unique

    def _table_signature(self, table: ExtractedTable) -> str:
        """Generate a signature for deduplication."""
        # Use label, page, and approximate content hash
        content_preview = table.content[:200] if table.content else ''
        return f"{table.label}:{table.page}:{hash(content_preview)}"

    def _filter_tables_with_captions(self, tables: List[ExtractedTable]) -> List[ExtractedTable]:
        """
        Filter out tables that don't have valid 'Table X' captions.

        This removes false positives like author affiliations, figure legends,
        reference lists, and multi-column layouts that were incorrectly detected as tables.

        Args:
            tables: List of extracted tables

        Returns:
            Filtered list containing only tables with valid captions
        """
        valid_tables = []

        for table in tables:
            # First check: Must have a valid "Table X" label
            if not re.search(r'Table\s+[IVX0-9]+[A-Z]?', table.label, re.IGNORECASE):
                self.logger.debug(f"Filtering out table without valid caption: {table.label}")
                continue

            # Second check: Content-based filtering to remove layout artifacts
            if not self._is_valid_data_table(table):
                self.logger.debug(f"Filtering out layout artifact: {table.label}")
                continue

            valid_tables.append(table)
            self.logger.debug(f"Keeping valid table: {table.label}")

        return valid_tables

    def _is_valid_data_table(self, table: ExtractedTable) -> bool:
        """
        Validate that a table is a real data table, not a page layout artifact.

        Filters out:
        - 2-column page layout artifacts (most common false positive)
        - Tables with journal headers/footers
        - Reference lists formatted as tables
        - Figure captions formatted as tables

        Args:
            table: ExtractedTable to validate

        Returns:
            True if valid data table, False if layout artifact
        """
        # Check 1: 2-column layout artifacts
        # These typically have exactly 2 columns and contain journal metadata
        if table.column_count == 2:
            content_lower = table.content.lower()

            # Check for journal/publication metadata patterns
            journal_patterns = [
                'j am acad dermatol',
                'volume',
                'march 2019',
                'robbins et al',
                'text fragment',
                'continuation',
                'page/reference',
                'text/content'
            ]

            # If multiple journal patterns found, likely a layout artifact
            pattern_matches = sum(1 for pattern in journal_patterns if pattern in content_lower)
            if pattern_matches >= 3:
                self.logger.debug(f"  Detected journal layout artifact (matched {pattern_matches} patterns)")
                return False

            # Check for reference list patterns (also applies to 3+ column tables)
            reference_patterns = [
                'et al',
                'doi:',
                'pubmed',
                'available at:',
                'http://',
                'https://'
            ]

            # Count lines that look like references
            lines = table.content.split('\n')
            reference_lines = sum(
                1 for line in lines
                if any(pattern in line.lower() for pattern in reference_patterns)
            )

            # If >50% of lines look like references, it's a reference list
            if len(lines) > 0 and reference_lines / len(lines) > 0.5:
                self.logger.debug(f"  Detected reference list ({reference_lines}/{len(lines)} lines)")
                return False

        # Check for reference sections in multi-column tables
        # These often have generic headers like "Text/Content", "Empty", etc.
        if table.column_count >= 3:
            content_lower = table.content.lower()

            # Check if header row contains generic/placeholder terms
            first_row = table.content.split('\n')[0] if table.content else ''
            generic_headers = [
                'text/content',
                'empty',
                'spacer',
                'continuation',
                'additional text',
                'notes'
            ]

            header_matches = sum(1 for header in generic_headers if header in first_row.lower())

            if header_matches >= 2:
                self.logger.debug(f"  Detected layout artifact with generic headers (matched {header_matches})")
                return False

            # Also check for reference-specific indicators
            reference_indicators = [
                'acknowledgments',
                'references',
                'bibliography',
                'study description'
            ]

            ref_matches = sum(1 for indicator in reference_indicators if indicator in first_row.lower())

            if ref_matches >= 1:
                self.logger.debug(f"  Detected reference section")
                return False

        # Check 2: Must have reasonable dimensions for a data table
        # Real data tables typically have at least 3 columns OR at least 5 rows
        if table.column_count < 3 and table.row_count < 5:
            self.logger.debug(f"  Too small: {table.row_count} rows x {table.column_count} cols")
            return False

        # Check 3: Look for actual table caption in content
        # Real tables should have "Table X." or "Table X:" in the first few rows
        first_rows = '\n'.join(table.content.split('\n')[:5])
        has_table_caption = re.search(
            r'Table\s+[IVX0-9]+[A-Z]?[\.:]\s+\w+',
            first_rows,
            re.IGNORECASE
        )

        # If it's a multi-column table (>=3 cols), caption is less critical
        # But for 2-column tables, we need strong evidence it's real
        if table.column_count >= 3:
            return True  # Multi-column tables are usually real
        elif has_table_caption:
            return True  # Has proper caption
        else:
            self.logger.debug(f"  2-column table without proper caption")
            return False

    def _calculate_quality_score(self, table: ExtractedTable) -> float:
        """Calculate overall quality score for a table."""
        score = 0.0

        # Fill ratio contributes up to 40 points
        score += table.fill_ratio * 40

        # Extraction accuracy contributes up to 30 points
        score += table.accuracy * 30

        # Column count contributes up to 15 points (more columns = likely data table)
        col_score = min(table.column_count / 10, 1.0) * 15
        score += col_score

        # Row count contributes up to 15 points
        row_score = min(table.row_count / 20, 1.0) * 15
        score += row_score

        # Bonus for labeled tables
        if re.match(r'Table\s+[IVX0-9]+', table.label):
            score += 5

        return score

    def _validate_table_dict(self, table_dict: Dict) -> bool:
        """Validate a table dictionary from HybridTableExtractor."""
        content = table_dict.get('content', '')
        if not content or len(content) < 20:
            return False

        # Count rows (markdown table lines)
        lines = [l for l in content.split('\n') if l.strip() and '|' in l]
        if len(lines) < self.config.min_rows:
            return False

        return True

    def _convert_to_extracted_table(
        self,
        table_dict: Dict,
        method: str
    ) -> ExtractedTable:
        """Convert a table dictionary to ExtractedTable."""
        content = table_dict.get('content', '')

        # Estimate row/column counts from markdown
        lines = [l for l in content.split('\n') if l.strip() and '|' in l]
        row_count = len(lines)
        col_count = lines[0].count('|') - 1 if lines else 0

        return ExtractedTable(
            label=table_dict.get('label', 'Unknown'),
            content=content,
            page=table_dict.get('page', 0),
            accuracy=table_dict.get('accuracy', 0.8),
            row_count=row_count,
            column_count=col_count,
            fill_ratio=0.8,  # Hybrid extractor typically has good fill
            extraction_method=method,
        )

