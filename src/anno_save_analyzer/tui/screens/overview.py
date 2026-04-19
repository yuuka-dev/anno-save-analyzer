"""Overview 画面．セーブのメタ情報と貿易サマリを 1 ページに表示．"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from ..i18n import Localizer
from ..state import TuiState


class OverviewScreen(Screen):
    """書記長の最初の着地点．"""

    def __init__(self, state: TuiState, localizer: Localizer) -> None:
        super().__init__(name="overview")
        self._state = state
        self._localizer = localizer

    def compose(self) -> ComposeResult:
        yield Header()
        yield VerticalScroll(self._render_body())
        yield Footer()

    def _render_body(self) -> Static:
        t = self._localizer.t
        ov = self._state.overview
        sessions_block = (
            "\n".join(f"  - {t('statistics.tree_session', index=sid)}" for sid in ov.session_ids)
            or f"  - ({t('overview.empty')})"
        )
        body = (
            f"[b]{t('overview.heading')}[/b]\n"
            f"  {t('overview.save')}    : {ov.save_path.name}\n"
            f"  {t('overview.title')}   : {ov.title.value}\n"
            f"\n"
            f"[b]{t('overview.sessions')}[/b]\n"
            f"{sessions_block}\n"
            f"\n"
            f"[b]{t('overview.snapshot')}[/b]\n"
            f"  {t('overview.events')}        : {ov.total_events:,}\n"
            f"  {t('overview.distinct_goods')}: {ov.distinct_goods:,}\n"
            f"  {t('overview.distinct_routes')}: {ov.distinct_routes:,}\n"
            f"  {t('overview.net_gold')}      : {ov.net_gold:+,} g\n"
        )
        return Static(body, id="overview-body")
