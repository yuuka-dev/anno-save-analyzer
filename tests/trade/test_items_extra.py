"""trade.items の追加テスト：__iter__ と locale != en で category が無視されること．"""

from __future__ import annotations

from pathlib import Path

from anno_save_analyzer.trade import ItemDictionary


def test_iter_yields_loaded_items(tmp_path: Path) -> None:
    title = "iterme"
    (tmp_path / f"items_{title}.en.yaml").write_text(
        "1:\n  name: A\n  category: x\n2:\n  name: B\n",
        encoding="utf-8",
    )
    d = ItemDictionary.load(title, data_dir=tmp_path)
    iterated = list(iter(d))
    guids = sorted(item.guid for item in iterated)
    assert guids == [1, 2]


def test_yaml_entry_without_name_is_skipped_silently(tmp_path: Path) -> None:
    """``name`` フィールドの無いエントリは無視される（``if "name" in entry`` の False 枝）．"""
    title = "noname"
    (tmp_path / f"items_{title}.en.yaml").write_text(
        "1:\n  category: orphan\n2:\n  name: Has Name\n",
        encoding="utf-8",
    )
    d = ItemDictionary.load(title, data_dir=tmp_path)
    # GUID 1 は name が無いので names は空 → fallback
    assert d[1].display_name("en") == "Good_1"
    # category だけ拾われる
    assert d[1].category == "orphan"
    assert d[2].display_name("en") == "Has Name"


def test_non_en_locale_does_not_set_category(tmp_path: Path) -> None:
    """``locale == "en"`` ガードによって ja のエントリが category を上書きしない．"""
    title = "catonly"
    (tmp_path / f"items_{title}.en.yaml").write_text(
        "1:\n  name: A\n  category: en-cat\n",
        encoding="utf-8",
    )
    # ja の YAML には category を入れてみるが，loader は en 以外の category を捨てる．
    (tmp_path / f"items_{title}.ja.yaml").write_text(
        "1:\n  name: ja-name\n  category: SHOULD-NOT-BE-USED\n",
        encoding="utf-8",
    )
    d = ItemDictionary.load(title, locales=["en", "ja"], data_dir=tmp_path)
    assert d[1].category == "en-cat"
    assert d[1].display_name("ja") == "ja-name"
