# Disease-First Mechanism Discovery Agent v1

This workflow systematically identifies promising therapeutic mechanisms for a given disease by mining off-label case series and case reports. Unlike the Drug Repurposing Case Series Agent (which starts with a drug and finds indications), this agent starts with a disease and identifies which mechanisms show the strongest clinical signals, enabling target prioritization for drug development or in-licensing decisions.

## Core Concept

**Input**: A disease/indication (e.g., dermatomyositis, IgA nephropathy, systemic sclerosis)

**Output**: Ranked list of therapeutic mechanisms with clinical evidence of efficacy, aggregated across all drugs sharing each mechanism

**Key Insight**: If multiple drugs targeting the same pathway (e.g., JAK inhibitors, direct IFN blockers) all show efficacy signals in case reports for a disease, this provides convergent evidence that the pathway is disease-relevant and druggable.

## Features

- **Disease-First Analysis**: Start with a disease, discover which mechanisms work
- **Approved Drug Exclusion**: Automatically filters out drugs with explicit FDA approval for the indication
- **Mechanism Enrichment**: Looks up MOA via database (ChEMBL) first, then web search fallback
- **Hierarchical Mechanism Taxonomy**: Captures target → mechanism class → pathway → biological effect
- **Pathway Convergence Detection**: Identifies when different mechanism classes affect the same pathway
- **Dual Literature Search**: Combines PubMed and Tavily for comprehensive coverage
- **Two-Stage Scoring**: Paper-level clinical scoring + mechanism-level tournament ranking
- **Multi-Format Export**: JSON for programmatic use, Excel with mechanism rankings for analysis

## Integration with Existing Infrastructure

### Disease Information Retrieval
- **Primary Source**: Disease normalization via MeSH terms or SNOMED-CT
- **Synonyms**: Expand search with disease aliases (e.g., "DM" for dermatomyositis)

### Approved Drug Identification (Exclusion List)
- **DrugDatabase (PostgreSQL)**: Check for cached approved drugs for this indication
- **DailyMed API**: Query FDA labels for drugs with this indication
- **Drugs@FDA**: Cross-reference approved indications
- **Web Search Fallback**: Tavily search for "FDA approved drugs for [disease]"

### Mechanism of Action Lookup
- **DrugDatabase (PostgreSQL)**: Check for cached MOA data
- **ChEMBL API**: Primary source for target and mechanism class data (open source)
- **Reactome**: Pathway mapping for mechanism clustering
- **Web Search Fallback**: Claude extracts MOA from authoritative sources (DrugBank pages, FDA labels)
- **Cache Back**: Store retrieved MOA data in DrugDatabase for future runs

### Literature Search
- **PubMedAPI**: Case reports, case series, expanded access, compassionate use
- **WebSearchTool (Tavily)**: Conference abstracts, recent reports, non-indexed sources

### Data Extraction
- Uses Claude for structured JSON extraction
- Pydantic schemas ensure data consistency

## How It Works

### Step 1: Disease Normalization & Context
The agent first normalizes the disease input and gathers baseline context:

1. **Disease Normalization**: Map input to standard terminology (MeSH, ICD-10, SNOMED-CT)
2. **Synonym Expansion**: Identify alternative names for comprehensive searching
3. **Disease Subtypes**: Note relevant subtypes that may have separate literature (e.g., juvenile vs adult dermatomyositis, amyopathic vs classic)
4. **Baseline Context**: Gather brief epidemiology and current treatment landscape context

**Example for "dermatomyositis":**
- MeSH: D003882
- Synonyms: DM, inflammatory myopathy, dermatomyositis sine myositis
- Subtypes: Juvenile DM, amyopathic DM, cancer-associated DM, anti-MDA5 DM
- Context: Rare autoimmune disease, ~10/million prevalence, high unmet need

### Step 2: Approved Drug Identification (Exclusion List)
Retrieve all drugs with explicit FDA approval for the indication. These will be excluded from results since we're looking for off-label signals.

