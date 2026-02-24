# Badenoch vs Lewis: Two Fixes for Plan 2 Student Loans

Martin Lewis and Kemi Badenoch agree Plan 2 is broken but propose different fixes. Following their [clash on GMB](https://www.theguardian.com/money/2025/feb/20/why-the-student-loans-row-is-escalating-and-what-it-means-for-graduates), this analysis simulates lifetime repayment under each proposed fix to quantify who benefits.

## The two fixes

| | Status quo (current Plan 2) | Badenoch fix | Lewis fix |
|---|---|---|---|
| **Repayment threshold** | £29,385 | £29,385 | £40,000 |
| **Interest rate** | RPI + up to 3% (sliding scale) | RPI only (flat) | RPI + up to 3% (sliding scale) |
| **Threshold indexation** | Frozen 2027–2029, RPI from 2030 | Frozen 2027–2029, RPI from 2030 | RPI-indexed from 2027 (no freeze) |
| **Write-off period** | 30 years | 30 years | 30 years |
| **Repayment rate** | 9% above threshold | 9% above threshold | 9% above threshold |

- **Badenoch** wants to cap Plan 2 interest at RPI only, removing the +3% sliding scale that penalises higher earners.
- **Lewis** wants to raise the repayment threshold to £40k and index it annually, undoing the freeze that drags in lower earners.

## Key findings

**The Badenoch fix (interest cap) primarily helps higher earners.** Those on £50k+ starting salaries see the biggest reduction in lifetime repayment, because they're the ones hit hardest by the RPI+3% interest rate. Lower earners — whose loans are written off anyway — barely notice the change.

**The Lewis fix (threshold raise) primarily helps low and middle earners.** Raising the threshold to £40k means graduates earning below that pay nothing, and those just above it pay far less per year. Higher earners, who comfortably clear their loans either way, see little difference.

**The two fixes are near-complementary** — they target opposite ends of the income distribution.

## How it works

The model (`policy_comparison.py`) does the following:

1. **Defines three scenarios** — status quo, Badenoch fix (RPI-only interest), Lewis fix (£40k threshold, indexed)
2. **Simulates year-by-year loan repayment** for each scenario, accounting for salary growth (3.5%/yr), OBR RPI forecasts, and threshold indexation rules
3. **Sweeps across starting salaries** (£20k–£120k) to show how outcomes vary by earnings
4. **Generates two interactive chart panels** as HTML (with hover) and static PNGs

### Assumptions

- £45,000 loan balance (typical Plan 2 graduate)
- 3.5% annual salary growth
- OBR RPI forecasts (2024–2029), then 2.39% long-term
- 30-year write-off for all three scenarios

## Running

```bash
pip install -r requirements.txt
python policy_comparison.py
```

Outputs saved to `results/` (interactive HTML + static PNG):
- `results/panel_salary.html` / `.png` — total lifetime repayment by starting salary (3 lines)
- `results/panel_years.html` / `.png` — years of repayment by starting salary (3 lines)

## Media context

- [Martin Lewis clashes with Kemi Badenoch over student loan reforms (The Guardian)](https://www.theguardian.com/money/2025/feb/20/martin-lewis-apologises-to-kemi-badenoch-after-gate-crashing-interview)
- [Why the student loans row is escalating (The Guardian)](https://www.theguardian.com/money/2025/feb/20/why-the-student-loans-row-is-escalating-and-what-it-means-for-graduates)
- [Badenoch clashes with Martin Lewis over student loan reforms (Evening Standard)](https://www.standard.co.uk/news/politics/badenoch-clashes-martin-lewis-student-loan-reforms-b1212817.html)
- [Martin Lewis apologises after gatecrashing Badenoch interview (The Independent)](https://www.independent.co.uk/news/uk/politics/martin-lewis-kemi-badenoch-student-loans-b2702841.html)

## Built with

- Python, NumPy, pandas, Plotly
