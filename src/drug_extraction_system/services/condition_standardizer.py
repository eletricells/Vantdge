"""
Condition Standardization Service.

Normalizes disease/condition names from clinical trials using:
1. Exact match lookup in existing mappings
2. MeSH API for standardized medical terminology
3. Fuzzy string matching for similar names
4. Manual mapping rules for common variations
"""

import re
import logging
from typing import Optional, Dict, List, Tuple, Any
from difflib import SequenceMatcher
from ..database.connection import DatabaseConnection
from ..api_clients.mesh_client import MeSHClient

logger = logging.getLogger(__name__)


# Common condition name normalizations (pre-defined mappings)
CONDITION_NORMALIZATIONS = {
    # Psoriasis variants
    "psoriasis": "Plaque Psoriasis",
    "psoriasis (pso)": "Plaque Psoriasis",
    "plaque psoriasis": "Plaque Psoriasis",
    "chronic plaque psoriasis": "Plaque Psoriasis",
    "plaque-type psoriasis": "Plaque Psoriasis",
    "chronic plaque-type psoriasis": "Plaque Psoriasis",
    "moderate to severe plaque psoriasis": "Plaque Psoriasis",
    "moderate-to-severe plaque psoriasis": "Plaque Psoriasis",
    "moderate to severe chronic plaque psoriasis": "Plaque Psoriasis",
    "moderate to severe plaque-type psoriasis": "Plaque Psoriasis",
    "moderate to severe chronic plaque-type psoriasis": "Plaque Psoriasis",
    "plaque type psoriasis": "Plaque Psoriasis",
    "plaque type psorisis": "Plaque Psoriasis",  # Typo
    "chronic plaque type psoriasis": "Plaque Psoriasis",
    "psoriasis vulgaris": "Plaque Psoriasis",
    "psoriasis, plaque-type psoriasis": "Plaque Psoriasis",
    "pediatric plaque psoriasis": "Pediatric Plaque Psoriasis",
    "pustular psoriasis": "Pustular Psoriasis",
    "moderate to severe nail psoriasis": "Nail Psoriasis",
    
    # Psoriatic Arthritis
    "psoriatic arthritis": "Psoriatic Arthritis",
    "psoriatic arthritis (psa)": "Psoriatic Arthritis",
    "juvenile psoriatic arthritis": "Juvenile Psoriatic Arthritis",
    
    # Ankylosing Spondylitis
    "ankylosing spondylitis": "Ankylosing Spondylitis",
    "spondylitis, ankylosing": "Ankylosing Spondylitis",
    "ankylosing spondyloarthritis": "Ankylosing Spondylitis",
    
    # Axial Spondyloarthritis
    "axial spondyloarthritis": "Axial Spondyloarthritis",
    "non-radiographic axial spondyloarthritis": "Non-radiographic Axial Spondyloarthritis",
    
    # Hidradenitis Suppurativa
    "hidradenitis suppurativa": "Hidradenitis Suppurativa",
    "hidradenitis suppurativa (hs)": "Hidradenitis Suppurativa",
    
    # Rheumatoid Arthritis
    "rheumatoid arthritis": "Rheumatoid Arthritis",
    "juvenile idiopathic arthritis": "Juvenile Idiopathic Arthritis",
    
    # Uveitis
    "uveitis": "Uveitis",
    "non-infectious uveitis": "Non-infectious Uveitis",
    "posterior or panuveitis": "Uveitis",
    
    # PNH variants
    "paroxysmal nocturnal hemoglobinuria": "Paroxysmal Nocturnal Hemoglobinuria",
    "paroxysmal nocturnal hemoglobinuria (pnh)": "Paroxysmal Nocturnal Hemoglobinuria",
    "hemoglobinuria, paroxysmal": "Paroxysmal Nocturnal Hemoglobinuria",
    "paroxysmal nocturnal hemoglobinuria (pnh) with signs of active hemolysis": "Paroxysmal Nocturnal Hemoglobinuria",
    
    # IgA Nephropathy
    "iga nephropathy": "IgA Nephropathy",
    "immunoglobulin a nephropathy": "IgA Nephropathy",
    "glomerulonephritis, iga": "IgA Nephropathy",
    "primary iga nephropathy": "IgA Nephropathy",
    "primary immunoglobulin a nephropathy (igan)": "IgA Nephropathy",
    
    # C3 Glomerulopathy
    "c3 glomerulopathy": "C3 Glomerulopathy",
    "c3g": "C3 Glomerulopathy",
    "c3 glomerulopathy (c3g)": "C3 Glomerulopathy",
    
    # aHUS
    "atypical hemolytic uremic syndrome": "Atypical Hemolytic Uremic Syndrome",
    
    # Other
    "lupus nephritis": "Lupus Nephritis",

    # Systemic Lupus Erythematosus (SLE)
    "sle": "Systemic Lupus Erythematosus",
    "systemic lupus erythematosus": "Systemic Lupus Erythematosus",
    "systemic lupus erythematosus (sle)": "Systemic Lupus Erythematosus",
    "lupus": "Systemic Lupus Erythematosus",
    "lupus erythematosus": "Systemic Lupus Erythematosus",
    "systemic lupus": "Systemic Lupus Erythematosus",
    "active systemic lupus erythematosus": "Systemic Lupus Erythematosus",
    "moderate to severe sle": "Systemic Lupus Erythematosus",
    "moderate to severe systemic lupus erythematosus": "Systemic Lupus Erythematosus",

    "multiple sclerosis": "Multiple Sclerosis",
    "crohn's disease": "Crohn's Disease",
    "giant cell arteritis": "Giant Cell Arteritis",
    "giant cell arteritis (gca)": "Giant Cell Arteritis",
    "polymyalgia rheumatica": "Polymyalgia Rheumatica",
    "dry eye": "Dry Eye Disease",
    "healthy": "Healthy Volunteers",
    "healthy male subjects": "Healthy Volunteers",
    "type 1 diabetes mellitus": "Type 1 Diabetes Mellitus",
    "age-related macular degeneration": "Age-related Macular Degeneration",
    "generalized myasthenia gravis": "Myasthenia Gravis",
    "myasthenia gravis": "Myasthenia Gravis",
    "cold agglutinin disease (cad)": "Cold Agglutinin Disease",
    "immune thrombocytopenia (itp)": "Immune Thrombocytopenia",

    # Atopic Dermatitis
    "atopic dermatitis": "Atopic Dermatitis",
    "dermatitis, atopic": "Atopic Dermatitis",
    "atopic eczema": "Atopic Dermatitis",
    "eczema": "Atopic Dermatitis",
    "moderate to severe atopic dermatitis": "Atopic Dermatitis",

    # Thyroid conditions (for batoclimab)
    "thyroid eye disease": "Thyroid Eye Disease",
    "graves' ophthalmopathy": "Thyroid Eye Disease",
    "graves ophthalmopathy": "Thyroid Eye Disease",
    "graves' disease": "Graves' Disease",
    "graves disease": "Graves' Disease",

    # Neuromuscular (for batoclimab)
    "chronic inflammatory demyelinating polyneuropathy": "Chronic Inflammatory Demyelinating Polyneuropathy",
    "cidp": "Chronic Inflammatory Demyelinating Polyneuropathy",
    "chronic inflammatory demyelinating polyradiculoneuropathy": "Chronic Inflammatory Demyelinating Polyneuropathy",
}

