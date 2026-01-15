"""
Centralized SQL queries for drug database.

All SQL queries are defined here for easier maintenance and review.
"""


class DrugQueries:
    """SQL queries for drugs table."""
    
    GET_BY_ID = "SELECT * FROM drugs WHERE drug_id = %s"
    
    GET_BY_KEY = "SELECT * FROM drugs WHERE drug_key = %s"
    
    GET_BY_BRAND_NAME = "SELECT * FROM drugs WHERE brand_name = %s"
    
    GET_BY_BRAND_AND_MANUFACTURER = """
        SELECT * FROM drugs 
        WHERE brand_name = %s AND manufacturer = %s
    """
    
    GET_BY_GENERIC_NAME = """
        SELECT * FROM drugs 
        WHERE generic_name ILIKE %s
        LIMIT 1
    """
    
    SEARCH = """
        SELECT * FROM drugs
        WHERE (brand_name ILIKE %s OR generic_name ILIKE %s)
        {filters}
        LIMIT %s
    """
    
    INSERT = """
        INSERT INTO drugs (
            brand_name, generic_name, manufacturer, drug_type,
            mechanism_of_action, approval_status, highest_phase,
            dailymed_setid, first_approval_date, is_combination, 
            combination_components, drug_key, target, moa_category,
            development_code
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING drug_id
    """
    
    UPDATE = """
        UPDATE drugs SET
            brand_name = COALESCE(%s, brand_name),
            generic_name = COALESCE(%s, generic_name),
            manufacturer = COALESCE(%s, manufacturer),
            drug_type = COALESCE(%s, drug_type),
            mechanism_of_action = COALESCE(%s, mechanism_of_action),
            approval_status = COALESCE(%s, approval_status),
            highest_phase = COALESCE(%s, highest_phase),
            dailymed_setid = COALESCE(%s, dailymed_setid),
            first_approval_date = COALESCE(%s, first_approval_date),
            updated_at = CURRENT_TIMESTAMP
        WHERE drug_id = %s
    """
    
    DELETE_RELATED = """
        DELETE FROM {table} WHERE drug_id = %s
    """


class DiseaseQueries:
    """SQL queries for diseases table."""
    
    GET_BY_ID = "SELECT * FROM diseases WHERE disease_id = %s"
    
    GET_BY_NAME = "SELECT * FROM diseases WHERE disease_name_standard = %s"
    
    GET_BY_ALIAS = """
        SELECT * FROM diseases
        WHERE disease_aliases @> %s::jsonb
    """
    
    INSERT = """
        INSERT INTO diseases (disease_name_standard, disease_aliases, icd10_codes, therapeutic_area)
        VALUES (%s, %s, %s, %s)
        RETURNING disease_id
    """


class IndicationQueries:
    """SQL queries for drug_indications table."""

    # Note: drug_indications stores disease_name directly, not disease_id
    GET_BY_DRUG = """
        SELECT *
        FROM drug_indications
        WHERE drug_id = %s
        ORDER BY approval_date DESC NULLS LAST
    """

    GET_BY_DISEASE_NAME = """
        SELECT di.*, dr.brand_name, dr.generic_name
        FROM drug_indications di
        JOIN drugs dr ON di.drug_id = dr.drug_id
        WHERE di.disease_name ILIKE %s
    """

    # Schema uses disease_name directly, not disease_id
    INSERT = """
        INSERT INTO drug_indications (
            drug_id, disease_name, mesh_id, population, severity,
            line_of_therapy, combination_therapy, approval_status,
            approval_date, special_conditions, raw_source_text,
            confidence_score, data_source
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING indication_id
    """

    # Upsert version for when we know the drug+disease combo
    UPSERT = """
        INSERT INTO drug_indications (
            drug_id, disease_name, mesh_id, population, severity,
            line_of_therapy, combination_therapy, approval_status,
            approval_date, special_conditions, raw_source_text,
            confidence_score, data_source
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (drug_id, disease_name, line_of_therapy)
        WHERE disease_name IS NOT NULL
        DO UPDATE SET
            approval_status = EXCLUDED.approval_status,
            approval_date = EXCLUDED.approval_date,
            severity = EXCLUDED.severity,
            population = EXCLUDED.population,
            data_source = EXCLUDED.data_source,
            updated_at = CURRENT_TIMESTAMP
        RETURNING indication_id
    """


class DosingQueries:
    """SQL queries for drug_dosing_regimens table."""

    GET_BY_DRUG = """
        SELECT *
        FROM drug_dosing_regimens
        WHERE drug_id = %s
        ORDER BY sequence_order
    """

    GET_BY_DRUG_AND_INDICATION = """
        SELECT *
        FROM drug_dosing_regimens
        WHERE drug_id = %s AND indication_id = %s
        ORDER BY sequence_order
    """

    INSERT = """
        INSERT INTO drug_dosing_regimens (
            drug_id, indication_id, regimen_phase, dose_amount, dose_unit,
            frequency_standard, frequency_raw, route_standard, route_raw,
            duration_weeks, weight_based, sequence_order, dosing_notes, data_source
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING dosing_id
    """


class MetadataQueries:
    """SQL queries for drug_metadata table."""
    
    GET_BY_DRUG = "SELECT * FROM drug_metadata WHERE drug_id = %s"
    
    UPSERT = """
        INSERT INTO drug_metadata (
            drug_id, orphan_designation, breakthrough_therapy, fast_track,
            has_black_box_warning, safety_notes
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (drug_id)
        DO UPDATE SET
            orphan_designation = EXCLUDED.orphan_designation,
            breakthrough_therapy = EXCLUDED.breakthrough_therapy,
            fast_track = EXCLUDED.fast_track,
            has_black_box_warning = EXCLUDED.has_black_box_warning,
            safety_notes = EXCLUDED.safety_notes,
            updated_at = CURRENT_TIMESTAMP
    """

