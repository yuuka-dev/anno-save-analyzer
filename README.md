# anno-save-analyzer

[![CI](https://github.com/yuuka-dev/anno-save-analyzer/actions/workflows/ci.yml/badge.svg)](https://github.com/yuuka-dev/anno-save-analyzer/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/yuuka-dev/anno-save-analyzer/branch/main/graph/badge.svg)](https://codecov.io/gh/yuuka-dev/anno-save-analyzer)
[![release](https://img.shields.io/github/v/release/yuuka-dev/anno-save-analyzer?include_prereleases)](https://github.com/yuuka-dev/anno-save-analyzer/releases/latest)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Status: alpha](https://img.shields.io/badge/status-alpha-orange)](docs/ROADMAP.md)

> **One-liner**: Save file analyzer for *Anno 1800* and *Anno 117: Pax Romana* — decompress `.a7s` / `.a8s` containers, parse FileDB binaries, and surface trade history through a Textual TUI and a JSON-friendly CLI.

> **Status**: v0.3.0 shipped (trade history viewer). Not on PyPI yet; install from Git tag or a local clone. Japanese README: [README.ja.md](README.ja.md).

## Overview

Anno saves are matryoshka-style containers:

1. `.a7s` / `.a8s` — RDA archive (V2.2 container, shared across Anno 1404 / 2070 / 2205 / 1800 / 117)
2. `data.a7s` inside it — zlib-compressed stream
3. FileDB V3 binary after decompression
4. `<SessionData><BinaryData>` — re-embedded full FileDB V3 documents, one per game session (Latium, Albion, Old World, …)
5. Inside each session: `AreaInfo`, `PassiveTrade > History`, `ConstructionAI > TradeRoute`, …

This project peels every layer natively in Python and turns the raw trade events into things players actually want: aggregated ledgers, partner breakdowns, cumulative charts, sparklines, and snapshot diffs between saves.

## Features (v0.3.0)

### Textual TUI (`anno-save-analyzer tui <save>`)

- 3-column layout: sessions/islands tree · items & routes tables · Partners pane + plotext chart
- nano-flavored hotkeys: `^X` exit / `^G` help / `^T` switch screen / `^L` locale / `^O` export
- Sparkline column (`▁▂▃▄▅▆▇█`) for cumulative quantity per good
- Selecting a row updates Partners pane + line chart in sync
- Chart x-axis auto-switches between minutes / hours ago by spread
- en / ja locale toggle; Anno 117 / 1800 session names localized
- Stage-granularity load gauge (`[n/5] <stage>`) on startup
- **USSR theme** (`--theme ussr`) — joke-tier palette with a ☭ title prefix

### CLI

- `trade list <save>` — dump every TradeEvent as JSON
- `trade summary <save> --by item|route` — aggregated view
- `trade diff <before> <after>` — added / removed / changed / unchanged between two saves
- `tui <save>` — launch the Textual viewer

### Parser

- **RDA V2.2** container parser (clean-room port of [@lysannschlegel/RDAExplorer](https://github.com/lysannschlegel/RDAExplorer)). Handles both `.a7s` and `.a8s`.
- **FileDB V3** streaming DOM with tag/attrib dictionaries, recursive `SessionData` extraction, AreaManager/island enumeration.
- **Anno 117 interpreter** for `PassiveTrade > History > {TradeRouteEntries,PassiveTradeEntries}` and `ConstructionAI > TradeRoute > TradeRoutes` (idle route enumeration).
- NPC-vs-NPC trades filtered out via the `AreaInfo > CityName` gate.

### Data pipeline

- `items_anno117.{en,ja}.yaml` auto-generated from the game's own `config.rda/assets.xml` and `texts_japanese.xml` — 151 Products × 33,146 localized strings. Regenerator at `scripts/generate_items_anno117.py`; run it after a game patch.

### Tests

- 338 tests, **100 % line + branch coverage** enforced by CI (`--cov-fail-under=100`).
- Python 3.12 and 3.13 both supported.

## Install

### With **uv** (recommended)

[uv](https://github.com/astral-sh/uv) installs a Python interpreter, creates a venv, and resolves dependencies in one step.

```bash
# Install the latest released version from the GitHub tag
uv pip install "anno-save-analyzer[tui] @ git+https://github.com/yuuka-dev/anno-save-analyzer@v0.3.0"

# Or install as a standalone CLI tool (no venv management)
uv tool install "anno-save-analyzer[tui] @ git+https://github.com/yuuka-dev/anno-save-analyzer@v0.3.0"
```

The `[tui]` extra pulls in Textual and textual-plotext. Omit it if you only need the CLI / library.

### Local clone (development)

```bash
git clone https://github.com/yuuka-dev/anno-save-analyzer.git
cd anno-save-analyzer
uv sync --extra tui        # or: python -m venv .venv && .venv/bin/pip install -e '.[tui]'
```

### Without uv (plain pip)

```bash
pip install "anno-save-analyzer[tui] @ git+https://github.com/yuuka-dev/anno-save-analyzer@v0.3.0"
```

> PyPI publication is planned for v1.0. Until then, Git tags are the supported distribution channel.

## Quick start

Everything runs under the `anno-save-analyzer` command. ``--title`` selects the
game (`anno117` / `anno1800`); `--locale` controls UI names (`en` / `ja`).

### Launch the TUI

```bash
anno-save-analyzer tui sample_anno117.a8s --title anno117 --locale ja
```

- `^X` exit · `^G` help · `^T` switch screen · `^L` toggle locale · `^O` export CSVs
- Add `--theme ussr` for the 書記長 palette (☭ title prefix)
- On load, a 5-stage gauge streams to stderr so you can see what's happening

### Inspect trades from the CLI

```bash
# Every TradeEvent as JSON
anno-save-analyzer trade list sample_anno117.a8s --title anno117

# Per-item / per-route aggregates
anno-save-analyzer trade summary sample_anno117.a8s --title anno117 --by item
anno-save-analyzer trade summary sample_anno117.a8s --title anno117 --by route

# Diff two saves (added / removed / changed / unchanged)
anno-save-analyzer trade diff before.a8s after.a8s --title anno117 --locale ja
anno-save-analyzer trade diff before.a8s after.a8s --by route --show-unchanged
```

All sub-commands emit JSON to stdout, so pipe them into `jq`, DuckDB, or your
favourite notebook.

### Get help

```bash
anno-save-analyzer --help
anno-save-analyzer trade --help
anno-save-analyzer tui --help
```

## Roadmap

| Version | Scope | Status |
|---|---|---|
| v0.1.0 | RDA V2.2 native parser | ✅ done |
| v0.2.x | FileDB V3 parser, recursive SessionData, island metadata | ✅ done (rolled into 0.3.0) |
| **v0.3.0** | **Trade history viewer: Textual TUI + CLI + snapshot diff** | ✅ **released** |
| v0.4 | StorageTrends (per-island inventory time series) TUI integration ([#23](https://github.com/yuuka-dev/anno-save-analyzer/issues/23)) | 🚧 next |
| v0.4+ | Data-volume progress gauge ([#26](https://github.com/yuuka-dev/anno-save-analyzer/issues/26)), Anno 1800 parity ([#24](https://github.com/yuuka-dev/anno-save-analyzer/issues/24)) | planned |
| v0.5 | OR-Tools MILP route optimizer | planned |
| v0.6 | Typed Pydantic models across the DOM (Island / Building / Population) | planned |
| v1.0 | PyPI publish, English docs, stable API | planned |

See [docs/ROADMAP.md](docs/ROADMAP.md) (English) / [docs/ROADMAP.ja.md](docs/ROADMAP.ja.md) (Japanese) for detailed milestones.

## Tech stack

| Category | Choice |
|---|---|
| Language | Python 3.12+ |
| Package manager | uv (recommended), pip compatible |
| CLI framework | typer |
| XML parser | lxml (`huge_tree=True`, `recover=True`) |
| Data models | pydantic v2 |
| Aggregation | pandas |
| TUI | [Textual](https://github.com/Textualize/Textual) + [textual-plotext](https://github.com/Textualize/textual-plotext) |
| Optimization (optional, v0.5) | OR-Tools |
| Notebook (optional) | JupyterLab (for `notebooks/island_inventory.ipynb`) |
| CI | GitHub Actions, pytest-cov, Codecov |
| Lint / format | ruff |

## Architecture

```text
sample_anno117.a8s  (RDA V2.2 container)
└─ data.a7s  (zlib stream inside RDA)
   └─ outer FileDB V3
      ├─ <SessionData><BinaryData>  (one per game session, recursively another FileDB V3)
      │  ├─ AreaInfo > <1> > AreaEconomy > StorageTrends  (inventory time series — v0.4)
      │  ├─ AreaInfo > <1> > PassiveTrade > History > TradeRouteEntries / PassiveTradeEntries > …
      │  └─ ConstructionAI > TradeRoute > TradeRoutes > <1>  (idle route definitions)
      └─ meta / header / gamesetup.a7s  (handled by RDAArchive)
```

See [docs/rda_format_spec.md](docs/rda_format_spec.md) and [docs/filedb_format_investigation.md](docs/filedb_format_investigation.md) for the write-ups.

## Testing / development

```bash
uv run pytest --cov=anno_save_analyzer --cov-branch --cov-fail-under=100
uv run ruff check src tests
uv run ruff format --check src tests
```

Tests that need a real save are auto-skipped if none is present. Drop a save as `sample.a7s` or `sample_anno117.a8s` at the repo root, or set `SAMPLE_A7S` / `SAMPLE_A8S`.

## Contributing

Pull requests welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for the branch strategy, commit conventions (English-subject + optional Japanese body block), Copilot review policy, and 100 % coverage expectation. In short:

- Feature work on `feature/*` → `dev` → (release branch) → `main`.
- Every PR requests Copilot review and must keep CI green with coverage at 100 %.
- Parser additions should cite a format reference in `docs/`.

## Disclaimer

This project is **not affiliated** with Ubisoft, Blue Byte, or the Anno franchise. It is a third-party, read-only analysis tool. *Anno*, *Anno 1800*, *Anno 117: Pax Romana*, *Ubisoft*, *Blue Byte* are trademarks of their respective owners.

## Acknowledgements

- RDA V2.2 format: [@lysannschlegel/RDAExplorer](https://github.com/lysannschlegel/RDAExplorer).
- FileDB format: [anno-mods/FileDBReader](https://github.com/anno-mods/FileDBReader).
- Prior art: [Anno1800SavegameVisualizer](https://github.com/NiHoel/Anno1800SavegameVisualizer), [AnnoSavegameViewer](https://github.com/Veraatversus/AnnoSavegameViewer), [anno1800-save-game-explorer](https://github.com/RobertLeePrice/anno1800-save-game-explorer).

## License

MIT — see [LICENSE](LICENSE) (to be added).
