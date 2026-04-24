# Decision Matrix

A rule-based prescription engine that classifies every (island, product)
deficit into one of five categories and explains why.

## Categories

| category | trigger | suggested action |
| --- | --- | --- |
| ``increase_production`` | chronic deficit + high satisfaction + strong route | Build more factories of this product. |
| ``trade_flex`` | transient deficit + weak correlation + weak route | Short-term trading or small route tweak. |
| ``rebalance_mix`` | strong route but still deficit | Rewrite the route's loadout, don't add ships. |
| ``ok`` | surplus | Nothing to do. |
| ``monitor`` | rule didn't fire | Keep an eye on it. |

## Usage

```python
from anno_save_analyzer.analysis.prescribe import diagnose, Thresholds

rx = diagnose(frames, storage_by_island=state.storage_by_island)

# Breakdown by category
rx["category"].value_counts()

# Okayama's top prescriptions
rx[rx["city_name"] == "大都会岡山"] \
    [["product_name", "category", "action", "rationale"]].head(20)
```

## Tuning thresholds

All rule thresholds live in {class}`~anno_save_analyzer.analysis.prescribe.Thresholds`.

```python
loose = Thresholds(
    high_saturation=0.60,          # default 0.70
    low_correlation=0.40,          # default 0.30
    strong_route_tons_per_min=0.5, # default 1.0
)
rx_loose = diagnose(frames, thresholds=loose,
                    storage_by_island=state.storage_by_island)
```

The ``rationale`` column is human-readable; filter on it to audit the rule
chain.

## What the rules look like

1. **Rule 1** — `persistence == "chronic"` ∧ `saturation >= high_saturation`
   ∧ `(city_name, product) ∈ strong_pairs`  →  ``increase_production``
2. **Rule 2** — `persistence == "transient"` ∧ `|correlation| < low_correlation`
   ∧ *not* in strong_pairs  →  ``trade_flex``
3. **Rule 3** — strong_pairs ∧ `delta < 0`  →  ``rebalance_mix``
4. **Fallback** — anything else unfinished → ``monitor``.

Persistence, correlation, and strong-pair computation are all pure functions
defined in the respective analyzer modules — see
{func}`~anno_save_analyzer.analysis.persistence.classify_deficit` and
{func}`~anno_save_analyzer.analysis.correlation.saturation_vs_deficit`.
