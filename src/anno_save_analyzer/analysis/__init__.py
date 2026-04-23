"""SCM analytics: ``TuiState`` を pandas DataFrame に変換する分析層．

v0.5 milestone の前提 (#81-A)．``to_frames`` で 4 本の DataFrame
(islands / tiers / balance / trade_events) を得てから，deficit heatmap /
相関 / route ランキング / 予測 / MILP 等の後続 analyzer を chain する．

Title 非依存: Anno 117 / Anno 1800 の両方で動く．``consumption`` /
``factory_recipes`` が無い title では balance は空 DataFrame だが schema
は維持する．
"""

from __future__ import annotations

from .frames import AnalysisFrames, to_frames

__all__ = ["AnalysisFrames", "to_frames"]
