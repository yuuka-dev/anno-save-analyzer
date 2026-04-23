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

    from PySide6.QtWidgets import QApplication

    from .main_window import BalanceMainWindow

    app = QApplication.instance() or QApplication(sys.argv)
    window = BalanceMainWindow(state)
    window.show()
    return _run_qt_event_loop(app)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
