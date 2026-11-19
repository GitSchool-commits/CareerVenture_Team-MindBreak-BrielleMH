import json
import math
from decimal import Decimal, ROUND_HALF_UP
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

# ==============================================================================
# 1. CONSTANTS & PATHWAY CONFIGURATION (PSY-3 | AP CALCULUS)
# ==============================================================================
TEAM_ID_DEFAULT = "TEAM-MINDBREAK"
PATHWAY_ID = "PSY-3"
BUSINESS_NAME = "Study Habits and Wellness Education Studio"
COURSE_NAME = "AP Calculus"
CURRENCY = "USD"

# Exact PSY baseline defaults from handbook (p. 88)
DEFAULTS = {
    "base_price": 30.00,
    "D0": 70,
    "staff_hours": 25.0,
    "hours_per_unit": 0.5,
    "program_seats": 50,
    "completion_rate": 0.80,
    "satisfaction_mean": 4.2,
    "owner_contribution": 5000.00,
    "equipment_assets": 700.00,
    "pre_opening_expense": 1300.00,
    "opening_cash": 3000.00,
    "var_facilitator": 3.00,
    "var_materials": 2.00,
    "var_survey": 1.00,
    "fix_venue": 200.00,
    "fix_software": 100.00,
    "fix_accessibility": 150.00,
    "fix_admin": 100.00,
}

# Exact PSY monthly fixture from handbook (p. 90)
PSY_FIXTURE_ROWS = [
    {"month": "2027-01", "requested": 70, "capacity_override": 50, "ad_cost": 0.00, "run_id": "FIX-2027-01"},
    {"month": "2027-02", "requested": 77, "capacity_override": 50, "ad_cost": 100.00, "run_id": "FIX-2027-02"},
    {"month": "2027-03", "requested": 63, "capacity_override": 37, "ad_cost": 0.00, "run_id": "FIX-2027-03"},
]


def to_money(val) -> Decimal:
    """Store money with exact 2-decimal Decimal precision (handbook p. 72)."""
    return Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def init_state():
    """Initialize durable session state representing the single approved record."""
    if "initialized" not in st.session_state:
        st.session_state.initialized = True
        st.session_state.team_id = TEAM_ID_DEFAULT
        st.session_state.pathway_id = PATHWAY_ID
        st.session_state.selected_course = COURSE_NAME
        st.session_state.selected_level = "Advanced"
        st.session_state.teacher_approved_skill = "Constrained Optimization & Accumulation"
        st.session_state.state_version = 1
        st.session_state.simulation_date = "2027-01-31"
        st.session_state.random_seed = 2027

        # Editable inputs
        st.session_state.inputs = DEFAULTS.copy()

        # Balances & Ledger
        st.session_state.cash = float(DEFAULTS["opening_cash"])
        st.session_state.equipment = float(DEFAULTS["equipment_assets"])
        st.session_state.debt = 0.0
        st.session_state.owner_equity = float(DEFAULTS["owner_contribution"])
        st.session_state.retained_earnings = -float(DEFAULTS["pre_opening_expense"])
        st.session_state.ledger = []  # List of transaction dicts
        st.session_state.processed_run_ids = []  # Duplicate-run protection
        st.session_state.decisions = []  # Decision memos
        st.session_state.ai_proposals = []  # Pending/approved manual handoffs


def reset_to_opening_state():
    """Reset ledger and balances back to post-startup opening state (handbook p. 90)."""
    inp = st.session_state.inputs
    st.session_state.cash = float(inp["opening_cash"])
    st.session_state.equipment = float(inp["equipment_assets"])
    st.session_state.debt = 0.0
    st.session_state.owner_equity = float(inp["owner_contribution"])
    st.session_state.retained_earnings = -float(inp["pre_opening_expense"])
    st.session_state.ledger = []
    st.session_state.processed_run_ids = []
    st.session_state.state_version += 1


# ==============================================================================
# 2. DETERMINISTIC SIMULATION & ACCOUNTING ENGINE (PSY-3)
# ==============================================================================
def compute_variable_per_unit(inp: dict) -> Decimal:
    return to_money(inp["var_facilitator"]) + to_money(inp["var_materials"]) + to_money(inp["var_survey"])


def compute_fixed_monthly(inp: dict) -> Decimal:
    return (
        to_money(inp["fix_venue"])
        + to_money(inp["fix_software"])
        + to_money(inp["fix_accessibility"])
        + to_money(inp["fix_admin"])
    )


def compute_normal_capacity(inp: dict) -> int:
    """Exact PSY capacity algorithm (handbook p. 89)."""
    if inp["hours_per_unit"] <= 0:
        return 0
    staff_cap = math.floor(inp["staff_hours"] / inp["hours_per_unit"])
    return max(0, min(staff_cap, int(inp["program_seats"])))


