# Minimal Sphinx Makefile.
# ``make html`` で ``_build/html/`` に生成．``make clean`` で掃除．

SPHINXOPTS    ?= --keep-going -n
SPHINXBUILD   ?= sphinx-build
SOURCEDIR     = source
BUILDDIR      = _build

.PHONY: help html clean livehtml gettext

help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS)

html:
	@$(SPHINXBUILD) -M html "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS)

clean:
	@$(SPHINXBUILD) -M clean "$(SOURCEDIR)" "$(BUILDDIR)"

# 日本語版: source_ja を別 build．MVP では手動 (後で gettext に統合予定)．
html-ja:
	@$(SPHINXBUILD) -M html "$(SOURCEDIR)" "$(BUILDDIR)/ja" -D language=ja $(SPHINXOPTS)
