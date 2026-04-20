"""ゲーム title ごとのセッション識別 → display key マップ．

内部 session id (``"0"`` / ``"1"`` ...) は単なる order index．書記長が見る
画面では ``"Latium"`` / ``"アルビオン"`` のような実プレイ名で出したい．
辞書はここに集約し，display 名は localizer 経由で解決する．
"""

from __future__ import annotations

from .models import GameTitle

# title → tuple of session keys (in extraction order)．
# locale yaml の `session.<title>.<key>` を引いて display 名を得る．
SESSION_KEYS: dict[GameTitle, tuple[str, ...]] = {
    GameTitle.ANNO_117: ("latium", "albion"),
    GameTitle.ANNO_1800: (
        "old_world",
        "new_world",
        "cape_trelawney",
        "arctic",
        "enbesa",
    ),
}


def session_key_for(title: GameTitle, index: int) -> str | None:
    """``index`` 番目のセッションに対応する key を返す．未定義なら ``None``．"""
    keys = SESSION_KEYS.get(title)
    if keys is None or index < 0 or index >= len(keys):
        return None
    return keys[index]


def session_locale_key(title: GameTitle, index: int) -> str:
    """``locales/*.yaml`` の lookup key を組む．未定義の index は generic にフォールバック．"""
    key = session_key_for(title, index)
    if key is None:
        return "session.unknown"
    return f"session.{title.value}.{key}"
