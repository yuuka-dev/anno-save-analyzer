"""PySide6 ``QMainWindow`` — 島 multi-select + balance テーブル．

TUI と同じモデル (``TuiState`` / ``SupplyBalanceTable``) を共有し，view だけ
Qt で再実装する．2 pane splitter:

- 左 (QListWidget, ``CheckState``): 島一覧 (プレイヤー → NPC 順)
- 右 (QTableWidget): 選択島の aggregate balance．赤字行は赤色

シグナル：左の checkState 変更 → ``_refresh_table`` で右を更新．
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from anno_save_analyzer.tui.state import TuiState

from .viewmodels import (
    IslandListItem,
    make_balance_rows,
    make_island_items,
)

_DELTA_RED = QColor("#d34248")
_DELTA_GREEN = QColor("#7fb650")


class BalanceMainWindow(QMainWindow):
    """supply balance を表示するメインウィンドウ．"""

    def __init__(self, state: TuiState) -> None:
        super().__init__()
        self._state = state
        self.setWindowTitle(self._window_title())
        self.resize(1100, 600)

        central = QWidget(self)
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(8, 8, 8, 8)

        self._summary_label = QLabel()
        root_layout.addWidget(self._summary_label)

        splitter = QSplitter(Qt.Orientation.Horizontal, central)
        root_layout.addWidget(splitter, 1)

        # 左: 島 list
        left = QWidget(splitter)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel(self._loc("balance.islands.title")))
        self._island_list = QListWidget(left)
        self._island_list.itemChanged.connect(self._on_item_changed)
        left_layout.addWidget(self._island_list, 1)

        # deficit only toggle
        self._deficit_toggle = QCheckBox(self._loc("balance.deficit_only"))
        self._deficit_toggle.stateChanged.connect(self._refresh_table)
        left_layout.addWidget(self._deficit_toggle)

        # select all / none buttons
        btn_row = QHBoxLayout()
        from PySide6.QtWidgets import QPushButton

        self._select_all_btn = QPushButton(self._loc("balance.select_all"))
        self._select_all_btn.clicked.connect(self._select_all)
        self._select_none_btn = QPushButton(self._loc("balance.select_none"))
        self._select_none_btn.clicked.connect(self._select_none)
        btn_row.addWidget(self._select_all_btn)
        btn_row.addWidget(self._select_none_btn)
        left_layout.addLayout(btn_row)

        splitter.addWidget(left)

        # 右: balance table
        right = QWidget(splitter)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(QLabel(self._loc("balance.table.title")))
        self._table = QTableWidget(right)
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(
            [
                self._loc("balance.col.product"),
                self._loc("balance.col.produced"),
                self._loc("balance.col.consumed"),
                self._loc("balance.col.delta"),
            ]
        )
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        right_layout.addWidget(self._table, 1)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        self._items = self._populate_islands()
        self._refresh_table()

    # ---------- Localization ----------

    def _loc(self, key: str) -> str:
        from anno_save_analyzer.tui.i18n import Localizer

        # state にロケールが入っているので，毎回軽く load (キャッシュは Localizer 側責務)．
        loc = Localizer.load(self._state.locale)
        return loc.t(key)

    def _window_title(self) -> str:
        base = self._loc("app.title")
        return f"{base} — {self._state.save_path.name}"

    # ---------- Setup ----------

    def _populate_islands(self) -> list[IslandListItem]:
        """左ペインに島 list を入れる．初期 check はプレイヤー島のみ．

        state.py の ``area_manager_to_city`` / ``area_manager_to_session_key``
        は本 PR 時点の dev にない可能性 (#78 merge 待ち) のため getattr で
        安全に参照する．
        """
        table = self._state.balance_table
        if table is None:
            return []
        am_to_city: dict[str, str] = getattr(self._state, "area_manager_to_city", {}) or {}
        am_to_session_key: dict[str, str] = (
            getattr(self._state, "area_manager_to_session_key", {}) or {}
        )

        # session key → 表示名 の resolver
        session_display: dict[str, str] = {
            am: self._loc(key) for am, key in am_to_session_key.items() if key
        }

        items = make_island_items(
            table,
            area_manager_to_city=am_to_city,
            area_manager_to_session=session_display,
        )
        any_player = any(it.is_player for it in items)
        for it in items:
            wi = QListWidgetItem(it.display_label)
            wi.setFlags(wi.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            default_checked = it.is_player if any_player else True
            wi.setCheckState(Qt.CheckState.Checked if default_checked else Qt.CheckState.Unchecked)
            wi.setData(Qt.ItemDataRole.UserRole, it.area_manager)
            self._island_list.addItem(wi)
        return items

    # ---------- Interaction ----------

    def _on_item_changed(self, _item: QListWidgetItem) -> None:
        self._refresh_table()

    def _select_all(self) -> None:
        self._island_list.blockSignals(True)
        for i in range(self._island_list.count()):
            self._island_list.item(i).setCheckState(Qt.CheckState.Checked)
        self._island_list.blockSignals(False)
        self._refresh_table()

    def _select_none(self) -> None:
        self._island_list.blockSignals(True)
        for i in range(self._island_list.count()):
            self._island_list.item(i).setCheckState(Qt.CheckState.Unchecked)
        self._island_list.blockSignals(False)
        self._refresh_table()

    def _selected_area_managers(self) -> set[str]:
        out: set[str] = set()
        for i in range(self._island_list.count()):
            w = self._island_list.item(i)
            if w.checkState() == Qt.CheckState.Checked:
                am = w.data(Qt.ItemDataRole.UserRole)
                if isinstance(am, str):
                    out.add(am)
        return out

    def _refresh_table(self) -> None:
        table = self._state.balance_table
        self._table.setRowCount(0)
        if table is None:
            return
        selected = self._selected_area_managers()
        combined = table.aggregate(selected) if selected else table.aggregate(())
        products = combined.deficits() if self._deficit_toggle.isChecked() else combined.products
        rows = make_balance_rows(products, self._state.items, locale=self._state.locale)
        self._table.setRowCount(len(rows))
        for row_idx, row in enumerate(rows):
            name_item = QTableWidgetItem(row.product_name)
            produced_item = QTableWidgetItem(row.produced_text)
            consumed_item = QTableWidgetItem(row.consumed_text)
            delta_item = QTableWidgetItem(row.delta_text)
            produced_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            consumed_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            delta_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if row.is_deficit:
                delta_item.setForeground(QBrush(_DELTA_RED))
            elif row.delta_value > 0:
                delta_item.setForeground(QBrush(_DELTA_GREEN))
            self._table.setItem(row_idx, 0, name_item)
            self._table.setItem(row_idx, 1, produced_item)
            self._table.setItem(row_idx, 2, consumed_item)
            self._table.setItem(row_idx, 3, delta_item)

        self._summary_label.setText(
            self._build_summary(selected, combined.resident_total, len(rows))
        )

    def _build_summary(self, selected: set[str], population: int, product_count: int) -> str:
        if not selected:
            return self._loc("balance.summary.none")
        tpl = self._loc("balance.summary")
        return tpl.format(
            islands=len(selected),
            population=f"{population:,}",
            products=product_count,
        )