# Therapeutic area mappings based on condition
THERAPEUTIC_AREAS = {
    # Dermatology
    "Plaque Psoriasis": "Dermatology",
    "Pediatric Plaque Psoriasis": "Dermatology",
    "Pustular Psoriasis": "Dermatology",
    "Nail Psoriasis": "Dermatology",
    "Hidradenitis Suppurativa": "Dermatology",
    "Atopic Dermatitis": "Dermatology",
    "Vitiligo": "Dermatology",
    "Alopecia Areata": "Dermatology",
    "Pemphigus Vulgaris": "Dermatology",
    "Bullous Pemphigoid": "Dermatology",

    # Rheumatology
    "Psoriatic Arthritis": "Rheumatology",
    "Juvenile Psoriatic Arthritis": "Rheumatology",
    "Ankylosing Spondylitis": "Rheumatology",
    "Axial Spondyloarthritis": "Rheumatology",
    "Non-radiographic Axial Spondyloarthritis": "Rheumatology",
    "Rheumatoid Arthritis": "Rheumatology",
    "Juvenile Idiopathic Arthritis": "Rheumatology",
    "Giant Cell Arteritis": "Rheumatology",
    "Polymyalgia Rheumatica": "Rheumatology",
    "Systemic Lupus Erythematosus": "Rheumatology",
    "Systemic Lupus Erythematosus (SLE)": "Rheumatology",
    "Sjogren Syndrome": "Rheumatology",
    "Sjogren Disease": "Rheumatology",
    "Sjogrens Syndrome": "Rheumatology",
    "Primary Sjogren's Syndrome": "Rheumatology",
    "Diffuse Cutaneous Systemic Sclerosis": "Rheumatology",
    "Systemic Sclerosis": "Rheumatology",
    "Scleroderma": "Rheumatology",
    "Dermatomyositis": "Rheumatology",
    "Polymyositis": "Rheumatology",
    "Vasculitis": "Rheumatology",
    "ANCA-associated Vasculitis": "Rheumatology",

    # Ophthalmology
    "Uveitis": "Ophthalmology",
    "Non-infectious Uveitis": "Ophthalmology",
    "Dry Eye Disease": "Ophthalmology",
    "Age-related Macular Degeneration": "Ophthalmology",
    "Thyroid Eye Disease": "Ophthalmology",
    "Diabetic Retinopathy": "Ophthalmology",
    "Diabetic Macular Edema": "Ophthalmology",

    # Hematology
    "Paroxysmal Nocturnal Hemoglobinuria": "Hematology",
    "Atypical Hemolytic Uremic Syndrome": "Hematology",
    "Cold Agglutinin Disease": "Hematology",
    "Immune Thrombocytopenia": "Hematology",
    "Primary Immune Thrombocytopenia": "Hematology",
    "Warm Autoimmune Hemolytic Anemia": "Hematology",
    "Thrombotic Thrombocytopenic Purpura": "Hematology",

    # Nephrology
    "IgA Nephropathy": "Nephrology",
    "C3 Glomerulopathy": "Nephrology",
    "Lupus Nephritis": "Nephrology",
    "Membranous Nephropathy": "Nephrology",
    "Focal Segmental Glomerulosclerosis": "Nephrology",
    "Chronic Kidney Disease": "Nephrology",

    # Neurology
    "Multiple Sclerosis": "Neurology",
    "Relapse Remitting Multiple Sclerosis": "Neurology",
    "Myasthenia Gravis": "Neurology",
    "Chronic Inflammatory Demyelinating Polyneuropathy": "Neurology",
    "Guillain-Barre Syndrome": "Neurology",
    "Neuromyelitis Optica": "Neurology",
    "Alzheimer's Disease": "Neurology",
    "Parkinson's Disease": "Neurology",

    # Gastroenterology
    "Crohn's Disease": "Gastroenterology",
    "Ulcerative Colitis": "Gastroenterology",
    "Inflammatory Bowel Disease": "Gastroenterology",
    "Celiac Disease": "Gastroenterology",
    "Primary Biliary Cholangitis": "Gastroenterology",
    "Autoimmune Hepatitis": "Gastroenterology",

    # Pulmonology
    "Idiopathic Pulmonary Fibrosis": "Pulmonology",
    "Asthma": "Pulmonology",
    "COPD": "Pulmonology",
    "Chronic Obstructive Pulmonary Disease": "Pulmonology",

    # Endocrinology
    "Type 1 Diabetes Mellitus": "Endocrinology",
    "Type 2 Diabetes Mellitus": "Endocrinology",
    "Graves' Disease": "Endocrinology",

    # Oncology
    "Non-Small Cell Lung Cancer": "Oncology",
    "Breast Cancer": "Oncology",
    "Melanoma": "Oncology",
    "Colorectal Cancer": "Oncology",

    # Other
    "Healthy Volunteers": "Clinical Pharmacology",
}


