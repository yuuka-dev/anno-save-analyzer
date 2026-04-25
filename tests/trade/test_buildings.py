"""``trade.buildings`` のテスト．packaged YAML + 合成 YAML の両方．"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from anno_save_analyzer.trade.buildings import BuildingDictionary, known_kinds


def _load_generator_module():
    """scripts/generate_buildings_anno1800.py を package 外から import する．

    `scripts/` は Python package ではないので importlib で直接 spec から読む．
    依存している `generate_items_anno1800` も同じディレクトリで隣接 import
    されるので，先に sys.path に scripts/ を入れる．
    """
    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    sys.path.insert(0, str(scripts_dir))
    try:
        spec = importlib.util.spec_from_file_location(
            "generate_buildings_anno1800",
            scripts_dir / "generate_buildings_anno1800.py",
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(scripts_dir))


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


def test_invalid_yaml_root_in_en_raises_value_error(tmp_path: Path) -> None:
    """en YAML ルートが mapping でなければ ValueError."""
    (tmp_path / "buildings_anno1800.en.yaml").write_text(
        """
- not
- a
- mapping
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="buildings_anno1800.en.yaml"):
        BuildingDictionary.load(data_dir=tmp_path, locales=("en",))


def test_invalid_yaml_root_in_locale_raises_value_error(tmp_path: Path) -> None:
    """locale YAML ルートが mapping でなければ ValueError."""
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
- invalid
- root
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="buildings_anno1800.ja.yaml"):
        BuildingDictionary.load(data_dir=tmp_path, locales=("ja", "en"))


# ---------- generator `_tier_for` パターン別テスト (#103) ----------


@pytest.mark.parametrize(
    ("internal_name", "expected_tier"),
    [
        # 旧世界 (base game) — 既存挙動の保証
        ("residence_tier01", "farmer"),
        ("residence_tier02", "worker"),
        ("residence_tier03", "artisan"),
        ("residence_tier04", "engineer"),
        ("residence_tier05", "investor"),
        # 新世界 (Caribbean) colony01
        ("residence_colony01_tier01", "jornaleros"),
        ("residence_colony01_tier02", "obreros"),
        ("residence_colony01_tier03", "artista"),
        # Hacienda residence module (Tourist Season DLC)．大文字混在もケースして
        # `.lower()` で吸収できることを確認．
        ("Hacienda residence module tier01", "jornaleros"),
        ("Hacienda residence module tier02", "obreros"),
        ("Hacienda residence module tier03", "artista"),
        # 北極圏 (The Passage DLC)
        ("residence_arctic_tier01", "explorer"),
        ("residence_arctic_tier02", "technician"),
        # エンベサ (Land of Lions DLC) colony02．scholar (tier3) は
        # SOC DLC の asset で確認できないが mapping は予約．
        ("residence_colony02_tier01", "shepherd"),
        ("residence_colony02_tier02", "elder"),
        ("residence_colony02_tier03", "scholar"),
        # 名前ベース — Hotel と Skyline Tower
        ("Hotel", "tourist"),
        ("HighLife_monument_03(residence)", "investor"),
    ],
)
def test_generator_tier_for_resolves_dlc_residences(internal_name: str, expected_tier: str) -> None:
    """``_tier_for`` が 6 系列すべての residence pattern で tier を返す (#103)．"""
    module = _load_generator_module()
    assert module._tier_for(internal_name) == expected_tier


@pytest.mark.parametrize(
    "internal_name",
    [
        "factory_lumberjack_01",  # residence でない
        "residence_tier99",  # 旧世界 mapping 範囲外
        "",  # 空文字
        "warehouse_01",  # 名前 needle に当たらない
    ],
)
def test_generator_tier_for_returns_none_when_no_match(internal_name: str) -> None:
    """どの pattern にも一致しなければ ``None`` を返す．"""
    module = _load_generator_module()
    assert module._tier_for(internal_name) is None
