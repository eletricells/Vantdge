# Drug Repurposing Case Series Agent v2

This flow of agents will systematically identify and analyze drug repurposing opportunities by mining case series and case reports from medical literature. I have some other agents I've previoulsy built that this will integrate into.

## Features

- **Drug-First Analysis**: Analyze a specific drug for all off-label repurposing opportunities
- **Mechanism-First Analysis**: Find all drugs sharing a mechanism, then analyze each for opportunities
- **Dual Literature Search**: Combines PubMed (peer-reviewed) and Tavily (web search) for comprehensive coverage
- **Automated Data Extraction**: Extracts 30+ structured fields from case reports using Claude
- **Market Intelligence Enrichment**: Adds epidemiology, standard of care, and competitive landscape data. this will be a WIP. I'm not sure if I'll able to built this out fully in a week given it will be comprised of several other agents.
- **Priority Scoring**: Ranks opportunities by clinical signal, evidence quality, market size, and feasibility
- **Multi-Format Export**: JSON for programmatic use, Excel with multiple sheets for analysis

## Integration with Existing Infrastructure

This agent leverages existing tools rather than building standalone components:

### Drug Information Retrieval
- **Primary Source**: DrugDatabase (PostgreSQL) for approved indications and drug metadata. I just created this database so it's empty but the idea here is that the more this workflow is run, the more context it will have in the future to leverage.
- **Fallback Source**: WebSearchTool (Tavily) when database is unavailable

### Literature Search
- **PubMedAPI**: Searches peer-reviewed case reports, case series, off-label studies, and compassionate use reports
- **WebSearchTool (Tavily)**: Captures other literature sources, recent reports, and conference abstracts not yet indexed in PubMed
- Uses existing tool classes from src/tools/ with case-series-specific search strategies

### Data Extraction
- Uses Claude for structured JSON extraction
- Pydantic schemas ensure data consistency and validation

## How It Works

### Step 1: Approved Indication Identification
The agent first retrieves all FDA-approved indications for the drug. This creates an exclusion list to ensure only off-label uses are captured. The data sources are queried in the following order:
1. **DrugDatabase (PostgreSQL)**: Checked first for cached drug information from previous runs
2. **DailyMed API**: Official FDA drug labeling database providing structured indication data
3. **Drugs.com Scraping**: Extracts approved indications from drug monographs via the existing Drug Extraction Agent
4. **Web Search Fallback**: If the above sources are unavailable, Tavily web search with Claude extraction is used

### Step 2: Case Series Search
Multiple complementary search strategies are executed across both PubMed and Tavily:
- Direct case report searches (drug name + "case report")
- Case series searches (drug name + "case series")
- Off-label use searches (drug name + "off-label")
- Expanded access and compassionate use searches
- Drug repurposing searches

Results are deduplicated by PMID or URL to avoid analyzing the same publication twice.

### Step 3: Structured Data Extraction (the limitation here is going to be what can be extracted from open source text or just the abstract if the paper is behind a paywall. i have another agent I've made that can extract from PDFs but it's not integrated yet. still need to refine that agent a bit more. it also costs a lot more to do this deeper dive so we can discuess that in more detail later)
For each case series/report, Claude extracts structured clinical data including:
- Disease/condition treated and whether it's truly off-label
- Patient population characteristics and prior treatment failures
- Treatment regimen details (dose, route, duration)
- Efficacy outcomes with response rates and effect sizes
- Safety outcomes including adverse events
- Overall outcome assessment (success/fail/mixed)

Papers that are not actually about off-label use are automatically filtered out.

### Step 4: Market Intelligence Enrichment (as mentioned earlier this is still a WIP and will require multiple agents to build out)
For each unique disease identified, the agent gathers market context:
- **Epidemiology**: US prevalence estimates, patient population size, trend direction
- **Standard of Care**: Top treatments, their efficacy ranges, and treatment paradigm
- **Unmet Need**: Assessment of whether current treatments leave gaps
- **Competitive Landscape**: Summary of existing therapeutic options

### Step 5: Priority Scoring (I'm still thinking though the best way to approach this and this may require a couple of runs and some manual evaluation, but open to any input here)
Each opportunity is scored across three dimensions to enable prioritization. Each individual factor within a dimension is scored on a 1-10 scale, then averaged to produce the dimension score. The dimension scores are then combined using the weights below.