**Data sources queried in order:**
1. **DrugDatabase (PostgreSQL)**: Cached data from previous runs
2. **DailyMed API**: Official FDA labeling database
3. **Drugs@FDA Database**: NDA/BLA approvals for the indication
4. **Web Search Fallback**: "FDA approved treatments for [disease]"

**Important**: Only exclude drugs with explicit approval for the exact indication. Do not exclude:
- Drugs approved for related but distinct indications
- Drugs in clinical trials (these are interesting signals)
- Drugs approved in other countries but not US

**Example exclusions for dermatomyositis:**
- Currently no FDA-approved drugs specifically for dermatomyositis (as of knowledge cutoff)
- Would NOT exclude: rituximab (approved for other indications), tofacitinib (approved for RA)

### Step 3: Case Series Literature Search
Multiple complementary search strategies executed across PubMed and Tavily:

**Search Queries:**
- "[disease] case report treatment"
- "[disease] case series"
- "[disease] off-label"
- "[disease] expanded access"
- "[disease] compassionate use"
- "[disease] refractory treatment"
- "[disease] novel therapy"
- "[disease synonym] case report" (for each synonym)

**Filters Applied:**
- Publication type: Case reports, case series, letters, brief communications
- Language: English
- Recency: Prioritize last 10 years, but include older landmark reports

**Deduplication:**
- By PMID for PubMed results
- By DOI or title similarity for Tavily results
- Merge records that appear in both sources

### Step 4: Initial Screening & Drug Identification
For each paper, perform initial screening:

1. **Extract Drug Name(s)**: Identify the therapeutic agent(s) used
2. **Check Exclusion List**: Skip if drug is FDA-approved for this indication
3. **Relevance Check**: Confirm paper is about treating the target disease
4. **Evidence Type Check**: Confirm it's a case report/series (not review, not RCT)

Papers passing screening proceed to full extraction.

### Step 5: Mechanism of Action Lookup
For each unique drug identified, retrieve mechanism data:

**Lookup Cascade:**
1. **DrugDatabase (PostgreSQL)**: Check local cache
2. **ChEMBL API Query**:
   ```
   GET /molecule/{drug_name}
   → Extract: target_chembl_id, mechanism_of_action, target_type
   ```
3. **Reactome Pathway Mapping**:
   ```
   Map target → pathway(s) via UniProt ID
   → Extract: pathway_name, pathway_hierarchy
   ```
4. **Web Search Fallback**: If not in ChEMBL (new drug, biologic, etc.)
   - Search: "[drug name] mechanism of action"
   - Claude extracts: primary target, mechanism class, affected pathways

**Hierarchical Mechanism Taxonomy:**
For each drug, capture four levels:

| Level | Field | Example (Tofacitinib) | Example (Anifrolumab) |
|-------|-------|----------------------|----------------------|
| 1 | Primary Target | JAK1, JAK3 | IFNAR1 |
| 2 | Mechanism Class | JAK inhibitor | Type I IFN receptor blocker |
| 3 | Affected Pathways | JAK-STAT signaling, Type I IFN signaling, IL-6 signaling | Type I IFN signaling |
| 4 | Biological Effect | Reduces IFN-stimulated gene expression, blocks cytokine signaling | Blocks Type I IFN signaling |

**Cache Results**: Store retrieved MOA data back to DrugDatabase for future runs.

### Step 6: Structured Data Extraction
For each case series/report, Claude extracts structured clinical data:

**Drug & Mechanism Fields (NEW in this workflow):**
- Drug name (generic)
- Drug name (brand)
- Primary target
- Mechanism class
- Affected pathways (list)
- Biological effect description
- Drug approval status (approved for other indications / investigational / withdrawn)
- Original approved indication(s) if applicable

**Source Information:**
- PubMed ID (PMID)
- Digital Object Identifier (DOI)
- Source URL
- Publication title
- Author list
- Journal name
- Publication year
- Publication venue type