class ConditionStandardizer:
    """Service for standardizing condition/disease names."""

    def __init__(self, db: DatabaseConnection):
        """Initialize with database connection."""
        self.db = db
        self.mesh = MeSHClient()
        self._cache: Dict[str, Optional[Dict]] = {}
        logger.info("ConditionStandardizer initialized")

    def standardize(self, raw_name: str) -> Optional[Dict[str, Any]]:
        """
        Standardize a condition name.

        Args:
            raw_name: Raw condition name from clinical trial

        Returns:
            Dictionary with standardized info or None if not found
        """
        if not raw_name:
            return None

        # Normalize for lookup
        normalized = raw_name.strip().lower()

        # Check cache first
        if normalized in self._cache:
            return self._cache[normalized]

        # 1. Check predefined mappings (fastest)
        if normalized in CONDITION_NORMALIZATIONS:
            std_name = CONDITION_NORMALIZATIONS[normalized]
            result = self._create_result(
                raw_name, std_name,
                match_type="predefined",
                confidence=1.0
            )
            self._cache[normalized] = result
            return result

        # 2. Check database mappings
        db_result = self._lookup_db_mapping(normalized)
        if db_result:
            self._cache[normalized] = db_result
            return db_result

        # 3. Try MeSH lookup
        mesh_result = self._lookup_mesh(raw_name)
        if mesh_result and mesh_result.get("confidence", 0) >= 0.8:
            self._cache[normalized] = mesh_result
            return mesh_result

        # 4. Fuzzy match against known conditions
        fuzzy_result = self._fuzzy_match(normalized)
        if fuzzy_result:
            self._cache[normalized] = fuzzy_result
            return fuzzy_result

        # No match found - return raw name as-is
        result = self._create_result(
            raw_name, raw_name,
            match_type="unmatched",
            confidence=0.0
        )
        self._cache[normalized] = result
        return result

    def _create_result(
        self, raw_name: str, std_name: str,
        match_type: str = "exact",
        confidence: float = 1.0,
        mesh_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create standardized result dict."""
        return {
            "raw_name": raw_name,
            "standard_name": std_name,
            "mesh_id": mesh_id,
            "therapeutic_area": THERAPEUTIC_AREAS.get(std_name),
            "match_type": match_type,
            "confidence": confidence
        }

    def _lookup_db_mapping(self, normalized: str) -> Optional[Dict]:
        """Look up existing mapping in database."""
        result = self.db.execute("""
            SELECT sc.standard_name, sc.mesh_id, sc.therapeutic_area,
                   cm.match_type, cm.confidence
            FROM condition_mappings cm
            JOIN standardized_conditions sc ON cm.condition_id = sc.condition_id
            WHERE LOWER(cm.raw_name) = %s
        """, (normalized,))

        if result:
            row = result[0]
            return {
                "raw_name": normalized,
                "standard_name": row["standard_name"],
                "mesh_id": row["mesh_id"],
                "therapeutic_area": row["therapeutic_area"],
                "match_type": row["match_type"],
                "confidence": float(row["confidence"])
            }
        return None

    def _lookup_mesh(self, term: str) -> Optional[Dict]:
        """Look up term in MeSH."""
        try:
            results = self.mesh.search_term(term, limit=5)
            if results:
                # Find best match
                best = results[0]
                confidence = self._calculate_mesh_confidence(term, best["label"])

                if confidence >= 0.7:
                    return self._create_result(
                        term, best["label"],
                        match_type="mesh_lookup",
                        confidence=confidence,
                        mesh_id=best["mesh_id"]
                    )
        except Exception as e:
            logger.warning(f"MeSH lookup failed for '{term}': {e}")
        return None

    def _fuzzy_match(self, normalized: str) -> Optional[Dict]:
        """Find fuzzy match in predefined conditions."""
        best_match = None
        best_score = 0.0

        for known, std_name in CONDITION_NORMALIZATIONS.items():
            score = SequenceMatcher(None, normalized, known).ratio()
            if score > best_score and score >= 0.8:
                best_score = score
                best_match = std_name

        if best_match:
            return self._create_result(
                normalized, best_match,
                match_type="fuzzy",
                confidence=best_score
            )
        return None

    def _calculate_mesh_confidence(self, query: str, result: str) -> float:
        """Calculate confidence score for MeSH match."""
        q_lower = query.lower()
        r_lower = result.lower()

        # Exact match
        if q_lower == r_lower:
            return 1.0

        # Substring match
        if q_lower in r_lower or r_lower in q_lower:
            return 0.9

        # Sequence similarity
        return SequenceMatcher(None, q_lower, r_lower).ratio()

    def standardize_trial_conditions(self, trial_id: int, raw_conditions: List[str]) -> List[Dict]:
        """
        Standardize conditions for a trial and store mappings.

        Args:
            trial_id: Database trial ID
            raw_conditions: List of raw condition names

        Returns:
            List of standardization results
        """
        results = []

        for raw_name in raw_conditions:
            std_result = self.standardize(raw_name)
            if std_result:
                # Ensure condition exists in database
                condition_id = self._ensure_condition_exists(std_result)
                if condition_id:
                    # Ensure mapping exists
                    self._ensure_mapping_exists(raw_name, condition_id, std_result)
                    # Link trial to condition
                    self._link_trial_condition(trial_id, condition_id)
                    std_result["condition_id"] = condition_id

                results.append(std_result)

        return results

    def _ensure_condition_exists(self, std_result: Dict) -> Optional[int]:
        """Ensure standardized condition exists in database, return ID."""
        std_name = std_result["standard_name"]

        # Check if exists
        result = self.db.execute(
            "SELECT condition_id FROM standardized_conditions WHERE standard_name = %s",
            (std_name,)
        )

        if result:
            return result[0]["condition_id"]

        # Insert new condition
        result = self.db.execute("""
            INSERT INTO standardized_conditions (standard_name, mesh_id, therapeutic_area)
            VALUES (%s, %s, %s)
            ON CONFLICT (standard_name) DO UPDATE SET updated_at = NOW()
            RETURNING condition_id
        """, (std_name, std_result.get("mesh_id"), std_result.get("therapeutic_area")))

        self.db.commit()
        return result[0]["condition_id"] if result else None

    def _ensure_mapping_exists(self, raw_name: str, condition_id: int, std_result: Dict):
        """Ensure mapping from raw name to condition exists."""
        self.db.execute("""
            INSERT INTO condition_mappings (raw_name, condition_id, match_type, confidence)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (raw_name) DO NOTHING
        """, (raw_name, condition_id, std_result["match_type"], std_result["confidence"]))
        self.db.commit()

    def _link_trial_condition(self, trial_id: int, condition_id: int):
        """Link a trial to a condition."""
        self.db.execute("""
            INSERT INTO trial_conditions (trial_id, condition_id)
            VALUES (%s, %s)
            ON CONFLICT (trial_id, condition_id) DO NOTHING
        """, (trial_id, condition_id))
        self.db.commit()

    def process_all_trials(self, drug_name: Optional[str] = None) -> Dict[str, int]:
        """
        Process all trials and standardize their conditions.

        Args:
            drug_name: Optional drug name filter

        Returns:
            Statistics dict
        """
        # Build query
        if drug_name:
            query = """
                SELECT t.trial_id, t.conditions
                FROM drug_clinical_trials t
                JOIN drugs d ON t.drug_id = d.drug_id
                WHERE d.generic_name ILIKE %s
            """
            trials = self.db.execute(query, (f"%{drug_name}%",))
        else:
            trials = self.db.execute(
                "SELECT trial_id, conditions FROM drug_clinical_trials"
            )

        stats = {"trials_processed": 0, "conditions_mapped": 0, "unique_conditions": set()}

        for trial in trials:
            trial_id = trial["trial_id"]
            raw_conditions = trial["conditions"] or []

            results = self.standardize_trial_conditions(trial_id, raw_conditions)
            stats["trials_processed"] += 1
            stats["conditions_mapped"] += len(results)

            for r in results:
                stats["unique_conditions"].add(r["standard_name"])

        stats["unique_conditions"] = len(stats["unique_conditions"])
        return stats

