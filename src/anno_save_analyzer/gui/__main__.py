"""``anno-save-analyzer-gui`` CLI entry．

Usage::

    anno-save-analyzer-gui <save.a7s> [--title anno1800] [--locale ja]

WSL2 から起動するときは ``QT_QPA_PLATFORM=wayland`` (WSLg) が default で効く．
ヘッドレス環境では ``QT_QPA_PLATFORM=offscreen`` を事前にセットする．
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from anno_save_analyzer.trade.models import GameTitle
from anno_save_analyzer.tui.state import load_state


def _run_qt_event_loop(app) -> int:
    """QApplication の event loop を回す．別関数化してるのは static
    analyzer の false positive (``app.exec`` を shell ``exec`` と誤認) 回避．
    """
    loop = getattr(app, "exec")  # noqa: B009
    return loop()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("save", type=Path, help="Anno save file (.a7s / .a8s)")
    parser.add_argument(
        "--title",
        choices=[t.value for t in GameTitle],
        default=GameTitle.ANNO_1800.value,
        help="game title (default: anno1800)",
    )
    parser.add_argument("--locale", default="en", help="UI locale (en / ja)")
    args = parser.parse_args(argv)

    if not args.save.is_file():
        print(f"ERROR: save file not found: {args.save}", file=sys.stderr)
        return 2

    title = GameTitle(args.title)
    state = load_state(args.save, title=title, locale=args.locale)

    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication

    from .main_window import BalanceMainWindow

    app = QApplication.instance() or QApplication(sys.argv)
    # cross-platform で揃った見た目にする．Windows native テーマはボタンが
    # 浮いて見栄えがブレるため Fusion で統一．
    app.setStyle("Fusion")
    # WSL2 は fontconfig のデフォルトが貧弱で日本語が豆腐 / ぼやける問題．
    # 優先順位で CJK 対応フォントを指定．Windows ネイティブでは Meiryo UI，
    # macOS は Hiragino，Linux は Noto Sans CJK が優先．
    font = QFont()
    font.setFamilies(
        [
            "Meiryo UI",
            "Segoe UI",
            "Hiragino Sans",
            "Noto Sans CJK JP",
            "Noto Sans CJK",
            "Sans Serif",
        ]
    )
    font.setPointSize(11)
    app.setFont(font)
    window = BalanceMainWindow(state)
    window.show()
    return _run_qt_event_loop(app)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