**Clinical Evidence:**
- Disease/condition treated (normalized to input disease)
- Disease subtype if specified
- Evidence level (Case Report, Case Series, Retrospective Study)
- Number of patients (N)
- Patient age description
- Sex distribution
- Prior treatments that failed (important for refractory signal)
- Disease severity at baseline
- Disease activity measures used
- Route of administration
- Dose used
- Dosing frequency
- Treatment duration
- Concomitant medications (especially immunosuppressants)
- Response criteria used
- Response rate (X/N format with percentage)
- Number of responders
- Number of complete responders vs partial
- Time to response
- Duration of response
- Durability signal (maintained at follow-up?)
- Steroid-sparing effect (yes/no, quantified if possible)
- Efficacy summary (2-3 sentences)
- Adverse events list
- Serious adverse events
- Number of discontinuations
- Discontinuation reasons
- Safety summary (2-3 sentences)
- Overall outcome result (Success/Fail/Mixed)
- Efficacy signal strength (Strong/Moderate/Weak/None)
- Follow-up duration
- Key findings (1-2 sentences)

### Step 7: Paper-Level Scoring
Each case series is scored on three dimensions (similar to v1):

**Clinical Signal Score (50% weight)**
- **Response Rate**: >80%=10, 60-80%=8, 40-60%=6, 20-40%=4, <20%=2
- **Safety Profile**: No SAEs=10, <5% SAEs=8, 5-10% SAEs=6, 10-20%=4, >20%=2
- **Refractory Population Bonus**: +1 if patients failed ≥2 prior therapies

**Evidence Quality Score (25% weight)**
- **Sample Size**: N≥50=10, N=20-49=8, N=10-19=6, N=5-9=4, N=2-4=2, N=1=1
- **Publication Venue**: Peer-reviewed=10, Preprint=6, Conference=4, Other=2
- **Follow-up Duration**: >1 year=10, 6-12mo=7, 3-6mo=5, 1-3mo=3, <1mo=1

**Mechanism Clarity Score (25% weight)** - NEW
- **Target Specificity**: Highly selective=10, Moderately selective=6, Broad/unknown=3
- **MOA Data Quality**: Database-confirmed=10, Web-extracted=6, Inferred=3
- **Pathway Attribution**: Clear single pathway=10, Multiple pathways=5, Unknown=2

**Paper Priority Score = (Clinical × 0.50) + (Evidence × 0.25) + (Mechanism × 0.25)**

### Step 8: Mechanism-Level Aggregation
Roll up paper-level data to mechanism level:

**Aggregation by Mechanism Class:**
For each unique mechanism class (e.g., "JAK inhibitor"), compute:

| Metric | Calculation |
|--------|-------------|
| Total Papers | Count of papers with this mechanism |
| Total Patients (N) | Sum of patients across all papers |
| Total Responders | Sum of responders across all papers |
| Weighted Response Rate | Total responders / Total patients |
| Unique Drugs | Count of distinct drugs in this class |
| Consistency Rate | % of papers showing positive signal |
| Max Paper Score | Highest individual paper score |
| Avg Paper Score | Mean of all paper scores |
| Evidence Diversity | Unique journals + unique author groups |

**Aggregation by Pathway:**
For mechanisms affecting the same pathway, create pathway-level roll-ups:

| Pathway | Mechanisms | Total N | Weighted RR | Convergence Score |
|---------|-----------|---------|-------------|-------------------|
| Type I IFN | JAK inhibitors, IFNAR blockers | 45 | 72% | HIGH |
| B-cell | Anti-CD20, Anti-CD19, BAFF inhibitors | 120 | 65% | HIGH |
| T-cell costim | CTLA4-Ig, Anti-CD40L | 15 | 40% | LOW |

### Step 9: Tournament Ranking System
Mechanisms are ranked through a tournament bracket:

```
┌─────────────────────────────────────────────────────────────────┐
│                    MECHANISM TOURNAMENT                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ROUND 1: SIGNAL DETECTION                                       │
│  ├── Criterion: ≥1 case series with efficacy signal             │
│  ├── Pass → Advance to Round 2                                  │
│  └── Fail → Eliminated (insufficient evidence)                  │
│                                                                  │
│  ROUND 2: REPLICATION FILTER                                     │
│  ├── Criterion: ≥2 independent publications OR ≥5 total N      │
│  ├── Pass → Advance to Round 3                                  │
│  └── Fail → "Hypothesis Only" tier                              │
│                                                                  │
│  ROUND 3: CONSISTENCY CHECK                                      │
│  ├── Criterion: ≥50% of papers show positive signal             │
│  ├── Pass → Advance to Round 4                                  │
│  └── Fail → "Inconsistent Signal" tier                          │
│                                                                  │
│  ROUND 4: CONVERGENT PATHWAY BONUS                               │
│  ├── Check: Do other mechanism classes affecting same pathway   │
│  │          also show positive signal?                          │
│  ├── Yes → +15% bonus to composite score                        │
│  └── No  → No bonus (not a penalty)                             │
│                                                                  │
│  FINALS: COMPOSITE SCORING                                       │
│  ├── Aggregate Clinical Signal (40%)                            │
│  │   └── Weighted response rate + safety profile                │
│  ├── Evidence Volume & Quality (30%)                            │
│  │   └── Total N + paper count + publication quality            │
│  ├── Mechanism Diversity (20%)                                  │
│  │   └── Number of unique drugs × consistency rate              │
│  └── Biological Coherence (10%)                                 │
│      └── Pathway convergence + mechanistic plausibility         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Final Output: Confidence Tiers**

| Tier | Criteria | Interpretation |
|------|----------|----------------|
| **Tier 1: High Confidence** | Multiple drugs, convergent pathways, consistent signal, N≥20 | Strong rationale for clinical development |
| **Tier 2: Moderate Confidence** | Single drug class with strong signal OR multiple drugs with small N | Promising, warrants further investigation |
| **Tier 3: Hypothesis-Generating** | Limited evidence but biologically plausible | Early signal, monitor for new publications |
| **Inconsistent** | Mixed results across papers | Mechanism may work in subpopulations |
| **Hypothesis Only** | Single case report, N<5 | Anecdotal, insufficient to draw conclusions |

### Step 10: Export
Results exported to JSON and Excel with mechanism rankings.

## Data Fields Extracted

### Drug & Mechanism Information (NEW)
- Drug name (generic)
- Drug name (brand)
- Primary target
- Mechanism class
- Affected pathways (list)
- Pathway hierarchy
- Biological effect description
- Target selectivity (high/moderate/low)
- Drug modality (small molecule, biologic, cell therapy)
- Drug approval status
- Original approved indication(s)
- ChEMBL ID (if available)
- MOA data source (database/web/inferred)

### Source Information
- PubMed ID (PMID)
- Digital Object Identifier (DOI)
- Source URL
- Publication title
- Author list
- Journal name
- Publication year
- Publication venue type

### Clinical Evidence
- Disease/condition (normalized)
- Disease subtype
- Evidence level
- Number of patients (N)
- Patient demographics
- Prior treatment failures
- Disease severity at baseline
- Disease activity measures
- Treatment regimen details
- Response criteria used
- Response rate
- Responder breakdown (complete/partial)
- Time to response
- Duration of response
- Durability signal
- Steroid-sparing effect
- Efficacy summary
- Adverse events
- Safety summary
- Overall outcome
- Efficacy signal strength
- Follow-up duration
- Key findings

### Paper-Level Scores
- Clinical signal score (1-10)
- Evidence quality score (1-10)
- Mechanism clarity score (1-10)
- Paper priority score (weighted)

### Mechanism-Level Aggregates
- Mechanism class
- Affected pathways
- Total papers
- Total patients (N)
- Total responders
- Weighted response rate
- Unique drugs in class
- Consistency rate
- Average paper score
- Max paper score
- Evidence diversity score
- Pathway convergence flag
- Convergence bonus applied

### Tournament Results
- Round 1 result (pass/fail)
- Round 2 result (pass/fail/hypothesis only)
- Round 3 result (pass/fail/inconsistent)
- Round 4 bonus (yes/no, bonus %)
- Composite score
- Confidence tier
- Final rank

## Output Formats

### JSON Export
Complete structured data for:
- Database storage
- Programmatic analysis
- Integration with pipeline prioritization tools
- API responses

### Excel Export (Multi-Sheet)

**Summary Sheet**
- Disease name (normalized)
- Disease synonyms searched
- Approved drugs excluded
- Total papers screened
- Total papers included
- Unique mechanisms identified
- Unique drugs identified
- Analysis date and timestamp
- Estimated API cost

**Mechanism Rankings Sheet** (PRIMARY OUTPUT)
- Rank
- Mechanism class
- Affected pathways
- Confidence tier
- Composite score
- Weighted response rate
- Total patients (N)
- Unique drugs
- Consistency rate
- Pathway convergence (yes/no)
- Top paper PMID
- Key evidence summary

**Paper Details Sheet**
- All papers with full extracted data
- Sorted by mechanism class, then by paper score
- Includes all clinical fields
- Linked to mechanism via mechanism_class field

**Drug Summary Sheet**
- Drug name
- Mechanism class
- Primary target
- Affected pathways
- Paper count
- Total N
- Response rate
- Best paper PMID

**Pathway Convergence Sheet**
- Pathway name
- Mechanism classes affecting this pathway
- Combined evidence (total N, weighted RR)
- Convergence strength (HIGH/MEDIUM/LOW)
- Interpretation

## Use Cases

### Target Prioritization for Drug Discovery
**Scenario**: Biotech evaluating which mechanism to pursue for dermatomyositis program
**Output**: Ranked mechanisms with JAK inhibition and Type I IFN blockade emerging as top candidates based on convergent case series evidence

### In-Licensing Due Diligence
**Scenario**: BD team evaluating an asset with a novel mechanism, wants to understand if similar mechanisms have shown efficacy
**Output**: Mechanism-level evidence for the pathway, supporting or challenging the biological hypothesis

### Competitive Intelligence
**Scenario**: Understanding which mechanisms competitors might pursue for a disease
**Output**: Map of all mechanisms with clinical evidence, identifying white space opportunities

### Clinical Development Strategy
**Scenario**: Planning which patient population to target in Phase 2
**Output**: Subtype-specific signals (e.g., anti-MDA5 DM responds particularly well to JAK inhibitors)

### Academic Research
**Scenario**: Systematic review of therapeutic mechanisms for a rare disease
**Output**: Comprehensive evidence synthesis organized by mechanism

## Relationship to Other Agents

### Complements Drug Repurposing Case Series Agent (v1)
- **v1 (Drug-First)**: "What diseases might respond to Drug X?"
- **This workflow (Disease-First)**: "What mechanisms might work for Disease Y?"
- Together they provide bidirectional analysis capability

### Integrates With:
- **Drug Extraction Agent**: Provides approved indication data for exclusion list
- **Literature Search Agent**: Shares PubMedAPI tool infrastructure
- **MOA Lookup Agent** (new): Encapsulates ChEMBL/Reactome/web search cascade
- **Clinical Data Extractor** (future): Deep extraction from full-text PDFs

### Feeds Into:
- **Target Prioritization Dashboard**: Mechanism rankings inform target selection
- **Pipeline Analysis**: Mechanisms identified here can be cross-referenced with active trials
- **Investor Presentations**: Evidence-backed mechanism thesis for BD discussions

## Cost Estimation

Based on Claude Sonnet pricing ($3/M input, $15/M output):

**Typical Costs:**
- Common disease (50 papers): $2.00 - $6.00
- Rare disease (20 papers): $0.75 - $2.00
- Disease with many subtypes (100 papers): $4.00 - $12.00

**Cost Drivers:**
- Number of case series found
- MOA lookup calls (ChEMBL is free, web search adds cost)
- Pathway mapping complexity
- Number of unique mechanisms to aggregate

## Limitations

### Current Version
- **Abstract-Only**: Works from abstracts; full-text extraction not integrated
- **Mechanism Attribution**: Some drugs have multiple mechanisms; may over-simplify
- **Pathway Databases**: Reactome coverage varies; some novel targets may lack pathway mapping
- **Subtype Conflation**: May mix signals across disease subtypes
- **Publication Bias**: Positive results more likely published as case reports
- **Combination Therapies**: Difficult to attribute efficacy when multiple drugs used

### Not Included (Future Additions)
- Preclinical mechanism validation data
- Genetic association data (GWAS hits supporting mechanism)
- Failed clinical trials analysis
- Real-world evidence from claims data
- Biomarker-stratified analysis

## Best Practices

### Starting an Analysis
- Use standardized disease names for best search coverage
- Include key subtypes in initial search if known
- Start with max_papers=50 for initial exploration

### Interpreting Results
- **Tier 1 mechanisms**: Ready for clinical development consideration
- **Convergent pathways**: Strongest biological signal
- **Single-drug signals**: May be drug-specific rather than mechanism-specific
- Always verify source publications directly
- Cross-reference with ClinicalTrials.gov for ongoing development

### Managing Costs
- Use max_papers=20 for quick scans
- Disable pathway mapping for simpler analysis
- Process one disease at a time

## Troubleshooting

### Too Few Results
- Check disease name spelling and synonyms
- Try broader search terms
- Include disease subtypes in search

### Too Many Low-Quality Results
- Increase minimum N threshold
- Filter to peer-reviewed only
- Focus on recent publications (last 5 years)

### Mechanism Clustering Issues
- Review mechanism taxonomy manually for edge cases
- JAK inhibitor subclasses may need manual separation
- Biologics with multiple mechanisms need careful attribution

## Future Enhancements

### Planned
- Full-text extraction integration
- ClinicalTrials.gov cross-reference for ongoing trials
- Genetic evidence integration (GWAS, rare variant studies)
- Biomarker-stratified subgroup analysis

### Research Extensions
- Combination mechanism identification
- Resistance mechanism detection (what fails?)
- Temporal analysis (are newer papers showing different mechanisms?)
- Geographic variation in treatment patterns

## Example Output: Dermatomyositis

**Disease**: Dermatomyositis
**Papers Screened**: 87
**Papers Included**: 52 (after exclusion of approved drugs)
**Unique Mechanisms**: 12
**Unique Drugs**: 23

### Top Mechanism Rankings

| Rank | Mechanism | Pathway | Tier | Score | N | RR | Drugs | Convergence |
|------|-----------|---------|------|-------|---|-----|-------|-------------|
| 1 | JAK inhibitor | Type I IFN, JAK-STAT | Tier 1 | 8.7 | 89 | 74% | 4 | Yes (IFN) |
| 2 | Type I IFN blocker | Type I IFN | Tier 1 | 8.2 | 32 | 78% | 2 | Yes (IFN) |
| 3 | Anti-CD20 | B-cell depletion | Tier 1 | 7.9 | 156 | 67% | 2 | No |
| 4 | Calcineurin inhibitor | T-cell | Tier 2 | 6.4 | 45 | 58% | 2 | No |
| 5 | Anti-IL-6 | IL-6 signaling | Tier 3 | 5.1 | 8 | 62% | 1 | No |

### Pathway Convergence Analysis

| Pathway | Mechanisms | Combined N | Combined RR | Strength |
|---------|-----------|------------|-------------|----------|
| **Type I IFN** | JAK inhibitors, IFNAR blockers | 121 | 75% | **HIGH** |
| B-cell | Anti-CD20, Anti-CD19 | 168 | 66% | MEDIUM |
| T-cell | CNI, CTLA4-Ig | 58 | 52% | LOW |

### Interpretation
Strong convergent evidence supporting Type I interferon pathway as key driver in dermatomyositis. Both JAK inhibitors (which reduce IFN-stimulated gene expression) and direct IFNAR blockers show consistent efficacy. This aligns with known disease biology (IFN gene signature in DM skin/muscle). B-cell depletion also effective but may be through different mechanism (autoantibody reduction vs IFN pathway).

---

*Document Version: 1.0*
*Last Updated: [Date]*
*Related Documents: CaseSeriesAnalysis_v1.md, DrugExtractionAgent.md*