**Clinical Signal Score (50% weight)**
Each factor below is scored 1-10, then averaged:
- **Response Rate**: Scored based on percentage of patients achieving the primary outcome for the disease (e.g., >80%=10, 60-80%=8, 40-60%=6, 20-40%=4, <20%=2). I'm planning on having a more robust version of this later on after I build out the agent that can retrieve clinical data for approved drugs and pipeline drugs. Then this would be benchmarked against approved drugs and pipeline drugs.
- **Safety Profile**: Scored based on % of patients experiencing serious adverse events (SAEs) or significant safety risks. No SAEs=10, <5% SAEs=8, 5-10% SAEs=6, 10-20% SAEs=4, 20-50% SAEs=2, >50% SAEs=1. Also factors in discontinuations due to adverse events.

**Evidence Quality Score (25% weight)**
Each factor below is scored 1-10, then averaged:
- **Sample Size**: N≥50=10, N=20-49=8, N=10-19=6, N=5-9=4, N=2-4=2, N=1=1
- **Publication Venue**: Peer-reviewed journal=10, Preprint=6, Conference abstract=4, Other=2
- **Follow-up Duration**: >1 year=10, 6-12 months=7, 3-6 months=5, 1-3 months=3, <1 month=1

**Market Opportunity Score (25% weight)**
Each factor below is scored 1-10, then averaged:
- **Number of Competitors**: No approved drugs=10, 1-2 approved drugs=7, 3-5 approved drugs=5, 6-10 approved drugs=3, >10 approved drugs=1
- **Market Size**: Calculated as patient population × average annual cost of top 3 branded approved drugs for the indication. If no approved drugs exist, pricing is estimated based on prevalence (rare disease pricing ~$200K+/year for <10K patients, specialty pricing ~$50-100K/year for 10K-100K patients, standard pricing ~$10-30K/year for >100K patients). Scored as: >$10B=10, $5-10B=9, $1-5B=8, $500M-1B=7, $100-500M=6, $50-100M=5, $10-50M=4, <$10M=2
- **Unmet Need**: Compares efficacy signal from case series vs efficacy range of top 3 approved drugs for the indication. If case series shows meaningfully better efficacy (e.g., higher response rate, better durability) than approved options, score=10. Similar efficacy=5. Worse efficacy=2. If there are no approved drugs for the indication, unmet need automatically scores 10.

**Overall Priority = (Clinical × 0.50) + (Evidence × 0.25) + (Market × 0.25)**

### Step 6: Export
Results are exported to JSON (for programmatic analysis) and/or Excel (for human review) with ranked opportunities and all supporting data.

## Data Fields Extracted

### Source Information
- PubMed ID (PMID)
- Digital Object Identifier (DOI)
- Source URL
- Publication title
- Author list
- Journal name
- Publication year
- Publication venue type (peer-reviewed journal, conference abstract, etc.)

### Clinical Evidence
- Disease/condition treated (normalized)
- Evidence level (Case Report, Case Series, Retrospective Study)
- Number of patients (N)
- Patient age description
- Sex distribution
- Prior treatments that failed
- Disease severity at baseline
- Route of administration
- Dose used
- Dosing frequency
- Treatment duration
- Concomitant medications
- Response rate (X/N format with percentage)
- Number of responders
- Time to response
- Duration of response
- Effect size description
- Primary efficacy endpoint and result
- Durability signal
- Efficacy summary (2-3 sentences)
- Adverse events list
- Serious adverse events
- Number of discontinuations
- Discontinuation reasons
- Safety summary (2-3 sentences)
- Overall safety profile assessment
- Outcome result (Success/Fail/Mixed)
- Efficacy signal strength (Strong/Moderate/Weak/None)
- Follow-up duration
- Key findings (1-2 sentences)

### Market Intelligence
- US prevalence estimate
- US incidence estimate
- Estimated patient population size
- Prevalence data source
- Disease trend (increasing/stable/decreasing)
- Top standard of care treatments with efficacy ranges
- Treatment paradigm description
- Unmet need assessment (yes/no)
- Unmet need description
- Competitive landscape summary

### Scoring
- Clinical signal score (1-10, 50% weight)
- Evidence quality score (1-10, 25% weight)
- Market opportunity score (1-10, 25% weight)
- Overall priority score (weighted average)
- Rank among all opportunities

## Output Formats

### JSON Export
Complete structured data exported as JSON for:
- Database storage
- Programmatic analysis
- Integration with other tools
- API responses

### Excel Export (Multi-Sheet)

**Summary Sheet**
- Drug name and generic name
- Mechanism of action
- List of approved indications
- Number of papers screened
- Number of opportunities found
- Analysis date and timestamp
- Estimated API cost

**Opportunities Sheet**
- All opportunities ranked by priority score
- Disease, evidence level, sample size
- Efficacy signal and outcome result
- Response rate and safety profile
- All three dimension scores plus overall priority
- Key findings and source information
- PMID and publication year

