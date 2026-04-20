"""Unicode block sparkline renderer．

DataTable の cell に埋め込める小さな文字列トレンド．plotext を使わず
``▁▂▃▄▅▆▇█`` の 8 段階ブロック文字列で累積時系列を表現する．
"""

from __future__ import annotations

from collections.abc import Iterable

_BLOCKS = "▁▂▃▄▅▆▇█"


def sparkline(values: Iterable[float], width: int = 12) -> str:
    """累積 / 時系列値を sparkline 文字列に変換．

    - ``values`` が空なら 1 つの ``BLOCKS[0]`` だけ返す (cell で空欄に見えない程度)
    - 値が全て同じなら中段で平坦な直線
    - ``width`` を超える場合は等間隔サンプリングして縮める
    - ``width`` 未満なら全部使う (padding はしない．cell 幅で揃う)
    """
    seq = [float(v) for v in values]
    if not seq:
        return _BLOCKS[0]
    if len(seq) > width:
        step = len(seq) / width
        seq = [seq[int(i * step)] for i in range(width)]
    lo = min(seq)
    hi = max(seq)
    if hi == lo:
        return _BLOCKS[len(_BLOCKS) // 2] * len(seq)
    span = hi - lo
    scale = len(_BLOCKS) - 1
    return "".join(_BLOCKS[min(scale, int((v - lo) / span * scale))] for v in seq)
