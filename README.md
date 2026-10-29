# Smart Earthworks — Scheduling Model Demonstration

ENGG3112 Conceptual Design Proposal, Tutorial 3 – Group 7 (The University of Sydney, S2 2026).

This prototype supports Section 3.4 (Model Demonstration) of the proposal. It schedules when
each battery-electric excavator digs, charges or waits so that planned excavation is completed
**without** site demand exceeding the temporary supply limit, and compares the result with
uncontrolled charging.

The model is a mixed-integer linear program written with the **PuLP** modelling library and
solved with the open-source **HiGHS** solver.

## How to run

Requires Python 3.12. Use a virtual environment so nothing is installed globally.

Windows:

```
py -3.12 -m venv env3112
env3112\Scripts\python.exe -m pip install -r requirements.txt
env3112\Scripts\python.exe model.py
```

macOS / Linux:

```
python3.12 -m venv env3112
env3112/bin/pip install -r requirements.txt
env3112/bin/python model.py
```

A full run takes about 2–3 minutes (main schedule up to 60 s, then a sensitivity sweep).

## Files

Running `model.py` writes the figures and `results.md` to an `outputs/` folder. The copies in this repository were produced by that run.

| File | Content |
|---|---|
| `params.py` | All scenario inputs; each is tagged SOURCE (published data) or ASSUMPTION |
| `model.py` | Uncontrolled-charging baseline, optimisation model, results and figures |
| `results.md` | Metrics, engineering-requirement check and sensitivity table |
| `fig1_schedule.png` | Dig / charge / wait schedule (proposal Figure: schedule) |
| `fig2_site_demand.png` | Site demand against the supply limit |
| `fig3_battery_soc.png` | Battery state of charge per machine |
| `fig4_sensitivity.png` | Diesel-generated energy at different supply limits |

## Formulation

Time step Δt = 15 min; modelled window 06:00–21:00; excavators *i*.

**Decision variables**
- dig<sub>i,t</sub> ∈ {0,1}: machine digs
- con<sub>i,t</sub> ∈ {0,1}: machine is on a charger
- p<sub>i,t</sub> ≥ 0: charging power (kW)
- E<sub>i,t</sub>: battery energy (kWh)
- g<sub>t</sub> ≥ 0: diesel-generated power (kW)
- s<sub>i</sub> ≥ 0: unmet digging hours (triggers the feasibility alert)

**Constraints**

| Constraint | Equation | Engineering requirement |
|---|---|---|
| One state at a time | dig + con ≤ 1 | — |
| Charging power | p<sub>i,t</sub> ≤ min(charger rating, machine limit) · con<sub>i,t</sub> | Compatible charging power |
| Shared chargers | Σ<sub>i</sub> con<sub>i,t</sub> ≤ number of chargers | — |
| Battery balance | E<sub>t+1</sub> = E<sub>t</sub> + η·p·Δt − P<sub>dig</sub>·Δt·dig | — |
| Battery limits | 20% ≤ SoC ≤ 100% | Machine readiness |
| Repeatable day | end SoC ≥ start SoC | — |
| Work completed | Σ dig·Δt + s<sub>i</sub> ≥ required digging hours | Machine readiness |
| Approved hours | dig = con = 0 outside 07:00–18:00; no digging during the 12:00 break | Approved working hours |
| Supply limit | base load<sub>t</sub> + Σ<sub>i</sub> p<sub>i,t</sub> − g<sub>t</sub> ≤ limit | Limited peak demand |

**Objective** (weighted in priority order)
1. Minimise unmet digging
2. Minimise diesel-generated energy
3. Minimise energy cost and demand charge
4. Small penalty per digging start, so work comes in practical blocks

The proposal (Section 3.3) gives the general formulation with tasks and individual chargers.
This prototype simplifies it: each excavator has one task expressed in digging hours, and the
chargers are treated as a shared pool.

**Solver status**
- The main run stops at a 60 s time limit. The schedule is the best found in that time, not a
  proven optimum, but every constraint is satisfied and `results.md` checks each requirement
  independently of the solver.
- The sensitivity sweep uses only the first two objectives and solves to optimality in about
  1 s per case.

## Uncontrolled-charging baseline
- Dig whenever work remains.
- Go to a charger at 25% SoC and charge at full power to 90%.
- All machines plug in at the lunch break.
- At 18:00, plug in and charge back to the morning SoC (so both scenarios end the day with the
  same stored energy).
- Chargers are first come, first served.
- Any demand above the supply limit is met by a diesel generator.

## Inputs

**From published sources**
- Volvo EC230 Electric: 450 kWh battery, 7–8 h runtime, up to 250 kW DC charging; 150 kW DC
  charger option (Volvo CE, 2025)
- Standard hours 07:00–18:00 (NSW Interim Construction Noise Guideline, 2009)

**Group assumptions** (to be replaced with RCC site data during the pilot)
- Supply limit 250 kW (≈ 400 A at 415 V three-phase, power factor 0.9)
- Hourly site base load of 30–80 kW
- Required digging hours and starting SoC for each machine
- 2 shared chargers; 93% charging efficiency
- 55 kW average digging power

**Indicative cost rates** used only for the model's daily cost comparison: $0.20/kWh grid
energy, $15/kW per month demand charge, $0.65/kWh diesel-generated energy. Section 7 of the
proposal re-estimates the value of avoided diesel using sourced generator and fuel-price data.
