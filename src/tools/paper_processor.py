"""
PDF processing pipeline with Camelot for table extraction.

Extracts structured content from scientific papers including:
- Full text (using PyMuPDF/fitz - better for scientific papers)
- Tables (using Camelot)
- Metadata
- Optional: Figures (future enhancement)
"""
from pathlib import Path
from typing import List, Dict, Any, Optional
import json
import logging
from dataclasses import dataclass

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# PyMuPDF for text extraction (better than PyPDF2 for scientific papers)
try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    logger.warning("PyMuPDF not available. Install with: pip install PyMuPDF")
    PYMUPDF_AVAILABLE = False

# Optional imports - Camelot requires additional dependencies
try:
    import camelot
    CAMELOT_AVAILABLE = True
except ImportError:
    logger.warning("Camelot not available. Install with: pip install camelot-py[cv]")
    CAMELOT_AVAILABLE = False

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    logger.warning("Pandas not available. Install with: pip install pandas")
    PANDAS_AVAILABLE = False


class ExtractedTable(BaseModel):
    """Extracted table data from PDF."""
    page_number: int = Field(..., description="Page number where table appears")
    table_number: int = Field(..., description="Table index on the page (0-indexed)")
    caption: Optional[str] = Field(None, description="Table caption if detected")
    data: List[List[str]] = Field(..., description="Raw table as list of lists")
    dataframe_json: Optional[str] = Field(None, description="Pandas DataFrame as JSON")
    accuracy: float = Field(..., description="Camelot extraction accuracy (0-100)")
    extraction_method: str = Field(..., description="Extraction method used (lattice/stream)")

    class Config:
        json_schema_extra = {
            "example": {
                "page_number": 5,
                "table_number": 0,
                "caption": "Table 2: In vitro binding affinity",
                "data": [["Antibody", "KD (nM)"], ["K1-70", "2.3"]],
                "accuracy": 95.5,
                "extraction_method": "lattice"
            }
        }


class ExtractedMetadata(BaseModel):
    """Extracted PDF metadata."""
    title: Optional[str] = None
    authors: Optional[str] = None
    subject: Optional[str] = None
    keywords: Optional[str] = None
    creator: Optional[str] = None
    producer: Optional[str] = None
    creation_date: Optional[str] = None
    page_count: int = 0


class ProcessedPaper(BaseModel):
    """Complete processed paper data."""
    paper_id: str = Field(..., description="Unique paper identifier")
    full_text: str = Field(..., description="Extracted full text")
    tables: List[ExtractedTable] = Field(default_factory=list, description="Extracted tables")
    metadata: ExtractedMetadata = Field(..., description="PDF metadata")
    extracted_path: Optional[str] = Field(None, description="Path to extracted data directory")
    processing_status: str = Field("processed", description="Processing status")
    error_message: Optional[str] = Field(None, description="Error message if processing failed")