def run_monthly_step(
    run_id: str,
    sim_date: str,
    requested: int,
    price: float,
    ad_cost: float = 0.0,
    capacity_override: int | None = None,
    refund_amount: float = 0.0,
    loan_cash: float = 0.0,
    principal_repaid: float = 0.0,
    interest_expense: float = 0.0,
    additional_capex: float = 0.0,
    mode: str = "Normal",
) -> tuple[bool, str, dict | None]:
    """
    Execute one simulation month deterministically.
    Enforces duplicate-run protection and PSY accounting rules (handbook pp. 58, 89).
    """
    if run_id in st.session_state.processed_run_ids:
        return False, f"Rejected duplicate run_id '{run_id}'. No transaction created.", None

    if requested < 0 or price < 0 or ad_cost < 0:
        return False, "Rejected negative input value.", None

    inp = st.session_state.inputs
    capacity = int(capacity_override) if capacity_override is not None else compute_normal_capacity(inp)
    sold = min(int(requested), capacity)
    unserved = max(0, int(requested) - sold)
    completed = math.floor(sold * inp["completion_rate"])

    p_dec = to_money(price)
    v_unit = compute_variable_per_unit(inp)
    f_month = compute_fixed_monthly(inp)
    ad_dec = to_money(ad_cost)
    ref_dec = to_money(refund_amount)
    int_dec = to_money(interest_expense)
    capex_dec = to_money(additional_capex)
    loan_dec = to_money(loan_cash)
    prin_dec = to_money(principal_repaid)

    # Revenue earned at program delivery; completion is a quality metric (handbook p. 89)
    gross_revenue = p_dec * Decimal(sold)
    net_revenue = gross_revenue - ref_dec
    variable_expense = v_unit * Decimal(sold)
    total_operating_expense = variable_expense + f_month + ad_dec
    operating_profit = net_revenue - total_operating_expense
    net_profit = operating_profit - int_dec

    opening_cash = to_money(st.session_state.cash)
    closing_cash = (
        opening_cash
        + net_revenue
        - variable_expense
        - f_month
        - ad_dec
        - int_dec
        - prin_dec
        - capex_dec
        + loan_dec
    )

    # Commit state atomically
    st.session_state.cash = float(closing_cash)
    st.session_state.equipment = float(to_money(st.session_state.equipment) + capex_dec)
    st.session_state.debt = float(to_money(st.session_state.debt) + loan_dec - prin_dec)
    st.session_state.retained_earnings = float(to_money(st.session_state.retained_earnings) + net_profit)
    st.session_state.state_version += 1
    st.session_state.simulation_date = sim_date
    st.session_state.processed_run_ids.append(run_id)

    record = {
        "transaction_id": f"TX-{len(st.session_state.ledger) + 1:04d}",
        "run_id": run_id,
        "date": sim_date,
        "mode": mode,
        "state_version": st.session_state.state_version,
        "price": float(p_dec),
        "requested": int(requested),
        "capacity": capacity,
        "sold": sold,
        "unserved_demand": unserved,
        "completed_quality": completed,
        "revenue": float(net_revenue),
        "variable_expense": float(variable_expense),
        "fixed_expense": float(f_month),
        "ad_expense": float(ad_dec),
        "total_expense": float(total_operating_expense + int_dec),
        "operating_profit": float(operating_profit),
        "net_profit": float(net_profit),
        "closing_cash": float(closing_cash),
    }
    st.session_state.ledger.append(record)
    return True, f"Committed {run_id} (state_version v{st.session_state.state_version}).", record


