"""``TradeApp`` — Textual app entry．"""

from __future__ import annotations

from pathlib import Path

from textual.app import App
from textual.binding import Binding

from anno_save_analyzer.trade.models import GameTitle

from .i18n import Localizer
from .screens import OverviewScreen, TradeStatisticsScreen
from .state import TuiState, load_state
from .theme import DEFAULT_CSS


class TradeApp(App[None]):
    """nano-flavored binding 契約をもつトップレベル App．"""

    CSS = DEFAULT_CSS

    # App-level に置く事で画面横断的に効く．screen-level binding はキーが
    # 子 widget に吸われて届かないことがある．
    BINDINGS = [
        Binding("ctrl+x", "quit", "Exit", priority=True),
        Binding("ctrl+g", "show_help", "Help"),
        Binding("ctrl+t", "switch_main_screen", "Switch screen"),
        Binding("ctrl+l", "toggle_locale", "Locale"),
    ]

    def __init__(
        self,
        state: TuiState,
        *,
        localizer: Localizer | None = None,
    ) -> None:
        super().__init__()
        self._state = state
        self._localizer = localizer or Localizer.load(state.locale)
        self._apply_localized_bindings()
        self.title = self._localizer.t("app.title")

    @classmethod
    def from_save(
        cls,
        save_path: str | Path,
        *,
        title: GameTitle = GameTitle.ANNO_117,
        locale: str = "en",
    ) -> TradeApp:
        state = load_state(Path(save_path), title=title, locale=locale)
        return cls(state)

    def on_mount(self) -> None:
        self.install_screen(OverviewScreen(self._state, self._localizer), name="overview")
        self.install_screen(TradeStatisticsScreen(self._state, self._localizer), name="statistics")
        self.push_screen("overview")

    def action_switch_main_screen(self) -> None:
        # 現在画面の type に応じてもう片方へ．switch_screen は same target なら
        # textual 側で no-op になるためガード不要．
        target = "statistics" if isinstance(self.screen, OverviewScreen) else "overview"
        self.switch_screen(target)

    def action_toggle_locale(self) -> None:
        new_code = "ja" if self._localizer.code == "en" else "en"
        self.switch_locale(new_code)

    def switch_locale(self, code: str) -> None:
        """Live locale switching．installed screens の localizer を差し替え，
        ``refresh(recompose=True)`` で再描画する．screen を uninstall するのは
        active stack 中はエラーになるため避ける．
        """
        self._localizer = self._localizer.with_locale(code)
        self._apply_localized_bindings()
        self.title = self._localizer.t("app.title")
        for screen in (self.get_screen("overview"), self.get_screen("statistics")):
            screen._localizer = self._localizer
            screen.refresh(recompose=True)

    def action_show_help(self) -> None:  # pragma: no cover - manual interaction only
        self.notify(self._localizer.t("binding.help"))

    def _apply_localized_bindings(self) -> None:
        self.BINDINGS = [
            Binding("ctrl+x", "quit", self._localizer.t("binding.exit"), priority=True),
            Binding("ctrl+g", "show_help", self._localizer.t("binding.help")),
            Binding(
                "ctrl+t",
                "switch_main_screen",
                f"{self._localizer.t('binding.overview')}/{self._localizer.t('binding.statistics')}",
            ),
            Binding("ctrl+l", "toggle_locale", self._localizer.t("binding.locale")),
        ]
        self.refresh_bindings()
