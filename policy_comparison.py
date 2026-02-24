"""
Plan 2 vs Plan 5: Who Pays More Under the 2023 Student Loan Reform?

The 2023 reform replaced Plan 2 with Plan 5 for new English students.
Key changes: lower threshold (£25k vs £29k), RPI-only interest (vs RPI+3%),
but 40-year writeoff (vs 30 years). The extra 10 years convert many middle
earners from "written off" to "full repayers".

Uses PolicyEngine UK for all parameters and microdata income distribution.

Run with: conda activate python313 && python policy_comparison.py
"""

import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from policyengine_uk import Microsimulation


# ── Load PolicyEngine UK parameters ──────────────────────────────────────────
YEAR = 2026

print("Loading PolicyEngine UK...")
baseline_sim = Microsimulation()
tbs = baseline_sim.tax_benefit_system
params = tbs.parameters
date = f"{YEAR}-01-01"
sl = params.gov.hmrc.student_loans

# Plan 2 parameters (from PE)
PLAN2 = {
    "name": "Plan 2",
    "threshold": sl.thresholds.plan_2(date),
    "repayment_rate": sl.repayment_rate(date),
    "writeoff_years": 30,
}

# Plan 5 parameters (from PE)
PLAN5 = {
    "name": "Plan 5",
    "threshold": sl.thresholds.plan_5(date),
    "repayment_rate": sl.repayment_rate(date),
    "writeoff_years": 40,
}

# Interest rates (PE or known fallbacks)
try:
    PLAN2["interest_min"] = sl.interest.plan_2.rate_below_threshold(date)
    PLAN2["interest_max"] = sl.interest.plan_2.rate_above_threshold(date)
    PLAN5["interest"] = sl.interest.plan_5.rate(date)
except (AttributeError, KeyError):
    PLAN2["interest_min"] = 0.045   # RPI
    PLAN2["interest_max"] = 0.078   # RPI + 3%
    PLAN5["interest"] = 0.045       # RPI only

INTEREST_UPPER = 49_530  # SLC upper earnings threshold for Plan 2 interest

print(f"\nPolicyEngine UK parameters ({YEAR}):")
print(f"  Plan 2: threshold £{PLAN2['threshold']:,.0f}, interest {PLAN2['interest_min']*100:.1f}%-{PLAN2['interest_max']*100:.1f}%, {PLAN2['writeoff_years']}yr writeoff")
print(f"  Plan 5: threshold £{PLAN5['threshold']:,.0f}, interest {PLAN5['interest']*100:.1f}%, {PLAN5['writeoff_years']}yr writeoff")
print(f"  Repayment rate: {PLAN2['repayment_rate']*100:.0f}%")

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


def plan2_interest_rate(salary, threshold):
    """Plan 2 sliding-scale interest: RPI at threshold, RPI+3% at upper."""
    if salary <= threshold:
        return PLAN2["interest_min"]
    if salary >= INTEREST_UPPER:
        return PLAN2["interest_max"]
    return PLAN2["interest_min"] + (PLAN2["interest_max"] - PLAN2["interest_min"]) * (
        (salary - threshold) / (INTEREST_UPPER - threshold)
    )


def simulate_lifetime(starting_salary, loan_balance, plan_params, interest_fn):
    """Simulate year-by-year loan repayment. Returns dict with lifetime metrics."""
    balance = loan_balance
    total_repaid = 0
    total_interest = 0
    salary = starting_salary
    threshold = plan_params["threshold"]
    writeoff = plan_params["writeoff_years"]
    rate = plan_params["repayment_rate"]
    years_repaying = 0

    for yr in range(1, writeoff + 1):
        if balance <= 0:
            break

        cal_year = YEAR + yr

        # Threshold indexation: Plan 2 frozen 2027-2029, RPI from 2030+
        # Plan 5: assume RPI indexation throughout (per current policy)
        if plan_params["name"] == "Plan 2":
            if cal_year >= 2030:
                threshold *= 1 + get_rpi(cal_year)
        else:
            if cal_year >= 2027:
                threshold *= 1 + get_rpi(cal_year)

        # Repayment first
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


