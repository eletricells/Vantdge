# Testing Checklist - New Features

**Use this checklist to verify all new features are working correctly**

---

## 🚀 Pre-Testing Setup

### Environment Check:
- [ ] Streamlit is installed (`pip install streamlit`)
- [ ] Plotly is installed (`pip install plotly`)
- [ ] Anthropic is installed (`pip install anthropic`)
- [ ] ANTHROPIC_API_KEY is set in environment variables
- [ ] PostgreSQL database is running
- [ ] All dependencies are up to date

### Data Check:
- [ ] `data/case_series/iptacopan_report_20251208_004224.xlsx` exists
- [ ] `data/case_series/iptacopan_full_20251208_004224.json` exists
- [ ] Database has historical runs (check with Tab 6)
- [ ] No temporary Excel files (~$) in data/case_series/

---

## 📊 Feature 1: Interactive Visualizations

### Tab 4 - Scoring & Results:
- [ ] Navigate to Tab 4
- [ ] Load opportunities (if not already loaded)
- [ ] Click "Score Opportunities" button
- [ ] Verify Priority Matrix chart appears
- [ ] Verify Market Opportunity chart appears
- [ ] Hover over bubbles - tooltips should show details
- [ ] Bubbles should be sized by patient count
- [ ] Colors should indicate priority/unmet need
- [ ] High priority zone should be highlighted
- [ ] Disease names should be abbreviated (TA-TMA, MPGN, etc.)

### Tab 5 - Full Analysis:
- [ ] Navigate to Tab 5
- [ ] Run full analysis (or use existing results)
- [ ] Scroll to results summary section
- [ ] Verify Priority Matrix chart appears
- [ ] Verify Market Opportunity chart appears
- [ ] Charts should match data in opportunities table
- [ ] Hover tooltips should work
- [ ] Charts should be interactive (zoom, pan)

### Tab 6 - Analysis Browser:
- [ ] Navigate to Tab 6
- [ ] Select a drug and run
- [ ] Click "View Full Report"
- [ ] Scroll to visualizations section
- [ ] Verify Priority Matrix chart appears
- [ ] Verify Market Opportunity chart appears
- [ ] Charts should match historical run data
- [ ] All interactive features should work

### Error Cases:
- [ ] No opportunities - should show message, not error
- [ ] Missing columns - should handle gracefully
- [ ] Empty DataFrame - should show message

---

## 🎯 Feature 2: Enhanced Analysis Browser

### Basic Navigation:
- [ ] Navigate to Tab 6
- [ ] Verify "Analysis Browser" title appears
- [ ] Verify table of historical runs appears
- [ ] Table should show: Drug, Date, Opportunities, Status

### Full Report View:
- [ ] Select a run from dropdown
- [ ] Click "View Full Report" button
- [ ] Verify drug information header appears
- [ ] Verify summary metrics appear (4 metrics)
- [ ] Verify visualizations appear
- [ ] Verify opportunities table appears
- [ ] Verify export options appear
- [ ] Verify report generation section appears

### Export Options:
- [ ] Click "Download Excel Report" button
- [ ] Verify Excel file downloads
- [ ] Open Excel file - verify all sheets present
- [ ] Click "Download JSON Export" button
- [ ] Verify JSON file downloads
- [ ] Open JSON file - verify structure is correct
- [ ] Click "Download CSV Export" button
- [ ] Verify CSV file downloads
- [ ] Open CSV file - verify data is correct

### Load to Session:
- [ ] Click "Load into Session" button
- [ ] Verify success message appears
- [ ] Navigate to Tab 5
- [ ] Verify data is loaded in current session

### Close Report:
- [ ] Click "Close Report" button
- [ ] Verify report view closes
- [ ] Verify back to run selection view

---

## 📋 Feature 3: Dropdown Selection System

### Drug Dropdown:
- [ ] Navigate to Tab 6
- [ ] Verify "📊 Select Drug" dropdown appears
- [ ] Dropdown should show all unique drugs
- [ ] Drugs should be alphabetically sorted
- [ ] Select a drug (e.g., "iptacopan")
- [ ] Verify second dropdown updates

### Run Dropdown:
- [ ] Verify "📅 Select Run" dropdown appears
- [ ] Dropdown should show only runs for selected drug
- [ ] Run labels should show: status emoji + date + opportunity count
- [ ] Example: "✅ 2025-12-08 00:42 (9 opps)"
- [ ] Status emojis should be correct:
  - ✅ for successful runs
  - ⚠️ for failed runs
  - 🔄 for in-progress runs
- [ ] Select a run
- [ ] Verify action buttons become enabled

### Action Buttons:
- [ ] Verify three buttons appear:
  - "📋 View Details (JSON)"
  - "📊 View Full Report"
  - "📥 Quick Load to Session"
- [ ] Buttons should be disabled until run is selected
- [ ] Click "View Details" - JSON should display
- [ ] Click "View Full Report" - full report should display
- [ ] Click "Quick Load" - data should load to session

### Edge Cases:
- [ ] No drug selected - run dropdown should be empty
- [ ] No run selected - action buttons should be disabled
- [ ] Switch drugs - run dropdown should update
- [ ] Switch runs - report should update

---

