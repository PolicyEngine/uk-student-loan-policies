"""
Badenoch vs Lewis: Two Fixes for Plan 2 Student Loans

Martin Lewis and Kemi Badenoch agree Plan 2 is broken but propose different fixes:
- Badenoch: Cap interest at RPI only (remove the +3% sliding scale)
- Lewis: Raise the repayment threshold to £40k and index it (undo the freeze)

These two levers help completely different segments of the income distribution.
This analysis simulates three scenarios — current system, Badenoch fix, Lewis fix —
across the salary range to quantify who benefits.

Run with: conda activate python313 && python policy_comparison.py
"""

import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import plotly.express as px
from policyengine_uk import CountryTaxBenefitSystem

# ── Load Plan 2 baseline from PolicyEngine UK ────────────────────────────────
YEAR = 2026

print("Loading PolicyEngine UK parameters...")
tbs = CountryTaxBenefitSystem()
params = tbs.parameters
date = f"{YEAR}-01-01"
sl = params.gov.hmrc.student_loans

_threshold = sl.thresholds.plan_2(date)
_repayment_rate = sl.repayment_rate(date)

try:
    _interest_min = sl.interest.plan_2.rate_below_threshold(date)  # RPI
    _interest_max = sl.interest.plan_2.rate_above_threshold(date)  # RPI+3%
except (AttributeError, KeyError):
    _interest_min = 0.045
    _interest_max = 0.078

INTEREST_UPPER = 49_530  # SLC upper earnings threshold for Plan 2 interest

# OBR RPI forecasts
RPI_FORECASTS = {
    2024: 0.0331, 2025: 0.0416, 2026: 0.0308,
    2027: 0.0300, 2028: 0.0283, 2029: 0.0283,
}
RPI_LONG_TERM = 0.0239

SALARY_GROWTH = 0.035
LOAN_BALANCE = 45_000


def get_rpi(year):
    return RPI_FORECASTS.get(year, RPI_LONG_TERM)


def sliding_interest(salary, threshold):
    """Plan 2 sliding-scale interest: RPI at threshold, RPI+3% at upper."""
    if salary <= threshold:
        return _interest_min
    if salary >= INTEREST_UPPER:
        return _interest_max
    return _interest_min + (_interest_max - _interest_min) * (
        (salary - threshold) / (INTEREST_UPPER - threshold)
    )


def rpi_only_interest(salary, threshold):
    """Badenoch fix: flat RPI interest regardless of income."""
    return _interest_min


# ── Three scenarios (all Plan 2, 30yr writeoff, 9% repayment rate) ───────────

STATUS_QUO = {
    "name": "Current system",
    "threshold": _threshold,           # £29,385
    "repayment_rate": _repayment_rate,
    "writeoff_years": 30,
    "interest_fn": sliding_interest,
    "threshold_index_from": 2030,       # frozen 2027-2029, RPI from 2030
}

BADENOCH = {
    "name": "Badenoch fix (cap interest)",
    "threshold": _threshold,           # £29,385
    "repayment_rate": _repayment_rate,
    "writeoff_years": 30,
    "interest_fn": rpi_only_interest,
    "threshold_index_from": 2030,       # same freeze as current system
}

LEWIS = {
    "name": "Lewis fix (raise threshold)",
    "threshold": 40_000,
    "repayment_rate": _repayment_rate,
    "writeoff_years": 30,
    "interest_fn": sliding_interest,    # keeps sliding scale
    "threshold_index_from": 2027,       # indexed from 2027 (no freeze)
}

SCENARIOS = [STATUS_QUO, BADENOCH, LEWIS]

print(f"\nPolicyEngine UK parameters ({YEAR}):")
print(f"  Plan 2 threshold: £{_threshold:,.0f}")
print(f"  Interest range: {_interest_min*100:.1f}% – {_interest_max*100:.1f}%")
print(f"  Repayment rate: {_repayment_rate*100:.0f}%")
print(f"\nThree scenarios:")
for sc in SCENARIOS:
    print(f"  {sc['name']}: threshold £{sc['threshold']:,.0f}, "
          f"indexed from {sc['threshold_index_from']}, "
          f"interest={'sliding' if sc['interest_fn'] is sliding_interest else 'RPI only'}")


# ── Simulation engine ────────────────────────────────────────────────────────

