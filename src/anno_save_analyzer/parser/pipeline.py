"""セーブデータ解析の薄い pipeline API．

v0.1.0 時点では RDA → inner zlib 解凍までを提供する．
FileDB 解析 / XML 化 / SessionData 解読は後続のマイルストーンで追加．
"""

from __future__ import annotations

import zlib
from pathlib import Path

from .rda import RDAArchive


def extract_inner_filedb(a7s_path: str | Path, dest: str | Path | None = None) -> bytes:
    """``.a7s`` RDA コンテナから ``data.a7s`` を取り出し zlib 解凍まで行う．

    返り値は FileDB (V1/V2/V3) 形式の生バイナリ．
    ``dest`` を指定するとそのパスに書き出す．
    """
    with RDAArchive(a7s_path) as rda:
        raw_data = rda.read("data.a7s")
    inner = zlib.decompress(raw_data)
    if dest is not None:
        Path(dest).write_bytes(inner)
    return inner
