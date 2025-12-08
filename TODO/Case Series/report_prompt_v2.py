"""
LLM Prompt Template for Drug Repurposing Case Series Report Generation (v2)

REVISED: Focuses on factual analysis without recommendations. Emphasizes
score justification with specific efficacy/safety data and concordance analysis.

Usage:
    from report_prompt_v2 import generate_report_prompt, format_data_for_prompt
    
    # Load your Excel data
    data = format_data_for_prompt('iptacopan_report.xlsx')
    
    # Generate the prompt
    prompt = generate_report_prompt(data)
    
    # Send to LLM (Claude, GPT-4, etc.)
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}]
    )
"""

import pandas as pd
from typing import Dict, Any
from pathlib import Path


def format_data_for_prompt(excel_path: str) -> Dict[str, Any]:
    """
    Load and format Excel analysis data for the report prompt.
    
    Returns a dictionary with all relevant data formatted as strings
    suitable for inclusion in an LLM prompt.
    """
    xlsx = pd.ExcelFile(excel_path)
    
    # Load all sheets
    analysis_df = pd.read_excel(xlsx, sheet_name='Analysis Summary')
    drug_df = pd.read_excel(xlsx, sheet_name='Drug Summary')
    opportunities_df = pd.read_excel(xlsx, sheet_name='Opportunities')
    market_df = pd.read_excel(xlsx, sheet_name='Market Intelligence')
    efficacy_df = pd.read_excel(xlsx, sheet_name='Efficacy Endpoints')
    safety_df = pd.read_excel(xlsx, sheet_name='Safety Endpoints')
    
    # Extract drug info
    drug_info = drug_df.iloc[0].to_dict() if len(drug_df) > 0 else {}
    
    # Format efficacy data more comprehensively
    efficacy_detail = efficacy_df[[
        'Disease', 'PMID', 'Endpoint Name', 'Endpoint Category',
        'Baseline Value', 'Final Value', 'Change from Baseline', 'Percent Change',
        'Response Rate (%)', 'Timepoint', 'Notes'
    ]].copy()
    efficacy_detail = efficacy_detail.fillna('')
    
    # Format safety data more comprehensively  
    safety_detail = safety_df[[
        'Disease', 'PMID', 'Event Name', 'Event Category', 'Is Serious (SAE)',
        'Patients Affected (n)', 'Incidence (%)', 'Related to Drug', 'Outcome', 'Notes'
    ]].copy()
    safety_detail = safety_detail.fillna('')
    
    # Format as readable strings
    data = {
        'drug_name': drug_info.get('Drug', 'Unknown'),
        'generic_name': drug_info.get('Generic Name', ''),
        'mechanism': drug_info.get('Mechanism', ''),
        'approved_indications': drug_info.get('Approved Indications', ''),
        'papers_screened': drug_info.get('Papers Screened', 0),
        'opportunities_found': drug_info.get('Opportunities Found', 0),
        'analysis_date': str(drug_info.get('Analysis Date', '')),
        
        # Summary statistics
        'n_indications': len(analysis_df),
        'total_patients': analysis_df['Total Patients'].sum(),
        'total_studies': analysis_df['# Studies'].sum(),
        
        # Top opportunities
        'top_opportunities': analysis_df.nlargest(5, 'Overall Score (avg)').to_dict('records'),
        
        # Full data as formatted strings
        'analysis_summary_table': analysis_df.to_markdown(index=False),
        
        # Detailed opportunities with scores breakdown
        'opportunities_table': opportunities_df[[
            'Disease (Standardized)', 'N Patients', 'Primary Endpoint', 'Endpoint Result',
            'Responders (%)', 'Time to Response', 'Duration of Response',
            'Clinical Score', 'Evidence Score', 'Market Score', 'Overall Priority',
            'Response Rate Score (Quality-Weighted)', 'Safety Score', 'Organ Domain Score',
            '# Efficacy Endpoints Scored', 'Efficacy Concordance',
            'Safety Summary', 'Key Findings', 'PMID'
        ]].to_markdown(index=False),
        
        'market_intelligence_table': market_df[[
            'Disease', 'US Prevalence', 'US Incidence', 'Patient Population',
            'Approved Treatments (Count)', 'Approved Drug Names',
            'Pipeline Therapies (Count)', 'Pipeline Details',
            'Unmet Need', 'Unmet Need Description',
            'TAM (Total Addressable Market)', 'Competitive Landscape'
        ]].to_markdown(index=False),
        
        # Detailed efficacy endpoints
        'efficacy_endpoints_table': efficacy_detail.to_markdown(index=False),
        
        # Detailed safety data
        'safety_endpoints_table': safety_detail.to_markdown(index=False),
        
        # Raw dataframes for additional processing
        '_analysis_df': analysis_df,
        '_opportunities_df': opportunities_df,
        '_market_df': market_df,
        '_efficacy_df': efficacy_df,
        '_safety_df': safety_df,
    }
    
    return data