def simulate_lifetime(starting_salary, loan_balance, plan_params):
    """Simulate year-by-year loan repayment. Returns dict with lifetime metrics."""
    balance = loan_balance
    total_repaid = 0
    total_interest = 0
    salary = starting_salary
    threshold = plan_params["threshold"]
    writeoff = plan_params["writeoff_years"]
    rate = plan_params["repayment_rate"]
    interest_fn = plan_params["interest_fn"]
    index_from = plan_params["threshold_index_from"]
    years_repaying = 0

    for yr in range(1, writeoff + 1):
        if balance <= 0:
            break

        cal_year = YEAR + yr

        # Threshold indexation
        if cal_year >= index_from:
            threshold *= 1 + get_rpi(cal_year)

        # Repayment
        repayment = max(0, (salary - threshold) * rate)
        actual = min(repayment, balance)
        balance -= actual
        total_repaid += actual
        if actual > 0:
            years_repaying = yr

        # Interest on remaining balance
        interest = interest_fn(salary, threshold) * balance
        balance += interest
        total_interest += interest

        salary *= 1 + SALARY_GROWTH

    paid_off = balance <= 0
    return {
        "total_repaid": total_repaid,
        "total_interest": total_interest,
        "paid_off": paid_off,
        "years_repaying": years_repaying if paid_off else writeoff,
        "balance_at_end": max(0, balance),
        "written_off": max(0, balance) if not paid_off else 0,
    }


def simulate_yearly(starting_salary, loan_balance, plan_params, max_years=40):
    """Simulate year-by-year loan repayment. Returns list of annual repayments."""
    balance = loan_balance
    salary = starting_salary
    threshold = plan_params["threshold"]
    writeoff = plan_params["writeoff_years"]
    rate = plan_params["repayment_rate"]
    interest_fn = plan_params["interest_fn"]
    index_from = plan_params["threshold_index_from"]
    yearly = []

    for yr in range(1, max_years + 1):
        # After writeoff, balance is wiped — no more repayments
        if yr > writeoff or balance <= 0:
            yearly.append({"year": yr, "annual_repayment": 0, "balance": 0})
            salary *= 1 + SALARY_GROWTH
            continue

        cal_year = YEAR + yr
        if cal_year >= index_from:
            threshold *= 1 + get_rpi(cal_year)

        repayment = max(0, (salary - threshold) * rate)
        actual = min(repayment, balance)
        balance -= actual

        interest = interest_fn(salary, threshold) * balance
        balance += interest

        yearly.append({"year": yr, "annual_repayment": actual, "balance": max(0, balance)})
        salary *= 1 + SALARY_GROWTH

    return yearly


# ── 1. Salary sweep ─────────────────────────────────────────────────────────
print("\nSimulating lifetime repayments across salary range...")

salaries = np.arange(20_000, 120_001, 100)
results_by_salary = []

for sal in salaries:
    row = {"salary": sal}
    for sc in SCENARIOS:
        key = sc["name"].split()[0].lower()  # "status", "badenoch", "lewis"
        r = simulate_lifetime(sal, LOAN_BALANCE, sc)
        row[f"{key}_repaid"] = r["total_repaid"]
        row[f"{key}_years"] = r["years_repaying"]
        row[f"{key}_paid_off"] = r["paid_off"]
        row[f"{key}_written_off"] = r["written_off"]
    results_by_salary.append(row)

salary_df = pd.DataFrame(results_by_salary)


# ── 2. Typical graduate profiles ─────────────────────────────────────────────
print("\n=== Typical Graduate Profiles ===")
profiles = [
    ("Low earner", 25_000),
    ("Median graduate", 30_000),
    ("Above median", 40_000),
    ("Higher earner", 55_000),
]

for label, sal in profiles:
    print(f"\n  {label} (£{sal:,} starting salary):")
    for sc in SCENARIOS:
        r = simulate_lifetime(sal, LOAN_BALANCE, sc)
        status = "(paid off)" if r["paid_off"] else f"(£{r['written_off']:,.0f} written off)"
        print(f"    {sc['name']}: repays £{r['total_repaid']:,.0f} over {r['years_repaying']} years {status}")


# ── 4. Charts ────────────────────────────────────────────────────────────────
import os
RESULTS_DIR = "results"
os.makedirs(RESULTS_DIR, exist_ok=True)

SLATE = "#94a3b8"   # Current system
TEAL = "#319795"     # Badenoch (interest cap)
AMBER = "#F59E0B"    # Lewis (threshold raise)

PLOT_LABELS = {
    "status": "Current system",
    "badenoch": "Cap interest at RPI",
    "lewis": "Raise threshold to £40k",
}

COLOR_MAP = {
    "Current system": SLATE,
    "Cap interest at RPI": TEAL,
    "Raise threshold to £40k": AMBER,
}