# ── 1. Salary sweep: Plan 2 vs Plan 5 by starting salary ─────────────────────
print("\nSimulating lifetime repayments across salary range...")

salaries = np.arange(20_000, 120_001, 100)
results_by_salary = []

for sal in salaries:
    p2 = simulate_lifetime(
        sal, LOAN_BALANCE, PLAN2,
        lambda s, t: plan2_interest_rate(s, t),
    )
    p5 = simulate_lifetime(
        sal, LOAN_BALANCE, PLAN5,
        lambda s, t: PLAN5["interest"],
    )
    results_by_salary.append({
        "salary": sal,
        "plan2_repaid": p2["total_repaid"],
        "plan5_repaid": p5["total_repaid"],
        "plan2_years": p2["years_repaying"],
        "plan5_years": p5["years_repaying"],
        "plan2_paid_off": p2["paid_off"],
        "plan5_paid_off": p5["paid_off"],
        "plan2_written_off": p2["written_off"],
        "plan5_written_off": p5["written_off"],
        "extra_repaid": p5["total_repaid"] - p2["total_repaid"],
        "extra_years": p5["years_repaying"] - p2["years_repaying"],
    })

salary_df = pd.DataFrame(results_by_salary)


# ── 2. PolicyEngine microdata: distributional effect by income decile ─────────
print("Loading PE microdata for income distribution...")

person_income = baseline_sim.calculate("employment_income", YEAR)
person_decile = baseline_sim.calculate("household_income_decile", YEAR, map_to="person")
person_plan = baseline_sim.calculate("student_loan_plan", YEAR)
weights = person_income.weights

incomes = person_income.values
plans = person_plan.values
deciles = person_decile.values

# Simulate for all borrowers (Plan 2 + Plan 5)
has_loan = (plans == "PLAN_2") | (plans == "PLAN_5")
has_income = incomes > 0
borrower_mask = has_loan & has_income

print(f"  Simulating {borrower_mask.sum()} borrowers...")

extra_repaid = np.zeros(len(incomes))
plan2_repaid_arr = np.zeros(len(incomes))
plan5_repaid_arr = np.zeros(len(incomes))
plan2_years_arr = np.zeros(len(incomes))
plan5_years_arr = np.zeros(len(incomes))

for idx in np.where(borrower_mask)[0]:
    inc = incomes[idx]
    p2 = simulate_lifetime(inc, LOAN_BALANCE, PLAN2, lambda s, t: plan2_interest_rate(s, t))
    p5 = simulate_lifetime(inc, LOAN_BALANCE, PLAN5, lambda s, t: PLAN5["interest"])
    plan2_repaid_arr[idx] = p2["total_repaid"]
    plan5_repaid_arr[idx] = p5["total_repaid"]
    plan2_years_arr[idx] = p2["years_repaying"]
    plan5_years_arr[idx] = p5["years_repaying"]
    extra_repaid[idx] = p5["total_repaid"] - p2["total_repaid"]

# Aggregate by income decile
decile_results = []
for d in range(1, 11):
    mask = (deciles == d) & borrower_mask
    w = weights[mask]
    total_w = w.sum()
    if total_w == 0:
        decile_results.append({
            "decile": d, "avg_extra_repaid": 0,
            "avg_plan2_repaid": 0, "avg_plan5_repaid": 0,
            "avg_plan2_years": 0, "avg_plan5_years": 0,
            "borrowers": 0, "total_extra": 0,
        })
        continue

    decile_results.append({
        "decile": d,
        "avg_extra_repaid": (extra_repaid[mask] * w).sum() / total_w,
        "avg_plan2_repaid": (plan2_repaid_arr[mask] * w).sum() / total_w,
        "avg_plan5_repaid": (plan5_repaid_arr[mask] * w).sum() / total_w,
        "avg_plan2_years": (plan2_years_arr[mask] * w).sum() / total_w,
        "avg_plan5_years": (plan5_years_arr[mask] * w).sum() / total_w,
        "borrowers": total_w,
        "total_extra": (extra_repaid[mask] * w).sum() / 1e6,
    })

decile_df = pd.DataFrame(decile_results)

