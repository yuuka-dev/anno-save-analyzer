# SCM analytics (v0.5)

A pandas-native analytics layer that turns every byte of your Anno save into
decision-ready tables. The analyzers line up with the question *where is my
bottleneck, and what do I do about it?*

## The 10 analyzers

| Function | Question it answers |
| --- | --- |
| {func}`~anno_save_analyzer.analysis.to_frames` | Give me tidy DataFrames. |
| {func}`~anno_save_analyzer.analysis.deficit.deficit_heatmap` | Which island × product is red? |
| {func}`~anno_save_analyzer.analysis.deficit.pareto` | Which 20% of products drive 80% of consumption? |
| {func}`~anno_save_analyzer.analysis.correlation.saturation_vs_deficit` | Is the deficit actually hurting satisfaction? |
| {func}`~anno_save_analyzer.analysis.routes.rank_routes` | Which ship routes do the most work? |
| {func}`~anno_save_analyzer.analysis.persistence.classify_deficit` | Is this deficit chronic or transient? |
| {func}`~anno_save_analyzer.analysis.sensitivity.route_leave_one_out` | If I remove one ship, what breaks? |
| {func}`~anno_save_analyzer.analysis.forecast.consumption_forecast` | How bad will the deficit get in N hours? |
| {func}`~anno_save_analyzer.analysis.prescribe.diagnose` | **Give me a prescription per island × product.** |
| {func}`~anno_save_analyzer.analysis.allocation.optimal_flow` | Optimal supplier → demander matching. |
| {func}`~anno_save_analyzer.analysis.optimize.optimize_routes` | VRP (ship routing) with capacity and distance. |

## Walk-through

```python
from anno_save_analyzer.tui.state import load_state
from anno_save_analyzer.trade.models import GameTitle
from anno_save_analyzer.analysis import to_frames
from anno_save_analyzer.analysis.deficit import deficit_heatmap, pareto
from anno_save_analyzer.analysis.prescribe import diagnose

state = load_state("sample_anno1800.a7s", title=GameTitle.ANNO_1800, locale="ja")
frames = to_frames(state)

# 1. Island × product heatmap (rows=islands, cols=products, cell=delta/min)
heat = deficit_heatmap(frames.balance)

# 2. ABC analysis of consumption (80/95 cutoffs)
abc = pareto(frames.balance, metric="consumed_per_minute")
top_20pct = abc[abc["abc_rank"] == "A"]

# 3. Prescription
rx = diagnose(frames, storage_by_island=state.storage_by_island)
rx["category"].value_counts()
```

For the full Decision Matrix see {doc}`decision-matrix`.