class PaperProcessor:
    """
    Process PDFs and extract structured content.

    Uses Camelot for table extraction (more accurate than pdfplumber)
    and PyPDF2 for text extraction.
    """

    def __init__(
        self,
        use_camelot: bool = True,
        camelot_flavor: str = "lattice",
        fallback_to_stream: bool = True,
        min_accuracy: float = 50.0
    ):
        """
        Initialize paper processor.

        Args:
            use_camelot: Use Camelot for table extraction
            camelot_flavor: "lattice" (bordered tables) or "stream" (borderless)
            fallback_to_stream: Try stream mode if lattice fails
            min_accuracy: Minimum Camelot accuracy threshold (0-100)
        """
        self.use_camelot = use_camelot and CAMELOT_AVAILABLE
        self.camelot_flavor = camelot_flavor
        self.fallback_to_stream = fallback_to_stream
        self.min_accuracy = min_accuracy

        if use_camelot and not CAMELOT_AVAILABLE:
            logger.warning("Camelot requested but not available. Table extraction will be limited.")

        logger.info(f"Initialized PaperProcessor (Camelot: {self.use_camelot})")

    def process_pdf(self, pdf_path: str | Path, paper_id: str) -> ProcessedPaper:
        """
        Process PDF and extract all content.

        Args:
            pdf_path: Path to PDF file
            paper_id: Unique identifier for this paper

        Returns:
            ProcessedPaper with all extracted data

        Raises:
            FileNotFoundError: If PDF file not found
            Exception: If processing fails
        """
        pdf_path = Path(pdf_path)

        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        logger.info(f"Processing PDF: {pdf_path} (ID: {paper_id})")

        try:
            # Extract metadata
            metadata = self._extract_metadata(pdf_path)

            # Extract full text
            full_text = self._extract_text(pdf_path)

            # Extract tables
            tables = []
            if self.use_camelot:
                tables = self._extract_tables_camelot(pdf_path)
            else:
                logger.info("Camelot not available - skipping table extraction")

            return ProcessedPaper(
                paper_id=paper_id,
                full_text=full_text,
                tables=tables,
                metadata=metadata,
                processing_status="processed"
            )

        except Exception as e:
            logger.error(f"Failed to process PDF {pdf_path}: {e}")
            return ProcessedPaper(
                paper_id=paper_id,
                full_text="",
                metadata=ExtractedMetadata(),
                processing_status="failed",
                error_message=str(e)
            )

    def _extract_text(self, pdf_path: Path) -> str:
        """
        Extract full text from PDF using PyMuPDF (fitz).

        PyMuPDF provides better text extraction for scientific papers than PyPDF2,
        preserving formatting and handling complex layouts more accurately.

        Args:
            pdf_path: Path to PDF file

        Returns:
            Extracted text
        """
        if not PYMUPDF_AVAILABLE:
            logger.error("PyMuPDF not available - cannot extract text")
            return ""

        try:
            text_parts = []

            # Open PDF with PyMuPDF
            doc = fitz.open(str(pdf_path))

            for page_num in range(len(doc)):
                try:
                    page = doc[page_num]

                    # Extract text with layout preservation
                    text = page.get_text("text")  # "text" preserves layout better than "blocks"

                    if text.strip():  # Only add non-empty pages
                        text_parts.append(f"--- Page {page_num + 1} ---\n{text}")

                except Exception as e:
                    logger.warning(f"Failed to extract text from page {page_num}: {e}")
                    continue

            doc.close()

            full_text = "\n\n".join(text_parts)
            logger.info(f"Extracted {len(full_text)} characters of text from {len(text_parts)} pages")
            return full_text

        except Exception as e:
            logger.error(f"Text extraction failed: {e}")
            return ""

    def _extract_metadata(self, pdf_path: Path) -> ExtractedMetadata:
        """
        Extract PDF metadata using PyMuPDF.

        Args:
            pdf_path: Path to PDF file

        Returns:
            ExtractedMetadata
        """
        if not PYMUPDF_AVAILABLE:
            logger.warning("PyMuPDF not available - returning empty metadata")
            return ExtractedMetadata()

        try:
            doc = fitz.open(str(pdf_path))
            metadata = doc.metadata

            # PyMuPDF uses different key names than PyPDF2
            extracted = ExtractedMetadata(
                title=metadata.get("title"),
                authors=metadata.get("author"),
                subject=metadata.get("subject"),
                keywords=metadata.get("keywords"),
                creator=metadata.get("creator"),
                producer=metadata.get("producer"),
                creation_date=metadata.get("creationDate"),
                page_count=len(doc)
            )

            doc.close()
            return extracted

        except Exception as e:
            logger.error(f"Metadata extraction failed: {e}")
            return ExtractedMetadata()

    def _extract_tables_camelot(self, pdf_path: Path) -> List[ExtractedTable]:
        """
        Extract tables using Camelot.

        Args:
            pdf_path: Path to PDF file

        Returns:
            List of extracted tables
        """
        if not CAMELOT_AVAILABLE:
            return []

        tables = []

        # Try lattice method first (for tables with borders)
        if self.camelot_flavor == "lattice" or self.fallback_to_stream:
            try:
                logger.info("Attempting table extraction with Camelot (lattice mode)")
                lattice_tables = camelot.read_pdf(
                    str(pdf_path),
                    pages='all',
                    flavor='lattice',
                    line_scale=40,
                    suppress_stdout=True
                )

                for i, table in enumerate(lattice_tables):
                    if table.accuracy >= self.min_accuracy:
                        extracted = self._format_camelot_table(table, i, 'lattice')
                        tables.append(extracted)
                        logger.info(f"Extracted table {i} (page {table.page}) - accuracy: {table.accuracy:.1f}%")

            except Exception as e:
                logger.warning(f"Lattice extraction failed: {e}")

        # Try stream method if fallback enabled or primary method
        if (self.fallback_to_stream and len(tables) == 0) or self.camelot_flavor == "stream":
            try:
                logger.info("Attempting table extraction with Camelot (stream mode)")
                stream_tables = camelot.read_pdf(
                    str(pdf_path),
                    pages='all',
                    flavor='stream',
                    edge_tol=50,
                    suppress_stdout=True
                )

                for i, table in enumerate(stream_tables):
                    if table.accuracy >= self.min_accuracy:
                        # Check if already extracted with lattice
                        if not self._is_duplicate_table(table, tables):
                            extracted = self._format_camelot_table(table, i, 'stream')
                            tables.append(extracted)
                            logger.info(f"Extracted table {i} (page {table.page}) - accuracy: {table.accuracy:.1f}%")

            except Exception as e:
                logger.warning(f"Stream extraction failed: {e}")

        logger.info(f"Extracted {len(tables)} tables total")
        return tables

    def _format_camelot_table(self, camelot_table, index: int, method: str) -> ExtractedTable:
        """
        Format Camelot table object into ExtractedTable.

        Args:
            camelot_table: Camelot table object
            index: Table index
            method: Extraction method used

        Returns:
            ExtractedTable
        """
        df = camelot_table.df

        # Convert DataFrame to list of lists
        data = df.values.tolist()

        # Convert DataFrame to JSON if pandas available
        dataframe_json = None
        if PANDAS_AVAILABLE:
            dataframe_json = df.to_json(orient='records')

        # Try to extract caption (placeholder - would need additional logic)
        caption = self._try_extract_caption(camelot_table)

        return ExtractedTable(
            page_number=camelot_table.page,
            table_number=index,
            caption=caption,
            data=data,
            dataframe_json=dataframe_json,
            accuracy=camelot_table.accuracy,
            extraction_method=method
        )

    def _try_extract_caption(self, camelot_table) -> Optional[str]:
        """
        Attempt to extract table caption.

        This is a placeholder - would require additional text extraction
        from the area surrounding the table.

        Args:
            camelot_table: Camelot table object

        Returns:
            Caption if found, else None
        """
        # TODO: Implement caption extraction by searching text above/below table
        return None

    def _is_duplicate_table(self, table, existing_tables: List[ExtractedTable]) -> bool:
        """
        Check if table was already extracted.

        Simple heuristic: same page and similar dimensions.

        Args:
            table: Camelot table object
            existing_tables: Already extracted tables

        Returns:
            True if likely duplicate
        """
        for existing in existing_tables:
            if existing.page_number == table.page:
                # Compare dimensions
                if len(table.df) == len(existing.data):
                    return True

        return False

    def save_extracted_data(
        self,
        processed: ProcessedPaper,
        output_dir: str | Path
    ) -> Dict[str, str]:
        """
        Save extracted data to disk.

        Args:
            processed: Processed paper data
            output_dir: Directory to save extracted data

        Returns:
            Dictionary of saved file paths
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        saved_paths = {}

        # Save full text
        text_path = output_dir / "full_text.txt"
        text_path.write_text(processed.full_text, encoding='utf-8')
        saved_paths['full_text'] = str(text_path)

        # Save tables
        if processed.tables:
            tables_path = output_dir / "tables.json"
            tables_data = [t.model_dump() for t in processed.tables]
            tables_path.write_text(json.dumps(tables_data, indent=2), encoding='utf-8')
            saved_paths['tables'] = str(tables_path)

            # Save individual table CSVs for easy inspection
            tables_dir = output_dir / "tables"
            tables_dir.mkdir(exist_ok=True)

            for i, table in enumerate(processed.tables):
                if PANDAS_AVAILABLE and table.dataframe_json:
                    df = pd.read_json(table.dataframe_json)
                    csv_path = tables_dir / f"table_{table.page_number}_{i}.csv"
                    df.to_csv(csv_path, index=False)
                    saved_paths[f'table_{i}_csv'] = str(csv_path)

        # Save metadata
        metadata_path = output_dir / "metadata.json"
        metadata_path.write_text(
            json.dumps(processed.metadata.model_dump(), indent=2),
            encoding='utf-8'
        )
        saved_paths['metadata'] = str(metadata_path)

        logger.info(f"Saved extracted data to {output_dir}")
        return saved_paths