# =============================================================================
# THE PROMPT TEMPLATE (v2 - Analysis-focused, no recommendations)
# =============================================================================

REPORT_PROMPT_TEMPLATE = '''
You are a pharmaceutical analyst creating a factual, data-driven report on drug repurposing opportunities identified through case series analysis. Your role is to **analyze and synthesize the data objectively** - not to make strategic recommendations or tell the reader what to do.

## YOUR TASK

Generate a comprehensive analytical report that:
1. Presents the findings factually and objectively
2. Explains how each score was derived by pointing to specific data
3. Analyzes concordance across studies, endpoints, and diseases
4. Highlights patterns, consistencies, and inconsistencies in the data
5. Acknowledges limitations and uncertainties
6. Lets the reader draw their own conclusions

**Do NOT:**
- Make recommendations (e.g., "pursue this indication", "deprioritize this")
- Suggest specific actions or next steps
- Tell the reader what they "should" do
- Speculate beyond what the data supports

---

## SCORING METHODOLOGY REFERENCE

When explaining scores, reference this methodology:

**Overall Priority Score (1-10)** = Clinical Signal (50%) + Evidence Quality (25%) + Market Opportunity (25%)

**Clinical Signal Score** comprises:
- **Response Rate Score (40%)**: Quality-weighted across all endpoints
  - Each endpoint scored 1-10 based on response % or % change from baseline
  - Weighted by endpoint category: Primary (1.0x), Secondary (0.6x), Exploratory (0.3x)
  - Weighted by endpoint quality: Validated instruments (1.0x) vs ad-hoc measures (0.4x)
  - Concordance multiplier applied (0.85-1.15x) based on agreement across endpoints
  - Final = 70% weighted average + 30% best single endpoint (prevents dilution)
- **Safety Score (40%)**: Based on AE frequency, severity, and relationship to drug
- **Organ Domain Score (20%)**: Breadth of organ systems showing improvement

**Evidence Quality Score** comprises:
- **Sample Size (35%)**: N≥20=10, N≥15=9, N≥10=8, N≥5=6, N≥3=4, N≥2=2, N=1=1
- **Publication Venue (25%)**: Journal quality and peer review status
- **Response Durability (25%)**: Length of follow-up and sustained response
- **Extraction Completeness (15%)**: How much data could be extracted from the paper

**Market Opportunity Score** comprises:
- **Competitive Landscape (33%)**: Number of approved and pipeline competitors
- **Market Size (33%)**: Total addressable market estimate
- **Unmet Need (33%)**: Adequacy of current treatment options

**Concordance Multiplier**:
- ≥90% of endpoints agree: 1.15x bonus
- ≥75% agree: 1.10x
- ≥60% agree: 1.00x (neutral)
- ≥40% agree: 0.90x penalty
- <40% agree: 0.85x penalty

**Evidence Confidence Levels** (disease-level aggregation):
- Moderate: ≥3 studies, ≥20 patients, consistent results
- Low: ≥2 studies, ≥10 patients
- Very Low: Limited data, single studies, or high heterogeneity

---

## DRUG INFORMATION

**Drug Name**: {drug_name}
**Generic Name**: {generic_name}
**Mechanism of Action**: {mechanism}
**Current Approved Indications**: {approved_indications}
**Analysis Date**: {analysis_date}

---

## ANALYSIS SCOPE

- **Publications Screened**: {papers_screened}
- **Repurposing Opportunities Identified**: {opportunities_found}
- **Unique Indications**: {n_indications}
- **Total Patients Across Studies**: {total_patients}
- **Total Studies**: {total_studies}

---

## DISEASE-LEVEL SUMMARY

{analysis_summary_table}

---

## INDIVIDUAL STUDY DETAILS WITH SCORE BREAKDOWN

{opportunities_table}

---

## DETAILED EFFICACY ENDPOINTS

{efficacy_endpoints_table}

---

## DETAILED SAFETY DATA

{safety_endpoints_table}

---

## MARKET INTELLIGENCE

{market_intelligence_table}

---

## REPORT STRUCTURE

Generate a report with the following sections:

### 1. EXECUTIVE SUMMARY
- Summarize the scope of the analysis (drug, number of indications, total evidence base)
- State the range of priority scores observed and what drove the variation
- Highlight the key patterns observed across indications
- State the overall evidence confidence level and primary limitations
- **Do not make recommendations - just summarize the findings**

### 2. MECHANISM AND BIOLOGICAL RATIONALE
- Explain {drug_name}'s mechanism of action
- Describe the biological connection between the approved indications and the new opportunities identified
- Note which disease mechanisms are most closely aligned with the drug's MOA
- This section provides context for why these indications appeared in the analysis

### 3. INDICATION-BY-INDICATION ANALYSIS

For each indication (ordered by Overall Score), provide:

#### [Indication Name] - Overall Score: X.X

**Score Derivation:**
- Clinical Score (X.X): Break down the response rate score, safety score, and organ domain score
  - Cite specific endpoints and their results that drove the response rate score
  - Explain the concordance multiplier applied and why (how many endpoints agreed/disagreed)
  - Note the safety score basis with specific AEs observed
- Evidence Score (X.X): Explain based on sample size (N=X), publication quality, follow-up duration
- Market Score (X.X): Explain based on competitor count, TAM, unmet need assessment

**Efficacy Data:**
- List the specific endpoints measured with baseline → final values
- Note which endpoints showed improvement, stability, or worsening
- Calculate and state the concordance rate across endpoints
- Compare results across studies if multiple exist for this indication

**Safety Data:**
- List specific adverse events reported
- Note frequency, severity (SAE vs AE), and relationship to drug
- Identify any concerning signals or notably clean profiles

**Cross-Study Consistency** (if multiple studies):
- Compare response rates across studies
- Note any heterogeneity in patient populations or outcomes
- State the consistency classification (High/Moderate/Low) and basis

**Evidence Gaps:**
- What data is missing or limited?
- What would strengthen or weaken confidence in these findings?

### 4. CROSS-INDICATION CONCORDANCE ANALYSIS

This section analyzes patterns across all indications:

**Endpoint Concordance:**
- Which endpoint types (e.g., hemoglobin, LDH, proteinuria) showed consistent improvement across indications?
- Were there any endpoints that showed mixed results?
- What does this suggest about the drug's mechanism?

**Disease Mechanism Patterns:**
- Group indications by underlying mechanism (e.g., complement-mediated hemolysis, complement-mediated kidney injury)
- Analyze whether response patterns correlate with mechanistic similarity

**Response Rate Patterns:**
- Compare pooled response rates across indications
- Identify any outliers (unusually high or low responses)
- Analyze whether response correlates with sample size, disease severity, or other factors

**Safety Pattern Analysis:**
- Which AEs appeared across multiple indications?
- Were there any indication-specific safety signals?
- How does the safety profile compare to the known profile from approved indications?

### 5. EVIDENCE QUALITY ASSESSMENT

**Overall Evidence Base Characterization:**
- Total patients, studies, and publications
- Distribution of evidence levels (case series vs case reports)
- Proportion with full-text vs abstract-only extraction

**Sample Size Analysis:**
- Distribution of sample sizes across studies
- Impact of small samples on score reliability
- Which indications have the most vs least evidence

**Methodological Limitations:**
- Case series/case report limitations (no control group, selection bias, publication bias)
- Data extraction limitations (what couldn't be extracted)
- Scoring system limitations (what the scores can and cannot tell you)

**Confidence Assessment by Indication:**
- Rank indications by evidence confidence
- Explain what drives confidence differences

### 6. COMPETITIVE LANDSCAPE ANALYSIS

**By Indication:**
- Number of approved competitors for each indication
- Number of pipeline therapies for each indication
- Key differentiating factors (mechanism, administration, efficacy benchmarks)

**Comparative Positioning:**
- How do the observed efficacy signals compare to approved therapies (where data exists)?
- Where does {drug_name} potentially differentiate (mechanism, convenience, safety)?

**Market Context:**
- TAM estimates by indication with methodology notes
- Unmet need characterization by indication

### 7. LIMITATIONS AND UNCERTAINTIES

**Data Limitations:**
- Publication bias (negative results rarely published)
- Small sample sizes and statistical uncertainty
- Heterogeneity in patient populations and outcome measures
- Missing data and extraction limitations

**Scoring Limitations:**
- What the scores capture vs what they miss
- Sensitivity of scores to individual data points
- Potential for scores to over- or under-weight certain factors

**Analytical Limitations:**
- Cross-study comparisons without standardized protocols
- Inability to assess causation from observational data
- Market estimates based on secondary sources

**What Would Change the Analysis:**
- Data that could significantly raise or lower confidence
- Findings that would alter the interpretation

### 8. APPENDIX: METHODOLOGY

**Data Sources:**
- How publications were identified (PubMed search, etc.)
- Inclusion/exclusion criteria

**Extraction Process:**
- Single-pass vs multi-stage extraction
- What was extracted from abstracts vs full text

**Scoring Formulas:**
- Detailed breakdown of each score component
- Weighting rationale

---

## FORMATTING GUIDELINES

- Use clear headers and subheaders
- **Include specific numbers throughout** - cite actual endpoint values, response rates, patient counts
- Present data objectively without value judgments like "impressive" or "disappointing"
- Use phrases like "the data show" rather than "this suggests we should"
- When discussing uncertainty, quantify it where possible
- Use tables within the prose where helpful to summarize comparisons
- Aim for ~3500-4500 words total

---

## TONE GUIDELINES

**Use language like:**
- "The data show..."
- "The score of X.X reflects..."
- "This indicates..."
- "The evidence is limited by..."
- "Concordance across endpoints was X%..."
- "The response rate of X% was observed in N patients..."

**Avoid language like:**
- "We recommend..."
- "The company should..."
- "This opportunity warrants..."
- "Priority should be given to..."
- "Next steps include..."
- "This is an attractive/unattractive opportunity..."

---

## IMPORTANT CONTEXT

- This analysis is based on case series and case reports, NOT randomized controlled trials
- Publication bias likely inflates reported efficacy (negative cases are rarely published)
- Small sample sizes mean high uncertainty around point estimates
- These findings represent signals in the published literature, not definitive proof of efficacy
- The reader should apply their own strategic judgment to these findings

Generate the analytical report now.
'''


