# Drug Repurposing Opportunity Agent

Systematically identifies and analyzes drug repurposing opportunities by mining case series and case reports from medical literature.

## Features

- **Drug-First Analysis**: Analyze a specific drug for repurposing opportunities
- **Mechanism-First Analysis**: Find all drugs with a mechanism, then analyze each
- **Automated Data Extraction**: Extracts 30+ structured fields from case reports
- **Market Intelligence**: Adds epidemiology, standard of care, and competitive landscape
- **Priority Scoring**: Ranks opportunities by clinical signal, evidence quality, market size, and feasibility
- **Excel Export**: Professional spreadsheet output with multiple sheets

## Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export ANTHROPIC_API_KEY="your-key-here"
export TAVILY_API_KEY="your-key-here"
```

## Quick Start

### Drug-First Analysis

```python
from drug_repurposing_agent import DrugRepurposingAgent

agent = DrugRepurposingAgent(
    anthropic_api_key="your-key",
    tavily_api_key="your-key"
)

# Analyze a specific drug
results = agent.analyze_drug("rimegepant")

# Export to Excel
agent.export_to_excel(results, "rimegepant_analysis.xlsx")
```

### Mechanism-First Analysis

```python
from mechanism_based_agent import MechanismBasedAgent

agent = MechanismBasedAgent(
    anthropic_api_key="your-key",
    tavily_api_key="your-key"
)

# Analyze all drugs with a mechanism
results = agent.analyze_mechanism("CGRP receptor antagonist")

# Export comprehensive analysis
agent.export_mechanism_analysis(results, "cgrp_antagonists.xlsx")
```

### Command Line Usage

```bash
# Drug analysis
python drug_repurposing_agent.py

# Mechanism analysis
python mechanism_based_agent.py
```

## How It Works

### 1. Approved Indication Identification
- Searches for FDA approval information
- Uses Claude to extract all approved indications
- Creates exclusion list for filtering

### 2. Case Series Search
- Multiple search strategies:
  - "[drug] case report"
  - "[drug] case series"
  - "[drug] off-label use"
  - "[drug] expanded access"
- Filters for genuine case reports/series
- Deduplicates by URL

### 3. Structured Data Extraction
For each case series, extracts:
- **Core Data**: Source, year, disease, sample size, evidence level
- **Clinical Data**: Patient population, dosing, response rate, efficacy, safety
- **Context**: Comparator, durability, publication venue

### 4. Market Enrichment
- **Epidemiology**: US prevalence estimates
- **Standard of Care**: Top 3 treatments and efficacy ranges
- **Competitive Landscape**: Summary of existing options
- **Unmet Need**: Assessment of treatment gaps

### 5. Priority Scoring

**Clinical Signal Score (40% weight)**
- Response rate magnitude
- Effect size description
- Durability of response

**Evidence Quality Score (20% weight)**
- Sample size (N)
- Publication venue (peer-reviewed vs conference)
- Follow-up duration

**Market Opportunity Score (20% weight)**
- US patient population size
- Unmet need assessment

**Feasibility Score (20% weight)**
- Known safety profile
- Development pathway (505(b)(2))
- IP considerations

**Overall Priority = Weighted Average**

## Data Fields Extracted

### Core Identification
- Source (citation)
- Drug name
- Mechanism/target
- Year of publication
- Disease/indication
- Sample size (N)

### Clinical Evidence
- Evidence level (Case Report / Case Series)
- Patient population description
- Route of administration
- Dose and frequency
- Duration of follow-up
- Response rate (X/N format)
- Time to response
- Success/Fail/Mixed
- Effect size description
- Efficacy summary (2-3 sentences)
- Safety summary (2-3 sentences)
- Comparator/baseline
- Durability signal
- Publication venue

### Strategic Context
- US prevalence estimate
- Prevalence source
- Current standard of care (top 3 drugs)
- SOC efficacy ranges
- Unmet need (Yes/No)
- Unmet need description
- Competitive landscape summary
- Approved indications (for exclusion)

### Scoring
- Clinical signal score (1-10)
- Evidence quality score (1-10)
- Market opportunity score (1-10)
- Feasibility score (1-10)
- Overall priority score (weighted)

## Output Format

### Excel Structure

**Main Sheet: "Repurposing Opportunities"**
- All opportunities ranked by priority score
- Full data for each opportunity
- Color-coded headers
- Frozen header row
- Wrapped text in cells

**Metadata Sheet**
- Drug/mechanism analyzed
- Analysis date
- Approved indications
- Total opportunities found
- API usage statistics
- Estimated cost

**Additional Sheets (Mechanism Analysis)**
- Summary sheet with all drugs
- Individual sheet per drug with opportunities

## Cost Estimation

Based on Claude Sonnet 4 pricing:
- Input: $3 per million tokens
- Output: $15 per million tokens

**Typical costs:**
- Single drug analysis: $0.50 - $2.00
- Mechanism analysis (3 drugs): $2.00 - $6.00
- Depends on: number of case series found, search depth

## Best Practices

### 1. Start Specific
```python
# Good: Specific drug
agent.analyze_drug("rimegepant")

# Good: Specific mechanism
agent.analyze_mechanism("JAK1/JAK2 inhibitor")

