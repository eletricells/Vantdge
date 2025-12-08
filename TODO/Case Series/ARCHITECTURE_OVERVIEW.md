# Architecture Overview - New Features

**Visual guide to understanding the new features and how they fit together**

---

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     STREAMLIT FRONTEND                          │
│                 (15_Case_Study_Analysis_v2.py)                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Tab 4: Scoring & Results                                      │
│  ├─ Scoring button                                             │
│  └─ 📊 Visualizations (Priority Matrix + Market Opportunity)   │
│                                                                 │
│  Tab 5: Full Analysis                                          │
│  ├─ Run full analysis button                                   │
│  ├─ 📊 Visualizations                                          │
│  ├─ 📥 Export options (Excel, JSON, CSV)                       │
│  └─ 🤖 Report generation                                       │
│                                                                 │
│  Tab 6: Analysis Browser                                       │
│  ├─ 📊 Drug dropdown (Select Drug)                            │
│  ├─ 📅 Run dropdown (Select Run)                              │
│  ├─ 📋 View Details / 📊 View Full Report / 📥 Quick Load     │
│  ├─ 📊 Visualizations                                          │
│  ├─ 📥 Export options                                          │
│  └─ 🤖 Report generation                                       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ calls
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    AGENT LAYER                                  │
│          (drug_repurposing_case_series_agent.py)                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  analyze_drug()                                                 │
│  ├─ Search for papers                                          │
│  ├─ Extract data                                               │
│  ├─ Score opportunities                                        │
│  └─ Return AnalysisResult                                      │
│                                                                 │
│  generate_analytical_report()  ← NEW                           │
│  ├─ Format data (Excel or Result)                             │
│  ├─ Generate prompt                                            │
│  ├─ Call Claude API                                            │
│  └─ Save report to markdown                                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ uses
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   SUPPORT MODULES                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  src/visualization/case_series_charts.py  ← NEW                │
│  ├─ render_priority_matrix()                                   │
│  ├─ render_market_opportunity()                                │
│  └─ shorten_disease()                                          │
│                                                                 │
│  src/reports/case_series_report_generator.py  ← NEW            │
│  ├─ format_data_from_excel()                                   │
│  ├─ format_data_from_result()                                  │
│  ├─ generate_prompt()                                          │
│  ├─ generate_report()                                          │
│  └─ save_report()                                              │
│                                                                 │
│  src/prompts/templates/case_series_report_template.txt  ← NEW  │
│  └─ 302-line prompt template for Claude                        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ outputs
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      DATA OUTPUTS                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  data/case_series/                                             │
│  ├─ {drug}_report_{timestamp}.xlsx  (Excel export)            │
│  └─ {drug}_full_{timestamp}.json    (JSON export)             │
│                                                                 │
│  data/reports/  ← NEW                                          │
│  └─ {drug}_report_{timestamp}.md    (Markdown report)         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🔄 Data Flow

### Flow 1: Full Analysis with Visualizations

```
User clicks "Run Full Analysis"
    ↓
Agent.analyze_drug()
    ↓
AnalysisResult object created
    ↓
Excel export generated
    ↓
DataFrame loaded from result
    ↓
render_priority_matrix(df) → Plotly chart
render_market_opportunity(df) → Plotly chart
    ↓
Charts displayed in Streamlit
```

### Flow 2: Report Generation

```
User clicks "Generate Report with Claude"
    ↓
Agent.generate_analytical_report()
    ↓
CaseSeriesReportGenerator.format_data()
    ↓
Load Excel or Result → Format to markdown tables
    ↓
CaseSeriesReportGenerator.generate_prompt()
    ↓
Load template → Fill placeholders → Create prompt
    ↓
CaseSeriesReportGenerator.generate_report()
    ↓
Call Claude API → Generate report text
    ↓
CaseSeriesReportGenerator.save_report()
    ↓
Save to data/reports/{drug}_report_{timestamp}.md
    ↓
Display in Streamlit + Download button
```

### Flow 3: Analysis Browser

```
User selects drug from dropdown
    ↓
Query database for runs with that drug
    ↓
Populate second dropdown with runs
    ↓
User selects specific run
    ↓
User clicks "View Full Report"
    ↓
Load AnalysisResult from database
    ↓
Display summary metrics
    ↓
Render visualizations
    ↓
Show opportunities table
    ↓
Provide export options
    ↓
Provide report generation option
```

---

## 📊 Component Relationships

### Visualization Components

```
case_series_charts.py
├─ render_priority_matrix()
│  ├─ Input: DataFrame with opportunities
│  ├─ Groups by: disease_name
│  ├─ Aggregates: clinical_score, evidence_score, total_patients
│  ├─ Creates: Plotly scatter plot
│  └─ Output: Interactive bubble chart
│
├─ render_market_opportunity()
│  ├─ Input: DataFrame with opportunities
│  ├─ Groups by: disease_name
│  ├─ Aggregates: competitive_landscape_score, priority_score, tam_estimate
│  ├─ Creates: Plotly scatter plot
│  └─ Output: Interactive bubble chart
│
└─ shorten_disease()
   ├─ Input: Disease name string
   ├─ Applies: Abbreviation rules
   └─ Output: Shortened name (e.g., "TA-TMA", "MPGN")
```

### Report Generation Components

