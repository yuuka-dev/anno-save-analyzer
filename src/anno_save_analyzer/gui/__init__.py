"""PySide6 GUI for anno-save-analyzer (optional extra ``[gui]``).

書記長のデスクトップ向け画面．TUI (``anno_save_analyzer.tui``) と同じ
``TuiState`` モデル層を共有しつつ，view だけ Qt で再実装する．

Entrypoint::

    anno-save-analyzer-gui sample_anno1800.a7s --title anno1800

PySide6 は optional dependency．本 package を import すること自体は
PySide6 無くても成功する (viewmodels は Qt 非依存)．``BalanceMainWindow``
などの Qt widget は lazy attribute 経由で取り出す．
"""

from __future__ import annotations

__all__ = ["BalanceMainWindow"]


def __getattr__(name: str):
    """PySide6 依存シンボルを遅延 import．PySide6 未 install 環境でも
    ``from anno_save_analyzer.gui.viewmodels import ...`` は通す．
    """
    if name == "BalanceMainWindow":
        from .main_window import BalanceMainWindow

        return BalanceMainWindow
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
