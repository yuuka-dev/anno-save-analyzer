"""Subdued default-theme overrides．

設計書 §9.3 通り，独自パレット無し，装飾無し，アクセントは端末赤（負）/
端末緑（正）の 2 色のみ．
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
