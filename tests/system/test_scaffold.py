"""system テスト layer の scaffold．

CLI / GUI entrypoint を実際に起動し終了コード / 出力を検証する試験を置く．
sample save に依存する場合は ``@pytest.mark.slow`` と併用して CI では
workflow_dispatch 時のみ走らせる方針．

本 PR はディレクトリと marker の足場のみ．具体 test は後続 feature PR で追加．

実行方法::

    pytest -m system
"""

from __future__ import annotations

import pytest


@pytest.mark.system
def test_system_scaffold_placeholder() -> None:
    """足場確認．marker が登録されていることと import 解決できることだけ見る．"""
    assert True
