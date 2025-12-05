"""
Hybrid table extraction: PyMuPDF for headers + Camelot for content.

This module combines the strengths of both libraries:
- PyMuPDF (fitz): Better at extracting table headers from text blocks
- Camelot: Better at extracting table data content

Strategy:
1. Use PyMuPDF to extract table headers from text blocks near tables
2. Use Camelot to extract table data content
3. Merge headers with Camelot data to create complete tables
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
import pandas as pd
import re

logger = logging.getLogger(__name__)


class HybridTableExtractor:
    """Extract tables using hybrid approach: PyMuPDF headers + Camelot content."""

    def __init__(self):
        """Initialize the hybrid extractor."""
        self.logger = logger
    
    def extract_tables_hybrid(self, pdf_path: str) -> List[Dict[str, Any]]:
        """
        Extract tables using hybrid approach.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            List of extracted tables with headers and content
        """
        try:
            import fitz  # PyMuPDF
            import camelot
        except ImportError as e:
            self.logger.error(f"Required library not found: {e}")
            return []

        tables = []

        try:
            # Step 1: Extract tables with Camelot (for content)
            self.logger.info("Step 1: Extracting table content with Camelot...")
            camelot_tables = self._extract_with_camelot(pdf_path)
            self.logger.info(f"  Found {len(camelot_tables)} tables with Camelot")

            # Step 2: Extract headers with PyMuPDF (for structure)
            self.logger.info("Step 2: Extracting table headers with PyMuPDF...")
            pymupdf_headers = self._extract_headers_with_pymupdf(pdf_path)
            self.logger.info(f"  Found {len(pymupdf_headers)} header blocks with PyMuPDF")

            # Step 2.5: Merge split Camelot tables from the same page using table labels
            self.logger.info("Step 2.5: Merging split tables using table labels...")
            camelot_tables = self._merge_tables_by_label(pdf_path, camelot_tables, pymupdf_headers)
            self.logger.info(f"  After merging: {len(camelot_tables)} tables")

            # Step 3: Merge headers with content
            self.logger.info("Step 3: Merging headers with content...")
            tables = self._merge_headers_and_content(camelot_tables, pymupdf_headers)
            self.logger.info(f"  Merged into {len(tables)} complete tables")

            return tables

        except Exception as e:
            self.logger.error(f"Hybrid extraction failed: {e}")
            return []
    
    def _extract_with_camelot(self, pdf_path: str) -> List[Dict[str, Any]]:
        """
        Extract tables with Camelot (for content).

        Strategy for scientific papers:
        1. Try lattice mode first (best for tables with clear borders/grid lines)
        2. Fix single-cell tables (when internal column separators are missing)
        3. Fall back to stream mode for borderless tables
        """
        import camelot

        tables = []

        try:
            # Try lattice mode first (best for scientific papers with bordered tables)
            self.logger.info("  Extracting with Camelot lattice mode (bordered tables)...")
            lattice_tables = camelot.read_pdf(
                pdf_path,
                pages='all',
                flavor='lattice',
                line_scale=40,
                suppress_stdout=True
            )

            for table in lattice_tables:
                df = table.df
                original_shape = df.shape

                # Check for single-cell tables that need fixing
                if df.shape[1] == 1 and df.shape[0] >= 2:
                    # Try to fix single-cell table
                    fixed_df = self._fix_single_cell_table(df)
                    if fixed_df is not None:
                        df = fixed_df
                        self.logger.info(f"  ✓ Fixed single-cell table on page {table.page}: {original_shape} → {df.shape}")

                if df.shape[0] < 3 or df.shape[1] < 2:
                    continue

                non_empty_cells = (df.astype(str).map(lambda x: len(str(x).strip()) > 0).sum().sum())
                total_cells = df.shape[0] * df.shape[1]
                fill_ratio = non_empty_cells / total_cells if total_cells > 0 else 0

                if fill_ratio >= 0.3 and table.accuracy > 0:
                    # Get bounding box if available
                    bbox = getattr(table, '_bbox', None)
                    if bbox is None and hasattr(table, 'cells'):
                        try:
                            all_x0 = [cell.x1 for row in table.cells for cell in row]
                            all_y0 = [cell.y1 for row in table.cells for cell in row]
                            all_x1 = [cell.x2 for row in table.cells for cell in row]
                            all_y1 = [cell.y2 for row in table.cells for cell in row]
                            bbox = (min(all_x0), min(all_y0), max(all_x1), max(all_y1))
                        except:
                            bbox = (0, 0, 0, 0)

                    tables.append({
                        'df': df,
                        'page': table.page,
                        'accuracy': table.accuracy,
                        'flavor': 'lattice',
                        'bbox': bbox or (0, 0, 0, 0)
                    })

            self.logger.info(f"  Found {len(tables)} tables with lattice mode")

            # Try stream mode as fallback for borderless tables
            # Only if we didn't find many tables with lattice
            if len(tables) < 5:
                self.logger.info("  Extracting with Camelot stream mode (borderless tables)...")
                stream_tables = camelot.read_pdf(
                    pdf_path,
                    pages='all',
                    flavor='stream',
                    suppress_stdout=True
                )

                for table in stream_tables:
                    df = table.df

                    # Filter: minimum size
                    if df.shape[0] < 3 or df.shape[1] < 2:
                        continue

                    # Filter: minimum fill ratio
                    non_empty_cells = (df.astype(str).map(lambda x: len(str(x).strip()) > 0).sum().sum())
                    total_cells = df.shape[0] * df.shape[1]
                    fill_ratio = non_empty_cells / total_cells if total_cells > 0 else 0

                    if fill_ratio < 0.2:
                        continue

                    # Check if this table overlaps with any lattice table
                    # (avoid duplicates)
                    is_duplicate = False
                    for existing_table in tables:
                        if (existing_table['page'] == table.page and
                            abs(existing_table['df'].shape[0] - df.shape[0]) < 3):
                            is_duplicate = True
                            break

                    if is_duplicate:
                        continue

                    # Get bounding box if available
                    bbox = getattr(table, '_bbox', None)
                    if bbox is None and hasattr(table, 'cells'):
                        try:
                            all_x0 = [cell.x1 for row in table.cells for cell in row]
                            all_y0 = [cell.y1 for row in table.cells for cell in row]
                            all_x1 = [cell.x2 for row in table.cells for cell in row]
                            all_y1 = [cell.y2 for row in table.cells for cell in row]
                            bbox = (min(all_x0), min(all_y0), max(all_x1), max(all_y1))
                        except:
                            bbox = (0, 0, 0, 0)

                    tables.append({
                        'df': df,
                        'page': table.page,
                        'accuracy': table.accuracy,
                        'flavor': 'stream',
                        'bbox': bbox or (0, 0, 0, 0)
                    })

                self.logger.info(f"  Found {len([t for t in tables if t['flavor'] == 'stream'])} additional tables with stream mode")

            self.logger.info(f"  Total tables extracted: {len(tables)}")
            return tables

        except Exception as e:
            self.logger.warning(f"Camelot extraction failed: {e}")
            return []
    
    def _fix_single_cell_table(self, df: pd.DataFrame) -> Optional[pd.DataFrame]:
        """
        Fix tables that Camelot extracts as a single cell with all content mashed together.

        This happens when Camelot's lattice mode detects the outer border but not the
        internal column separators (e.g., when internal lines are too thin/faint).

        Args:
            df: DataFrame with shape (rows, 1) where content is in a single column

        Returns:
            Fixed DataFrame with proper columns, or None if unable to fix
        """
        if df.shape[1] != 1 or df.shape[0] < 2:
            return None

        # Get the content from the single cell (usually in row 1)
        content = None
        for i in range(min(3, df.shape[0])):
            cell_content = str(df.iloc[i, 0])
            if len(cell_content) > 100:  # Likely the data cell
                content = cell_content
                break

        if not content:
            return None

        # Split by newlines
        lines = [line.strip() for line in content.split('\n') if line.strip()]

        if len(lines) < 10:  # Too few lines to be a real table
            return None

        # Try to detect the number of columns by looking for patterns
        # Common patterns:
        # 1. Header with (N = X) indicates treatment arms
        # 2. Repeating pattern of values (e.g., every 3rd line has numbers)

        # Look for (N = X) patterns to detect columns
        n_pattern_count = sum(1 for line in lines[:10] if re.search(r'\(N\s*=\s*\d+\)', line))

        # Estimate number of columns
        # If we see 2 (N = X) patterns, it's likely a 3-column table (Event + 2 arms)
        # If we see 3 (N = X) patterns, it's likely a 4-column table (Event + 3 arms)
        num_cols = n_pattern_count + 1 if n_pattern_count > 0 else 3  # Default to 3

        # Find where data starts (after header info)
        data_start_idx = None
        for i, line in enumerate(lines):
            # Look for common header end markers
            if any(marker in line.lower() for marker in ['number (percent)', 'n (%)', 'no. (%)']):
                data_start_idx = i + 1
                break

        if data_start_idx is None:
            # Try to find first data row (contains numbers or percentages)
            for i, line in enumerate(lines):
                if re.search(r'\d+\s*\(\d+\.?\d*\)', line) or re.search(r'^\d+$', line):
                    # This might be data, but check if previous lines look like headers
                    if i >= num_cols:
                        data_start_idx = i
                        break

        if data_start_idx is None or data_start_idx >= len(lines):
            return None

        # Parse data rows
        # Strategy: Look for lines with numbers/percentages - these are likely data values
        # The line before them is likely the event name
        rows = []
        i = data_start_idx

        while i < len(lines):
            # Skip empty lines
            if not lines[i].strip():
                i += 1
                continue

            # Check if we have enough lines left for a complete row
            if i + num_cols - 1 >= len(lines):
                break

            # Look ahead to see if the next lines contain numbers (data values)
            # For a 3-column table: Event, Value1, Value2
            # For a 4-column table: Event, Value1, Value2, Value3

            # Check if the next (num_cols - 1) lines look like data values
            looks_like_data_row = True
            for col_idx in range(1, num_cols):
                if i + col_idx >= len(lines):
                    looks_like_data_row = False
                    break

                line = lines[i + col_idx]
                # Data values should have numbers or be "0"
                if not (re.search(r'\d', line) or line == "0"):
                    looks_like_data_row = False
                    break

            if looks_like_data_row:
                # Extract the row
                row_data = [lines[i + col_idx].strip() for col_idx in range(num_cols)]
                rows.append(row_data)
                i += num_cols
            else:
                # This might be a section header or multi-line text, skip it
                i += 1

        if len(rows) < 5:  # Too few rows to be a real table
            return None

        # Create column names
        # Try to extract from header lines
        header_lines = lines[:data_start_idx]
        col_names = []

        # Look for treatment arm names with (N = X)
        for line in header_lines:
            if re.search(r'\(N\s*=\s*\d+\)', line):
                col_names.append(line)

        # If we found column names, use them
        if len(col_names) == num_cols - 1:
            col_names = ['Event'] + col_names
        else:
            # Generic column names
            col_names = ['Event'] + [f'Column {i+1}' for i in range(num_cols - 1)]

        # Create DataFrame
        try:
            fixed_df = pd.DataFrame(rows, columns=col_names)
            self.logger.info(f"  Successfully fixed single-cell table: {len(rows)} rows x {num_cols} columns")
            return fixed_df
        except Exception as e:
            self.logger.warning(f"  Failed to create DataFrame from parsed rows: {e}")
            return None

    def _extract_headers_with_pymupdf(self, pdf_path: str) -> List[Dict[str, Any]]:
        """Extract table headers using PyMuPDF text blocks."""
        import fitz

        headers_list = []

        try:
            doc = fitz.open(pdf_path)

            for page_num in range(len(doc)):
                page = doc[page_num]

                try:
                    # Extract text blocks
                    blocks = page.get_text("blocks")

                    # Look for blocks that contain table headers
                    # These typically have "Characteristic" and treatment arm names
                    for block_idx, block in enumerate(blocks):
                        if len(block) < 5:
                            continue

                        # block is a tuple: (x0, y0, x1, y1, text, block_no, block_type)
                        text = block[4]

                        # Look for blocks with "Characteristic" and treatment arms
                        # This is a strong indicator of a table header
                        if 'Characteristic' in text and ('Placebo' in text or 'Treatment' in text or 'Drug' in text or 'Anifrolumab' in text):
                            # Parse the header text
                            lines = [line.strip() for line in text.split('\n') if line.strip()]

                            # Try to extract column headers
                            headers = self._parse_header_block(lines)

                            if headers and len(headers) >= 2:
                                headers_list.append({
                                    'page': page_num + 1,  # 1-indexed
                                    'block_idx': block_idx,
                                    'headers': headers,
                                    'num_cols': len(headers),
                                    'bbox': block[:4],
                                    'raw_text': text
                                })

                                self.logger.info(f"  Found header block on page {page_num + 1}: {headers}")

                except Exception as e:
                    self.logger.debug(f"Error extracting headers from page {page_num + 1}: {e}")
                    continue

            doc.close()
            return headers_list

        except Exception as e:
            self.logger.warning(f"PyMuPDF header extraction failed: {e}")
            return []

    def _merge_tables_by_label(
        self,
        pdf_path: str,
        camelot_tables: List[Dict[str, Any]],
        pymupdf_headers: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Merge Camelot tables based on table labels found in the PDF.

        Strategy:
        1. Find all "Table X" labels in the PDF
        2. For each label, find all Camelot tables between this label and the next
        3. Merge all those tables together

        Args:
            pdf_path: Path to PDF file
            camelot_tables: List of tables extracted by Camelot
            pymupdf_headers: List of headers extracted by PyMuPDF

        Returns:
            List of merged tables
        """
        import fitz

        if not camelot_tables:
            return []

        # Extract table labels from PDF
        doc = fitz.open(pdf_path)
        table_labels_by_page = {}

        for page_num in range(len(doc)):
            page = doc[page_num]
            blocks = page.get_text("dict")["blocks"]

            labels = []
            for block in blocks:
                if block.get("type") == 0:  # Text block
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            text = span.get("text", "").strip()
                            # Look for "Table X" or "Table X."
                            if text.startswith("Table") and any(c.isdigit() for c in text):
                                bbox = block["bbox"]
                                labels.append({
                                    "text": text,
                                    "y_pos": bbox[1],  # Top of label
                                    "bbox": bbox
                                })

            if labels:
                # Sort labels by vertical position (top to bottom in PDF coords = high y to low y)
                labels.sort(key=lambda x: -x["y_pos"])  # Higher y = top of page
                table_labels_by_page[page_num + 1] = labels  # 1-indexed page numbers

        doc.close()

        # Group Camelot tables by page
        tables_by_page = {}
        for table in camelot_tables:
            page = table['page']
            if page not in tables_by_page:
                tables_by_page[page] = []
            tables_by_page[page].append(table)

        # Merge tables based on labels
        merged_tables = []

        for page, page_tables in tables_by_page.items():
            labels = table_labels_by_page.get(page, [])

            if not labels:
                # No labels found, use old merging logic
                self.logger.info(f"  Page {page}: No table labels found, keeping tables as-is")
                merged_tables.extend(page_tables)
                continue

            # Sort tables by vertical position (top to bottom)
            page_tables.sort(key=lambda t: -t['bbox'][1])

            # For each label, find tables that belong to it
            for i, label in enumerate(labels):
                label_y = label["y_pos"]
                next_label_y = labels[i + 1]["y_pos"] if i + 1 < len(labels) else float('inf')

                # Find tables between this label and the next
                # In PDF coords: y increases from bottom to top
                # Label at y=60 is near top visually (8% from bottom)
                # Table at y=700 is near bottom visually (97% from bottom)
                # So table content is ABOVE the label in PDF coords (higher y values)
                # We want tables where: table_y_bottom > label_y (table is above label)
                # and table_y_top < next_label_y (table is below next label)
                label_tables = []
                for table in page_tables:
                    table_y_top = table['bbox'][3]  # Top of table (higher y value in PDF coords)
                    table_y_bottom = table['bbox'][1]  # Bottom of table (lower y value)

                    # Table should be above the label (table_y_bottom > label_y)
                    # and below the next label (table_y_top < next_label_y)
                    if table_y_bottom > label_y and table_y_top < next_label_y:
                        label_tables.append(table)

                if label_tables:
                    # Remove overlapping tables (keep larger ones)
                    label_tables = self._remove_overlapping_tables(label_tables)

                    # Group tables by column count (only merge tables with same # of columns)
                    tables_by_cols = {}
                    for table in label_tables:
                        num_cols = table['df'].shape[1]
                        if num_cols not in tables_by_cols:
                            tables_by_cols[num_cols] = []
                        tables_by_cols[num_cols].append(table)

                    # Process each group separately
                    for num_cols, col_tables in tables_by_cols.items():
                        # Find matching headers
                        matching_headers = [
                            h for h in pymupdf_headers
                            if h['page'] == page and h['num_cols'] == num_cols
                        ]
                        header_info = matching_headers[0] if matching_headers else None

                        if len(col_tables) > 1:
                            # Merge multiple tables with same column count
                            merged_table = self._combine_tables(col_tables, header_info)
                            merged_tables.append(merged_table)
                            self.logger.info(f"  Page {page}: Merged {len(col_tables)} tables ({num_cols} cols) for {label['text']}")
                        else:
                            # Single table
                            merged_tables.append(col_tables[0])
                            self.logger.info(f"  Page {page}: Single table ({num_cols} cols) for {label['text']}")

        return merged_tables

    def _merge_split_tables_old(
        self,
        camelot_tables: List[Dict[str, Any]],
        pymupdf_headers: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Merge Camelot tables from the same page that belong together.

        Tables are merged if they:
        1. Are on the same page
        2. Have the same number of columns
        3. Have matching headers (from PyMuPDF)
        4. Are vertically adjacent (within reasonable distance)

        Args:
            camelot_tables: List of tables extracted by Camelot
            pymupdf_headers: List of headers extracted by PyMuPDF

        Returns:
            List of merged tables
        """
        if not camelot_tables:
            return []

        # Group tables by page
        tables_by_page = {}
        for table in camelot_tables:
            page = table['page']
            if page not in tables_by_page:
                tables_by_page[page] = []
            tables_by_page[page].append(table)

        merged_tables = []

        for page, page_tables in tables_by_page.items():
            # Find PyMuPDF headers for this page
            page_headers = [h for h in pymupdf_headers if h['page'] == page]

            if not page_headers:
                # No headers found, can't determine which tables to merge
                merged_tables.extend(page_tables)
                continue

            # Sort tables by vertical position (top to bottom)
            # In PDF coordinates, higher y values are at the top of the page
            page_tables.sort(key=lambda t: -t['bbox'][1])  # Sort by -y0 (top to bottom)

            # Try to merge tables with same column count and matching headers
            i = 0
            while i < len(page_tables):
                current_table = page_tables[i]
                current_df = current_table['df']
                current_cols = current_df.shape[1]

                # Find matching headers for this table
                matching_headers = [
                    h for h in page_headers
                    if h['num_cols'] == current_cols
                ]

                if not matching_headers:
                    # No headers match, keep table as-is
                    merged_tables.append(current_table)
                    i += 1
                    continue

                # Check if this table overlaps with the next table
                if i + 1 < len(page_tables):
                    next_table = page_tables[i + 1]
                    next_df = next_table['df']

                    if self._tables_overlap(current_df, next_df):
                        # Skip current table, it's a subset of the next one
                        self.logger.info(f"  Skipping table {i+1} (overlaps with table {i+2})")
                        i += 1
                        continue

                # Look ahead to find tables to merge
                tables_to_merge = [current_table]
                j = i + 1

                while j < len(page_tables):
                    next_table = page_tables[j]
                    next_df = next_table['df']
                    next_cols = next_df.shape[1]

                    # Check if this table should be merged
                    should_merge = (
                        next_cols == current_cols and  # Same number of columns
                        self._tables_are_adjacent(current_table, next_table) and  # Vertically adjacent
                        not self._table_has_header_row(next_df, matching_headers[0]['headers'])  # No duplicate header
                    )

                    if should_merge:
                        tables_to_merge.append(next_table)
                        current_table = next_table  # Update for adjacency check
                        j += 1
                    else:
                        break

                # Merge the tables
                if len(tables_to_merge) > 1:
                    merged_table = self._combine_tables(tables_to_merge, matching_headers[0])
                    merged_tables.append(merged_table)
                    self.logger.info(f"  Merged {len(tables_to_merge)} tables on page {page} into one table")
                else:
                    merged_tables.append(tables_to_merge[0])

                i = j

        return merged_tables

    def _remove_overlapping_tables(self, tables: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Remove overlapping tables from a list, keeping the larger ones.

        Args:
            tables: List of tables (sorted top to bottom)

        Returns:
            List of non-overlapping tables
        """
        if len(tables) <= 1:
            return tables

        # Sort by size (largest first)
        sorted_tables = sorted(tables, key=lambda t: t['df'].shape[0], reverse=True)

        # Keep non-overlapping tables
        kept_tables = []
        for table in sorted_tables:
            # Check if this table overlaps with any kept table
            overlaps = False
            for kept in kept_tables:
                if self._tables_overlap(table['df'], kept['df']) or self._tables_overlap(kept['df'], table['df']):
                    overlaps = True
                    break

            if not overlaps:
                kept_tables.append(table)

        # Sort back to original order (top to bottom)
        kept_tables.sort(key=lambda t: -t['bbox'][1])

        return kept_tables

    def _tables_overlap(self, df1, df2) -> bool:
        """
        Check if two dataframes overlap (one is a subset of the other).

        Returns True if df1's data rows appear in df2 (df2 is a superset).
        """
        import pandas as pd

        # If df1 is larger, they don't overlap in the way we care about
        if df1.shape[0] >= df2.shape[0]:
            return False

        # Find the first data row in df1 (skip headers/titles)
        # Look for a row that contains "age" or other characteristic names
        start_row = 0
        for i in range(df1.shape[0]):
            first_col = str(df1.iloc[i, 0]).strip().lower()
            # Look for rows that start with characteristic names
            if any(keyword in first_col for keyword in ['age', 'female', 'male', 'race', 'sex', 'weight', 'height']):
                start_row = i
                break

        # Check if df1's data rows appear in df2
        # Compare up to 3 data rows
        rows_to_check = min(3, df1.shape[0] - start_row)
        matches = 0

        for i in range(start_row, start_row + rows_to_check):
            row1 = ' '.join(str(cell).strip() for cell in df1.iloc[i].tolist())

            # Check if this row appears anywhere in df2
            for j in range(df2.shape[0]):
                row2 = ' '.join(str(cell).strip() for cell in df2.iloc[j].tolist())
                if row1 == row2:
                    matches += 1
                    break

        # If at least 2 out of 3 rows match, consider it an overlap
        return matches >= 2

    def _tables_are_adjacent(self, table1: Dict[str, Any], table2: Dict[str, Any]) -> bool:
        """
        Check if two tables are vertically adjacent.

        In PDF coordinates, y increases from bottom to top.
        So table1 (higher on page) has larger y values than table2 (lower on page).
        """
        bbox1 = table1['bbox']
        bbox2 = table2['bbox']

        # bbox is (x0, y0, x1, y1)
        # table1 is above table2, so table1's y0 (bottom) should be close to table2's y1 (top)
        # But since we're going top-to-bottom, table2 has smaller y values
        # Gap = table1's bottom (y0) - table2's top (y1)
        gap = bbox1[1] - bbox2[3]  # y0 of table1 - y1 of table2

        # Allow overlap (negative gap) or small gap
        return -50 <= gap <= 100

    def _table_has_header_row(self, df, expected_headers: List[str]) -> bool:
        """Check if the dataframe's first row contains header-like text."""
        if df.shape[0] == 0:
            return False

        first_row = df.iloc[0].tolist()
        first_row_text = ' '.join(str(cell).lower() for cell in first_row)

        # Check if first row contains header keywords
        header_keywords = ['characteristic', 'placebo', 'treatment', 'drug', 'n =', 'n=']
        return any(keyword in first_row_text for keyword in header_keywords)

    def _combine_tables(
        self,
        tables: List[Dict[str, Any]],
        header_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Combine multiple tables into one."""
        import pandas as pd

        # Concatenate all dataframes
        dfs = [t['df'] for t in tables]
        combined_df = pd.concat(dfs, ignore_index=True)

        # Use the first table's metadata
        first_table = tables[0]

        # Calculate combined bounding box
        min_x0 = min(t['bbox'][0] for t in tables)
        min_y0 = min(t['bbox'][1] for t in tables)
        max_x1 = max(t['bbox'][2] for t in tables)
        max_y1 = max(t['bbox'][3] for t in tables)

        return {
            'df': combined_df,
            'page': first_table['page'],
            'bbox': (min_x0, min_y0, max_x1, max_y1),
            'accuracy': sum(t['accuracy'] for t in tables) / len(tables)  # Average accuracy
        }

    def _parse_header_block(self, lines: List[str]) -> List[str]:
        """
        Parse header block text to extract column names.

        Example input:
        ['Characteristic', 'Placebo', '(N = 182)', 'Anifrolumab, 300 mg', '(N = 180)']

        Expected output:
        ['Characteristic', 'Placebo (N = 182)', 'Anifrolumab, 300 mg (N = 180)']
        """
        if not lines:
            return []

        headers = []
        current_header = ""

        for line in lines:
            # Check if this line is an N value (e.g., "(N = 182)")
            if re.match(r'\(N\s*=\s*\d+\)', line):
                # Append to current header
                if current_header:
                    current_header += f" {line}"
                    headers.append(current_header)
                    current_header = ""
            else:
                # Start a new header
                if current_header:
                    # Previous header didn't have N value, add it anyway
                    headers.append(current_header)
                current_header = line

        # Add last header if exists
        if current_header:
            headers.append(current_header)

        return headers
    
    def _merge_headers_and_content(
        self,
        camelot_tables: List[Dict[str, Any]],
        pdfplumber_headers: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Merge pdfplumber headers with Camelot content."""
        
        merged_tables = []
        
        for i, camelot_table in enumerate(camelot_tables):
            df = camelot_table['df'].copy()
            page = camelot_table['page']
            
            # Find matching pdfplumber headers for this page
            matching_headers = [
                h for h in pdfplumber_headers
                if h['page'] == page and h['num_cols'] == df.shape[1]
            ]
            
            # Try to use pdfplumber headers
            if matching_headers:
                headers = matching_headers[0]['headers']

                # Check if headers look valid (not all numbers)
                if self._are_headers_valid(headers):
                    # Check if first row is a header row (similar to the headers we found)
                    first_row = [str(cell).strip() for cell in df.iloc[0].tolist()] if df.shape[0] > 0 else []
                    first_row_is_header = self._row_looks_like_header(first_row, headers)

                    # Replace column names with proper headers
                    df.columns = headers

                    # Only remove first row if it looks like a header
                    if first_row_is_header:
                        df = df.iloc[1:].reset_index(drop=True)
                        self.logger.info(f"  Table {i+1}: Used pdfplumber headers (removed header row): {headers[:3]}")
                    else:
                        self.logger.info(f"  Table {i+1}: Used pdfplumber headers (kept first row as data): {headers[:3]}")
                else:
                    # Headers don't look valid, keep Camelot's extraction
                    self.logger.info(f"  Table {i+1}: pdfplumber headers invalid, keeping Camelot")
            else:
                # No matching headers found
                self.logger.info(f"  Table {i+1}: No matching pdfplumber headers found")
            
            # Convert to markdown
            table_content = df.to_markdown(index=False)
            
            # Extract table label
            first_row_text = ' '.join(str(cell) for cell in df.iloc[0].tolist()) if df.shape[0] > 0 else ''
            label_match = re.search(r'Table\s+([IVX]+|[0-9]+)[.\s]([^\n]*)', first_row_text, re.IGNORECASE)
            
            if label_match:
                table_label = f"Table {label_match.group(1)}"
            else:
                table_label = f"Table {i+1}"
            
            # Build result
            result = {
                'label': table_label,
                'content': table_content,
                'accuracy': camelot_table['accuracy'],
                'page': page,
                'extraction_method': 'hybrid (PyMuPDF headers + Camelot content)'
            }

            # Include headers if they were found and used
            if matching_headers and self._are_headers_valid(matching_headers[0]['headers']):
                result['headers'] = matching_headers[0]['headers']

            merged_tables.append(result)
        
        return merged_tables
    
    def _row_looks_like_header(self, row: List[str], expected_headers: List[str]) -> bool:
        """
        Check if a row looks like a header row.

        Args:
            row: The row to check
            expected_headers: The headers we expect to see

        Returns:
            True if the row looks like a header row
        """
        if not row or len(row) != len(expected_headers):
            return False

        # Check if any cell in the row matches any expected header (case-insensitive, partial match)
        matches = 0
        for cell in row:
            cell_lower = cell.lower()
            for header in expected_headers:
                header_lower = header.lower()
                # Check for partial match (at least 50% of header text)
                if len(header_lower) > 3 and header_lower[:len(header_lower)//2] in cell_lower:
                    matches += 1
                    break
                elif cell_lower in header_lower or header_lower in cell_lower:
                    matches += 1
                    break

        # If at least 50% of cells match headers, it's probably a header row
        return matches >= len(row) / 2

    def _are_headers_valid(self, headers: List[str]) -> bool:
        """Check if headers look valid (not all numbers or empty)."""

        # Filter out empty headers
        non_empty = [h for h in headers if h and h.strip()]

        if not non_empty:
            return False

        # Check if all headers are just numbers
        all_numbers = all(h.isdigit() for h in non_empty)

        if all_numbers:
            return False

        # Check if headers have reasonable length
        avg_length = sum(len(h) for h in non_empty) / len(non_empty)

        if avg_length < 1:
            return False

        return True

