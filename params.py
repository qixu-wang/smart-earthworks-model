"""Scenario parameters for the Smart Earthworks scheduling model.

Every value is tagged SOURCE (published data) or ASSUMPTION (group judgement,
listed in Appendix A of the proposal).
"""

# ---------------------------------------------------------------- time grid
DT_H = 0.25                 # ASSUMPTION: 15-min time step, common in smart-charging studies
DAY_START_H = 6.0           # modelled window 06:00-21:00 (wider than approved hours so the
DAY_END_H = 21.0            #   baseline's out-of-hours charging is visible)
APPROVED_START_H = 7.0      # SOURCE ICNG (2009) standard hours Mon-Fri 07:00-18:00
APPROVED_END_H = 18.0
LUNCH_START_H = 12.0        # ASSUMPTION: 30-min crew break, no digging
LUNCH_END_H = 12.5

# ---------------------------------------------------------------- machines
# SOURCE Volvo CE (2025), EC230 Electric: 450 kWh battery, 7-8 h runtime,
# DC fast charging up to 250 kW.
BATTERY_KWH = 450.0
MACHINE_MAX_CHARGE_KW = 250.0
# ASSUMPTION: average digging draw = ~90% of 450 kWh over a 7.5 h runtime = 54 kW -> 55 kW
DIG_POWER_KW = 55.0
SOC_MIN = 0.20              # ASSUMPTION: 20% reserve (Volvo quotes fast-charge times from 20%)
SOC_MAX = 1.00
CHARGE_EFF = 0.93           # ASSUMPTION: grid-to-battery efficiency

# name, required digging hours today, state of charge at 07:00
# ASSUMPTION: illustrative early-earthworks day for a 3-excavator fleet
EXCAVATORS = [
    ("Excavator 1", 7.5, 0.55),
    ("Excavator 2", 7.0, 0.45),
    ("Excavator 3", 6.0, 0.65),
]
# ASSUMPTION: each machine must end the day with at least its starting SoC,
# so the plan is repeatable day after day without out-of-hours charging.
TERMINAL_SOC_AT_LEAST_START = True

# ---------------------------------------------------------------- site power
N_CHARGERS = 2              # ASSUMPTION: fewer chargers than machines (shared hire units)
CHARGER_RATED_KW = 150.0    # SOURCE Volvo CE (2025): Volvo offers a 150 kW DC fast charger option
# ASSUMPTION: temporary supply ~400 A, 415 V three-phase
#   sqrt(3) x 415 V x 400 A = 287 kVA; x 0.9 power factor = 259 kW -> 250 kW usable
SITE_LIMIT_KW = 250.0

# ASSUMPTION: base load (site sheds, lighting, dewatering pumps, small tools), kW by hour
BASE_LOAD_BY_HOUR = {
    6: 30, 7: 55, 8: 65, 9: 70, 10: 70, 11: 75, 12: 60, 13: 75,
    14: 80, 15: 75, 16: 70, 17: 60, 18: 40, 19: 30, 20: 30,
}

# ---------------------------------------------------------------- baseline behaviour
# ASSUMPTION: "uncontrolled" = how crews charge without a plan
BASELINE_LOW_SOC = 0.25     # go to a charger when SoC falls to 25%
BASELINE_RESUME_SOC = 0.90  # charge until 90% before resuming digging
BASELINE_CHARGE_AT_LUNCH = True
# Plug in at 18:00 and charge back to the morning SoC, so both scenarios end the day
# with the same stored energy (like-for-like energy, diesel and cost comparison).
BASELINE_KNOCKOFF_TO_START_SOC = True

# ---------------------------------------------------------------- illustrative costs
# ASSUMPTION: indicative rates for the model's daily cost comparison only;
# Section 7 of the proposal re-estimates avoided diesel with sourced data
ENERGY_PRICE_PER_KWH = 0.20      # $/kWh network + retail energy
DEMAND_CHARGE_PER_KW_MONTH = 15  # $/kW/month on maximum demand, cf. Ausgrid demand pricing
WORKING_DAYS_PER_MONTH = 22
DIESEL_COST_PER_KWH = 0.65       # ~0.3 L/kWh x ~$2.15/L generator fuel
