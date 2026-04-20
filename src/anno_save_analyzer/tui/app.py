"""``TradeApp`` — Textual app entry．"""

from __future__ import annotations

import datetime as _dt
import hashlib
from pathlib import Path

from textual.app import App
from textual.binding import Binding

from anno_save_analyzer.trade import (
    by_item,
    by_route,
    events_to_csv,
    inventory_to_csv,
    items_to_csv,
    routes_to_csv,
)
from anno_save_analyzer.trade.aggregate import filter_events
from anno_save_analyzer.trade.models import GameTitle

from .i18n import Localizer
from .screens import OverviewScreen, TradeStatisticsScreen
from .state import TuiState, load_state
from .theme import USSR_TITLE_PREFIX, theme_css

_UNSAFE_FILENAME_CHARS_SET = frozenset('/\\<>:"|?*')
_ASCII_CONTROL_CHAR_THRESHOLD = 32


def _sanitize_filename_component(value: str) -> str:
    """ファイル名 suffix に使える安全な文字列へ正規化する / Normalize suffix safely."""
    sanitized = "".join(
        "-" if ch in _UNSAFE_FILENAME_CHARS_SET or ord(ch) < _ASCII_CONTROL_CHAR_THRESHOLD else ch
        for ch in value
    )
    cleaned = sanitized.strip(" .")
    if cleaned:
        return cleaned
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]
    return f"unknown-{digest}"


class TradeApp(App[None]):
    """nano-flavored binding 契約をもつトップレベル App．"""

    CSS = theme_css("default")

    # Textual デフォルトの command palette (``ctrl+p``) を無効化．nano 互換 UI
    # では書記長独自のパレット (例: Statistics 画面の履歴窓 ``^P``) と衝突する．
    ENABLE_COMMAND_PALETTE = False

    # App-level に置く事で画面横断的に効く．screen-level binding はキーが
    # 子 widget に吸われて届かないことがある．
    BINDINGS = [
        Binding("ctrl+x", "quit", "Exit", priority=True),
        Binding("ctrl+g", "show_help", "Help"),
        Binding("ctrl+t", "switch_main_screen", "Switch screen"),
        Binding("ctrl+l", "toggle_locale", "Locale"),
        Binding("ctrl+o", "export", "Export", priority=True),
    ]

    def __init__(
        self,
        state: TuiState,
        *,
        localizer: Localizer | None = None,
        theme: str = "default",
    ) -> None:
        super().__init__()
        self._state = state
        self._localizer = localizer or Localizer.load(state.locale)
        self._theme_name = theme
        # App.CSS は class attr なので runtime 切替時は instance attr で上書きする．
        # (default は ``CSS`` class attr がそのまま使われる)
        if theme != "default":
            self.CSS = theme_css(theme)
        self._apply_localized_bindings()
        self.title = self._localized_title()

    def _localized_title(self) -> str:
        base = self._localizer.t("app.title")
        if self._theme_name == "ussr":
            return USSR_TITLE_PREFIX + base + " " + USSR_TITLE_PREFIX.strip()
        return base

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
        self.title = self._localized_title()
        for screen in (self.get_screen("overview"), self.get_screen("statistics")):
            screen.set_localizer(self._localizer)
            screen.refresh(recompose=True)

    def action_show_help(self) -> None:  # pragma: no cover - manual interaction only
        self.notify(self._localizer.t("binding.help"))

    def action_export(self) -> None:
        """nano 風 ^O: 現在画面の内容を CSV にエクスポート．

        - Overview: items + routes + ledger 3 枚同時書き出し
        - Statistics: 現在画面時と同じく 3 枚同時 (タブ切替しても全量出す方が作業が楽)

        書き出し先は現在 working directory．ファイル名は
        ``<save_basename>_<kind>_<YYYYMMDD_HHMMSS>.csv``．
        """
        paths = self._write_exports()
        label = ", ".join(p.name for p in paths)
        self.notify(f"exported: {label}")

    def _active_filter(self):
        """現在の画面が Statistics なら ``TradeFilter``，それ以外は None．

        循環 import 回避のためローカル import．export は画面横断的に呼ばれるので
        ここで画面種別を見て filter を取りに行く．
        """
        from .screens import TradeStatisticsScreen

        screen = self.screen
        if isinstance(screen, TradeStatisticsScreen):
            return screen._filter
        return None

    def _write_exports(self) -> list[Path]:
        stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        basename = self._state.save_path.stem or "anno_save"
        out_dir = Path.cwd()
        locale = self._localizer.code

        # Statistics 画面が active なら ``_filter`` を汲む．それ以外は全量．
        filt = self._active_filter()
        events = (
            filter_events(self._state.events, session=filt.session, island=filt.island)
            if filt is not None
            else list(self._state.events)
        )
        item_rows = (
            by_item(events) if filt is not None and not filt.is_all else self._state.item_summaries
        )
        route_rows = (
            by_route(events)
            if filt is not None and not filt.is_all
            else self._state.route_summaries
        )
        # idle route (history 無し) は全量/全 session export では全件含める。
        # session-only filter 時は当該 session の idle route を含め、
        # island filter 時のみ CSV から除外する．``filt.is_all`` で session/island
        # 共に None の case は先頭 branch で拾うため else 不要．
        if filt is None or filt.is_all:
            idle_routes = [rd for routes in self._state.routes_by_session.values() for rd in routes]
        elif filt.island:
            idle_routes = []
        else:
            # filt.session is not None here (is_all が False で island も無いので session ある)
            idle_routes = list(self._state.routes_by_session.get(filt.session or "", []))
        active_ids = {s.route_id for s in route_rows if s.route_id is not None}

        suffix_parts: list[str] = []
        if filt is not None and filt.island:
            suffix_parts.append(f"island-{_sanitize_filename_component(filt.island)}")
        elif filt is not None and filt.session:
            suffix_parts.append(f"session-{_sanitize_filename_component(filt.session)}")
        suffix = ("_" + "_".join(suffix_parts)) if suffix_parts else ""

        # Inventory (StorageTrends): session 横断で島単位の時系列．
        # filter によって対象島を絞る．
        inventory_trends: list = []
        if filt is None or filt.is_all:
            for trends in self._state.storage_by_island.values():
                inventory_trends.extend(trends)
        elif filt.island:
            inventory_trends.extend(self._state.storage_by_island.get(filt.island, ()))
        else:
            # session filter: 当該 session に属する島のみ
            island_names = {
                i.city_name for i in self._state.islands_by_session.get(filt.session or "", ())
            }
            for name in island_names:
                inventory_trends.extend(self._state.storage_by_island.get(name, ()))

        targets = [
            (
                f"{basename}_items{suffix}_{stamp}.csv",
                items_to_csv(item_rows, locale=locale),
            ),
            (
                f"{basename}_routes{suffix}_{stamp}.csv",
                routes_to_csv(
                    route_rows,
                    idle_routes=idle_routes,
                    active_ids=active_ids,
                ),
            ),
            (
                f"{basename}_events{suffix}_{stamp}.csv",
                events_to_csv(events, locale=locale),
            ),
            (
                f"{basename}_inventory{suffix}_{stamp}.csv",
                inventory_to_csv(inventory_trends, items=self._state.items, locale=locale),
            ),
        ]
        written: list[Path] = []
        for name, content in targets:
            path = out_dir / name
            path.write_text(content, encoding="utf-8")
            written.append(path)
        return written

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
            Binding("ctrl+o", "export", self._localizer.t("binding.export"), priority=True),
        ]
        self.refresh_bindings()