## 📄 Feature 4: Analytical Report Generation

### Tab 5 - Report Generation:
- [ ] Navigate to Tab 5
- [ ] Run full analysis (or use existing results)
- [ ] Scroll to "Generate Analytical Report" section
- [ ] Verify section header appears
- [ ] Verify description text appears
- [ ] Verify "🤖 Generate Report with Claude" button appears
- [ ] Verify cost estimate appears (~$0.10-0.20)
- [ ] Verify time estimate appears (1-2 min)
- [ ] Click "Generate Report with Claude" button
- [ ] Verify spinner appears with message
- [ ] Wait 1-2 minutes for generation
- [ ] Verify success message appears
- [ ] Verify report path is shown
- [ ] Verify "📥 Download Report" button appears
- [ ] Verify expandable report viewer appears
- [ ] Expand report viewer - verify report displays
- [ ] Click download button - verify markdown file downloads

### Tab 6 - Report Generation:
- [ ] Navigate to Tab 6
- [ ] Select a drug and run
- [ ] Click "View Full Report"
- [ ] Scroll to "Generate Analytical Report" section
- [ ] Verify all UI elements appear (same as Tab 5)
- [ ] Click "Generate Report with Claude" button
- [ ] Verify report generates successfully
- [ ] Verify report displays and downloads

### Report Content:
- [ ] Open generated markdown file
- [ ] Verify 8 sections are present:
  1. Executive Summary
  2. Mechanism and Biological Rationale
  3. Indication-by-Indication Analysis
  4. Cross-Indication Concordance Analysis
  5. Evidence Quality Assessment
  6. Competitive Landscape Analysis
  7. Limitations and Uncertainties
  8. Appendix: Methodology
- [ ] Verify report includes specific data citations
- [ ] Verify report includes score derivations
- [ ] Verify report includes concordance analysis
- [ ] Verify report is ~3500-4500 words
- [ ] Verify markdown formatting is correct

### Error Cases:
- [ ] No Excel file - should show error message
- [ ] API key missing - should show error message
- [ ] API error - should show error message with details
- [ ] Network error - should handle gracefully

---

## 🔄 Integration Testing

### Full Workflow Test:
- [ ] Start Streamlit
- [ ] Navigate to Tab 1 - enter drug name
- [ ] Navigate to Tab 2 - run search
- [ ] Navigate to Tab 3 - filter papers
- [ ] Navigate to Tab 4 - score opportunities
- [ ] Verify visualizations appear
- [ ] Navigate to Tab 5 - run full analysis
- [ ] Verify visualizations appear
- [ ] Generate report
- [ ] Verify report generates successfully
- [ ] Navigate to Tab 6 - find the run
- [ ] View full report
- [ ] Verify all data matches
- [ ] Generate report again
- [ ] Verify report is consistent

### Multiple Runs Test:
- [ ] Run analysis for Drug A
- [ ] Run analysis for Drug B
- [ ] Navigate to Tab 6
- [ ] Verify both drugs appear in dropdown
- [ ] Select Drug A - verify runs appear
- [ ] Select Drug B - verify runs appear
- [ ] View report for Drug A run
- [ ] View report for Drug B run
- [ ] Verify no data mixing between runs

### Session State Test:
- [ ] Load run A into session
- [ ] Navigate to Tab 5
- [ ] Verify data is from run A
- [ ] Navigate to Tab 6
- [ ] Load run B into session
- [ ] Navigate to Tab 5
- [ ] Verify data is now from run B
- [ ] Verify no conflicts or errors

---

## 📊 Performance Testing

### Visualization Performance:
- [ ] Load large dataset (>20 opportunities)
- [ ] Verify charts render in <2 seconds
- [ ] Verify hover tooltips are responsive
- [ ] Verify zoom/pan is smooth

### Report Generation Performance:
- [ ] Generate report for small dataset (<5 opportunities)
- [ ] Verify generation time is <1 minute
- [ ] Generate report for large dataset (>10 opportunities)
- [ ] Verify generation time is <2 minutes
- [ ] Verify cost is within expected range

### Browser Performance:
- [ ] Load browser with >10 historical runs
- [ ] Verify dropdown populates quickly
- [ ] Verify report view loads in <1 second
- [ ] Verify no lag when switching between runs

---

## ✅ Final Verification

### Code Quality:
- [ ] No errors in Streamlit terminal
- [ ] No errors in browser console
- [ ] No warnings in logs
- [ ] All imports resolve correctly
- [ ] All file paths are correct

### User Experience:
- [ ] All buttons have clear labels
- [ ] All sections have clear headers
- [ ] All error messages are helpful
- [ ] All success messages are clear
- [ ] All tooltips are informative

### Documentation:
- [ ] All features are documented
- [ ] All code has comments
- [ ] All functions have docstrings
- [ ] All files have headers

---

## 🎉 Success Criteria

**All features pass when:**

✅ All visualizations render correctly  
✅ All dropdowns work smoothly  
✅ All reports generate successfully  
✅ All exports work correctly  
✅ No errors in terminal or console  
✅ Performance is acceptable  
✅ User experience is smooth  

---

**If all checkboxes are checked, the implementation is complete and ready for production! 🚀**

