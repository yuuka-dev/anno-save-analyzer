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
    # Anno 1800 は book 1 から DLC を時系列で解放する順に作られる内部 index と
    # 思っとったが **実セーブで実測したら違った** (書記長報告 2026-04-22)．
    # FileDB の ``SessionData > BinaryData`` が並ぶ順は「Cape Trelawney, Old World,
    # Enbesa, New World, Arctic」やった．世界地図の章立て順でも年代順でもない，
    # Ubisoft 内部の asset ID 順っぽい．実セーブ起点で固定する．
    GameTitle.ANNO_1800: (
        "cape_trelawney",
        "old_world",
        "enbesa",
        "new_world",
        "arctic",
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
