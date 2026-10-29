"""Smart Earthworks - dig/charge scheduling model (ENGG3112 TUT03 Group 7).

Compares two ways of running battery-electric excavators on a site with a
temporary power limit:
  * baseline  - uncontrolled charging (crews plug in when low, at lunch, at knock-off)
  * optimised - time-step MILP deciding dig / charge / wait for every machine
Then checks both against the engineering requirements (Table 2 of the proposal).

Run:  env3112\\Scripts\\python.exe model.py   (see README.md)
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pulp

import params as P

OUT = Path(__file__).parent / "outputs"
COLOURS = {"dig": "#1b998b", "charge": "#2e86de", "wait": "#b0b7bf", "off": "#ffffff"}


# ---------------------------------------------------------------- time grid
def time_grid():
    n = int(round((P.DAY_END_H - P.DAY_START_H) / P.DT_H))
    hours = P.DAY_START_H + P.DT_H * np.arange(n)
    approved = (hours >= P.APPROVED_START_H) & (hours < P.APPROVED_END_H)
    lunch = (hours >= P.LUNCH_START_H) & (hours < P.LUNCH_END_H)
    base = np.array([P.BASE_LOAD_BY_HOUR[int(h)] for h in hours], dtype=float)
    return hours, approved, lunch, base


def charge_cap_kw():
    """Charging power may never exceed charger or machine rating."""
    return min(P.CHARGER_RATED_KW, P.MACHINE_MAX_CHARGE_KW)


# ---------------------------------------------------------------- baseline
def simulate_baseline(limit_kw=P.SITE_LIMIT_KW):
    hours, approved, lunch, base = time_grid()
    n, m = len(hours), len(P.EXCAVATORS)
    cap, pmax = P.BATTERY_KWH, charge_cap_kw()

    soc = np.zeros((m, n + 1))
    soc[:, 0] = [s0 * cap for _, _, s0 in P.EXCAVATORS]
    remaining = np.array([req / P.DT_H for _, req, _ in P.EXCAVATORS])  # dig steps left
    power = np.zeros((m, n))
    modes = np.full((m, n), "off", dtype=object)
    in_low_soc_session = [False] * m
    knockoff_target = [s0 * cap if P.BASELINE_KNOCKOFF_TO_START_SOC else P.SOC_MAX * cap
                       for _, _, s0 in P.EXCAVATORS]
    on_charger = set()

    for t in range(n):
        h = hours[t]
        wants_charge, wants_dig = [], []
        for i in range(m):
            s = soc[i, t]
            if approved[t] and lunch[t]:
                if P.BASELINE_CHARGE_AT_LUNCH and s < P.SOC_MAX * cap - 1e-6:
                    wants_charge.append(i)
            elif approved[t]:
                if in_low_soc_session[i] and s >= P.BASELINE_RESUME_SOC * cap:
                    in_low_soc_session[i] = False
                if not in_low_soc_session[i] and s - P.DIG_POWER_KW * P.DT_H < P.BASELINE_LOW_SOC * cap:
                    in_low_soc_session[i] = True
                if in_low_soc_session[i]:
                    wants_charge.append(i)
                elif remaining[i] > 0:
                    wants_dig.append(i)
            elif h >= P.APPROVED_END_H:
                # knock-off: plug in and charge to target, regardless of hours
                if s < knockoff_target[i] - 1e-6:
                    wants_charge.append(i)

        # first come, first served on the shared chargers
        on_charger = {i for i in on_charger if i in wants_charge}
        for i in wants_charge:
            if len(on_charger) < P.N_CHARGERS:
                on_charger.add(i)

        for i in range(m):
            s = soc[i, t]
            if i in on_charger:
                top = knockoff_target[i] if h >= P.APPROVED_END_H else P.SOC_MAX * cap
                p = min(pmax, (top - s) / (P.CHARGE_EFF * P.DT_H))
                power[i, t] = p
                soc[i, t + 1] = s + P.CHARGE_EFF * p * P.DT_H
                modes[i, t] = "charge"
            elif i in wants_dig:
                soc[i, t + 1] = s - P.DIG_POWER_KW * P.DT_H
                remaining[i] -= 1
                modes[i, t] = "dig"
            else:
                soc[i, t + 1] = s
                modes[i, t] = "wait" if (approved[t] or i in wants_charge) else "off"

    demand = base + power.sum(axis=0)
    diesel = np.maximum(0.0, demand - limit_kw)
    return dict(name="Uncontrolled baseline", hours=hours, approved=approved, base=base,
                power=power, soc=soc, modes=modes, demand=demand, diesel=diesel,
                grid=demand - diesel, unmet_h=remaining * P.DT_H, limit=limit_kw)


# ---------------------------------------------------------------- optimised
def solve_optimised(limit_kw=P.SITE_LIMIT_KW, time_limit_s=60, full_objective=True):
    """full_objective=False keeps only unmet digging + diesel in the objective
    (fast feasibility check used by the sensitivity sweep)."""
    hours, approved, lunch, base = time_grid()
    n, m = len(hours), len(P.EXCAVATORS)
    cap, pmax, dt = P.BATTERY_KWH, charge_cap_kw(), P.DT_H
    T, M = range(n), range(m)
    dc_daily = P.DEMAND_CHARGE_PER_KW_MONTH / P.WORKING_DAYS_PER_MONTH

    prob = pulp.LpProblem("smart_earthworks", pulp.LpMinimize)
    dig = prob.add_variable_dicts("dig", (M, T), cat="Binary")
    con = prob.add_variable_dicts("con", (M, T), cat="Binary")
    p = prob.add_variable_dicts("p", (M, T), lowBound=0, upBound=pmax)
    soc = prob.add_variable_dicts("soc", (M, range(n + 1)), lowBound=P.SOC_MIN * cap, upBound=P.SOC_MAX * cap)
    dig_start = prob.add_variable_dicts("dig_start", (M, T), lowBound=0)
    diesel = prob.add_variable_dicts("diesel", T, lowBound=0)
    short = prob.add_variable_dicts("short", M, lowBound=0)       # unmet digging hours (feasibility alert)
    peak = prob.add_variable("peak_grid_kw", lowBound=0)

    for i, (_, req_h, s0) in enumerate(P.EXCAVATORS):
        prob += soc[i][0] == s0 * cap
        if P.TERMINAL_SOC_AT_LEAST_START:
            prob += soc[i][n] >= s0 * cap
        prob += pulp.lpSum(dig[i][t] for t in T) * dt + short[i] >= req_h
        for t in T:
            prob += dig[i][t] + con[i][t] <= 1                       # one state at a time
            prob += p[i][t] <= pmax * con[i][t]                       # compatible charging power
            if not approved[t]:                                       # approved working hours
                prob += dig[i][t] == 0
                prob += con[i][t] == 0
            if lunch[t]:
                prob += dig[i][t] == 0
            prob += soc[i][t + 1] == soc[i][t] + P.CHARGE_EFF * p[i][t] * dt - P.DIG_POWER_KW * dt * dig[i][t]
            if full_objective:
                prob += dig_start[i][t] >= dig[i][t] - (dig[i][t - 1] if t else 0)

    for t in T:
        prob += pulp.lpSum(con[i][t] for i in M) <= P.N_CHARGERS
        load = base[t] + pulp.lpSum(p[i][t] for i in M)
        prob += load - diesel[t] <= limit_kw                         # temporary supply limit
        prob += peak >= load - diesel[t]

    grid_kwh = pulp.lpSum(base[t] + pulp.lpSum(p[i][t] for i in M) - diesel[t] for t in T) * dt
    prob += (1e7 * pulp.lpSum(short[i] for i in M)   # completing planned work dominates
             + 1e3 * pulp.lpSum(diesel[t] for t in T) * dt
             + ((P.ENERGY_PRICE_PER_KWH * grid_kwh + dc_daily * peak
                 + 2.0 * pulp.lpSum(dig_start[i][t] for i in M for t in T)) if full_objective else 0))

    gap = 1e-2 if full_objective else 1e-6
    status = prob.solve(pulp.getSolver("HiGHS", msg=False, timeLimit=time_limit_s, gapRel=gap))

    power = np.array([[p[i][t].value() or 0.0 for t in T] for i in M])
    power[power < 1e-6] = 0.0
    socv = np.array([[soc[i][t].value() for t in range(n + 1)] for i in M])
    digv = np.array([[round(dig[i][t].value() or 0) for t in T] for i in M])
    modes = np.full((m, n), "off", dtype=object)
    for i in M:
        for t in T:
            if digv[i, t]:
                modes[i, t] = "dig"
            elif power[i, t] > 1e-3:
                modes[i, t] = "charge"
            elif approved[t]:
                modes[i, t] = "wait"
    dsl = np.array([diesel[t].value() or 0.0 for t in T])
    demand = base + power.sum(axis=0)
    return dict(name="Optimised schedule", hours=hours, approved=approved, base=base,
                power=power, soc=socv, modes=modes, demand=demand, diesel=dsl,
                grid=demand - dsl, unmet_h=np.array([short[i].value() or 0.0 for i in M]),
                limit=limit_kw, status=getattr(getattr(status, "status", status), "name", str(status)))


# ---------------------------------------------------------------- requirement checks
def metrics(r):
    dt, cap = P.DT_H, P.BATTERY_KWH
    active = np.isin(r["modes"], ["dig", "charge"])
    out_of_hours = active & ~r["approved"][None, :]
    gen_out_of_hours = (r["diesel"] > 1e-6) & ~r["approved"]
    grid_kwh = r["grid"].sum() * dt
    diesel_kwh = r["diesel"].sum() * dt
    peak_grid = r["grid"].max()
    cost = (grid_kwh * P.ENERGY_PRICE_PER_KWH
            + peak_grid * P.DEMAND_CHARGE_PER_KW_MONTH / P.WORKING_DAYS_PER_MONTH
            + diesel_kwh * P.DIESEL_COST_PER_KWH)
    return {
        "peak_demand_kw": r["demand"].max(),
        "steps_over_limit": int((r["demand"] > r["limit"] + 1e-6).sum()),
        "unmet_dig_h": float(r["unmet_h"].sum()),
        "min_soc_pct": 100 * r["soc"].min() / cap,
        "max_charge_kw": r["power"].max(),
        "out_of_hours_activity_h": out_of_hours.sum() * dt,
        "diesel_kwh": diesel_kwh,
        "grid_kwh": grid_kwh,
        "peak_grid_kw": peak_grid,
        "daily_cost": cost,
        "gen_hours_out_of_hours": gen_out_of_hours.sum() * dt,
    }


def er_table(mb, mo):
    lim, cap_kw = P.SITE_LIMIT_KW, charge_cap_kw()
    ok = lambda c: "PASS" if c else "FAIL"
    rows = [
        ("Limited peak demand", f"demand <= {lim:.0f} kW at 100% of steps",
         f"{mb['steps_over_limit']} steps over (peak {mb['peak_demand_kw']:.0f} kW)",
         f"{mo['steps_over_limit']} steps over (peak {mo['peak_demand_kw']:.0f} kW)",
         ok(mb["steps_over_limit"] == 0), ok(mo["steps_over_limit"] == 0)),
        ("Machine readiness", "100% of planned digging done, SoC never below reserve",
         f"{mb['unmet_dig_h']:.2f} h unmet, min SoC {mb['min_soc_pct']:.0f}%",
         f"{mo['unmet_dig_h']:.2f} h unmet, min SoC {mo['min_soc_pct']:.0f}%",
         ok(mb["unmet_dig_h"] < 1e-6 and mb["min_soc_pct"] >= 100 * P.SOC_MIN - 1e-6),
         ok(mo["unmet_dig_h"] < 1e-6 and mo["min_soc_pct"] >= 100 * P.SOC_MIN - 1e-6)),
        ("Compatible charging power", f"<= {cap_kw:.0f} kW per machine",
         f"max {mb['max_charge_kw']:.0f} kW", f"max {mo['max_charge_kw']:.0f} kW",
         ok(mb["max_charge_kw"] <= cap_kw + 1e-6), ok(mo["max_charge_kw"] <= cap_kw + 1e-6)),
        ("Approved working hours", "0 h of digging/charging outside 07:00-18:00",
         f"{mb['out_of_hours_activity_h']:.2f} h outside", f"{mo['out_of_hours_activity_h']:.2f} h outside",
         ok(mb["out_of_hours_activity_h"] == 0), ok(mo["out_of_hours_activity_h"] == 0)),
        ("Reduced diesel reliance", "< baseline; 0 kWh if grid-only plan exists",
         f"{mb['diesel_kwh']:.0f} kWh", f"{mo['diesel_kwh']:.0f} kWh",
         "baseline", ok(mo["diesel_kwh"] < mb["diesel_kwh"] or mo["diesel_kwh"] == 0)),
        ("Cost-effective charging", "daily cost <= baseline",
         f"${mb['daily_cost']:.0f}/day", f"${mo['daily_cost']:.0f}/day",
         "baseline", ok(mo["daily_cost"] <= mb["daily_cost"] + 1e-6)),
        ("Limited community noise", "0 h generator use outside standard hours",
         f"{mb['gen_hours_out_of_hours']:.2f} h", f"{mo['gen_hours_out_of_hours']:.2f} h",
         ok(mb["gen_hours_out_of_hours"] == 0), ok(mo["gen_hours_out_of_hours"] == 0)),
    ]
    head = "| Requirement | Specification | Baseline | Optimised | Baseline result | Optimised result |\n|---|---|---|---|---|---|\n"
    return head + "\n".join("| " + " | ".join(r) + " |" for r in rows)


# ---------------------------------------------------------------- figures
def _shade_hours(ax):
    ax.axvspan(P.DAY_START_H, P.APPROVED_START_H, color="#f2f2f2", zorder=0)
    ax.axvspan(P.APPROVED_END_H, P.DAY_END_H, color="#f2f2f2", zorder=0)
    ax.set_xlim(P.DAY_START_H, P.DAY_END_H)
    ax.set_xticks(range(int(P.DAY_START_H), int(P.DAY_END_H) + 1, 2))
    ax.set_xticklabels([f"{h:02d}:00" for h in range(int(P.DAY_START_H), int(P.DAY_END_H) + 1, 2)])


def plot_schedule(rb, ro, path):
    names = [e[0] for e in P.EXCAVATORS]
    fig, axes = plt.subplots(2, 1, figsize=(10, 4.8), sharex=True)
    for ax, r in zip(axes, (rb, ro)):
        _shade_hours(ax)
        for i, nm in enumerate(names):
            for t, mode in enumerate(r["modes"][i]):
                if mode != "off":
                    ax.broken_barh([(r["hours"][t], P.DT_H)], (len(names) - 1 - i - 0.35, 0.7),
                                   facecolors=COLOURS[mode], edgecolor="none")
        ax.set_yticks(range(len(names)))
        ax.set_yticklabels(names[::-1])
        ax.set_title(r["name"], loc="left", fontsize=11)
    handles = [plt.Rectangle((0, 0), 1, 1, color=COLOURS[k]) for k in ("dig", "charge", "wait")]
    handles.append(plt.Rectangle((0, 0), 1, 1, color="#f2f2f2"))
    fig.legend(handles, ["Dig", "Charge", "Wait", "Outside approved hours"], loc="lower center", ncol=4, frameon=False)
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    fig.savefig(path, dpi=200)
    plt.close(fig)


def plot_demand(rb, ro, path):
    fig, ax = plt.subplots(figsize=(10, 4.2))
    _shade_hours(ax)
    h = np.append(rb["hours"], P.DAY_END_H)
    ax.step(h, np.append(rb["demand"], rb["demand"][-1]), where="post", color="#e17055", lw=1.8, label="Uncontrolled baseline")
    ax.step(h, np.append(ro["demand"], ro["demand"][-1]), where="post", color="#1b998b", lw=2.2, label="Optimised schedule")
    ax.step(h, np.append(rb["base"], rb["base"][-1]), where="post", color="#7f8c8d", lw=1, ls=":", label="Site base load")
    ax.axhline(P.SITE_LIMIT_KW, color="#d35400", ls="--", lw=1.5, label=f"Temporary supply limit ({P.SITE_LIMIT_KW:.0f} kW)")
    ax.fill_between(h, P.SITE_LIMIT_KW, np.append(rb["demand"], rb["demand"][-1]), step="post",
                    where=np.append(rb["demand"], rb["demand"][-1]) > P.SITE_LIMIT_KW, color="#e17055", alpha=0.2,
                    label="Excess supplied by diesel generator")
    ax.set_ylabel("Site demand (kW)")
    ax.set_ylim(0, max(rb["demand"].max(), P.SITE_LIMIT_KW) * 1.15)
    ax.legend(loc="upper left", fontsize=8, frameon=False, ncol=2)
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


def plot_soc(rb, ro, path):
    m = len(P.EXCAVATORS)
    fig, axes = plt.subplots(m, 1, figsize=(10, 2.1 * m), sharex=True)
    h = np.append(rb["hours"], P.DAY_END_H)
    for i, ax in enumerate(np.atleast_1d(axes)):
        _shade_hours(ax)
        ax.plot(h, 100 * rb["soc"][i] / P.BATTERY_KWH, color="#e17055", lw=1.5, ls="--", label="Baseline")
        ax.plot(h, 100 * ro["soc"][i] / P.BATTERY_KWH, color="#1b998b", lw=2, label="Optimised")
        ax.axhline(100 * P.SOC_MIN, color="#7f8c8d", ls=":", lw=1, label="20% reserve")
        ax.set_ylim(0, 105)
        ax.set_ylabel("SoC (%)")
        ax.set_title(P.EXCAVATORS[i][0], loc="left", fontsize=10)
    np.atleast_1d(axes)[0].legend(loc="upper right", fontsize=8, frameon=False, ncol=3)
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


def sensitivity(limits):
    rows = []
    for lim in map(float, limits):
        mb = metrics(simulate_baseline(lim))
        mo = metrics(solve_optimised(lim, time_limit_s=30, full_objective=False))
        rows.append((float(lim), mb["diesel_kwh"], mo["diesel_kwh"], mo["unmet_dig_h"]))
    return np.array(rows)


def plot_sensitivity(rows, path):
    fig, ax = plt.subplots(figsize=(10, 3.8))
    ax.plot(rows[:, 0], rows[:, 1], "o-", color="#e17055", label="Baseline diesel energy")
    ax.plot(rows[:, 0], rows[:, 2], "o-", color="#1b998b", label="Optimised diesel energy")
    feasible = rows[(rows[:, 2] < 1e-3) & (rows[:, 3] < 1e-3), 0]
    if len(feasible):
        ax.axvline(feasible.min(), color="#2e86de", ls="--", lw=1.2,
                   label=f"Lowest limit with grid-only plan: {feasible.min():.0f} kW")
    ax.set_xlabel("Temporary supply limit (kW)")
    ax.set_ylabel("Diesel energy for charging (kWh/day)")
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return feasible.min() if len(feasible) else None


# ---------------------------------------------------------------- main
def main():
    OUT.mkdir(exist_ok=True)
    rb, ro = simulate_baseline(), solve_optimised()
    print("Solver status:", ro["status"])
    mb, mo = metrics(rb), metrics(ro)
    plot_schedule(rb, ro, OUT / "fig1_schedule.png")
    plot_demand(rb, ro, OUT / "fig2_site_demand.png")
    plot_soc(rb, ro, OUT / "fig3_battery_soc.png")
    limits = np.arange(100, 310, 10)
    rows = sensitivity(limits)
    min_lim = plot_sensitivity(rows, OUT / "fig4_sensitivity.png")

    keys = [("peak_demand_kw", "Peak site demand (kW)"), ("peak_grid_kw", "Peak grid import (kW)"),
            ("grid_kwh", "Grid energy (kWh/day)"), ("diesel_kwh", "Diesel energy (kWh/day)"),
            ("unmet_dig_h", "Unmet digging (h)"), ("min_soc_pct", "Lowest SoC (%)"),
            ("out_of_hours_activity_h", "Activity outside approved hours (h)"),
            ("daily_cost", "Illustrative daily cost ($)")]
    lines = ["# Model results\n", f"Solver status: {ro['status']}\n",
             "## Key metrics\n", "| Metric | Baseline | Optimised |", "|---|---|---|"]
    lines += [f"| {lab} | {mb[k]:.1f} | {mo[k]:.1f} |" for k, lab in keys]
    lines += ["\n## Engineering requirement check\n", er_table(mb, mo),
              "\n## Sensitivity to supply limit\n",
              "| Limit (kW) | Baseline diesel (kWh) | Optimised diesel (kWh) | Optimised unmet digging (h) |",
              "|---|---|---|---|"]
    lines += [f"| {r[0]:.0f} | {r[1]:.0f} | {r[2]:.0f} | {r[3]:.2f} |" for r in rows]
    lines.append(f"\nLowest supply limit with a grid-only, fully completed plan: **{min_lim} kW**")
    (OUT / "results.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
