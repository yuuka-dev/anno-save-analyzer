"""Anno 1800 interpreter．

DOM spike (2026-04-22, ``sample_anno1800.a7s`` 8852 events) で次を実測確認
してあり，``Anno117Interpreter`` のロジックそのままで通る:

- ``TradedGoods`` の祖先 stack は 117 と完全同形
  (``[..., AreaInfo, <1>, PassiveTrade, History, {TradeRouteEntries|PassiveTradeEntries}, <1>, <1>, TradedGoods]``)
- ``GoodGuid`` / ``GoodAmount`` / ``TotalPrice`` の attrib 名・layout も同一
- 内側エントリの ``ExecutionTime`` / ``RouteID`` / ``RouteName`` / ``Trader`` も同名

固有の差: Anno 1800 では ``TotalPrice`` が sparse (実測 4.5%)．自国島間
ルート輸送には gold が発生せず，NPC 取引のみ price が付くため．これは
ゲーム仕様で interpreter の問題ではない．

回帰テストは ``tests/trade/test_anno1800_smoke.py`` で end-to-end に保護する．
"""

from __future__ import annotations

from ..models import GameTitle
from .anno117 import Anno117Interpreter


class Anno1800Interpreter(Anno117Interpreter):
    """Anno 1800 用 interpreter．DOM 同形のため 117 を継承するだけで動く．"""

    title = GameTitle.ANNO_1800