# ==============================================================================
# 3. AP CALCULUS ADAPTER MATH ENGINE (HANDBOOK PP. 38, 70)
# ==============================================================================
def get_calculus_model(D0: float, p0: float, v: float, F: float, capacity: int):
    """
    Exact AP Calculus adapter equations (handbook p. 70):
    a = 2 * D0, b = D0 / p0, q(p) = a - b*p on 0 <= p <= 2*p0
    Unconstrained P(p) = (p - v)*(a - b*p) - F
    P'(p) = a + b*v - 2*b*p
    Capacity corner p_cap = (a - capacity) / b
    """
    a = 2.0 * D0
    b = D0 / p0 if p0 > 0 else 0.0
    p_max = 2.0 * p0
    p_unconstrained = (a + b * v) / (2.0 * b) if b > 0 else p0
    p_cap = (a - capacity) / b if b > 0 else 0.0

    def profit_at_price(p: float, enforce_cap: bool = True) -> tuple[float, float, float]:
        q_raw = max(0.0, a - b * p)
        s = min(float(capacity), q_raw) if enforce_cap else q_raw
        prof = (p - v) * s - F
        # Derivative P'(p)
        if enforce_cap and q_raw > capacity:
            d_prof = float(capacity)  # On capacity branch, s(p) = capacity -> R'(p)=cap, C'=0 -> P'=cap
        elif q_raw <= 0:
            d_prof = 0.0
        else:
            d_prof = a + b * v - 2.0 * b * p
        return s, prof, d_prof

    # Evaluate candidate points on [0, 2*p0] for constrained optimum
    candidates = [0.0, p_max]
    if 0.0 <= p_cap <= p_max:
        candidates.append(p_cap)
    if p_cap <= p_unconstrained <= p_max:
        candidates.append(p_unconstrained)

    best_p = max(candidates, key=lambda x: profit_at_price(x, True)[1])
    best_s, best_prof, _ = profit_at_price(best_p, True)

    return {
        "a": a,
        "b": b,
        "p_max": p_max,
        "p_unconstrained": p_unconstrained,
        "p_cap": p_cap,
        "best_p": best_p,
        "best_s": best_s,
        "best_prof": best_prof,
        "profit_at_price": profit_at_price,
    }


def build_snapshot_payload() -> dict:
    """Export canonical JSON snapshot matching handbook data contract (p. 58)."""
    return {
        "team_id": st.session_state.team_id,
        "course": st.session_state.selected_course,
        "pathway_id": st.session_state.pathway_id,
        "snapshot_id": f"SNAP-{st.session_state.team_id}-v{st.session_state.state_version}",
        "state_version": st.session_state.state_version,
        "simulation_date": st.session_state.simulation_date,
        "base_period": "Monthly",
        "working_days": 20,
        "currency": CURRENCY,
        "level_by_skill": {
            st.session_state.teacher_approved_skill: st.session_state.selected_level
        },
        "random_seed": st.session_state.random_seed,
        "inputs": st.session_state.inputs,
        "balances": {
            "cash": st.session_state.cash,
            "equipment": st.session_state.equipment,
            "debt": st.session_state.debt,
            "owner_equity": st.session_state.owner_equity,
            "retained_earnings": st.session_state.retained_earnings,
        },
        "processed_run_ids": st.session_state.processed_run_ids,
        "ledger": st.session_state.ledger,
        "decisions": st.session_state.decisions,
    }


def validate_and_load_snapshot(raw_json: str) -> tuple[bool, str]:
    """Validate team_id, schema, and state_version on import (handbook p. 58)."""
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        return False, f"Invalid JSON syntax: {exc}"

    required_keys = ["team_id", "course", "pathway_id", "state_version", "inputs", "balances", "ledger"]
    missing = [k for k in required_keys if k not in data]
    if missing:
        return False, f"Rejected import: missing required fields {missing}."

    if data["team_id"] != st.session_state.team_id:
        return (
            False,
            f"Rejected import: team_id '{data['team_id']}' does not match active team '{st.session_state.team_id}'.",
        )

    if data["pathway_id"] != PATHWAY_ID:
        return False, f"Rejected import: pathway '{data['pathway_id']}' does not match '{PATHWAY_ID}'."

    if int(data["state_version"]) < st.session_state.state_version:
        return (
            False,
            f"Rejected stale snapshot v{data['state_version']} (current state is v{st.session_state.state_version}).",
        )

    # Restore state
    st.session_state.state_version = int(data["state_version"])
    st.session_state.simulation_date = data.get("simulation_date", st.session_state.simulation_date)
    st.session_state.inputs = data["inputs"]
    bal = data["balances"]
    st.session_state.cash = float(bal["cash"])
    st.session_state.equipment = float(bal["equipment"])
    st.session_state.debt = float(bal["debt"])
    st.session_state.owner_equity = float(bal["owner_equity"])
    st.session_state.retained_earnings = float(bal["retained_earnings"])
    st.session_state.ledger = data["ledger"]
    st.session_state.processed_run_ids = data.get("processed_run_ids", [r["run_id"] for r in data["ledger"]])
    st.session_state.decisions = data.get("decisions", [])
    return True, f"Restored snapshot v{st.session_state.state_version} for {data['team_id']}."


# ==============================================================================
# 4. STREAMLIT UI
# ==============================================================================
st.set_page_config(page_title="Career Venture Lab | PSY-3", layout="wide")
init_state()