def generate_report_prompt(data: Dict[str, Any]) -> str:
    """
    Generate the complete report prompt with data filled in.
    
    Parameters:
    -----------
    data : dict
        Output from format_data_for_prompt()
    
    Returns:
    --------
    str
        Complete prompt ready to send to an LLM
    """
    return REPORT_PROMPT_TEMPLATE.format(
        drug_name=data['drug_name'],
        generic_name=data['generic_name'],
        mechanism=data['mechanism'][:800] + '...' if len(str(data['mechanism'])) > 800 else data['mechanism'],
        approved_indications=data['approved_indications'],
        analysis_date=data['analysis_date'],
        papers_screened=data['papers_screened'],
        opportunities_found=data['opportunities_found'],
        n_indications=data['n_indications'],
        total_patients=data['total_patients'],
        total_studies=data['total_studies'],
        analysis_summary_table=data['analysis_summary_table'],
        opportunities_table=data['opportunities_table'],
        efficacy_endpoints_table=data['efficacy_endpoints_table'],
        safety_endpoints_table=data['safety_endpoints_table'],
        market_intelligence_table=data['market_intelligence_table']
    )


# =============================================================================
# STREAMLIT INTEGRATION
# =============================================================================

def render_report_generator_ui():
    """
    Streamlit UI component for generating reports.
    
    Add this to your Streamlit app:
        from report_prompt_v2 import render_report_generator_ui
        render_report_generator_ui()
    """
    import streamlit as st
    
    st.subheader("📄 Generate Analytical Report")
    
    st.markdown("""
    Generate a detailed analytical report from your case series analysis. 
    The report provides **objective analysis of the data** without making 
    strategic recommendations - allowing you to draw your own conclusions.
    
    The report includes:
    - Score derivation with specific data citations
    - Concordance analysis across studies and endpoints
    - Cross-indication pattern analysis
    - Evidence quality assessment
    - Competitive landscape context
    """)
    
    uploaded_file = st.file_uploader(
        "Upload analysis Excel file",
        type=['xlsx'],
        key="report_generator_upload"
    )
    
    if uploaded_file is not None:
        try:
            # Save temporarily and load
            import tempfile
            with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
                tmp.write(uploaded_file.getvalue())
                tmp_path = tmp.name
            
            data = format_data_for_prompt(tmp_path)
            
            st.success(f"Loaded data for **{data['drug_name']}** with {data['n_indications']} indications")
            
            # Show preview
            with st.expander("Preview: Top Opportunities"):
                for i, opp in enumerate(data['top_opportunities'][:3], 1):
                    st.markdown(f"**{i}. {opp.get('Disease', 'Unknown')}** - Score: {opp.get('Overall Score (avg)', 'N/A')}")
            
            # Generate prompt button
            if st.button("Generate Report Prompt", type="primary"):
                prompt = generate_report_prompt(data)
                
                st.markdown("### Generated Prompt")
                st.markdown("Copy this prompt and send it to Claude or another LLM:")
                
                st.code(prompt, language=None)
                
                # Also provide download
                st.download_button(
                    label="Download Prompt as Text File",
                    data=prompt,
                    file_name=f"{data['drug_name'].lower()}_report_prompt.txt",
                    mime="text/plain"
                )
                
                st.info("""
                **Next steps:**
                1. Copy the prompt above
                2. Paste into Claude.ai or your preferred LLM
                3. The AI will generate an analytical report
                4. Review and edit as needed
                """)
        
        except Exception as e:
            st.error(f"Error processing file: {e}")


