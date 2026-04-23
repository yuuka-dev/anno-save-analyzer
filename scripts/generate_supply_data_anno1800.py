"""Anno1800Calculator から tier 別消費レート YAML を再生成する．

Node.js で ``extract_calculator_data.mjs`` を呼び，``populationLevels`` を
JSON で受け取って ``data/consumption_anno1800.{en,ja}.yaml`` を上書きする．

Calculator は MIT ライセンス．DLC 追加 / バランス patch 時に本スクリプトで
一発再生成できる．CI でも呼び出されて ``git diff --exit-code`` で YAML 陳腐化
を検知する．

Usage::

    python scripts/generate_supply_data_anno1800.py \\
        --calculator-dir ~/repo/Anno1800Calculator \\
        --data-dir src/anno_save_analyzer/data
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

_LOCALE_EN = "english"
_LOCALE_JA = "japanese"
_ZERO_WIDTH = "​"


def _run_node(calc_dir: Path) -> dict[str, Any]:
    """Node.js script を起動して Calculator 由来 JSON を返す．"""
    script = Path(__file__).with_name("extract_calculator_data.mjs")
    if not script.exists():
        raise FileNotFoundError(f"extractor not found: {script}")
    result = subprocess.run(
        ["node", str(script), str(calc_dir)],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def _build_en_payload(data: dict[str, Any]) -> dict[str, Any]:
    """英語版 YAML ペイロード — 全メタ + 英語名を保持する canonical YAML．"""
    tiers: list[dict[str, Any]] = []
    for tier in data.get("tiers", []):
        name = tier.get("loca_text", {}).get(_LOCALE_EN) or tier.get("name") or ""
        tiers.append(
            {
                "guid": tier["guid"],
                "name": name,
                "full_house": tier.get("full_house"),
                "dlcs": list(tier.get("dlcs") or []),
                "needs": [
                    {
                        "product_guid": n["product_guid"],
                        "tpmin": n.get("tpmin"),
                        "residents": n.get("residents", 0),
                        "happiness": n.get("happiness", 0),
                        "is_bonus_need": bool(n.get("is_bonus_need")),
                        "dlcs": list(n.get("dlcs") or []),
                    }
                    for n in tier.get("needs") or []
                ],
            }
        )
    return {
        "source": {"calculator_version": data.get("source", {}).get("calculator_version")},
        "tiers": tiers,
    }


def _build_ja_payload(data: dict[str, Any]) -> dict[str, Any]:
    """日本語版 YAML ペイロード — guid + 日本語名のみ (items_*.ja.yaml と同形式)．"""
    tiers: list[dict[str, Any]] = []
    for tier in data.get("tiers", []):
        ja = tier.get("loca_text", {}).get(_LOCALE_JA)
        if not ja:
            continue
        tiers.append({"guid": tier["guid"], "name": ja.replace(_ZERO_WIDTH, "")})
    return {"tiers": tiers}


def _dump_yaml(payload: dict[str, Any], out_path: Path) -> None:
    """敵対的な YAML 差分を避けるため ``sort_keys=False`` + ``allow_unicode``．"""
    out_path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=120),
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--calculator-dir",
        type=Path,
        required=True,
        help="Anno1800Calculator repo のローカルパス",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        required=True,
        help="YAML 出力先 (通常 src/anno_save_analyzer/data)",
    )
    args = parser.parse_args(argv)

    if not args.calculator_dir.is_dir():
        print(f"ERROR: calculator dir not found: {args.calculator_dir}", file=sys.stderr)
        return 2
    args.data_dir.mkdir(parents=True, exist_ok=True)

    data = _run_node(args.calculator_dir)
    en_path = args.data_dir / "consumption_anno1800.en.yaml"
    ja_path = args.data_dir / "consumption_anno1800.ja.yaml"
    _dump_yaml(_build_en_payload(data), en_path)
    _dump_yaml(_build_ja_payload(data), ja_path)
    print(f"wrote {en_path}", file=sys.stderr)
    print(f"wrote {ja_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
