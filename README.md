# anno-save-analyzer

> **One-liner**: Save file analyzer for *Anno 1800* and *Anno 117: Pax Romana* — decompress `.a7s` / `.a8s` containers, parse FileDB binaries, and visualize supply chains, trade routes, and quest progress.

> **Status: Work in Progress.** This project is under active development and APIs may break between commits. See the [Roadmap](#roadmap) for current status. Japanese README: [README.ja.md](README.ja.md).

## Overview

Anno 1800 saves are matryoshka-style containers:

1. `.a7s` — RDA archive (V2.2 container format used across Anno 1404 / 2070 / 2205 / 1800)
2. `data.a7s` inside it — zlib-compressed stream
3. FileDB V1/V2/V3 binary after decompression
4. `data.xml` — multi-million-line XML tree (approximately 2.2M lines on a real late-game save)
5. `<SessionData><BinaryData>` — re-embedded binary blobs inside that XML (still being reverse-engineered)

This project aims to peel every layer natively in Python (with a possible Rust re-port later) and expose the data in ways that let players actually use it: supply-chain balance tables, route-efficiency reports, and quest dashboards.

## Current features (v0.1.5)

- RDA V2.2 container parser, fully native Python
  - Magic / header / block chain / directory entry / per-file zlib decompression
  - Context-manager API: `with RDAArchive(path) as rda: ...`
  - `entries` / `read(name)` / `extract(...)` / `extract_all(...)`
  - Clean-room reimplementation of [@lysannschlegel/RDAExplorer](https://github.com/lysannschlegel/RDAExplorer) based on format spec only
- `parser.pipeline.extract_inner_filedb` — one call `a7s` to inner FileDB bytes

## Roadmap

| Version | Scope | Status |
|---|---|---|
| v0.1.5 | RDA V2.2 native parser | done |
| v0.2 | FileDB V1/V2/V3 parser, route data models | next |
| v0.3 | `SessionData` / `BinaryData` decoder (the hard part) | planned |
| v0.4 | Per-island supply-chain balance sheet | planned |
| v0.5 | OR-Tools MILP route optimizer | planned |
| v0.6 | Tauri v2 desktop GUI | planned |
| v1.0 | Public release, English-only docs | planned |
| v1.1 | Anno 117 (`.a8s`) support | planned |

## Tech stack

| Category | Choice |
|---|---|
| Language | Python 3.12+ |
| Package manager | uv (recommended), pip compatible |
| XML parser | lxml (`huge_tree=True`, `recover=True`) |
| Data models | pydantic v2 |
| Aggregation | pandas |
| Optimization (optional) | OR-Tools |

## Architecture

```text
sample.a7s  (RDA V2.2 container)
    └─ data.a7s  (zlib-compressed)
        └─ FileDB binary  (V1/V2/V3, Blue Byte proprietary)
            └─ data.xml  (multi-million-line XML tree)
                └─ <SessionData><BinaryData>  (still under reverse engineering)
```

See [docs/rda_format_spec.md](docs/rda_format_spec.md) for the full RDA V2.2 format write-up.

## Getting started

### Requirements

- Python 3.12 or newer
- `uv` (recommended) or `pip`
- A real Anno 1800 save file (`.a7s`) for end-to-end verification (unit tests ship with synthetic fixtures and do not require one)

### Install

```bash
git clone https://github.com/yuuka-dev/anno-save-analyzer.git
cd anno-save-analyzer
uv sync          # or: python -m venv .venv && .venv/bin/pip install -e .
```

### Quick start

```python
import zlib
from anno_save_analyzer.parser.rda import RDAArchive

with RDAArchive("Autosave 182.a7s") as rda:
    for e in rda.entries:
        print(e.filename, e.uncompressed_size)

    data_bytes = rda.read("data.a7s")
    filedb_bytes = zlib.decompress(data_bytes)
    # filedb_bytes is now a FileDB V2 binary (~165 MB for a late-game save)
```

### Run tests

```bash
uv run pytest
# or: .venv/bin/python -m pytest
```

Tests that require a real save are auto-skipped if none is present. To run them, place a save as `sample.a7s` at the repo root, or set the `SAMPLE_A7S` environment variable.

## Disclaimer

This project is **not affiliated** with Ubisoft, Blue Byte, or the Anno franchise. It is a third-party, read-only analysis tool. *Anno*, *Anno 1800*, *Anno 117: Pax Romana*, *Ubisoft*, *Blue Byte* are trademarks of their respective owners.

## Acknowledgements

- Based on the reverse-engineering work of [@lysannschlegel's RDAExplorer](https://github.com/lysannschlegel/RDAExplorer).
- FileDB format research draws on [anno-mods/FileDBReader](https://github.com/anno-mods/FileDBReader).
- Prior art / inspiration: [Anno1800SavegameVisualizer](https://github.com/NiHoel/Anno1800SavegameVisualizer), [AnnoSavegameViewer](https://github.com/Veraatversus/AnnoSavegameViewer), [anno1800-save-game-explorer](https://github.com/RobertLeePrice/anno1800-save-game-explorer).

## License

MIT — see [LICENSE](LICENSE) (to be added).