# Top Control & Snapshot Header
st.title(f"Career Venture Lab — {BUSINESS_NAME}")
st.caption(
    f"**Team:** `{st.session_state.team_id}` | **Pathway:** `{PATHWAY_ID}` | "
    f"**Course:** `{COURSE_NAME}` | **State Version:** `v{st.session_state.state_version}` | "
    f"**Stage 1 Build:** Deterministic Core, Ledger & Math Panel (Simulation Only — Fictional Data)"
)

# Persistent Math Skills & Challenge Level Banner (Handbook p. 6)
with st.container(border=True):
    c1, c2, c3, c4 = st.columns([1.2, 1.2, 1.5, 1.1])
    with c1:
        st.markdown(f"**Selected Course:** {COURSE_NAME}")
        level = st.selectbox(
            "Challenge Level (Teacher-Approved)",
            ["Foundation", "Applied", "Advanced"],
            index=["Foundation", "Applied", "Advanced"].index(st.session_state.selected_level),
        )
        if level != st.session_state.selected_level:
            st.session_state.selected_level = level
            st.rerun()
    with c2:
        st.markdown("**Named Skill:**")
        st.write("Constrained Profit Optimization & Rate Accumulation")
    with c3:
        st.markdown("**Business Question:**")
        st.write(
            "What program seat price maximizes monthly profit without exceeding "
            "facilitator/room capacity, and what is cumulative campaign net gain?"
        )
    with c4:
        st.metric("Spendable Cash", f"${st.session_state.cash:,.2f}")
        st.metric("Normal Capacity", f"{compute_normal_capacity(st.session_state.inputs)} seats/mo")

# Navigation Tabs (Stage 1 active; Stage 2 & 3 clearly marked)
tab_overview, tab_inputs, tab_math, tab_ops_fin, tab_tests = st.tabs(
    [
        "1. Overview & Save/Load",
        "2. Inputs, Funding & Ledger",
        "3. Math Skills & Levels (AP Calc)",
        "4. Operations & Finance View",
        "5. Stage 1 Acceptance Tests",
    ]
)

# ------------------------------------------------------------------------------
# TAB 1: OVERVIEW & SAVE/LOAD
# ------------------------------------------------------------------------------
with tab_overview:
    col_a, col_b = st.columns([1.4, 1.0])
    with col_a:
        st.subheader("System Map & Operating Cycle")
        st.info(
            "**Manual Handoff Workflow (Stage 1):** Edit Inputs/Scenarios → Commit Approved Monthly Step → "
            "Export Snapshot JSON → Consult Departmental AI Roles → Verify Math Independently → Approve Changes."
        )
        fig_map = go.Figure()
        nodes = [
            ("Inputs & Funding", 0, 1),
            ("Deterministic Engine", 1, 1),
            ("Dated Ledger (JSON)", 2, 1),
            ("AP Calc Math Panel", 1, 0),
            ("AI Roles & Student Check", 2, 0),
        ]
        for label, x, y in nodes:
            fig_map.add_trace(
                go.Scatter(
                    x=[x],
                    y=[y],
                    mode="markers+text",
                    marker=dict(size=36, color="#1f4e78", symbol="square"),
                    text=[label],
                    textposition="bottom center",
                    showlegend=False,
                )
            )
        fig_map.update_layout(
            height=260,
            margin=dict(l=20, r=20, t=20, b=40),
            xaxis=dict(visible=False, range=[-0.5, 2.5]),
            yaxis=dict(visible=False, range=[-0.5, 1.5]),
        )
        st.plotly_chart(fig_map, use_container_width=True)

        st.markdown("**Module Status Roadmap:**")
        st.markdown(
            "- ✅ **Stage 1 (Active):** Inputs & Funding, PSY-3 Deterministic Engine, Dated Ledger, "
            "AP Calculus Panel (Foundation/Applied/Advanced), JSON Save/Restore, Acceptance Tests.\n"
            "- ⏳ **Stage 2 (Planned):** Full Report Center (PDF/CSV), Costed Marketing Studio, 3 Decision Rounds.\n"
            "- ⏳ **Stage 3 (Planned):** Cross-Course Connections Panel & Frozen Snapshot Practice Assessments."
        )

    with col_b:
        st.subheader("Durable Save / Restore (JSON)")
        snapshot_data = build_snapshot_payload()
        st.download_button(
            label="Download Current Snapshot JSON",
            data=json.dumps(snapshot_data, indent=2),
            file_name=f"{snapshot_data['snapshot_id']}.json",
            mime="application/json",
            use_container_width=True,
        )

        uploaded_snap = st.file_uploader("Restore Snapshot JSON", type=["json"])
        if uploaded_snap is not None:
            if st.button("Validate & Import Snapshot", use_container_width=True):
                ok, msg = validate_and_load_snapshot(uploaded_snap.read().decode("utf-8"))
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

        st.divider()
        if st.button("Reset to Post-Startup Opening State ($3,000 Cash)", type="secondary", use_container_width=True):
            reset_to_opening_state()
            st.warning("Reset to opening balances and cleared ledger.")
            st.rerun()