# =============================================================================
# EXAMPLE: DIRECT API CALL
# =============================================================================

def generate_report_via_api(
    excel_path: str,
    api_key: str = None,
    model: str = "claude-sonnet-4-20250514"
) -> str:
    """
    Generate report by calling Claude API directly.
    
    Parameters:
    -----------
    excel_path : str
        Path to the analysis Excel file
    api_key : str
        Anthropic API key (or set ANTHROPIC_API_KEY env var)
    model : str
        Model to use
    
    Returns:
    --------
    str
        Generated report text
    """
    import anthropic
    import os
    
    # Get API key
    if api_key is None:
        api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        raise ValueError("API key required. Set ANTHROPIC_API_KEY or pass api_key parameter.")
    
    # Load and format data
    data = format_data_for_prompt(excel_path)
    prompt = generate_report_prompt(data)
    
    # Call API
    client = anthropic.Anthropic(api_key=api_key)
    
    message = client.messages.create(
        model=model,
        max_tokens=8000,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )
    
    return message.content[0].text


# =============================================================================
# CLI USAGE
# =============================================================================

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python report_prompt_v2.py <excel_file> [--generate]")
        print("")
        print("Options:")
        print("  <excel_file>  Path to the analysis Excel file")
        print("  --generate    Call Claude API to generate report (requires ANTHROPIC_API_KEY)")
        print("")
        print("Examples:")
        print("  python report_prompt_v2.py analysis.xlsx              # Print prompt only")
        print("  python report_prompt_v2.py analysis.xlsx --generate   # Generate full report")
        sys.exit(1)
    
    excel_path = sys.argv[1]
    generate = "--generate" in sys.argv
    
    print(f"Loading data from: {excel_path}")
    data = format_data_for_prompt(excel_path)
    print(f"Drug: {data['drug_name']}")
    print(f"Indications: {data['n_indications']}")
    print(f"Total patients: {data['total_patients']}")
    print("")
    
    if generate:
        print("Generating report via Claude API...")
        report = generate_report_via_api(excel_path)
        print("\n" + "="*80)
        print("GENERATED REPORT")
        print("="*80 + "\n")
        print(report)
    else:
        prompt = generate_report_prompt(data)
        print("\n" + "="*80)
        print("PROMPT (copy and paste to Claude)")
        print("="*80 + "\n")
        print(prompt)
