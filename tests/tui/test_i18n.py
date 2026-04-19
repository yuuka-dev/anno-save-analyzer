"""tui.i18n のテスト．"""

from __future__ import annotations

from pathlib import Path

import pytest

from anno_save_analyzer.tui.i18n import Localizer


class TestLocalizer:
    def test_load_packaged_en(self) -> None:
        loc = Localizer.load("en")
        assert loc.code == "en"
        assert loc.t("overview.heading") == "Overview"

    def test_load_packaged_ja(self) -> None:
        loc = Localizer.load("ja")
        assert loc.t("overview.heading") == "概要"

    def test_unknown_key_returns_self(self) -> None:
        loc = Localizer.load("en")
        assert loc.t("definitely.does.not.exist") == "definitely.does.not.exist"

    def test_format_kwargs_substituted(self) -> None:
        loc = Localizer.load("en")
        assert loc.t("statistics.tree_session", index="0") == "Session #0"

    def test_with_locale_returns_new_instance(self) -> None:
        loc = Localizer.load("en")
        ja = loc.with_locale("ja")
        assert loc is not ja
        assert ja.code == "ja"

    def test_data_dir_override(self, tmp_path: Path) -> None:
        (tmp_path / "fr.yaml").write_text(
            "overview.heading: 'Aperçu'\n",
            encoding="utf-8",
        )
        loc = Localizer.load("fr", data_dir=tmp_path)
        assert loc.t("overview.heading") == "Aperçu"

    def test_missing_locale_yaml_returns_empty_strings(self, tmp_path: Path) -> None:
        loc = Localizer.load("xx", data_dir=tmp_path)
        # キーがそのまま返る
        assert loc.t("overview.heading") == "overview.heading"

    def test_packaged_unknown_locale_falls_back_to_keys(self) -> None:
        # 同梱パッケージに無い locale を要求すると空辞書 → key 名が返る
        loc = Localizer.load("zz")
        assert loc.t("overview.heading") == "overview.heading"

    def test_empty_yaml_returns_empty_dict(self, tmp_path: Path) -> None:
        (tmp_path / "empty.yaml").write_text("", encoding="utf-8")
        loc = Localizer.load("empty", data_dir=tmp_path)
        assert loc.t("anything") == "anything"

    def test_non_mapping_yaml_raises_value_error(self, tmp_path: Path) -> None:
        (tmp_path / "bad.yaml").write_text("- not\n- a\n- mapping\n", encoding="utf-8")
        with pytest.raises(ValueError, match="Locale YAML root must be a mapping"):
            Localizer.load("bad", data_dir=tmp_path)
