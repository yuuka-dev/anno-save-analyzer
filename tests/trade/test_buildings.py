"""``trade.buildings`` のテスト．packaged YAML + 合成 YAML の両方．"""

from __future__ import annotations

from pathlib import Path

import pytest

from anno_save_analyzer.trade.buildings import BuildingDictionary, known_kinds

# ---------- 実データ smoke ----------


def test_load_packaged_yaml_has_expected_counts() -> None:
    """packaged buildings YAML が 200+ 件読める．実 Anno 1800 install から生成された
    canonical YAML で最低限 factory / residence / farm が存在する．"""
    d = BuildingDictionary.load()
    assert len(d) >= 200
    assert len(d.by_kind("factory")) >= 50
    assert len(d.by_kind("residence")) >= 5
    assert len(d.by_kind("farm")) >= 10


def test_known_kinds_cover_loaded_entries() -> None:
    """packaged YAML の kind はすべて ``known_kinds`` に含まれる．"""
    d = BuildingDictionary.load()
    loaded_kinds = {e.kind for e in d.entries.values()}
    assert loaded_kinds <= known_kinds()


def test_residence_tier_resolution_partial() -> None:
    """Residence の tier は internal_name ``residence_tier0N`` から解決される．
    命名規則外の Colony / Arctic 系は tier=None の可能性がある．"""
    d = BuildingDictionary.load()
    farmers = d.by_tier("farmer")
    # 少なくとも 1 件は tier 判定に成功している
    assert len(farmers) >= 1


def test_ja_locale_override_for_known_building() -> None:
    """``ja`` ロケールで日本語名が引ける (packaged YAML の一部で確認)．"""
    en = BuildingDictionary.load(locales=("en",))
    ja = BuildingDictionary.load(locales=("ja", "en"))
    # 同 GUID で name が違う = override 効いてる (少なくとも 1 件あればOK)
    diff_count = sum(
        1 for g, e in en.entries.items() if g in ja.entries and ja.entries[g].name != e.name
    )
    assert diff_count >= 1


# ---------- 合成 YAML ----------


def test_load_from_custom_data_dir(tmp_path: Path) -> None:
    """``data_dir`` 指定で任意 YAML を読める．"""
    (tmp_path / "buildings_anno1800.en.yaml").write_text(
        """
100:
  name: "Test Residence"
  kind: residence
  template: "ResidenceBuilding"
  tier: farmer
200:
  name: "Test Factory"
  kind: factory
  template: "FactoryBuilding7"
""",
        encoding="utf-8",
    )
    d = BuildingDictionary.load(data_dir=tmp_path, locales=("en",))
    assert len(d) == 2
    assert d[100].name == "Test Residence"
    assert d[100].tier == "farmer"
    assert d[200].kind == "factory"
    assert d[200].tier is None
    assert d.get(999) is None
    assert 100 in d
    assert 999 not in d


def test_ja_override_from_custom_data_dir(tmp_path: Path) -> None:
    """``ja`` override が en メタに重なる．"""
    (tmp_path / "buildings_anno1800.en.yaml").write_text(
        """
100:
  name: "Farm"
  kind: farm
  template: "FarmBuilding"
""",
        encoding="utf-8",
    )
    (tmp_path / "buildings_anno1800.ja.yaml").write_text(
        """
100:
  name: "農場"
""",
        encoding="utf-8",
    )
    d = BuildingDictionary.load(data_dir=tmp_path, locales=("ja", "en"))
    assert d[100].name == "農場"
    assert d[100].kind == "farm"  # en からメタは維持


def test_missing_locale_file_is_ignored(tmp_path: Path) -> None:
    """指定 locale の YAML が無くても en だけで load できる．"""
    (tmp_path / "buildings_anno1800.en.yaml").write_text(
        """
100:
  name: "Farm"
  kind: farm
  template: "FarmBuilding"
""",
        encoding="utf-8",
    )
    # ja YAML 無し → fallback で en name
    d = BuildingDictionary.load(data_dir=tmp_path, locales=("ja", "en"))
    assert d[100].name == "Farm"


def test_malformed_entries_skipped(tmp_path: Path) -> None:
    """dict でないエントリは skip．"""
    (tmp_path / "buildings_anno1800.en.yaml").write_text(
        """
100:
  name: "Farm"
  kind: farm
  template: "FarmBuilding"
200: "not a dict"
""",
        encoding="utf-8",
    )
    d = BuildingDictionary.load(data_dir=tmp_path, locales=("en",))
    assert 100 in d
    assert 200 not in d


def test_entries_are_frozen(tmp_path: Path) -> None:
    """BuildingEntry は frozen．"""
    (tmp_path / "buildings_anno1800.en.yaml").write_text(
        """
100:
  name: "Farm"
  kind: farm
  template: "FarmBuilding"
""",
        encoding="utf-8",
    )
    d = BuildingDictionary.load(data_dir=tmp_path, locales=("en",))
    with pytest.raises(Exception):  # noqa: B017
        d[100].name = "X"  # type: ignore[misc]
