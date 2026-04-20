"""Subdued default-theme overrides．

設計書 §9.3 通り，独自パレット無し，装飾無し，アクセントは端末赤（負）/
端末緑（正）の 2 色のみ．USSR テーマはジョーク枠で書記長本人のみ利用．
"""

from __future__ import annotations

# Textual の default theme の上に乗せる薄い CSS．
# クラス命名は Pythonic に keep し，``add_class("trend-positive")`` 等で当てる．
DEFAULT_CSS = """
.trend-positive {
    color: $success;
}
.trend-negative {
    color: $error;
}
.muted {
    color: $text-muted;
}
.heading {
    text-style: bold;
}
"""

# USSR テーマ (書記長専用)．赤 + 金のコミンテルン配色．
# 鎌と槌 ``☭`` は ``TradeApp`` 側で title に prefix する．
USSR_CSS = """
Screen {
    background: rgb(139, 0, 0);
}
Header {
    background: rgb(178, 34, 34);
    color: rgb(255, 215, 0);
    text-style: bold;
}
Footer {
    background: rgb(178, 34, 34);
    color: rgb(255, 215, 0);
}
.trend-positive {
    color: rgb(255, 215, 0);
}
.trend-negative {
    color: rgb(255, 220, 220);
}
.muted {
    color: rgb(255, 215, 0) 60%;
}
.heading {
    text-style: bold;
    color: rgb(255, 215, 0);
}
"""

_THEMES: dict[str, str] = {
    "default": DEFAULT_CSS,
    "ussr": USSR_CSS,
}

# USSR テーマでのみ付与する title prefix．
USSR_TITLE_PREFIX = "☭ "


def theme_css(name: str) -> str:
    """テーマ名から CSS を引く．未知名は default にフォールバック．"""
    return _THEMES.get(name, DEFAULT_CSS)
