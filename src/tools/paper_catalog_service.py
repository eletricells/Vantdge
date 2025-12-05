"""
Paper catalog service - central orchestrator for paper management.

Integrates storage, processing, database cataloging, and auto-tagging.
"""
from typing import List, Dict, Any, Optional, BinaryIO
from pathlib import Path
import json
import logging
from datetime import datetime
from dataclasses import dataclass

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.tools.paper_storage import PaperStorage, create_storage
from src.tools.paper_processor import PaperProcessor, ProcessedPaper
from src.models.paper_catalog import (
    Paper, Disease, Drug, Target, AnalysisType,
    init_database, get_session, Base
)

logger = logging.getLogger(__name__)


@dataclass
class AnalysisContext:
    """Context for paper analysis - used for auto-tagging."""
    disease: Optional[str] = None
    drug: Optional[str] = None
    target: Optional[str] = None
    analysis_type: Optional[str] = None
    source: str = "unknown"


class AutoTagger:
    """
    Automatically generate tags from paper content and context.

    Tags help organize papers and enable efficient search/reuse.
    """

    # Common drug type indicators
    ANTIBODY_KEYWORDS = ["antibody", "mab", "monoclonal", "igg", "immunoglobulin"]
    SMALL_MOLECULE_KEYWORDS = ["small molecule", "inhibitor", "compound", "oral"]
    GENE_THERAPY_KEYWORDS = ["gene therapy", "aav", "lentivirus", "viral vector"]

    # Study type indicators
    IN_VITRO_KEYWORDS = ["in vitro", "cell culture", "cell line", "cultured cells"]
    IN_VIVO_KEYWORDS = ["in vivo", "animal model", "mice", "mouse", "rat", "primate"]
    CLINICAL_KEYWORDS = ["clinical trial", "phase 1", "phase 2", "phase 3", "patients"]

    # Data type indicators
    EFFICACY_KEYWORDS = ["efficacy", "response", "tumor", "survival", "reduction"]
    SAFETY_KEYWORDS = ["safety", "toxicity", "adverse event", "tolerability"]
    MECHANISM_KEYWORDS = ["mechanism", "signaling", "pathway", "binding"]
    PK_KEYWORDS = ["pharmacokinetic", "pk/pd", "half-life", "bioavailability", "clearance"]

    def tag_paper(
        self,
        full_text: str,
        tables_count: int,
        context: AnalysisContext
    ) -> List[str]:
        """
        Generate tags from paper content and context.

        Args:
            full_text: Extracted paper text
            tables_count: Number of tables extracted
            context: Analysis context (disease, drug, target)

        Returns:
            List of tags
        """
        tags = []
        text_lower = full_text.lower()
        text_sample = text_lower[:5000]  # Sample first 5000 chars for performance

        # Add analysis type tag
        if context.analysis_type:
            tags.append(context.analysis_type)

        # Detect drug type
        drug_type = self._detect_drug_type(text_sample)
        if drug_type:
            tags.append(drug_type)

        # Detect study types
        if self._contains_any(text_sample, self.IN_VITRO_KEYWORDS):
            tags.append("in_vitro")

        if self._contains_any(text_sample, self.IN_VIVO_KEYWORDS):
            tags.append("in_vivo")

        if self._contains_any(text_sample, self.CLINICAL_KEYWORDS):
            tags.append("clinical")

        # Detect data types
        if self._contains_any(text_sample, self.EFFICACY_KEYWORDS):
            tags.append("efficacy")

        if self._contains_any(text_sample, self.SAFETY_KEYWORDS):
            tags.append("safety")

        if self._contains_any(text_sample, self.MECHANISM_KEYWORDS):
            tags.append("mechanism")

        if self._contains_any(text_sample, self.PK_KEYWORDS):
            tags.append("pharmacokinetics")

        # Add metadata tags
        if tables_count > 0:
            tags.append("has_tables")

        if tables_count >= 5:
            tags.append("data_rich")

        # Deduplicate
        return list(set(tags))

    def _detect_drug_type(self, text_sample: str) -> Optional[str]:
        """Detect drug type from text."""
        if self._contains_any(text_sample, self.ANTIBODY_KEYWORDS):
            return "antibody"
        elif self._contains_any(text_sample, self.SMALL_MOLECULE_KEYWORDS):
            return "small_molecule"
        elif self._contains_any(text_sample, self.GENE_THERAPY_KEYWORDS):
            return "gene_therapy"
        return None

    @staticmethod
    def _contains_any(text: str, keywords: List[str]) -> bool:
        """Check if text contains any of the keywords."""
        return any(keyword in text for keyword in keywords)


