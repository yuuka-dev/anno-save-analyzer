"""``trade.consumption`` のテスト．

- packaged YAML (実データ) を load して既知 tier / need の値をアサート
- 合成 YAML で round-trip / fallback 挙動を確認
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from anno_save_analyzer.trade.consumption import ConsumptionTable, PopulationTier, TierNeed

# ---------- 実データ smoke ----------


def test_load_packaged_yaml_yields_known_tiers() -> None:
    """packaged YAML が load できて Farmers (15000000) が含まれる．"""
    table = ConsumptionTable.load()
    farmer = table.get_tier(15000000)
    assert farmer is not None
    assert farmer.name == "Farmers"
    assert farmer.full_house == 10


def test_packaged_farmer_fish_rate_matches_calculator() -> None:
    """Farmer (15000000) の Fish (1010200) 消費レートが Calculator と一致．"""
    table = ConsumptionTable.load()
    # Calculator params.js の Farmers needs[1] = {guid: 1010200, tpmin: 0.0025000002}
    rate = table.get_rate(15000000, 1010200)
    assert rate is not None
    assert rate == pytest.approx(0.0025000002)


def test_packaged_japanese_names_present() -> None:
    """``ja`` ロケールで日本語名が引ける．"""
    table = ConsumptionTable.load()
    assert table.display_name(15000000, "ja") == "農家"
    # 英語 fallback
    assert table.display_name(15000000, "en") == "Farmers"
    assert table.display_name(15000000, "xx") == "Farmers"


def test_packaged_unknown_tier_returns_none() -> None:
    """未登録 tier / product は None を返す．"""
    table = ConsumptionTable.load()
    assert table.get_tier(-1) is None
    assert table.get_rate(-1, 1010200) is None
    assert table.get_rate(15000000, -1) is None
    assert table.display_name(-1, "ja") is None


# ---------- 合成 YAML ----------


def _write_yaml(path: Path, payload: dict) -> None:
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


def test_load_from_custom_data_dir(tmp_path: Path) -> None:
    """``data_dir`` 指定で任意 YAML を読める．"""
    _write_yaml(
        tmp_path / "consumption_anno1800.en.yaml",
        {
            "tiers": [
                {
                    "guid": 100,
                    "name": "Toy",
                    "full_house": 4,
                    "dlcs": [],
                    "needs": [
                        {
                            "product_guid": 999,
                            "tpmin": 0.5,
                            "residents": 1,
                            "happiness": 0,
                            "is_bonus_need": False,
                            "dlcs": [],
                        }
                    ],
                }
            ]
        },
    )
    _write_yaml(
        tmp_path / "consumption_anno1800.ja.yaml",
        {"tiers": [{"guid": 100, "name": "おもちゃ"}]},
    )

    table = ConsumptionTable.load(data_dir=tmp_path)
    assert len(table.tiers) == 1
    assert table.get_rate(100, 999) == pytest.approx(0.5)
    assert table.display_name(100, "ja") == "おもちゃ"


def test_load_without_ja_file_still_works(tmp_path: Path) -> None:
    """``ja`` YAML が無くても en だけで load できる．"""
    _write_yaml(
        tmp_path / "consumption_anno1800.en.yaml",
        {"tiers": [{"guid": 100, "name": "Toy", "full_house": 4, "dlcs": [], "needs": []}]},
    )

    table = ConsumptionTable.load(data_dir=tmp_path)
    assert table.display_name(100, "ja") == "Toy"  # en fallback


def test_pydantic_models_are_frozen() -> None:
    """モデルは frozen で副作用安全．"""
    need = TierNeed(product_guid=1, tpmin=0.1)
    with pytest.raises(Exception):  # noqa: B017 — pydantic ValidationError / FrozenInstanceError
        need.tpmin = 0.2  # type: ignore[misc]
    tier = PopulationTier(guid=1, name="x")
    with pytest.raises(Exception):  # noqa: B017
        tier.name = "y"  # type: ignore[misc]