# ------------------------------------------------------------------------------
# TAB 2: INPUTS, FUNDING & LEDGER
# ------------------------------------------------------------------------------
with tab_inputs:
    st.subheader("Editable Business Parameters (Fictional Teaching Defaults)")
    inp = st.session_state.inputs

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("**Pricing, Demand & Capacity**")
        inp["base_price"] = st.number_input("Base Price ($/seat)", min_value=1.0, value=float(inp["base_price"]), step=1.0)
        inp["D0"] = st.number_input("Baseline Demand D0 (seats/mo)", min_value=0, value=int(inp["D0"]), step=1)
        inp["staff_hours"] = st.number_input("Facilitator Staff Hours/mo", min_value=0.0, value=float(inp["staff_hours"]), step=1.0)
        inp["hours_per_unit"] = st.number_input("Hours per Seat", min_value=0.1, value=float(inp["hours_per_unit"]), step=0.1)
        inp["program_seats"] = st.number_input("Venue Program Seats/mo", min_value=0, value=int(inp["program_seats"]), step=1)
        inp["completion_rate"] = st.slider("Program Completion Rate (Quality)", 0.0, 1.0, float(inp["completion_rate"]), 0.05)

    with col2:
        st.markdown("**Variable Costs ($/seat sold)**")
        inp["var_facilitator"] = st.number_input("Facilitator Delivery ($)", min_value=0.0, value=float(inp["var_facilitator"]), step=0.5)
        inp["var_materials"] = st.number_input("Learning Materials ($)", min_value=0.0, value=float(inp["var_materials"]), step=0.5)
        inp["var_survey"] = st.number_input("Survey Processing ($)", min_value=0.0, value=float(inp["var_survey"]), step=0.5)
        st.info(f"**Total Variable Cost (v):** ${compute_variable_per_unit(inp)} / seat")

    with col3:
        st.markdown("**Monthly Fixed Costs ($/month)**")
        inp["fix_venue"] = st.number_input("Venue ($/mo)", min_value=0.0, value=float(inp["fix_venue"]), step=10.0)
        inp["fix_software"] = st.number_input("Software ($/mo)", min_value=0.0, value=float(inp["fix_software"]), step=10.0)
        inp["fix_accessibility"] = st.number_input("Accessibility ($/mo)", min_value=0.0, value=float(inp["fix_accessibility"]), step=10.0)
        inp["fix_admin"] = st.number_input("Admin ($/mo)", min_value=0.0, value=float(inp["fix_admin"]), step=10.0)
        st.info(f"**Total Fixed Cost (F):** ${compute_fixed_monthly(inp)} / month")

    st.divider()
    st.subheader("Advance Simulation by One Approved Month")
    with st.form("advance_month_form"):
        fc1, fc2, fc3, fc4 = st.columns(4)
        with fc1:
            run_id_input = st.text_input("Unique Run ID", value=f"RUN-{len(st.session_state.ledger) + 1:03d}")
            sim_date_input = st.text_input("Month-End Date (YYYY-MM-DD)", value="2027-01-31")
        with fc2:
            req_input = st.number_input("Requested Demand (seats)", min_value=0, value=int(inp["D0"]), step=1)
            price_input = st.number_input("Active Seat Price ($)", min_value=0.0, value=float(inp["base_price"]), step=1.0)
        with fc3:
            ad_input = st.number_input("Approved Ad Campaign Expense ($)", min_value=0.0, value=0.0, step=25.0)
            loan_input = st.number_input("New Loan Cash Inflow ($)", min_value=0.0, value=0.0, step=100.0)
        with fc4:
            capex_input = st.number_input("Equipment Purchase CapEx ($)", min_value=0.0, value=0.0, step=100.0)
            int_input = st.number_input("Loan Interest Expense ($)", min_value=0.0, value=0.0, step=10.0)

        submitted = st.form_submit_button("Approve & Commit Month to Ledger")
        if submitted:
            ok, msg, _ = run_monthly_step(
                run_id=run_id_input.strip(),
                sim_date=sim_date_input.strip(),
                requested=req_input,
                price=price_input,
                ad_cost=ad_input,
                loan_cash=loan_input,
                additional_capex=capex_input,
                interest_expense=int_input,
                mode="Normal",
            )
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

    st.subheader("Dated Event Ledger (Actual Committed Transactions)")
    if st.session_state.ledger:
        df_ledger = pd.DataFrame(st.session_state.ledger)
        st.dataframe(df_ledger, use_container_width=True)
    else:
        st.caption("No transactions committed yet. Use the form above or run the Stage 1 fixture test in Tab 5.")

