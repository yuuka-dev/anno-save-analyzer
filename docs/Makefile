# Sphinx Makefile．
# ``make html``      英語版 build  → _build/html/
# ``make html-ja``   日本語版 build → _build/ja/html/
# ``make site``      両方 build して _build/site/ に GitHub Pages 同等構造で集約
# ``make serve``     site を local で http.server (127.0.0.1:8080)
# ``make gettext``   翻訳用 .pot を _build/gettext に抽出
# ``make intl-update``  .pot から locales/ja/LC_MESSAGES/*.po を更新

SPHINXOPTS    ?= --keep-going -n
SPHINXBUILD   ?= sphinx-build
SOURCEDIR     = source
BUILDDIR      = _build
LANGUAGE_JA   = ja
SERVE_PORT    ?= 8080

.PHONY: help html clean html-ja site serve gettext intl-update

help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS)

html:
	@$(SPHINXBUILD) -M html "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS)

clean:
	@$(SPHINXBUILD) -M clean "$(SOURCEDIR)" "$(BUILDDIR)"
	@rm -rf "$(BUILDDIR)/site"

html-ja:
	@$(SPHINXBUILD) -M html "$(SOURCEDIR)" "$(BUILDDIR)/ja" -D language=$(LANGUAGE_JA) $(SPHINXOPTS)

site: html html-ja
	@rm -rf "$(BUILDDIR)/site"
	@mkdir -p "$(BUILDDIR)/site"
	@cp -r "$(BUILDDIR)/html/." "$(BUILDDIR)/site/"
	@mkdir -p "$(BUILDDIR)/site/ja"
	@cp -r "$(BUILDDIR)/ja/html/." "$(BUILDDIR)/site/ja/"
	@echo "Assembled site → $(BUILDDIR)/site (en at /, ja at /ja/)"

serve: site
	@cd "$(BUILDDIR)/site" && python -m http.server $(SERVE_PORT) --bind 127.0.0.1

# ---- i18n ------------------------------------------------------------------
# 1) ``make gettext``      → ソースから .pot を生成
# 2) ``make intl-update``  → locales/ja/LC_MESSAGES/*.po を更新 (既存翻訳は保持)
# 3) .po ファイルを翻訳 (手作業 or Claude Code)
# 4) ``make html-ja``      → .po を参照して翻訳適用 HTML をビルド

gettext:
	@$(SPHINXBUILD) -M gettext "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS)

intl-update: gettext
	@sphinx-intl update -p "$(BUILDDIR)/gettext" -l $(LANGUAGE_JA) -d "$(SOURCEDIR)/locales"