print("\n=== Plan 5 vs Plan 2: Extra Lifetime Repayment by Income Decile ===")
print(f"{'Decile':<8} {'Extra repaid':>14} {'P2 years':>10} {'P5 years':>10} {'Borrowers':>12}")
print("-" * 58)
for _, r in decile_df.iterrows():
    print(
        f"  {int(r['decile']):<6} "
        f"£{r['avg_extra_repaid']:>10,.0f}   "
        f"{r['avg_plan2_years']:>8.1f}   "
        f"{r['avg_plan5_years']:>8.1f}   "
        f"{r['borrowers']:>10,.0f}"
    )
total_extra = decile_df["total_extra"].sum()
print(f"\n  Total extra repaid under Plan 5: £{total_extra:,.0f}m")


# ── 3. Typical graduate profiles ──────────────────────────────────────────────
print("\n=== Typical Graduate Profiles ===")
profiles = [
    ("Low earner", 25_000),
    ("Median graduate", 30_000),
    ("Above median", 40_000),
    ("Higher earner", 55_000),
]

for label, sal in profiles:
    p2 = simulate_lifetime(sal, LOAN_BALANCE, PLAN2, lambda s, t: plan2_interest_rate(s, t))
    p5 = simulate_lifetime(sal, LOAN_BALANCE, PLAN5, lambda s, t: PLAN5["interest"])
    diff = p5["total_repaid"] - p2["total_repaid"]
    print(f"\n  {label} (£{sal:,} starting salary):")
    print(f"    Plan 2: repays £{p2['total_repaid']:,.0f} over {p2['years_repaying']} years"
          f"{' (paid off)' if p2['paid_off'] else f' (£{p2['written_off']:,.0f} written off)'}")
    print(f"    Plan 5: repays £{p5['total_repaid']:,.0f} over {p5['years_repaying']} years"
          f"{' (paid off)' if p5['paid_off'] else f' (£{p5['written_off']:,.0f} written off)'}")
    print(f"    Difference: {'£' + f'{diff:,.0f} MORE' if diff > 0 else '£' + f'{abs(diff):,.0f} LESS'} under Plan 5")


# ── 4. Plot (Plotly Express) ──────────────────────────────────────────────────
import os
RESULTS_DIR = "results"
os.makedirs(RESULTS_DIR, exist_ok=True)

TEAL = "#319795"   # PolicyEngine primary
AMBER = "#F59E0B"  # Contrast

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
    value_vars=["plan2_repaid", "plan5_repaid"],
    var_name="plan",
    value_name="total_repaid",
)
salary_long["plan"] = salary_long["plan"].map({
    "plan2_repaid": "Plan 2 (2012-2022)",
    "plan5_repaid": "Plan 5 (2023+)",
})
salary_long["salary_k"] = salary_long["salary"] / 1000
salary_long["repaid_k"] = salary_long["total_repaid"] / 1000

fig_salary = px.line(
    salary_long,
    x="salary_k",
    y="repaid_k",
    color="plan",
    color_discrete_map={"Plan 2 (2012-2022)": TEAL, "Plan 5 (2023+)": AMBER},
    labels={"salary_k": "Graduate starting salary (£k)", "repaid_k": "Total lifetime repayment (£k)", "plan": "Plan"},
    title=f"Total lifetime repayment (£{LOAN_BALANCE // 1000}k loan)",
    custom_data=["salary", "total_repaid"],
)
fig_salary.update_traces(
    line=dict(width=2.5),
    hovertemplate="Salary: £%{customdata[0]:,.0f}<br>Total repaid: £%{customdata[1]:,.0f}<extra>%{fullData.name}</extra>",
)
fig_salary.add_hline(
    y=LOAN_BALANCE / 1000, line_dash="dash", line_color="#94a3b8", line_width=1,
    annotation_text="Original loan", annotation_position="top left",
    annotation_font_color="#94a3b8", annotation_font_size=11,
)
fig_salary.update_xaxes(tickprefix="£", ticksuffix="k")
fig_salary.update_yaxes(tickprefix="£", ticksuffix="k")
fig_salary.update_layout(**LAYOUT_COMMON)

