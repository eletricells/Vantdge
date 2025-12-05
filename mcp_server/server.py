"""
Vantdge MCP Database Server

Provides database access for proprietary data including:
- Historical deals
- Expert annotations
- Target biology knowledge
- Disease knowledge
- Competitive intelligence
"""
import logging
from typing import List, Dict, Any, Optional
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError


logger = logging.getLogger(__name__)


class VantdgeDatabaseServer:
    """
    MCP-compatible database server for proprietary data.

    Provides safe, query-based access to internal knowledge bases.
    """

    def __init__(self, database_url: str):
        """
        Initialize database server.

        Args:
            database_url: SQLAlchemy database URL (e.g., postgresql://user:pass@localhost/dbname)
        """
        self.database_url = database_url
        self.engine = create_engine(database_url, echo=False)
        self.SessionLocal = sessionmaker(bind=self.engine)
        logger.info(f"VantdgeDatabaseServer initialized")

    def query_similar_deals(
        self,
        target: Optional[str] = None,
        indication: Optional[str] = None,
        phase: Optional[str] = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Query historical deals similar to given criteria.

        Args:
            target: Drug or target name
            indication: Therapeutic indication
            phase: Development phase
            limit: Maximum number of results

        Returns:
            List of similar deals with outcomes and rationale
        """
        try:
            with self.SessionLocal() as session:
                query = """
                    SELECT
                        deal_name,
                        target_company,
                        drug_name,
                        target_biology,
                        indication,
                        phase,
                        deal_type,
                        total_deal_value_usd,
                        upfront_payment_usd,
                        probability_of_success,
                        outcome,
                        deal_rationale,
                        key_strengths,
                        key_risks,
                        actual_peak_sales_usd
                    FROM historical_deals
                    WHERE 1=1
                """
                params = {}

                if indication:
                    query += " AND (indication ILIKE :indication OR indication ILIKE :indication_pattern)"
                    params['indication'] = indication
                    params['indication_pattern'] = f'%{indication}%'

                if target:
                    query += " AND (drug_name ILIKE :target OR target_biology ILIKE :target)"
                    params['target'] = f'%{target}%'

                if phase:
                    query += " AND phase ILIKE :phase"
                    params['phase'] = f'%{phase}%'

                query += f" ORDER BY announcement_date DESC LIMIT :limit"
                params['limit'] = limit

                result = session.execute(text(query), params)
                rows = result.fetchall()

                return [dict(row._mapping) for row in rows]

        except SQLAlchemyError as e:
            logger.error(f"Database query failed: {str(e)}")
            return []

    def query_expert_annotations(
        self,
        target: Optional[str] = None,
        drug: Optional[str] = None,
        indication: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Query expert annotations and internal insights.

        Args:
            target: Target name
            drug: Drug name
            indication: Therapeutic indication
            limit: Maximum number of results

        Returns:
            List of expert annotations with insights and concerns
        """
        try:
            with self.SessionLocal() as session:
                query = """
                    SELECT
                        target_name,
                        drug_name,
                        indication,
                        expert_name,
                        expert_role,
                        confidence_level,
                        annotation_type,
                        notes,
                        key_insights,
                        concerns,
                        annotation_date
                    FROM expert_annotations
                    WHERE 1=1
                """
                params = {}

                if target:
                    query += " AND target_name ILIKE :target"
                    params['target'] = f'%{target}%'

                if drug:
                    query += " AND drug_name ILIKE :drug"
                    params['drug'] = f'%{drug}%'

                if indication:
                    query += " AND indication ILIKE :indication"
                    params['indication'] = f'%{indication}%'

                query += f" ORDER BY annotation_date DESC LIMIT :limit"
                params['limit'] = limit

                result = session.execute(text(query), params)
                rows = result.fetchall()

                return [dict(row._mapping) for row in rows]

        except SQLAlchemyError as e:
            logger.error(f"Database query failed: {str(e)}")
            return []

    def query_target_biology_kb(
        self,
        target: str
    ) -> Optional[Dict[str, Any]]:
        """
        Query internal target biology knowledge base.

        Args:
            target: Target name

        Returns:
            Target biology knowledge or None
        """
        try:
            with self.SessionLocal() as session:
                query = """
                    SELECT
                        target_name,
                        target_type,
                        genetic_evidence_strength,
                        preclinical_validation_strength,
                        druggability_score,
                        safety_risk_level,
                        strategic_priority,
                        portfolio_fit_score,
                        competitive_landscape_assessment,
                        internal_notes,
                        key_papers,
                        failed_programs,
                        last_reviewed_date
                    FROM target_biology_kb
                    WHERE target_name ILIKE :target
                    LIMIT 1
                """

                result = session.execute(text(query), {'target': f'%{target}%'})
                row = result.fetchone()

                if row:
                    return dict(row._mapping)
                return None

        except SQLAlchemyError as e:
            logger.error(f"Database query failed: {str(e)}")
            return None

    def query_disease_kb(
        self,
        disease: str
    ) -> Optional[Dict[str, Any]]:
        """
        Query internal disease knowledge base.

        Args:
            disease: Disease name

        Returns:
            Disease knowledge or None
        """
        try:
            with self.SessionLocal() as session:
                query = """
                    SELECT
                        disease_name,
                        icd_codes,
                        us_prevalence,
                        global_prevalence,
                        market_size_usd,
                        market_growth_rate,
                        strategic_priority,
                        unmet_need_severity,
                        competitive_intensity,
                        internal_expertise_level,
                        portfolio_assets_count,
                        internal_notes,
                        key_kols,
                        patient_advocacy_groups,
                        last_reviewed_date
                    FROM disease_kb
                    WHERE disease_name ILIKE :disease
                    LIMIT 1
                """

                result = session.execute(text(query), {'disease': f'%{disease}%'})
                row = result.fetchone()

                if row:
                    return dict(row._mapping)
                return None

        except SQLAlchemyError as e:
            logger.error(f"Database query failed: {str(e)}")
            return None

    def query_competitive_intelligence(
        self,
        competitor: Optional[str] = None,
        drug: Optional[str] = None,
        target: Optional[str] = None,
        indication: Optional[str] = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Query competitive intelligence database.
        """
        try:
            with self.SessionLocal() as session:
                query = """
                    SELECT
                        competitor_name,
                        drug_name,
                        target_biology,
                        indication,
                        phase,
                        latest_clinical_data,
                        safety_signals,
                        efficacy_signals,
                        competitive_threat_level,
                        differentiation_vs_our_assets,
                        last_updated
                    FROM competitive_intelligence
                    WHERE 1=1
                """
                params = {}

                if competitor:
                    query += " AND competitor_name ILIKE :competitor"
                    params['competitor'] = f'%{competitor}%'

                if drug:
                    query += " AND drug_name ILIKE :drug"
                    params['drug'] = f'%{drug}%'

                if target:
                    query += " AND target_biology ILIKE :target"
                    params['target'] = f'%{target}%'

                if indication:
                    query += " AND indication ILIKE :indication"
                    params['indication'] = f'%{indication}%'

                query += f" ORDER BY last_updated DESC LIMIT :limit"
                params['limit'] = limit

                result = session.execute(text(query), params)
                rows = result.fetchall()

                return [dict(row._mapping) for row in rows]

        except SQLAlchemyError as e:
            logger.error(f"Database query failed: {str(e)}")
            return []

    def close(self):
        """Close database connections"""
        self.engine.dispose()
        logger.info("VantdgeDatabaseServer connections closed")


# Backwards compatibility alias
BiopharmaDatabaseServer = VantdgeDatabaseServer