class PaperCatalogService:
    """
    Central service for paper management.

    Orchestrates:
    - PDF storage (local or S3)
    - PDF processing (text + table extraction)
    - Database cataloging
    - Auto-tagging
    """

    def __init__(
        self,
        database_url: str,
        storage_type: str = "local",
        storage_config: Optional[Dict[str, Any]] = None,
        use_camelot: bool = True
    ):
        """
        Initialize paper catalog service.

        Args:
            database_url: PostgreSQL connection string
            storage_type: "local" or "s3"
            storage_config: Storage-specific configuration
            use_camelot: Use Camelot for table extraction
        """
        # Initialize database
        self.engine = init_database(database_url)
        logger.info(f"Connected to database: {database_url}")

        # Initialize storage
        storage_config = storage_config or {"base_path": "data"}
        self.storage = create_storage(storage_type, **storage_config)
        logger.info(f"Initialized {storage_type} storage")

        # Initialize processor
        self.processor = PaperProcessor(use_camelot=use_camelot)
        logger.info(f"Initialized paper processor (Camelot: {use_camelot})")

        # Initialize auto-tagger
        self.tagger = AutoTagger()

    def add_paper(
        self,
        pdf_data: bytes | BinaryIO,
        paper_id: str,
        context: AnalysisContext,
        doi: Optional[str] = None,
        pmid: Optional[str] = None,
        title: Optional[str] = None,
        authors: Optional[str] = None,
        journal: Optional[str] = None,
        year: Optional[int] = None
    ) -> Paper:
        """
        Add a paper to the catalog.

        Complete workflow:
        1. Store PDF
        2. Process PDF (extract text, tables)
        3. Auto-tag
        4. Create database record
        5. Link to diseases/drugs/targets

        Args:
            pdf_data: PDF file data
            paper_id: Unique identifier
            context: Analysis context for tagging
            doi: DOI identifier (optional)
            pmid: PubMed ID (optional)
            title: Paper title (optional - will extract from PDF if not provided)
            authors: Authors (optional)
            journal: Journal name (optional)
            year: Publication year (optional)

        Returns:
            Paper database object
        """
        logger.info(f"Adding paper to catalog: {paper_id}")

        # Step 1: Store PDF
        pdf_path = self.storage.store_pdf(paper_id, pdf_data, source=context.source)

        # Step 2: Process PDF
        processed = self.processor.process_pdf(pdf_path, paper_id)

        if processed.processing_status == "failed":
            logger.error(f"Failed to process PDF: {processed.error_message}")
            # Store anyway with error status
            return self._create_paper_record(
                paper_id=paper_id,
                doi=doi,
                pmid=pmid,
                title=title or "Failed to process",
                authors=authors,
                journal=journal,
                year=year,
                pdf_path=pdf_path,
                processing_status="failed",
                context=context
            )

        # Step 3: Save extracted data
        extracted_dir = Path("data") / "extracted" / paper_id
        self.processor.save_extracted_data(processed, extracted_dir)

        # Store extracted data in storage system
        self.storage.store_extracted_data(paper_id, "full_text", processed.full_text)
        if processed.tables:
            tables_json = json.dumps([t.model_dump() for t in processed.tables])
            self.storage.store_extracted_data(paper_id, "tables", tables_json)

        metadata_json = json.dumps(processed.metadata.model_dump())
        self.storage.store_extracted_data(paper_id, "metadata", metadata_json)

        # Step 4: Auto-tag
        tags = self.tagger.tag_paper(
            full_text=processed.full_text,
            tables_count=len(processed.tables),
            context=context
        )

        # Step 5: Create database record
        # Use extracted metadata if not provided
        if not title and processed.metadata.title:
            title = processed.metadata.title
        if not authors and processed.metadata.authors:
            authors = processed.metadata.authors

        paper = self._create_paper_record(
            paper_id=paper_id,
            doi=doi,
            pmid=pmid,
            title=title or "Unknown Title",
            authors=authors,
            journal=journal,
            year=year,
            pdf_path=pdf_path,
            extracted_path=str(extracted_dir),
            tables_extracted=len(processed.tables),
            tags=tags,
            processing_status="processed",
            context=context
        )

        logger.info(f"Successfully added paper {paper_id} to catalog with {len(tags)} tags")
        return paper

    def _create_paper_record(
        self,
        paper_id: str,
        doi: Optional[str],
        pmid: Optional[str],
        title: str,
        authors: Optional[str],
        journal: Optional[str],
        year: Optional[int],
        pdf_path: str,
        processing_status: str,
        context: AnalysisContext,
        extracted_path: Optional[str] = None,
        tables_extracted: int = 0,
        tags: Optional[List[str]] = None
    ) -> Paper:
        """Create database record for paper."""
        session = get_session(self.engine)

        try:
            # Create paper record
            paper = Paper(
                id=paper_id,
                doi=doi,
                pmid=pmid,
                title=title,
                authors=authors,
                journal=journal,
                year=year,
                pdf_path=pdf_path,
                extracted_path=extracted_path,
                processing_status=processing_status,
                tables_extracted=tables_extracted,
                date_processed=datetime.utcnow() if processing_status == "processed" else None,
                source=context.source,
                tags=json.dumps(tags) if tags else None
            )

            # Link to disease
            if context.disease:
                disease = self._get_or_create_disease(session, context.disease)
                paper.diseases.append(disease)

            # Link to drug
            if context.drug:
                drug = self._get_or_create_drug(session, context.drug)
                paper.drugs.append(drug)

            # Link to target
            if context.target:
                target = self._get_or_create_target(session, context.target)
                paper.targets.append(target)

            # Link to analysis type
            if context.analysis_type:
                analysis_type = self._get_or_create_analysis_type(session, context.analysis_type)
                paper.analysis_types.append(analysis_type)

            session.add(paper)
            session.commit()

            logger.info(f"Created database record for {paper_id}")
            return paper

        except Exception as e:
            session.rollback()
            logger.error(f"Failed to create paper record: {e}")
            raise
        finally:
            session.close()

    def _get_or_create_disease(self, session: Session, disease_name: str) -> Disease:
        """Get or create disease record."""
        disease_id = disease_name.lower().replace(" ", "_").replace("'", "")

        disease = session.query(Disease).filter_by(id=disease_id).first()
        if not disease:
            disease = Disease(id=disease_id, name=disease_name)
            session.add(disease)
            logger.info(f"Created new disease: {disease_name}")

        return disease

    def _get_or_create_drug(self, session: Session, drug_name: str) -> Drug:
        """Get or create drug record."""
        drug_id = drug_name.lower().replace(" ", "_").replace("-", "_")

        drug = session.query(Drug).filter_by(id=drug_id).first()
        if not drug:
            drug = Drug(id=drug_id, name=drug_name)
            session.add(drug)
            logger.info(f"Created new drug: {drug_name}")

        return drug

    def _get_or_create_target(self, session: Session, target_name: str) -> Target:
        """Get or create target record."""
        target_id = target_name.upper()  # Gene symbols are uppercase

        target = session.query(Target).filter_by(id=target_id).first()
        if not target:
            target = Target(id=target_id, name=target_name)
            session.add(target)
            logger.info(f"Created new target: {target_name}")

        return target

    def _get_or_create_analysis_type(self, session: Session, analysis_type_name: str) -> AnalysisType:
        """Get or create analysis type record."""
        analysis_type_id = analysis_type_name.lower()

        analysis_type = session.query(AnalysisType).filter_by(id=analysis_type_id).first()
        if not analysis_type:
            analysis_type = AnalysisType(id=analysis_type_id, name=analysis_type_name)
            session.add(analysis_type)
            logger.info(f"Created new analysis type: {analysis_type_name}")

        return analysis_type

    def search_papers(
        self,
        disease: Optional[str] = None,
        drug: Optional[str] = None,
        target: Optional[str] = None,
        analysis_type: Optional[str] = None,
        tags: Optional[List[str]] = None,
        year_min: Optional[int] = None
    ) -> List[Paper]:
        """
        Search for papers in catalog.

        Args:
            disease: Disease name
            drug: Drug name
            target: Target name
            analysis_type: Analysis type
            tags: List of tags to match
            year_min: Minimum publication year

        Returns:
            List of matching papers
        """
        session = get_session(self.engine)

        try:
            query = session.query(Paper)

            # Apply filters
            if disease:
                query = query.join(Paper.diseases).filter(
                    Disease.name.ilike(f"%{disease}%")
                )

            if drug:
                query = query.join(Paper.drugs).filter(
                    Drug.name.ilike(f"%{drug}%")
                )

            if target:
                query = query.join(Paper.targets).filter(
                    Target.name.ilike(f"%{target}%")
                )

            if analysis_type:
                query = query.join(Paper.analysis_types).filter(
                    AnalysisType.name == analysis_type
                )

            if year_min:
                query = query.filter(Paper.year >= year_min)

            if tags:
                for tag in tags:
                    query = query.filter(Paper.tags.contains(tag))

            # Only return successfully processed papers
            query = query.filter(Paper.processing_status == "processed")

            results = query.all()
            logger.info(f"Found {len(results)} papers matching search criteria")
            return results

        finally:
            session.close()

    def get_paper(self, paper_id: str) -> Optional[Paper]:
        """
        Get paper by ID.

        Args:
            paper_id: Paper identifier

        Returns:
            Paper object or None
        """
        session = get_session(self.engine)

        try:
            return session.query(Paper).filter_by(id=paper_id).first()
        finally:
            session.close()