LAYOUT_COMMON = dict(
    plot_bgcolor="white",
    paper_bgcolor="white",
    font=dict(family="Roboto, Helvetica Neue, Arial, sans-serif", color="#1e293b"),
    xaxis=dict(gridcolor="#f1f5f9", linecolor="#cbd5e1"),
    yaxis=dict(gridcolor="#f1f5f9", linecolor="#cbd5e1"),
    legend=dict(bgcolor="rgba(255,255,255,0.95)", bordercolor="#e2e8f0", borderwidth=1),
)

# ── Panel 1: Total lifetime repayment by starting salary ──
salary_long = salary_df.melt(
    id_vars=["salary"],
    value_vars=["current_repaid", "badenoch_repaid", "lewis_repaid"],
    var_name="scenario",
    value_name="total_repaid",
)
salary_long["scenario"] = salary_long["scenario"].map({
    "current_repaid": "Current system",
    "badenoch_repaid": "Cap interest at RPI",
    "lewis_repaid": "Raise threshold to £40k",
})
salary_long["salary_k"] = salary_long["salary"] / 1000
salary_long["repaid_k"] = salary_long["total_repaid"] / 1000

fig_salary = px.line(
    salary_long,
    x="salary_k",
    y="repaid_k",
    color="scenario",
    color_discrete_map=COLOR_MAP,
    labels={"salary_k": "Graduate starting salary (£k)", "repaid_k": "Total lifetime repayment (£k)", "scenario": "Scenario"},
    title=f"Total lifetime repayment (£{LOAN_BALANCE // 1000}k loan, Plan 2)",
    custom_data=["salary", "total_repaid"],
)
fig_salary.update_traces(
    line=dict(width=2.5),
    hovertemplate="Salary: £%{customdata[0]:,.0f}<br>Total repaid: £%{customdata[1]:,.0f}<extra>%{fullData.name}</extra>",
)
fig_salary.add_hline(
    y=LOAN_BALANCE / 1000, line_dash="dash", line_color="#cbd5e1", line_width=1,
    annotation_text="Original loan", annotation_position="top left",
    annotation_font_color="#94a3b8", annotation_font_size=11,
)
fig_salary.update_xaxes(tickprefix="£", ticksuffix="k")
fig_salary.update_yaxes(tickprefix="£", ticksuffix="k")
fig_salary.update_layout(**LAYOUT_COMMON)

fig_salary.write_html(f"{RESULTS_DIR}/panel_salary.html")
fig_salary.write_image(f"{RESULTS_DIR}/panel_salary.png", width=800, height=500, scale=2)
print(f"\nSaved {RESULTS_DIR}/panel_salary.html + panel_salary.png")

# ── Panel 2: Years of repayment by starting salary ──
years_long = salary_df.melt(
    id_vars=["salary"],
    value_vars=["current_years", "badenoch_years", "lewis_years"],
    var_name="scenario",
    value_name="years",
)
years_long["scenario"] = years_long["scenario"].map({
    "current_years": "Current system",
    "badenoch_years": "Cap interest at RPI",
    "lewis_years": "Raise threshold to £40k",
})
years_long["salary_k"] = years_long["salary"] / 1000

fig_years = px.line(
    years_long,
    x="salary_k",
    y="years",
    color="scenario",
    color_discrete_map=COLOR_MAP,
    labels={"salary_k": "Graduate starting salary (£k)", "years": "Years repaying", "scenario": "Scenario"},
    title=f"Years of repayment (£{LOAN_BALANCE // 1000}k loan, Plan 2)",
    custom_data=["salary"],
)
fig_years.update_traces(
    line=dict(width=2.5),
    hovertemplate="Salary: £%{customdata[0]:,.0f}<br>Years: %{y}<extra>%{fullData.name}</extra>",
)
fig_years.add_hline(y=30, line_dash="dot", line_color="#cbd5e1", line_width=1, opacity=0.5,
                    annotation_text="30yr writeoff", annotation_position="top right",
                    annotation_font_color="#94a3b8", annotation_font_size=11)
fig_years.update_xaxes(tickprefix="£", ticksuffix="k")
fig_years.update_layout(**LAYOUT_COMMON)

fig_years.write_html(f"{RESULTS_DIR}/panel_years.html")
fig_years.write_image(f"{RESULTS_DIR}/panel_years.png", width=800, height=500, scale=2)
print(f"Saved {RESULTS_DIR}/panel_years.html + panel_years.png")

# ── Panel 3: Savings vs current system by starting salary ──
salary_df["badenoch_saving"] = salary_df["current_repaid"] - salary_df["badenoch_repaid"]
salary_df["lewis_saving"] = salary_df["current_repaid"] - salary_df["lewis_repaid"]

