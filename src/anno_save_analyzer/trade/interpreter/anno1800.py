"""Anno 1800 interpreter（Week 3 で完全実装予定の skeleton）．

現状は Anno 117 とほぼ同じ DOM 構造（FileDB V3）を使うため，差分が
判明するまでは Anno117Interpreter のロジックを継承する．
"""

from __future__ import annotations

from ..models import GameTitle
from .anno117 import Anno117Interpreter


class Anno1800Interpreter(Anno117Interpreter):
    """Anno 1800 用 interpreter．Week 3 で 1800 固有の差分を追加予定．"""

    title = GameTitle.ANNO_1800
