"""``trade.factory_recipes`` のテスト．"""

from __future__ import annotations

from pathlib import Path

import pytest

from anno_save_analyzer.trade.factory_recipes import (
    FactoryRecipe,
    FactoryRecipeTable,
    RecipeInput,
    RecipeOutput,
)

# ---------- packaged (実データ) ----------


def test_load_packaged_yaml_known_factory() -> None:
    """packaged YAML が読め，Fishery (1010278) が取れる．"""
    table = FactoryRecipeTable.load()
    fishery = table.get(1010278)
    assert fishery is not None
    assert fishery.name == "Fishery"
    assert fishery.tpmin == 2
    # Fish (1010200) を output
    assert any(o.product_guid == 1010200 for o in fishery.outputs)


def test_packaged_ja_override() -> None:
    """ja ロケールで日本語名が引ける．"""
    table = FactoryRecipeTable.load(locales=("ja", "en"))
    fishery = table.get(1010278)
    assert fishery is not None
    # 漁場 (or 類似) が入ってる
    assert fishery.name != "Fishery"
    assert any(ch in fishery.name for ch in "漁場養")


def test_packaged_unknown_guid_returns_none() -> None:
    table = FactoryRecipeTable.load()
    assert table.get(-1) is None
    assert -1 not in table


# ---------- produced_per_minute 計算 ----------


def test_produced_per_minute_basic() -> None:
    """tpmin=2, output amount=1, productivity=1.0 → 2 /min．"""
    r = FactoryRecipe(
        guid=1,
        name="F",
        tpmin=2.0,
        outputs=(RecipeOutput(product_guid=100, amount=1.0),),
    )
    assert r.produced_per_minute(1.0) == {100: pytest.approx(2.0)}
    assert r.produced_per_minute(0.5) == {100: pytest.approx(1.0)}
    assert r.produced_per_minute(2.0) == {100: pytest.approx(4.0)}


def test_produced_per_minute_multi_output() -> None:
    r = FactoryRecipe(
        guid=1,
        name="F",
        tpmin=1.0,
        outputs=(
            RecipeOutput(product_guid=100, amount=1.0),
            RecipeOutput(product_guid=200, amount=2.0),
        ),
    )
    out = r.produced_per_minute(1.0)
    assert out[100] == pytest.approx(1.0)
    assert out[200] == pytest.approx(2.0)


def test_produced_per_minute_missing_tpmin() -> None:
    """tpmin 未定義なら空 dict (=生産量未計算)．"""
    r = FactoryRecipe(guid=1, name="F", tpmin=None)
    assert r.produced_per_minute(1.0) == {}


def test_produced_per_minute_default_output_amount() -> None:
    """output.amount が None の稀ケースは 1.0 とみなす．"""
    r = FactoryRecipe(
        guid=1,
        name="F",
        tpmin=2.0,
        outputs=(RecipeOutput(product_guid=100, amount=None),),
    )
    assert r.produced_per_minute(1.0) == {100: pytest.approx(2.0)}


# ---------- 合成 YAML ----------


def test_load_from_custom_data_dir(tmp_path: Path) -> None:
    (tmp_path / "factory_recipes_anno1800.en.yaml").write_text(
        """
factories:
  - guid: 100
    name: "Test Factory"
    tpmin: 2.5
    region: 5000000
    dlcs: []
    outputs:
      - product_guid: 500
        amount: 1.0
        storage_amount: 4
    inputs:
      - product_guid: 400
        amount: 1.0
""",
        encoding="utf-8",
    )
    table = FactoryRecipeTable.load(data_dir=tmp_path, locales=("en",))
    assert len(table) == 1
    recipe = table.get(100)
    assert recipe is not None
    assert recipe.tpmin == 2.5
    assert recipe.outputs == (RecipeOutput(product_guid=500, amount=1.0, storage_amount=4),)
    assert recipe.inputs == (RecipeInput(product_guid=400, amount=1.0),)


def test_load_invalid_yaml_root_raises(tmp_path: Path) -> None:
    (tmp_path / "factory_recipes_anno1800.en.yaml").write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(ValueError, match="YAML root"):
        FactoryRecipeTable.load(data_dir=tmp_path, locales=("en",))


def test_frozen_models() -> None:
    r = FactoryRecipe(guid=1, name="F")
    with pytest.raises(Exception):  # noqa: B017
        r.name = "G"  # type: ignore[misc]