savings_long = salary_df.melt(
    id_vars=["salary"],
    value_vars=["badenoch_saving", "lewis_saving"],
    var_name="scenario",
    value_name="saving",
)
savings_long["scenario"] = savings_long["scenario"].map({
    "badenoch_saving": "Cap interest at RPI",
    "lewis_saving": "Raise threshold to £40k",
})
savings_long["salary_k"] = savings_long["salary"] / 1000
savings_long["saving_k"] = savings_long["saving"] / 1000

fig_savings = px.line(
    savings_long,
    x="salary_k",
    y="saving_k",
    color="scenario",
    color_discrete_map=COLOR_MAP,
    labels={"salary_k": "Graduate starting salary (£k)", "saving_k": "Reduction in lifetime repayment (£k)", "scenario": "Scenario"},
    title=f"Reduction in lifetime loan repayment vs current system (£{LOAN_BALANCE // 1000}k loan, Plan 2)",
    custom_data=["salary", "saving"],
)
fig_savings.update_traces(
    line=dict(width=2.5),
    hovertemplate="Salary: £%{customdata[0]:,.0f}<br>Less repaid: £%{customdata[1]:,.0f}<extra>%{fullData.name}</extra>",
)
fig_savings.add_hline(
    y=0, line_dash="solid", line_color="#cbd5e1", line_width=1,
)
fig_savings.update_xaxes(tickprefix="£", ticksuffix="k")
fig_savings.update_yaxes(tickprefix="£", ticksuffix="k")
fig_savings.update_layout(**LAYOUT_COMMON)

fig_savings.write_html(f"{RESULTS_DIR}/panel_savings.html")
fig_savings.write_image(f"{RESULTS_DIR}/panel_savings.png", width=800, height=500, scale=2)
print(f"Saved {RESULTS_DIR}/panel_savings.html + panel_savings.png")

# ── Panel 4: Annual repayment over time — 4 salary levels ───────────────────
from plotly.subplots import make_subplots
import plotly.graph_objects as go

print("\nGenerating annual repayment profiles...")

PROFILE_SALARIES = [
    ("£25k first-year income", 25_000),
    ("£45k first-year income", 45_000),
    ("£65k first-year income", 65_000),
    ("£85k first-year income", 85_000),
]

SC_PLOT = [
    (BADENOCH, "Cap interest at RPI", TEAL),
    (LEWIS, "Raise threshold to £40k", AMBER),
]

fig_annual = make_subplots(
    rows=2, cols=2,
    subplot_titles=[label for label, _ in PROFILE_SALARIES],
    horizontal_spacing=0.12,
    vertical_spacing=0.18,
)

for i, (label, sal) in enumerate(PROFILE_SALARIES):
    row = i // 2 + 1
    col = i % 2 + 1
    for sc, sc_name, colour in SC_PLOT:
        yearly = simulate_yearly(sal, LOAN_BALANCE, sc)
        years = [r["year"] for r in yearly]
        repayments = [r["annual_repayment"] for r in yearly]

        fig_annual.add_trace(
            go.Scatter(
                x=years,
                y=repayments,
                name=sc_name,
                line=dict(color=colour, width=2),
                showlegend=(i == 0),
                hovertemplate="Year %{x}<br>Repayment: £%{y:,.0f}<extra>" + sc_name + "</extra>",
            ),
            row=row, col=col,
        )

fig_annual.update_xaxes(title_text="Years from graduation", dtick=5, range=[0, 40])
fig_annual.update_yaxes(title_text="Annual repayment (£)", tickprefix="£")
fig_annual.update_layout(
    title=f"Annual student loan repayment — two proposed fixes (£{LOAN_BALANCE // 1000}k loan, Plan 2)",
    height=700, width=900,
    plot_bgcolor="white",
    paper_bgcolor="white",
    font=dict(family="Roboto, Helvetica Neue, Arial, sans-serif", color="#1e293b"),
    legend=dict(
        bgcolor="rgba(255,255,255,0.95)", bordercolor="#e2e8f0", borderwidth=1,
        orientation="h", yanchor="bottom", y=-0.18, xanchor="center", x=0.5,
    ),
)
# Style all subplots
for i in range(1, 5):
    fig_annual.update_xaxes(gridcolor="#f1f5f9", linecolor="#cbd5e1", selector=dict(anchor=f"y{i}" if i > 1 else "y"))
    fig_annual.update_yaxes(gridcolor="#f1f5f9", linecolor="#cbd5e1", selector=dict(anchor=f"x{i}" if i > 1 else "x"))

fig_annual.write_html(f"{RESULTS_DIR}/panel_annual.html")
fig_annual.write_image(f"{RESULTS_DIR}/panel_annual.png", width=900, height=700, scale=2)
print(f"Saved {RESULTS_DIR}/panel_annual.html + panel_annual.png")