# ------------------------------------------------------------------------------
# TAB 3: MATH SKILLS & LEVELS (AP CALCULUS ADAPTER)
# ------------------------------------------------------------------------------
with tab_math:
    inp = st.session_state.inputs
    D0 = float(inp["D0"])
    p0 = float(inp["base_price"])
    v = float(compute_variable_per_unit(inp))
    F = float(compute_fixed_monthly(inp))
    cap = compute_normal_capacity(inp)
    calc = get_calculus_model(D0, p0, v, F, cap)

    st.subheader(f"AP Calculus Analysis — Level: {st.session_state.selected_level}")

    if st.session_state.selected_level == "Foundation":
        st.markdown(
            f"**Task (Foundation):** Build unconstrained profit $P(p) = (p - {v:.2f})({calc['a']:.1f} - {calc['b']:.4f}p) - {F:.2f}$ "
            f"on domain $0 \le p \le {calc['p_max']:.2f}$. Compute $P'(p)$, find the critical point, and interpret units ($/dollar)."
        )
    elif st.session_state.selected_level == "Applied":
        st.markdown(
            f"**Task (Applied):** Enforce capacity $s(p) = \min({cap}, \max(0, {calc['a']:.1f} - {calc['b']:.4f}p))$. "
            f"Check the capacity corner $p = {calc['p_cap']:.2f}$, critical points, and endpoints $[0, {calc['p_max']:.2f}]$."
        )
    else:
        st.markdown(
            f"**Task (Advanced):** Perform constrained optimization with capacity corner $p = {calc['p_cap']:.2f}$, "
            f"compare continuous optimum vs. integer seat rounding, perform sensitivity analysis on capacity/costs, "
            f"and evaluate campaign rate accumulation $\int_0^{{10}} (r(t) - c(t))\,dt$."
        )

    test_p = st.slider(
        "Transfer Check Slider — Predict Profit & Derivative Before Moving Price p ($/seat):",
        min_value=0.0,
        max_value=float(max(60.0, calc["p_max"])),
        value=float(p0),
        step=0.5,
    )
    enforce_constraint = st.session_state.selected_level in ["Applied", "Advanced"]
    s_cont, prof_cont, d_prof = calc["profit_at_price"](test_p, enforce_cap=enforce_constraint)
    s_int = math.floor(s_cont)
    prof_int = (test_p - v) * s_int - F

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Continuous Sales s(p)", f"{s_cont:.2f} seats", f"Integer: {s_int} seats")
    m2.metric("Continuous Profit P(p)", f"${prof_cont:,.2f}", f"Integer: ${prof_int:,.2f}")
    m3.metric("Marginal Profit P'(p)", f"${d_prof:,.2f} / $1 price")
    m4.metric(
        "Optimum Price",
        f"${calc['best_p']:.2f}" if enforce_constraint else f"${calc['p_unconstrained']:.2f}",
        f"Unconstrained: ${calc['p_unconstrained']:.2f}",
    )

    prices = np.linspace(0, calc["p_max"], 200)
    profs = [calc["profit_at_price"](px, enforce_cap=enforce_constraint)[1] for px in prices]
    derivs = [calc["profit_at_price"](px, enforce_cap=enforce_constraint)[2] for px in prices]

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        subplot_titles=(
            f"Monthly Profit P(p) [{'Constrained cap=' + str(cap) if enforce_constraint else 'Unconstrained'}]",
            "Marginal Profit Derivative P'(p) ($ profit per $1 price change)",
        ),
    )
    fig.add_trace(go.Scatter(x=prices, y=profs, name="Profit P(p)", line=dict(color="#1f77b4", width=3)), row=1, col=1)
    fig.add_hline(y=0, line_dash="dash", line_color="black", annotation_text="Break-Even ($0)", row=1, col=1)
    fig.add_vline(x=test_p, line_dash="dot", line_color="#d62728", annotation_text=f"Selected p=${test_p:.2f}", row=1, col=1)

    fig.add_trace(go.Scatter(x=prices, y=derivs, name="Derivative P'(p)", line=dict(color="#ff7f0e", width=3)), row=2, col=1)
    fig.add_hline(y=0, line_dash="dash", line_color="black", row=2, col=1)
    if enforce_constraint and 0 <= calc["p_cap"] <= calc["p_max"]:
        fig.add_vline(
            x=calc["p_cap"],
            line_dash="dash",
            line_color="#2ca02c",
            annotation_text=f"Capacity Corner p=${calc['p_cap']:.2f} (P' undefined)",
            row=2,
            col=1,
        )
    fig.update_xaxes(title_text="Seat Price p (USD / seat)", row=2, col=1)
    fig.update_yaxes(title_text="Profit (USD)", row=1, col=1)
    fig.update_yaxes(title_text="P'(p) (USD / USD)", row=2, col=1)
    fig.update_layout(height=520, showlegend=True)
    st.plotly_chart(fig, use_container_width=True)

    sample_prices = sorted(list(set([0.0, round(calc["p_cap"], 2), round(p0, 2), round(calc["p_unconstrained"], 2), round(calc["p_max"], 2)])))
    table_rows = []
    for sp in sample_prices:
        sc, pc, dpc = calc["profit_at_price"](sp, enforce_cap=enforce_constraint)
        table_rows.append(
            {
                "Price p ($)": sp,
                "Continuous Demand q(p)": round(max(0.0, calc["a"] - calc["b"] * sp), 2),
                "Feasible Sales s(p)": round(sc, 2),
                "Integer Sold": math.floor(sc),
                "Continuous Profit ($)": round(pc, 2),
                "P'(p) ($/$)": round(dpc, 2),
            }
        )
    st.markdown("**Linked Price-Response Table (Continuous Model vs. Integer Rounding):**")
    st.dataframe(pd.DataFrame(table_rows), use_container_width=True)

    if st.session_state.selected_level == "Advanced":
        with st.expander("Advanced Integration Exercise: Campaign Rate Accumulation (Handbook p. 70)", expanded=True):
            st.markdown(
                "Models an isolated 10-day promotional rate exercise ($0 \le t \le 10$ days): "
                "$r(t) = 100 + 20t$ ($/day) and $c(t) = 60 + 5t$ ($/day). "
                "*(Does not overwrite monthly ledger.)*"
            )
            t_end = st.slider("Integration Horizon T (days)", 1, 10, 10)
            acc_rev = 100.0 * t_end + 10.0 * (t_end ** 2)
            acc_cost = 60.0 * t_end + 2.5 * (t_end ** 2)
            acc_net = acc_rev - acc_cost
            ic1, ic2, ic3 = st.columns(3)
            ic1.metric("Accumulated Revenue ∫r(t)dt", f"${acc_rev:,.2f}")
            ic2.metric("Accumulated Cost ∫c(t)dt", f"${acc_cost:,.2f}")
            ic3.metric("Net Campaign Gain ∫(r-c)dt", f"${acc_net:,.2f}")

