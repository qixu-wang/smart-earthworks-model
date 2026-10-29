# Model results

Solver status: TimeLimit

## Key metrics

| Metric | Baseline | Optimised |
|---|---|---|
| Peak site demand (kW) | 375.0 | 191.0 |
| Peak grid import (kW) | 250.0 | 191.0 |
| Grid energy (kWh/day) | 1764.2 | 2097.4 |
| Diesel energy (kWh/day) | 333.2 | 0.0 |
| Unmet digging (h) | 0.0 | 0.0 |
| Lowest SoC (%) | 25.3 | 20.0 |
| Activity outside approved hours (h) | 1.5 | 0.0 |
| Illustrative daily cost ($) | 739.9 | 549.7 |

## Engineering requirement check

| Requirement | Specification | Baseline | Optimised | Baseline result | Optimised result |
|---|---|---|---|---|---|
| Limited peak demand | demand <= 250 kW at 100% of steps | 12 steps over (peak 375 kW) | 0 steps over (peak 191 kW) | FAIL | PASS |
| Machine readiness | 100% of planned digging done, SoC never below reserve | 0.00 h unmet, min SoC 25% | 0.00 h unmet, min SoC 20% | PASS | PASS |
| Compatible charging power | <= 150 kW per machine | max 150 kW | max 136 kW | PASS | PASS |
| Approved working hours | 0 h of digging/charging outside 07:00-18:00 | 1.50 h outside | 0.00 h outside | FAIL | PASS |
| Reduced diesel reliance | < baseline; 0 kWh if grid-only plan exists | 333 kWh | 0 kWh | baseline | PASS |
| Cost-effective charging | daily cost <= baseline | $740/day | $550/day | baseline | PASS |
| Limited community noise | 0 h generator use outside standard hours | 0.50 h | 0.00 h | FAIL | PASS |

## Sensitivity to supply limit

| Limit (kW) | Baseline diesel (kWh) | Optimised diesel (kWh) | Optimised unmet digging (h) |
|---|---|---|---|
| 100 | 1025 | 867 | 0.00 |
| 110 | 972 | 757 | 0.00 |
| 120 | 921 | 647 | 0.00 |
| 130 | 871 | 537 | 0.00 |
| 140 | 821 | 427 | 0.00 |
| 150 | 771 | 317 | 0.00 |
| 160 | 721 | 207 | 0.00 |
| 170 | 671 | 118 | 0.00 |
| 180 | 621 | 48 | 0.00 |
| 190 | 571 | 0 | 0.00 |
| 200 | 521 | 0 | 0.00 |
| 210 | 471 | 0 | 0.00 |
| 220 | 429 | 0 | 0.00 |
| 230 | 394 | 0 | 0.00 |
| 240 | 363 | 0 | 0.00 |
| 250 | 333 | 0 | 0.00 |
| 260 | 303 | 0 | 0.00 |
| 270 | 273 | 0 | 0.00 |
| 280 | 243 | 0 | 0.00 |
| 290 | 213 | 0 | 0.00 |
| 300 | 185 | 0 | 0.00 |

Lowest supply limit with a grid-only, fully completed plan: **190.0 kW**