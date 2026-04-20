"""trade.items のテスト．"""

from __future__ import annotations

from pathlib import Path

import pytest

from anno_save_analyzer.trade import GameTitle, ItemDictionary


class TestItemDictionaryShipped:
    """同梱 items_anno117.*.yaml は config.rda/assets.xml から auto-generate されてる．

    GUID はゲーム本体の Standard/GUID に一致し，同じ GUID は game version 更新でも
    基本固定．テストでは Wood (2077) と Sardines (2088) で happy path を確認．
    """

    def test_loads_packaged_anno117_yaml(self) -> None:
        d = ItemDictionary.load(GameTitle.ANNO_117)
        assert len(d) >= 150  # 151 Products from config.rda
        wood = d[2077]
        assert wood.display_name("en") == "Wood"
        sardines = d[2088]
        assert sardines.display_name("en") == "Sardines"

    def test_merges_japanese_locale(self) -> None:
        d = ItemDictionary.load(GameTitle.ANNO_117, locales=["en", "ja"])
        assert d[2077].display_name("ja") == "木材"
        assert d[2088].display_name("ja") == "イワシ"

    def test_unknown_guid_creates_fallback_entry(self) -> None:
        d = ItemDictionary.load(GameTitle.ANNO_117)
        item = d[999_999]
        assert item.display_name("en") == "Good_999999"
        assert 999_999 in d

    def test_membership_and_len(self) -> None:
        d = ItemDictionary.load(GameTitle.ANNO_117)
        assert 2077 in d
        prev_len = len(d)
        # __getitem__ で auto-add（fallback）するので len が増える
        _ = d[42_424_242]
        assert len(d) == prev_len + 1
        # iter は entries を返す
        assert any(item.guid == 2077 for item in d._items.values())

    def test_string_title_accepted(self) -> None:
        d = ItemDictionary.load("anno117")
        assert 2077 in d


class TestItemDictionaryDataDirOverride:
    def test_load_from_custom_data_dir(self, tmp_path: Path) -> None:
        title = "miniame"
        en = tmp_path / f"items_{title}.en.yaml"
        ja = tmp_path / f"items_{title}.ja.yaml"
        en.write_text(
            "1:\n  name: Apple\n  category: fruit\n2:\n  name: Bread\n",
            encoding="utf-8",
        )
        ja.write_text("1:\n  name: りんご\n", encoding="utf-8")
        d = ItemDictionary.load(title, locales=["en", "ja"], data_dir=tmp_path)
        assert d[1].display_name("ja") == "りんご"
        assert d[1].category == "fruit"
        assert d[2].display_name("en") == "Bread"
        assert d[2].display_name("ja") == "Bread"  # ja 未提供 → en fallback

    def test_missing_locale_yaml_silently_skipped(self, tmp_path: Path) -> None:
        title = "nomeon"
        (tmp_path / f"items_{title}.en.yaml").write_text(
            "1:\n  name: Only English\n",
            encoding="utf-8",
        )
        d = ItemDictionary.load(title, locales=["en", "ja"], data_dir=tmp_path)
        assert d[1].display_name("ja") == "Only English"

    def test_completely_missing_data_dir_returns_empty(self, tmp_path: Path) -> None:
        d = ItemDictionary.load("nonexistent_title", data_dir=tmp_path)
        assert len(d) == 0
        # 未知 GUID も fallback で取れる
        assert d[1].display_name("en") == "Good_1"

    def test_empty_yaml_treated_as_empty_dict(self, tmp_path: Path) -> None:
        title = "emptiness"
        (tmp_path / f"items_{title}.en.yaml").write_text("", encoding="utf-8")
        d = ItemDictionary.load(title, data_dir=tmp_path)
        assert len(d) == 0


class TestPackagedDataNotFound:
    def test_packaged_load_handles_missing_file(self) -> None:
        # 同梱 data に items_doesnotexist.en.yaml は無い
        d = ItemDictionary.load("doesnotexist")
        assert len(d) == 0


@pytest.mark.parametrize(
    "input_locales, expected_first",
    [
        (["ja"], "en"),  # ja だけ指定でも en が先頭に挿入
        (["en"], "en"),
        (["fr", "en", "ja"], "en"),  # en は先頭に re-arranged
    ],
)
def test_locale_list_always_prepends_en(input_locales, expected_first, tmp_path) -> None:
    """en を先頭で読まないと canonical metadata が上書きされる懸念があるためテストで担保．"""
    title = "primer"
    (tmp_path / f"items_{title}.en.yaml").write_text(
        "1:\n  name: A\n  category: alpha\n",
        encoding="utf-8",
    )
    d = ItemDictionary.load(title, locales=input_locales, data_dir=tmp_path)
    assert d[1].category == "alpha"
    assert d[1].display_name("en") == "A"