# ------------------------------------------------------------------------------
# TAB 4: OPERATIONS & FINANCE VIEW
# ------------------------------------------------------------------------------
with tab_ops_fin:
    col_ops, col_fin = st.columns(2)
    inp = st.session_state.inputs
    with col_ops:
        st.subheader("Operations Capacity & Quality")
        staff_cap = math.floor(inp["staff_hours"] / inp["hours_per_unit"]) if inp["hours_per_unit"] > 0 else 0
        seat_cap = int(inp["program_seats"])
        actual_cap = compute_normal_capacity(inp)
        bottleneck = "Facilitator Hours" if staff_cap < seat_cap else ("Venue Seats" if seat_cap < staff_cap else "Balanced (50/50)")
        st.write(f"- **Facilitator Hours Limit:** `{staff_cap}` seats ({inp['staff_hours']} hrs / {inp['hours_per_unit']} hrs/seat)")
        st.write(f"- **Venue Seats Limit:** `{seat_cap}` seats")
        st.write(f"- **Effective Monthly Capacity:** `{actual_cap}` seats (**Bottleneck:** {bottleneck})")
        st.write(f"- **Completion Rate (Quality):** `{inp['completion_rate']*100:.0f}%` (Revenue earned at delivery; noncompletion does not trigger automatic refund)")
        st.write(f"- **Satisfaction Mean:** `{inp['satisfaction_mean']} / 5.0` (Does not auto-inflate demand)")

    with col_fin:
        st.subheader("Simplified Balance Reconciliation")
        assets = st.session_state.cash + st.session_state.equipment
        liab_eq = st.session_state.debt + st.session_state.owner_equity + st.session_state.retained_earnings
        st.write(f"- **Cash:** `${st.session_state.cash:,.2f}`")
        st.write(f"- **Equipment Assets:** `${st.session_state.equipment:,.2f}`")
        st.write(f"- **Total Assets:** `${assets:,.2f}`")
        st.write(f"- **Debt + Owner Equity + Retained Earnings:** `${liab_eq:,.2f}`")
        if abs(assets - liab_eq) < 0.01:
            st.success("Balance Check PASS: Assets = Liabilities + Equity")
        else:
            st.error(f"Balance Discrepancy: ${assets - liab_eq:,.2f}")

