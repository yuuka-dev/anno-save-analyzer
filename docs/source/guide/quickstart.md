# Quickstart

Install, open a save, and get analysis-ready data in under 5 minutes.

## Install

Install with the extras you need:

```bash
# Core + TUI
pip install -e ".[tui]"

# Plus GUI (PySide6) and optimizer (OR-Tools VRP)
pip install -e ".[tui,gui,optimizer]"
```

## Locate your save

| Game | Default save folder (Windows) |
| --- | --- |
| Anno 1800 | ``%USERPROFILE%\Documents\Anno 1800\accounts\<id>\savegame\`` |
| Anno 117 | ``%USERPROFILE%\Documents\Anno 117 - Pax Romana\accounts\<id>\savegame\`` |

Copy a ``.a7s`` (Anno 1800) or ``.a8s`` (Anno 117) file somewhere convenient.
The tool is **read-only** — it never modifies your save.

## Launch the TUI

```bash
anno-save-analyzer tui sample_anno1800.a7s --title anno1800 --locale ja
```

Use ``Ctrl+T`` to switch screens (Overview → Trade Statistics →
Supply Balance). ``Ctrl+L`` toggles English/Japanese.

## Export the full state as JSON

```bash
anno-save-analyzer state sample_anno1800.a7s \
    --title anno1800 --locale ja --out state.json
```

The JSON contains overview + islands + tier breakdown + balance + every
TradeEvent. Load it with `pandas.read_json` / `pandas.json_normalize` and
you are analysis-ready (see {doc}`scm-analytics`).

## One-liner Python API

```python
from anno_save_analyzer.tui.state import load_state
from anno_save_analyzer.trade.models import GameTitle
from anno_save_analyzer.analysis import to_frames

state = load_state("sample_anno1800.a7s", title=GameTitle.ANNO_1800, locale="ja")
frames = to_frames(state)

# island × product × balance
frames.balance.head()
```