# Avoid: Too broad
agent.analyze_mechanism("kinase inhibitor")  # Will find 100+ drugs
```

### 2. Monitor Costs
```python
results = agent.analyze_drug("drug_name")
print(f"Input tokens: {agent.total_input_tokens}")
print(f"Output tokens: {agent.total_output_tokens}")
print(f"Estimated cost: ${agent.total_input_tokens * 0.003 / 1000 + agent.total_output_tokens * 0.015 / 1000:.2f}")
```

### 3. Filter by Priority
```python
# Focus on high-priority opportunities
high_priority = [
    case for case in results['case_series'] 
    if case['scores']['overall_priority'] >= 7.0
]
```

### 4. Validate Key Findings
- Review source publications directly
- Verify prevalence estimates with CDC/NIH data
- Check ClinicalTrials.gov for ongoing trials
- Confirm approved indications with FDA Orange Book

## Limitations

### Current Version
- **Search Depth**: Limited to publicly available case reports
- **Sample Sizes**: Most case reports are N=1 to N=10
- **Evidence Quality**: Pre-clinical and RCT data not included
- **Geographic Bias**: US-focused prevalence data
- **Language**: English publications only
- **Recency**: Case reports may lag actual clinical practice

### Not Included
- Mechanistic rationale analysis
- Preclinical efficacy data
- Failed trials (unless published as case series)
- Real-world evidence databases (claims data)
- Patent landscape analysis
- Detailed IP strategy
- Manufacturing/CMC considerations
- Payer/reimbursement analysis

## Advanced Usage

### Custom Scoring Weights

```python
def custom_score_opportunity(case: Dict) -> Dict:
    """Custom scoring with different weights"""
    clinical = agent._score_clinical_signal(case)
    evidence = agent._score_evidence_quality(case)
    market = agent._score_market_opportunity(case)
    feasibility = 7
    
    # Custom weights: prioritize clinical signal heavily
    overall = (
        clinical * 0.6 +    # 60% weight
        evidence * 0.2 +     # 20% weight
        market * 0.1 +       # 10% weight
        feasibility * 0.1    # 10% weight
    )
    
    return {
        'clinical_signal': clinical,
        'evidence_quality': evidence,
        'market_opportunity': market,
        'feasibility': feasibility,
        'overall_priority': round(overall, 1)
    }

# Monkey patch the scoring function
agent._score_opportunity = custom_score_opportunity
```

### Filtering Search Results

```python
def filter_case_series(cases: List[Dict], min_n: int = 3) -> List[Dict]:
    """Filter for minimum sample size"""
    return [
        case for case in cases 
        if case.get('n', 0) >= min_n
    ]

# Apply filter
filtered_cases = filter_case_series(results['case_series'], min_n=5)
```

### Adding Custom Data Sources

```python
def get_clinicaltrials_data(disease: str) -> Dict:
    """Fetch data from ClinicalTrials.gov API"""
    import requests
    
    response = requests.get(
        "https://clinicaltrials.gov/api/v2/studies",
        params={
            "query.cond": disease,
            "format": "json"
        }
    )
    
    data = response.json()
    return {
        'active_trials': len(data.get('studies', [])),
        'recruiting': sum(1 for s in data.get('studies', []) 
                         if s.get('protocolSection', {}).get('statusModule', {}).get('overallStatus') == 'Recruiting')
    }

# Integrate into analysis
for case in results['case_series']:
    case['clinical_trials'] = get_clinicaltrials_data(case['disease'])
```

## Troubleshooting

### Issue: No results found
**Solution:** 
- Check drug spelling (use generic names)
- Try alternative names (e.g., "anti-CGRP" vs "CGRP antagonist")
- Verify drug has published case reports (recent drugs may not)

### Issue: API rate limits
**Solution:**
- Add delays between calls: `time.sleep(1)`
- Reduce max_results in searches
- Process drugs sequentially, not in parallel

### Issue: Extraction errors
**Solution:**
- Check if source content is actually accessible
- Verify JSON parsing (look for markdown code blocks)
- Add error logging: `logging.basicConfig(level=logging.DEBUG)`

### Issue: High costs
**Solution:**
- Reduce search queries (combine similar searches)
- Filter case series before extraction
- Use smaller max_results values
- Cache intermediate results

## Future Enhancements

### Planned Features
- [ ] PubMed API integration for more comprehensive search
- [ ] Conference abstract mining (ASCO, AAN, etc.)
- [ ] Real-world evidence database integration
- [ ] Mechanistic rationale scoring
- [ ] Patent landscape analysis
- [ ] Clinical trial matching (ClinicalTrials.gov)
- [ ] Automated report generation with visualizations
- [ ] Interactive dashboard (Streamlit/Dash)

### Research Extensions
- [ ] Multi-drug combination opportunities
- [ ] Biomarker-stratified patient populations
- [ ] Disease progression modeling
- [ ] Health economics analysis
- [ ] Regulatory pathway optimization
- [ ] Partnership opportunity identification

## Citation

If using this tool for research:

```
Drug Repurposing Opportunity Agent (2024)
Systematic identification of drug repurposing opportunities through
automated case series analysis and market intelligence.
```

## License

MIT License - See LICENSE file for details

## Support

For issues, feature requests, or questions:
- Open an issue on GitHub
- Email: [your contact]

## Acknowledgments

- Anthropic Claude API for structured data extraction
- Tavily Search API for medical literature discovery
- OpenPyxl for Excel generation
