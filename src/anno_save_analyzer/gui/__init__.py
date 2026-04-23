"""PySide6 GUI for anno-save-analyzer (optional extra ``[gui]``).

書記長のデスクトップ向け画面．TUI (``anno_save_analyzer.tui``) と同じ
``TuiState`` モデル層を共有しつつ，view だけ Qt で再実装する．

Entrypoint::

    anno-save-analyzer-gui sample_anno1800.a7s --title anno1800
"""

from .main_window import BalanceMainWindow

__all__ = ["BalanceMainWindow"]
