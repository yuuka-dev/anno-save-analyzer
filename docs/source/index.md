# anno-save-analyzer

An offline analysis toolkit for **Anno 1800** and **Anno 117: Pax Romana**
save files. Parses the RDA / FileDB container stack, reconstructs trade
history, inventory trends, population breakdown, and supply-demand balance,
then surfaces everything through a Textual TUI, a PySide6 GUI (frozen), a
JSON export CLI, and a **pandas-native SCM analytics layer** (v0.5).

:::{note}
This is an open-source side project by [@yuuka-dev](https://github.com/yuuka-dev).
The tool is strictly **read-only**; it never modifies your save.
:::

## Quick navigation

:::{grid} 1 1 2 2
:gutter: 2

:::{grid-item-card} Getting started
:link: guide/quickstart
:link-type: doc

Install, pick a save file, launch the TUI, export JSON. Start here if
you are new.
:::

:::{grid-item-card} SCM analytics (v0.5)
:link: guide/scm-analytics
:link-type: doc

DataFrame layer, deficit maps, correlation, route rankings,
**Decision Matrix**, Min-Cost Flow, and OR-Tools VRP.
:::

:::{grid-item-card} API reference
:link: api/index
:link-type: doc

autodoc-generated reference for `analysis`, `trade`, `parser`, `tui`,
`gui`, `cli`.
:::

:::{grid-item-card} Save file format
:link: reference/rda_format_spec
:link-type: doc

RDA container, FileDB V3, SessionData recursion, and the tag dictionary.
:::
:::

## Site map

```{toctree}
:maxdepth: 2
:caption: Guides

guide/quickstart
guide/scm-analytics
guide/decision-matrix
```

```{toctree}
:maxdepth: 2
:caption: API reference

api/index
```

```{toctree}
:maxdepth: 2
:caption: Reference

reference/rda_format_spec
reference/filedb_format_investigation
reference/session_binary_investigation
reference/factory_extraction_spike
design/v0.3-trade-history-design
```

```{toctree}
:maxdepth: 1
:caption: Project

roadmap
```

---

Japanese documentation: [ja/index.html](ja/index.html) (build with ``make html-ja`` /
``make site`` for combined preview)．