**Market Intelligence Sheet**
- Disease name
- US prevalence estimate
- Patient population size
- Unmet need assessment and description
- Competitive landscape summary

## Analysis Modes

### Single Drug Analysis
Analyze one drug to find all off-label uses with clinical evidence.

**Use Cases:**
- Portfolio assessment of an existing asset
- Competitive intelligence on a competitor's drug
- Academic research on a specific compound
- Due diligence for licensing opportunities
- Identifying label expansion opportunities

### Mechanism-Based Analysis
Find all drugs sharing a mechanism, then analyze each for repurposing opportunities.

**Use Cases:**
- Identifying the best candidate in a drug class for a new indication
- Understanding which indications respond to a specific mechanism
- Finding differentiation opportunities within a competitive class
- Mapping the full opportunity landscape for a mechanism hypothesis
- Informing target selection for new drug discovery

## Relationship to Other Agents

This agent complements and integrates with the existing agent ecosystem:

- **Drug Extraction Agent**: Provides approved indications and drug metadata that this agent uses as baseline for identifying off-label opportunities
- **Literature Search Agent**: Shares the PubMedAPI tool; this agent adds case-series-specific search strategies and structured extraction
- **Off-Label Case Study Agent**: Earlier version focused on mechanism extraction; this agent is more comprehensive with market intelligence, scoring, and dual-source literature search
- **Clinical Data Extractor** (future integration): Will provide deeper extraction from full-text papers; currently this agent works from abstracts only

## Cost Estimation

Based on Claude Sonnet pricing:
- Input: $3 per million tokens
- Output: $15 per million tokens

**Typical Costs:**
- Single drug analysis (20 papers): $0.50 - $2.00
- Single drug analysis (50 papers): $1.50 - $5.00
- Mechanism analysis (3 drugs): $3.00 - $10.00
- Mechanism analysis (10 drugs): $10.00 - $30.00

Costs depend on: number of case series found, search depth, market intelligence enrichment enabled.

## Limitations

### Current Version
- **Abstract-Only Extraction**: Works from abstracts and snippets; full-text extraction not yet integrated
- **Search Depth**: Limited to publicly available case reports indexed in PubMed or findable via web search
- **Sample Sizes**: Most case reports are N=1 to N=10; larger studies require different search strategies
- **Evidence Quality**: Pre-clinical data and RCT results not included in this agent's scope
- **Geographic Bias**: Market intelligence is US-focused for prevalence and epidemiology data
- **Language**: English publications only
- **Recency**: Case reports may lag actual clinical practice by 1-2 years

### Not Included (Potential Future Additions)
- Mechanistic rationale analysis and biological plausibility scoring
- Preclinical efficacy data from animal studies
- Failed clinical trials (unless published as case series)
- Real-world evidence from claims databases

## Best Practices

### Starting an Analysis
- Use generic drug names for best search results
- Start with specific mechanisms rather than broad categories (e.g., "JAK1/JAK2 inhibitor" not "kinase inhibitor")
- For mechanism analysis, limit to 5-10 drugs initially to manage costs

### Interpreting Results
- High priority scores indicate opportunities worth deeper investigation, not definitive recommendations
- Always verify source publications directly before making decisions
- Cross-reference prevalence estimates with CDC/NIH authoritative sources
- Check ClinicalTrials.gov for ongoing trials in the same drug-indication pair
- Confirm approved indications with FDA Orange Book

### Managing Costs
- Use smaller max_papers values (10-20) for initial exploration
- Disable market intelligence enrichment for quick scans
- Process drugs sequentially to monitor costs
- Review intermediate results before processing additional drugs

## Troubleshooting

### No Results Found
- Verify drug spelling (use generic names)
- Try alternative names or spellings
- Check if the drug is recent (may not have published case reports yet)
- Broaden search by trying mechanism-based analysis

### Low Quality Results
- Increase max_papers to capture more publications
- Review filtered papers to ensure relevant ones aren't being excluded
- Check if the drug has primarily RCT data rather than case reports

### High Costs
- Reduce max_papers parameter
- Disable market intelligence enrichment
- Process fewer drugs in mechanism analysis
- Use the agent for targeted analysis rather than broad exploration

## Future Enhancements

### Planned Integrations
- Full-text extraction via Clinical Data Extractor for richer evidence
- Clinical trials cross-referencing with ClinicalTrials.gov API
- Patent landscape analysis integration
- Automated monitoring for new publications

### Research Extensions
- Multi-drug combination opportunity identification
- Biomarker-stratified patient population analysis
- Health economics and outcomes research integration
- Regulatory pathway optimization recommendations
- Partnership and licensing opportunity identification