```
case_series_report_generator.py
├─ CaseSeriesReportGenerator
│  ├─ __init__(client, model)
│  │  └─ Initialize with Anthropic client
│  │
│  ├─ format_data_from_excel(excel_path)
│  │  ├─ Load Excel file with pandas
│  │  ├─ Read all sheets (Analysis Summary, Opportunities, etc.)
│  │  ├─ Convert to markdown tables
│  │  └─ Return formatted data dict
│  │
│  ├─ format_data_from_result(result)
│  │  ├─ Extract data from AnalysisResult object
│  │  ├─ Group opportunities by disease
│  │  ├─ Create markdown tables
│  │  └─ Return formatted data dict
│  │
│  ├─ generate_prompt(data)
│  │  ├─ Load template from file
│  │  ├─ Fill placeholders with data
│  │  └─ Return complete prompt
│  │
│  ├─ generate_report(data, max_tokens)
│  │  ├─ Create Anthropic client if needed
│  │  ├─ Call messages.create() with prompt
│  │  └─ Return report text
│  │
│  ├─ save_report(report_text, output_path, drug_name)
│  │  ├─ Generate filename with timestamp
│  │  ├─ Create directories if needed
│  │  ├─ Write to file
│  │  └─ Return saved path
│  │
│  └─ generate_and_save_report(...)
│     ├─ Call format_data()
│     ├─ Call generate_report()
│     ├─ Call save_report()
│     └─ Return (report_text, saved_path)
```

---

## 🎨 UI Component Layout

### Tab 5: Full Analysis

```
┌─────────────────────────────────────────────────────────┐
│ 🎯 Full Analysis                                        │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ [Run Full Analysis Button]                             │
│                                                         │
│ ─────────────────────────────────────────────────────── │
│                                                         │
│ 📊 Analysis Summary                                     │
│ • Total Opportunities: 9                                │
│ • High Priority: 3                                      │
│ • Average Score: 7.1                                    │
│ • Unique Indications: 4                                 │
│                                                         │
│ ─────────────────────────────────────────────────────── │
│                                                         │
│ 📊 Interactive Visualizations                           │
│                                                         │
│ [Priority Matrix Chart]                                 │
│ Clinical Score vs Evidence Score                        │
│                                                         │
│ [Market Opportunity Chart]                              │
│ Competitive Landscape vs Priority Score                 │
│                                                         │
│ ─────────────────────────────────────────────────────── │
│                                                         │
│ 📥 Export Options                                       │
│ [Download Excel] [Download JSON] [Download CSV]         │
│                                                         │
│ ─────────────────────────────────────────────────────── │
│                                                         │
│ 📄 Generate Analytical Report                           │
│                                                         │
│ [🤖 Generate Report with Claude]                       │
│ 💰 Cost: ~$0.10-0.20  ⏱️ Time: 1-2 min                 │
│                                                         │
│ [📥 Download Report]                                    │
│                                                         │
│ ▼ 📄 View Full Report                                   │
│   [Report content displayed here]                       │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### Tab 6: Analysis Browser

```
┌─────────────────────────────────────────────────────────┐
│ 📊 Analysis Browser                                     │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ 📊 Select Drug:  [iptacopan ▼]                         │
│                                                         │
│ 📅 Select Run:   [✅ 2025-12-08 00:42 (9 opps) ▼]     │
│                                                         │
│ [📋 View Details] [📊 View Full Report] [📥 Quick Load]│
│                                                         │
│ ─────────────────────────────────────────────────────── │
│                                                         │
│ 📊 Full Report View                                     │
│                                                         │
│ Drug: iptacopan                                         │
│ Generic: iptacopan                                      │
│ Mechanism: Alternative complement pathway inhibitor     │
│                                                         │
│ Summary Metrics:                                        │
│ • Total Opportunities: 9                                │
│ • High Priority: 3                                      │
│ • Average Score: 7.1                                    │
│ • Unique Indications: 4                                 │
│                                                         │
│ [Priority Matrix Chart]                                 │
│ [Market Opportunity Chart]                              │
│                                                         │
│ Top 10 Opportunities Table                              │
│ [Table with scores and response rates]                  │
│                                                         │
│ 📥 Export Options                                       │
│ [Download Excel] [Download JSON] [Download CSV]         │
│                                                         │
│ 📄 Generate Analytical Report                           │
│ [🤖 Generate Report with Claude]                       │
│ [📥 Download Report]                                    │
│                                                         │
│ [Close Report]                                          │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## 🔗 Integration Points

### Where Visualizations Are Used:
1. **Tab 4** - After scoring button (if opportunities exist)
2. **Tab 5** - In results summary section (after full analysis)
3. **Tab 6** - In full report view (for historical runs)

### Where Report Generation Is Used:
1. **Tab 5** - After export options (uses Excel file)
2. **Tab 6** - In full report view (uses AnalysisResult object)

### Where Dropdown Is Used:
1. **Tab 6** - At top of Analysis Browser (drug + run selection)

---

## 📦 Module Dependencies

```
frontend/pages/15_Case_Study_Analysis_v2.py
├─ imports src.agents.drug_repurposing_case_series_agent
├─ imports src.visualization.case_series_charts
└─ imports src.reports.case_series_report_generator (indirectly via agent)

src/agents/drug_repurposing_case_series_agent.py
└─ imports src.reports.case_series_report_generator

src/reports/case_series_report_generator.py
├─ imports anthropic (Claude API)
├─ imports pandas (data manipulation)
└─ loads src/prompts/templates/case_series_report_template.txt

src/visualization/case_series_charts.py
├─ imports plotly.express (charts)
├─ imports plotly.graph_objects (annotations)
└─ imports pandas (data manipulation)
```

---

**This architecture is modular, maintainable, and extensible! 🚀**

