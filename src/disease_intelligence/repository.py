"""
Repository for Disease Intelligence database operations.
"""

import json
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any

from .models import (
    DiseaseIntelligence,
    PrevalenceData,
    PatientSegmentation,
    TreatmentParadigm,
    TreatmentLine,
    TreatmentDrug,
    TreatmentEstimate,
    FailureRates,
    MarketFunnel,
    DiseaseSource,
    SeverityBreakdown,
    Subpopulation,
)

logger = logging.getLogger(__name__)


class DiseaseIntelligenceRepository:
    """Database operations for Disease Intelligence."""

    def __init__(self, db):
        """
        Initialize repository.

        Args:
            db: Database connection (DatabaseConnection instance)
        """
        self.db = db

    def save_disease(self, disease: DiseaseIntelligence) -> int:
        """
        Save or update a disease intelligence record.

        Returns:
            disease_id of saved record
        """
        self.db.ensure_connected()

        with self.db.cursor() as cur:
            # Check if disease exists
            cur.execute(
                "SELECT disease_id FROM disease_intelligence WHERE LOWER(disease_name) = LOWER(%s)",
                (disease.disease_name,)
            )
            existing = cur.fetchone()

            # Prepare JSONB fields
            treatment_paradigm_json = None
            if disease.treatment_paradigm:
                treatment_paradigm_json = json.dumps(disease.treatment_paradigm.model_dump())

            severity_json = None
            if disease.segmentation.severity:
                severity_json = json.dumps(disease.segmentation.severity.model_dump())

            subpopulations_json = None
            if disease.segmentation.subpopulations:
                subpopulations_json = json.dumps([s.model_dump() for s in disease.segmentation.subpopulations])

            sources_json = None
            if disease.sources:
                sources_json = json.dumps([s.model_dump() for s in disease.sources])

            # Prepare source estimates JSONB - merge with existing if updating
            prevalence_estimates_json = None
            failure_rate_estimates_json = None

            if existing:
                # Load existing estimates to merge with new ones
                disease_id = existing["disease_id"]
                cur.execute("""
                    SELECT prevalence_estimates, failure_rate_estimates
                    FROM disease_intelligence WHERE disease_id = %s
                """, (disease_id,))
                existing_row = cur.fetchone()

                # Merge prevalence estimates (deduplicate by PMID)
                if disease.prevalence.source_estimates:
                    new_estimates = [e.model_dump() for e in disease.prevalence.source_estimates]
                    existing_estimates = existing_row.get("prevalence_estimates") or [] if existing_row else []
                    if isinstance(existing_estimates, str):
                        existing_estimates = json.loads(existing_estimates)

                    # Build set of existing PMIDs
                    existing_pmids = set()
                    for e in existing_estimates:
                        pmid = e.get("pmid")
                        if pmid:
                            existing_pmids.add(str(pmid))

                    # Add new estimates that don't already exist
                    merged = list(existing_estimates)
                    for e in new_estimates:
                        pmid = e.get("pmid")
                        if pmid and str(pmid) not in existing_pmids:
                            merged.append(e)
                            existing_pmids.add(str(pmid))
                        elif not pmid:
                            # No PMID - check by title
                            title = e.get("title", "").lower()
                            if not any(ex.get("title", "").lower() == title for ex in merged):
                                merged.append(e)

                    prevalence_estimates_json = json.dumps(merged) if merged else None
                    logger.info(f"Merged prevalence estimates: {len(existing_estimates)} existing + {len(new_estimates)} new = {len(merged)} total")

                # Merge failure rate estimates (deduplicate by PMID)
                if disease.failure_rates.source_estimates:
                    new_estimates = [e.model_dump() for e in disease.failure_rates.source_estimates]
                    existing_estimates = existing_row.get("failure_rate_estimates") or [] if existing_row else []
                    if isinstance(existing_estimates, str):
                        existing_estimates = json.loads(existing_estimates)

                    # Build set of existing PMIDs
                    existing_pmids = set()
                    for e in existing_estimates:
                        pmid = e.get("pmid")
                        if pmid:
                            existing_pmids.add(str(pmid))

                    # Add new estimates that don't already exist
                    merged = list(existing_estimates)
                    for e in new_estimates:
                        pmid = e.get("pmid")
                        if pmid and str(pmid) not in existing_pmids:
                            merged.append(e)
                            existing_pmids.add(str(pmid))
                        elif not pmid:
                            # No PMID - check by title
                            title = e.get("title", "").lower()
                            if not any(ex.get("title", "").lower() == title for ex in merged):
                                merged.append(e)

                    failure_rate_estimates_json = json.dumps(merged) if merged else None
                    logger.info(f"Merged failure rate estimates: {len(existing_estimates)} existing + {len(new_estimates)} new = {len(merged)} total")
            else:
                # New disease - just use the new estimates
                if disease.prevalence.source_estimates:
                    prevalence_estimates_json = json.dumps([e.model_dump() for e in disease.prevalence.source_estimates])
                if disease.failure_rates.source_estimates:
                    failure_rate_estimates_json = json.dumps([e.model_dump() for e in disease.failure_rates.source_estimates])

            if existing:
                # Update existing - use COALESCE to preserve existing values when new is NULL
                disease_id = existing["disease_id"]
                cur.execute("""
                    UPDATE disease_intelligence SET
                        disease_aliases = COALESCE(%s, disease_aliases),
                        therapeutic_area = COALESCE(%s, therapeutic_area),
                        total_patients = COALESCE(%s, total_patients),
                        adult_patients = COALESCE(%s, adult_patients),
                        pediatric_patients = COALESCE(%s, pediatric_patients),
                        prevalence_source = COALESCE(%s, prevalence_source),
                        prevalence_year = COALESCE(%s, prevalence_year),
                        pct_diagnosed = COALESCE(%s, pct_diagnosed),
                        pct_treated = COALESCE(%s, pct_treated),
                        severity_breakdown = COALESCE(%s, severity_breakdown),
                        subpopulations = COALESCE(%s, subpopulations),
                        treatment_paradigm = COALESCE(%s, treatment_paradigm),
                        fail_1L_pct = COALESCE(%s, fail_1L_pct),
                        fail_1L_reason = COALESCE(%s, fail_1L_reason),
                        fail_2L_pct = COALESCE(%s, fail_2L_pct),
                        fail_2L_reason = COALESCE(%s, fail_2L_reason),
                        patients_treated = COALESCE(%s, patients_treated),
                        patients_fail_1L = COALESCE(%s, patients_fail_1L),
                        patients_addressable_2L = COALESCE(%s, patients_addressable_2L),
                        market_size_2L_usd = COALESCE(%s, market_size_2L_usd),
                        data_quality = COALESCE(%s, data_quality),
                        sources = COALESCE(%s, sources),
                        notes = COALESCE(%s, notes),
                        prevalence_estimates = COALESCE(%s, prevalence_estimates),
                        failure_rate_estimates = COALESCE(%s, failure_rate_estimates),
                        prevalence_methodology = COALESCE(%s, prevalence_methodology),
                        failure_rate_methodology = COALESCE(%s, failure_rate_methodology),
                        prevalence_confidence = COALESCE(%s, prevalence_confidence),
                        failure_rate_confidence = COALESCE(%s, failure_rate_confidence),
                        prevalence_range = COALESCE(%s, prevalence_range),
                        failure_rate_range = COALESCE(%s, failure_rate_range),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE disease_id = %s
                """, (
                    json.dumps(disease.disease_aliases) if disease.disease_aliases else None,
                    disease.therapeutic_area,
                    disease.prevalence.total_patients,
                    disease.prevalence.adult_patients,
                    disease.prevalence.pediatric_patients,
                    disease.prevalence.prevalence_source,
                    disease.prevalence.prevalence_year,
                    disease.segmentation.pct_diagnosed,
                    disease.segmentation.pct_treated,
                    severity_json,
                    subpopulations_json,
                    treatment_paradigm_json,
                    disease.failure_rates.fail_1L_pct,
                    disease.failure_rates.fail_1L_reason,
                    disease.failure_rates.fail_2L_pct,
                    disease.failure_rates.fail_2L_reason,
                    disease.market_funnel.patients_treated if disease.market_funnel else None,
                    disease.market_funnel.patients_fail_1L if disease.market_funnel else None,
                    disease.market_funnel.patients_addressable_2L if disease.market_funnel else None,
                    disease.market_funnel.market_size_2L_usd if disease.market_funnel else None,
                    disease.data_quality,
                    sources_json,
                    disease.notes,
                    prevalence_estimates_json,
                    failure_rate_estimates_json,
                    disease.prevalence.methodology_notes,
                    disease.failure_rates.methodology_notes,
                    disease.prevalence.confidence,
                    disease.failure_rates.confidence,
                    disease.prevalence.estimate_range,
                    disease.failure_rates.estimate_range,
                    disease_id,
                ))
                logger.info(f"Updated disease intelligence for {disease.disease_name}")
            else:
                # Insert new
                cur.execute("""
                    INSERT INTO disease_intelligence (
                        disease_name, disease_aliases, therapeutic_area,
                        total_patients, adult_patients, pediatric_patients,
                        prevalence_source, prevalence_year,
                        pct_diagnosed, pct_treated, severity_breakdown, subpopulations,
                        treatment_paradigm,
                        fail_1L_pct, fail_1L_reason, fail_2L_pct, fail_2L_reason,
                        patients_treated, patients_fail_1L, patients_addressable_2L, market_size_2L_usd,
                        data_quality, sources, notes,
                        prevalence_estimates, failure_rate_estimates,
                        prevalence_methodology, failure_rate_methodology,
                        prevalence_confidence, failure_rate_confidence,
                        prevalence_range, failure_rate_range
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    RETURNING disease_id
                """, (
                    disease.disease_name,
                    json.dumps(disease.disease_aliases),
                    disease.therapeutic_area,
                    disease.prevalence.total_patients,
                    disease.prevalence.adult_patients,
                    disease.prevalence.pediatric_patients,
                    disease.prevalence.prevalence_source,
                    disease.prevalence.prevalence_year,
                    disease.segmentation.pct_diagnosed,
                    disease.segmentation.pct_treated,
                    severity_json,
                    subpopulations_json,
                    treatment_paradigm_json,
                    disease.failure_rates.fail_1L_pct,
                    disease.failure_rates.fail_1L_reason,
                    disease.failure_rates.fail_2L_pct,
                    disease.failure_rates.fail_2L_reason,
                    disease.market_funnel.patients_treated if disease.market_funnel else None,
                    disease.market_funnel.patients_fail_1L if disease.market_funnel else None,
                    disease.market_funnel.patients_addressable_2L if disease.market_funnel else None,
                    disease.market_funnel.market_size_2L_usd if disease.market_funnel else None,
                    disease.data_quality,
                    sources_json,
                    disease.notes,
                    prevalence_estimates_json,
                    failure_rate_estimates_json,
                    disease.prevalence.methodology_notes,
                    disease.failure_rates.methodology_notes,
                    disease.prevalence.confidence,
                    disease.failure_rates.confidence,
                    disease.prevalence.estimate_range,
                    disease.failure_rates.estimate_range,
                ))
                disease_id = cur.fetchone()["disease_id"]
                logger.info(f"Inserted new disease intelligence for {disease.disease_name}")

            self.db.commit()
            return disease_id

    def get_disease(self, disease_name: str) -> Optional[DiseaseIntelligence]:
        """Get disease intelligence by name."""
        self.db.ensure_connected()

        with self.db.cursor() as cur:
            cur.execute("""
                SELECT * FROM disease_intelligence
                WHERE LOWER(disease_name) = LOWER(%s)
            """, (disease_name,))
            row = cur.fetchone()

            if not row:
                return None

            return self._row_to_model(dict(row))

    def get_disease_by_id(self, disease_id: int) -> Optional[DiseaseIntelligence]:
        """Get disease intelligence by ID."""
        self.db.ensure_connected()

        with self.db.cursor() as cur:
            cur.execute("SELECT * FROM disease_intelligence WHERE disease_id = %s", (disease_id,))
            row = cur.fetchone()

            if not row:
                return None

            return self._row_to_model(dict(row))

    def list_diseases(self, therapeutic_area: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all diseases with summary info."""
        self.db.ensure_connected()

        with self.db.cursor() as cur:
            query = """
                SELECT disease_id, disease_name, therapeutic_area,
                       total_patients, pct_treated, fail_1L_pct,
                       market_size_2L_usd, data_quality, updated_at
                FROM disease_intelligence
            """
            params = []

            if therapeutic_area:
                query += " WHERE therapeutic_area = %s"
                params.append(therapeutic_area)

            query += " ORDER BY disease_name"

            cur.execute(query, params)
            return [dict(row) for row in cur.fetchall()]

    def save_source(self, disease_id: int, source: DiseaseSource) -> int:
        """Save a literature source for a disease."""
        self.db.ensure_connected()

        with self.db.cursor() as cur:
            cur.execute("""
                INSERT INTO disease_intel_sources (
                    disease_id, pmid, doi, url, title, authors, journal, publication_year,
                    source_type, data_extracted, quality_tier,
                    abstract, full_text_available, relevant_excerpts
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING source_id
            """, (
                disease_id,
                source.pmid,
                source.doi,
                source.url,
                source.title,
                source.authors,
                source.journal,
                source.publication_year,
                source.source_type,
                json.dumps(source.data_extracted) if source.data_extracted else None,
                source.quality_tier,
                source.abstract,
                source.full_text_available,
                json.dumps(source.relevant_excerpts) if source.relevant_excerpts else None,
            ))
            source_id = cur.fetchone()["source_id"]
            self.db.commit()
            return source_id

    def get_sources(self, disease_id: int) -> List[DiseaseSource]:
        """Get all sources for a disease."""
        self.db.ensure_connected()

        with self.db.cursor() as cur:
            cur.execute("""
                SELECT * FROM disease_intel_sources
                WHERE disease_id = %s
                ORDER BY quality_tier, publication_year DESC
            """, (disease_id,))

            sources = []
            for row in cur.fetchall():
                row_dict = dict(row)
                sources.append(DiseaseSource(
                    pmid=row_dict.get("pmid"),
                    doi=row_dict.get("doi"),
                    url=row_dict.get("url"),
                    title=row_dict.get("title"),
                    authors=row_dict.get("authors"),
                    journal=row_dict.get("journal"),
                    publication_year=row_dict.get("publication_year"),
                    source_type=row_dict.get("source_type", "unknown"),
                    data_extracted=row_dict.get("data_extracted"),
                    quality_tier=row_dict.get("quality_tier"),
                    abstract=row_dict.get("abstract"),
                    full_text_available=row_dict.get("full_text_available", False),
                    relevant_excerpts=row_dict.get("relevant_excerpts"),
                ))
            return sources

    def save_treatment(
        self,
        disease_id: int,
        line_of_therapy: str,
        drug: TreatmentDrug,
    ) -> int:
        """Save a treatment drug for a disease."""
        self.db.ensure_connected()

        with self.db.cursor() as cur:
            cur.execute("""
                INSERT INTO disease_treatments (
                    disease_id, line_of_therapy, drug_name, generic_name,
                    drug_class, wac_monthly, wac_source, is_standard_of_care, notes
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING treatment_id
            """, (
                disease_id,
                line_of_therapy,
                drug.drug_name,
                drug.generic_name,
                drug.drug_class,
                drug.wac_monthly,
                drug.wac_source,
                drug.is_standard_of_care,
                drug.notes,
            ))
            treatment_id = cur.fetchone()["treatment_id"]
            self.db.commit()
            return treatment_id

    def delete_disease(self, disease_id: int) -> bool:
        """Delete a disease and all related data."""
        self.db.ensure_connected()

        with self.db.cursor() as cur:
            cur.execute("DELETE FROM disease_intelligence WHERE disease_id = %s", (disease_id,))
            deleted = cur.rowcount > 0
            self.db.commit()
            return deleted

    def get_pipeline_runs(self, disease_id: int) -> List[Dict[str, Any]]:
        """
        Get all pipeline runs for a disease.

        Args:
            disease_id: ID of the disease

        Returns:
            List of run dictionaries with run metadata and statistics
        """
        self.db.ensure_connected()

        with self.db.cursor() as cur:
            cur.execute("""
                SELECT
                    run_id,
                    disease_id,
                    disease_key,
                    run_timestamp,
                    run_type,
                    clinicaltrials_searched,
                    web_sources_searched,
                    drugs_found_total,
                    drugs_new,
                    drugs_updated,
                    status,
                    error_message,
                    created_at
                FROM disease_pipeline_runs
                WHERE disease_id = %s
                ORDER BY run_timestamp DESC
            """, (disease_id,))

            return [dict(row) for row in cur.fetchall()]

    def get_pipeline_sources(self, disease_id: int) -> List[Dict[str, Any]]:
        """
        Get all pipeline sources for a disease.

        Args:
            disease_id: ID of the disease

        Returns:
            List of source dictionaries with NCT IDs, URLs, etc.
        """
        self.db.ensure_connected()

        with self.db.cursor() as cur:
            cur.execute("""
                SELECT
                    source_id,
                    disease_id,
                    drug_id,
                    nct_id,
                    source_url,
                    source_type,
                    title,
                    publication_date,
                    content_summary,
                    extracted_data,
                    confidence_score,
                    verified,
                    created_at
                FROM disease_pipeline_sources
                WHERE disease_id = %s
                ORDER BY created_at DESC
            """, (disease_id,))

            return [dict(row) for row in cur.fetchall()]

    def get_drugs_for_disease(self, disease_name: str) -> List[Dict[str, Any]]:
        """
        Get all drugs associated with a disease from the drugs database.

        Args:
            disease_name: Name of the disease

        Returns:
            List of drug dictionaries with drug details
        """
        self.db.ensure_connected()

        with self.db.cursor() as cur:
            cur.execute("""
                SELECT
                    d.drug_id,
                    d.brand_name,
                    d.generic_name,
                    d.manufacturer,
                    d.drug_type,
                    d.mechanism_of_action,
                    d.highest_phase,
                    d.approval_status,
                    d.first_approval_date,
                    di.line_of_therapy,
                    di.approval_date as indication_approval_date,
                    CASE d.highest_phase
                        WHEN 'Approved' THEN 1
                        WHEN 'Phase 3' THEN 2
                        WHEN 'Phase 2' THEN 3
                        WHEN 'Phase 1' THEN 4
                        WHEN 'Preclinical' THEN 5
                        ELSE 6
                    END as phase_order
                FROM drugs d
                JOIN drug_indications di ON d.drug_id = di.drug_id
                JOIN diseases ds ON di.disease_id = ds.disease_id
                WHERE LOWER(ds.disease_name_standard) ILIKE LOWER(%s)
                   OR LOWER(ds.disease_name_standard) ILIKE LOWER(%s)
                ORDER BY phase_order, d.brand_name
            """, (f'%{disease_name}%', disease_name))

            return [dict(row) for row in cur.fetchall()]

    def get_all_pipeline_runs(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get all pipeline runs across all diseases (most recent first).

        Args:
            limit: Maximum number of runs to return

        Returns:
            List of run dictionaries including disease name
        """
        self.db.ensure_connected()

        with self.db.cursor() as cur:
            cur.execute("""
                SELECT
                    r.run_id,
                    r.disease_id,
                    r.disease_key,
                    di.disease_name,
                    di.therapeutic_area,
                    r.run_timestamp,
                    r.run_type,
                    r.clinicaltrials_searched,
                    r.web_sources_searched,
                    r.drugs_found_total,
                    r.drugs_new,
                    r.drugs_updated,
                    r.status,
                    r.error_message,
                    r.created_at
                FROM disease_pipeline_runs r
                JOIN disease_intelligence di ON r.disease_id = di.disease_id
                ORDER BY r.run_timestamp DESC
                LIMIT %s
            """, (limit,))

            return [dict(row) for row in cur.fetchall()]

    def _row_to_model(self, row: Dict[str, Any]) -> DiseaseIntelligence:
        """Convert database row to DiseaseIntelligence model."""
        # Parse prevalence estimates
        prevalence_estimates = []
        if row.get("prevalence_estimates"):
            est_data = row["prevalence_estimates"]
            if isinstance(est_data, str):
                est_data = json.loads(est_data)
            from .models import PrevalenceEstimate
            prevalence_estimates = [PrevalenceEstimate(**e) for e in est_data]

        # Parse prevalence
        prevalence = PrevalenceData(
            total_patients=row.get("total_patients"),
            adult_patients=row.get("adult_patients"),
            pediatric_patients=row.get("pediatric_patients"),
            prevalence_source=row.get("prevalence_source"),
            prevalence_year=row.get("prevalence_year"),
            source_estimates=prevalence_estimates,
            estimate_range=row.get("prevalence_range"),
            methodology_notes=row.get("prevalence_methodology"),
            confidence=row.get("prevalence_confidence"),
        )

        # Parse segmentation
        severity = None
        if row.get("severity_breakdown"):
            severity_data = row["severity_breakdown"]
            if isinstance(severity_data, str):
                severity_data = json.loads(severity_data)
            severity = SeverityBreakdown(**severity_data)

        subpopulations = []
        if row.get("subpopulations"):
            subpop_data = row["subpopulations"]
            if isinstance(subpop_data, str):
                subpop_data = json.loads(subpop_data)
            subpopulations = [Subpopulation(**s) for s in subpop_data]

        # Parse treatment estimates
        treatment_estimates = []
        if row.get("treatment_estimates"):
            te_data = row["treatment_estimates"]
            if isinstance(te_data, str):
                te_data = json.loads(te_data)
            treatment_estimates = [TreatmentEstimate(**e) for e in te_data]

        segmentation = PatientSegmentation(
            pct_diagnosed=float(row["pct_diagnosed"]) if row.get("pct_diagnosed") else None,
            pct_treated=float(row["pct_treated"]) if row.get("pct_treated") else None,
            severity=severity,
            subpopulations=subpopulations,
            treatment_estimates=treatment_estimates,
        )

        # Parse treatment paradigm
        treatment_paradigm = TreatmentParadigm()
        if row.get("treatment_paradigm"):
            tp_data = row["treatment_paradigm"]
            if isinstance(tp_data, str):
                tp_data = json.loads(tp_data)
            treatment_paradigm = TreatmentParadigm(**tp_data)

        # Parse failure rate estimates
        failure_rate_estimates = []
        if row.get("failure_rate_estimates"):
            est_data = row["failure_rate_estimates"]
            if isinstance(est_data, str):
                est_data = json.loads(est_data)
            from .models import FailureRateEstimate
            failure_rate_estimates = [FailureRateEstimate(**e) for e in est_data]

        # Parse failure rates (PostgreSQL lowercases column names)
        failure_rates = FailureRates(
            fail_1L_pct=float(row["fail_1l_pct"]) if row.get("fail_1l_pct") else None,
            fail_1L_reason=row.get("fail_1l_reason"),
            fail_2L_pct=float(row["fail_2l_pct"]) if row.get("fail_2l_pct") else None,
            fail_2L_reason=row.get("fail_2l_reason"),
            source_estimates=failure_rate_estimates,
            estimate_range=row.get("failure_rate_range"),
            methodology_notes=row.get("failure_rate_methodology"),
            confidence=row.get("failure_rate_confidence"),
        )

        # Parse market funnel (PostgreSQL lowercases column names)
        market_funnel = None
        if row.get("patients_treated") is not None:
            market_size = row.get("market_size_2l_usd")
            # Format market size for display
            market_formatted = None
            if market_size:
                if market_size >= 1_000_000_000:
                    market_formatted = f"${market_size / 1_000_000_000:.1f}B"
                elif market_size >= 1_000_000:
                    market_formatted = f"${market_size / 1_000_000:.0f}M"
                else:
                    market_formatted = f"${market_size:,}"

            market_funnel = MarketFunnel(
                total_patients=row.get("total_patients") or 0,
                patients_treated=row.get("patients_treated") or 0,
                patients_fail_1L=row.get("patients_fail_1l") or 0,
                patients_addressable_2L=row.get("patients_addressable_2l") or 0,
                market_size_2L_usd=market_size,
                market_size_2L_formatted=market_formatted,
            )

        # Parse sources
        sources = []
        if row.get("sources"):
            sources_data = row["sources"]
            if isinstance(sources_data, str):
                sources_data = json.loads(sources_data)
            sources = [DiseaseSource(**s) for s in sources_data]

        # Parse aliases
        aliases = []
        if row.get("disease_aliases"):
            aliases_data = row["disease_aliases"]
            if isinstance(aliases_data, str):
                aliases_data = json.loads(aliases_data)
            aliases = aliases_data

        return DiseaseIntelligence(
            disease_id=row.get("disease_id"),
            disease_name=row["disease_name"],
            disease_aliases=aliases,
            therapeutic_area=row.get("therapeutic_area"),
            prevalence=prevalence,
            segmentation=segmentation,
            treatment_paradigm=treatment_paradigm,
            failure_rates=failure_rates,
            market_funnel=market_funnel,
            sources=sources,
            data_quality=row.get("data_quality"),
            notes=row.get("notes"),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )
