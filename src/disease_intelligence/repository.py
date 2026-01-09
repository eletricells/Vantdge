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

            if existing:
                # Update existing
                disease_id = existing["disease_id"]
                cur.execute("""
                    UPDATE disease_intelligence SET
                        disease_aliases = %s,
                        therapeutic_area = %s,
                        total_patients = %s,
                        adult_patients = %s,
                        pediatric_patients = %s,
                        prevalence_source = %s,
                        prevalence_year = %s,
                        pct_diagnosed = %s,
                        pct_treated = %s,
                        severity_breakdown = %s,
                        subpopulations = %s,
                        treatment_paradigm = %s,
                        fail_1L_pct = %s,
                        fail_1L_reason = %s,
                        fail_2L_pct = %s,
                        fail_2L_reason = %s,
                        patients_treated = %s,
                        patients_fail_1L = %s,
                        patients_addressable_2L = %s,
                        market_size_2L_usd = %s,
                        data_quality = %s,
                        sources = %s,
                        notes = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE disease_id = %s
                """, (
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
                        data_quality, sources, notes
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
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

    def _row_to_model(self, row: Dict[str, Any]) -> DiseaseIntelligence:
        """Convert database row to DiseaseIntelligence model."""
        # Parse prevalence
        prevalence = PrevalenceData(
            total_patients=row.get("total_patients"),
            adult_patients=row.get("adult_patients"),
            pediatric_patients=row.get("pediatric_patients"),
            prevalence_source=row.get("prevalence_source"),
            prevalence_year=row.get("prevalence_year"),
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

        segmentation = PatientSegmentation(
            pct_diagnosed=float(row["pct_diagnosed"]) if row.get("pct_diagnosed") else None,
            pct_treated=float(row["pct_treated"]) if row.get("pct_treated") else None,
            severity=severity,
            subpopulations=subpopulations,
        )

        # Parse treatment paradigm
        treatment_paradigm = TreatmentParadigm()
        if row.get("treatment_paradigm"):
            tp_data = row["treatment_paradigm"]
            if isinstance(tp_data, str):
                tp_data = json.loads(tp_data)
            treatment_paradigm = TreatmentParadigm(**tp_data)

        # Parse failure rates (PostgreSQL lowercases column names)
        failure_rates = FailureRates(
            fail_1L_pct=float(row["fail_1l_pct"]) if row.get("fail_1l_pct") else None,
            fail_1L_reason=row.get("fail_1l_reason"),
            fail_2L_pct=float(row["fail_2l_pct"]) if row.get("fail_2l_pct") else None,
            fail_2L_reason=row.get("fail_2l_reason"),
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