fig_salary.write_html(f"{RESULTS_DIR}/panel_salary.html")
fig_salary.write_image(f"{RESULTS_DIR}/panel_salary.png", width=800, height=500, scale=2)
print(f"Saved {RESULTS_DIR}/panel_salary.html + panel_salary.png")

# ── Panel 2: Years of repayment by starting salary ──
years_long = salary_df.melt(
    id_vars=["salary"],
    value_vars=["plan2_years", "plan5_years"],
    var_name="plan",
    value_name="years",
)
years_long["plan"] = years_long["plan"].map({
    "plan2_years": "Plan 2 (2012-2022)",
    "plan5_years": "Plan 5 (2023+)",
})
years_long["salary_k"] = years_long["salary"] / 1000

fig_years = px.line(
    years_long,
    x="salary_k",
    y="years",
    color="plan",
    color_discrete_map={"Plan 2 (2012-2022)": TEAL, "Plan 5 (2023+)": AMBER},
    labels={"salary_k": "Graduate starting salary (£k)", "years": "Years repaying", "plan": "Plan"},
    title=f"Years of repayment (£{LOAN_BALANCE // 1000}k loan)",
    custom_data=["salary"],
)
fig_years.update_traces(
    line=dict(width=2.5),
    hovertemplate="Salary: £%{customdata[0]:,.0f}<br>Years: %{y}<extra>%{fullData.name}</extra>",
)
fig_years.add_hline(y=30, line_dash="dot", line_color=TEAL, line_width=1, opacity=0.5,
                    annotation_text="30yr writeoff", annotation_position="top right",
                    annotation_font_color=TEAL, annotation_font_size=11)
fig_years.add_hline(y=40, line_dash="dot", line_color=AMBER, line_width=1, opacity=0.5,
                    annotation_text="40yr writeoff", annotation_position="top right",
                    annotation_font_color=AMBER, annotation_font_size=11)
fig_years.update_xaxes(tickprefix="£", ticksuffix="k")
fig_years.update_layout(**LAYOUT_COMMON)

fig_years.write_html(f"{RESULTS_DIR}/panel_years.html")
fig_years.write_image(f"{RESULTS_DIR}/panel_years.png", width=800, height=500, scale=2)
print(f"Saved {RESULTS_DIR}/panel_years.html + panel_years.png")

# ── Panel 3: Total repayment by household income decile (PE microdata) ──
decile_long = decile_df.melt(
    id_vars=["decile", "borrowers"],
    value_vars=["avg_plan2_repaid", "avg_plan5_repaid"],
    var_name="plan",
    value_name="avg_repaid",
)
decile_long["plan"] = decile_long["plan"].map({
    "avg_plan2_repaid": "Plan 2",
    "avg_plan5_repaid": "Plan 5",
})
decile_long["repaid_k"] = decile_long["avg_repaid"] / 1000
decile_long["decile_str"] = decile_long["decile"].astype(int).astype(str)

fig_decile = px.bar(
    decile_long,
    x="decile_str",
    y="repaid_k",
    color="plan",
    barmode="group",
    color_discrete_map={"Plan 2": TEAL, "Plan 5": AMBER},
    labels={"decile_str": "Household income decile", "repaid_k": "Avg. lifetime repayment per borrower (£k)", "plan": "Plan"},
    title=f"Total lifetime repayment by household income decile (£{LOAN_BALANCE // 1000}k loan)",
    custom_data=["avg_repaid", "borrowers"],
)
fig_decile.update_traces(
    hovertemplate="Repaid: £%{customdata[0]:,.0f}<br>Borrowers: %{customdata[1]:,.0f}<extra>%{fullData.name}</extra>",
    opacity=0.85,
)
fig_decile.update_yaxes(tickprefix="£", ticksuffix="k")
fig_decile.update_layout(**LAYOUT_COMMON)

fig_decile.write_html(f"{RESULTS_DIR}/panel_decile.html")
fig_decile.write_image(f"{RESULTS_DIR}/panel_decile.png", width=800, height=500, scale=2)
print(f"Saved {RESULTS_DIR}/panel_decile.html + panel_decile.png")
