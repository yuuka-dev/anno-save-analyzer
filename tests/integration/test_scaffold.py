"""integration テスト layer の scaffold．

v0.4 supply-balance milestone (#12) で save → population → factories → balance
→ render の end-to-end を検証する予定．本 PR はディレクトリと marker の足場
のみで，具体 test は後続 feature PR で追加する．

実行方法::

    pytest -m integration
"""

from __future__ import annotations

import pytest


@pytest.mark.integration
def test_integration_scaffold_placeholder() -> None:
    """足場確認．marker が登録されていることと import 解決できることだけ見る．"""
    assert True
