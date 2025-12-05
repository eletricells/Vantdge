# Quick Start Guide

## 1. Install Dependencies (30 seconds)

```bash
pip install anthropic requests pandas openpyxl python-dotenv
```

## 2. Set API Keys (1 minute)

Get your API keys:
- **Anthropic**: https://console.anthropic.com/
- **Tavily**: https://tavily.com/

Set them as environment variables:

```bash
export ANTHROPIC_API_KEY="your-anthropic-key"
export TAVILY_API_KEY="your-tavily-key"
```

Or create a `.env` file:

```bash
ANTHROPIC_API_KEY=your-anthropic-key
TAVILY_API_KEY=your-tavily-key
```

## 3. Run Analysis (2 minutes)

### Option A: Single Drug

```python
from drug_repurposing_agent import DrugRepurposingAgent
import os

agent = DrugRepurposingAgent(
    anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
    tavily_api_key=os.getenv("TAVILY_API_KEY")
)

# Analyze rimegepant
results = agent.analyze_drug("rimegepant")

# Export to Excel
agent.export_to_excel(results, "rimegepant_analysis.xlsx")

print(f"Found {len(results['case_series'])} opportunities!")
```

### Option B: Mechanism

```python
from mechanism_based_agent import MechanismBasedAgent
import os

agent = MechanismBasedAgent(
    anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
    tavily_api_key=os.getenv("TAVILY_API_KEY")
)

# Analyze all CGRP antagonists
results = agent.analyze_mechanism("CGRP receptor antagonist")

# Export comprehensive analysis
agent.export_mechanism_analysis(results, "cgrp_analysis.xlsx")

print(f"Analyzed {len(results['drugs_analyzed'])} drugs!")
```

### Option C: Interactive Examples

```bash
python examples.py
```

Then select from the menu:
1. Single Drug Analysis
2. Mechanism-Based Analysis
3. Batch Drug Analysis
4. High-Priority Only
5. Custom Scoring
6. Therapeutic Area Focus

## 4. Review Results

Open the generated Excel file:
- **Main sheet**: All opportunities ranked by priority
- **Metadata sheet**: Statistics and costs
- **Additional sheets**: Individual drug breakdowns (mechanism analysis)

## What Gets Analyzed

For each repurposing opportunity:
- ✓ Clinical evidence (N, response rate, efficacy, safety)
- ✓ Market size (US prevalence)
- ✓ Standard of care (top 3 treatments and efficacy)
- ✓ Competitive landscape
- ✓ Priority scores (clinical, evidence, market, feasibility)

## Expected Costs

- **Single drug**: $0.50 - $2.00
- **Mechanism (3 drugs)**: $2.00 - $6.00
- **Batch (5 drugs)**: $3.00 - $10.00

Depends on number of case series found.

## Tips

✓ **Start small**: Test with one drug first  
✓ **Use generic names**: "rimegepant" not "Nurtec"  
✓ **Check costs**: Monitor `agent.total_input_tokens`  
✓ **Validate findings**: Review source papers directly  
✓ **Filter results**: Focus on priority score ≥ 7.0  

## Common Issues

**"No results found"**
→ Try alternative drug names or check spelling

**"API rate limit"**
→ Add `time.sleep(1)` between analyses

**"Import error"**
→ Run `pip install -r requirements.txt`

## Next Steps

1. Read full [README.md](README.md) for detailed documentation
2. Review [examples.py](examples.py) for advanced usage
3. Customize scoring in `_score_opportunity()`
4. Add custom data sources (ClinicalTrials.gov, etc.)

## Support

Questions? Check the README or open an issue.

---

**Ready to discover repurposing opportunities?**

```bash
python examples.py
```