# ------------------------------------------------------------------------------
# TAB 5: STAGE 1 ACCEPTANCE TESTS (HANDBOOK PP. 60, 70, 90)
# ------------------------------------------------------------------------------
with tab_tests:
    st.subheader("Automated Stage 1 Verification & Fixture Replay")
    st.caption("Runs deterministic checks against PSY-3 and AP Calculus expected results (Handbook pp. 70, 90).")

    if st.button("Run All Stage 1 Acceptance Tests", type="primary"):
        results = []

        # Test 1: Zero sales check
        reset_to_opening_state()
        ok0, _, rec0 = run_monthly_step("TEST-ZERO", "2027-01-31", requested=0, price=30.0)
        pass0 = ok0 and rec0["revenue"] == 0.0 and rec0["variable_expense"] == 0.0 and rec0["operating_profit"] == -550.0
        results.append(("Zero Sales Check (Rev=$0, Profit=-$550)", pass0, f"Got Profit=${rec0['operating_profit']:.2f}"))

        # Test 2: Demand exceeds capacity
        reset_to_opening_state()
        ok_cap, _, rec_cap = run_monthly_step("TEST-CAP", "2027-01-31", requested=70, price=30.0)
        pass_cap = ok_cap and rec_cap["sold"] == 50 and rec_cap["unserved_demand"] == 20
        results.append(("Demand Exceeds Capacity (Sold=50, Unserved=20)", pass_cap, f"Sold={rec_cap['sold']}, Unserved={rec_cap['unserved_demand']}"))

        # Test 3: Duplicate run_id rejection
        ok_dup, msg_dup, _ = run_monthly_step("TEST-CAP", "2027-01-31", requested=70, price=30.0)
        results.append(("Duplicate Run ID Rejected", not ok_dup, msg_dup))

        # Test 4: Business-specific completion rate test (handbook p. 90)
        reset_to_opening_state()
        st.session_state.inputs["completion_rate"] = 0.50
        ok_comp, _, rec_comp = run_monthly_step("TEST-COMP", "2027-01-31", requested=70, price=30.0)
        pass_comp = ok_comp and rec_comp["completed_quality"] == 25 and rec_comp["revenue"] == 1500.0 and rec_comp["operating_profit"] == 650.0
        st.session_state.inputs["completion_rate"] = 0.80
        results.append(("PSY Quality Test (50% completion -> 25 completed, Profit=$650)", pass_comp, f"Completed={rec_comp['completed_quality']}, Profit=${rec_comp['operating_profit']:.2f}"))

        # Test 5: AP Calculus Adapter Numerical Check (handbook p. 70: D0=60, p0=30, v=10, F=500, cap=40 -> opt p=40, prof=700)
        calc_check = get_calculus_model(D0=60, p0=30, v=10, F=500, capacity=40)
        pass_calc = abs(calc_check["best_p"] - 40.0) < 1e-4 and abs(calc_check["best_prof"] - 700.0) < 1e-4
        results.append(("AP Calculus Constrained Optimum Check (p=$40, Profit=$700)", pass_calc, f"Got p=${calc_check['best_p']:.2f}, Profit=${calc_check['best_prof']:.2f}"))

        # Test 6: Replay exact 3-month PSY fixture (handbook p. 90)
        reset_to_opening_state()
        expected_fixture = [
            (50, 1500.0, 850.0, 650.0, 3650.0),
            (50, 1500.0, 950.0, 550.0, 4200.0),
            (37, 1110.0, 772.0, 338.0, 4538.0),
        ]
        fixture_ok = True
        detail_msgs = []
        for row, exp in zip(PSY_FIXTURE_ROWS, expected_fixture):
            _, _, r = run_monthly_step(
                run_id=row["run_id"],
                sim_date=f"{row['month']}-28",
                requested=row["requested"],
                price=30.0,
                ad_cost=row["ad_cost"],
                capacity_override=row["capacity_override"],
                mode="Fixture-Override",
            )
            got = (r["sold"], r["revenue"], r["total_expense"], r["operating_profit"], r["closing_cash"])
            if got != exp:
                fixture_ok = False
            detail_msgs.append(f"{row['month']}: Sold={r['sold']}, Cash=${r['closing_cash']:.2f}")
        results.append(("PSY 3-Month Fixture Replay (Closing Cash $4,538.00)", fixture_ok, " | ".join(detail_msgs)))

        df_tests = pd.DataFrame(
            [{"Test Case": name, "Status": "PASS" if passed else "FAIL", "Evidence": ev} for name, passed, ev in results]
        )
        st.dataframe(df_tests, use_container_width=True)
