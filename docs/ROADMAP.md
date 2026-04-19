# Roadmap

> Last updated: 2026-04-19. This roadmap is directional, not a commitment. Priorities may shift as the *Anno 1800* save-file format yields its secrets. Japanese version: [ROADMAP.ja.md](ROADMAP.ja.md).

## Current release

### v0.1.0 — RDA V2.2 native parser (shipped)

Native Python reader for the outer `.a7s` RDA container. Provides:

- `RDAArchive` context-manager API with entry enumeration and per-file zlib decompression
- `parser.pipeline.extract_inner_filedb` one-call unwrap to FileDB bytes
- Format specification documented in [rda_format_spec.md](rda_format_spec.md)
- pytest suite (14 tests) using synthetic fixtures and optional real-save integration

## Planned milestones

### v0.2 — FileDB parser

Goal: expose the structured XML tree that sits inside `data.a7s`.

- Decode FileDB V1 / V2 / V3 binary tag streams
- Produce an lxml-compatible XML document (streamed where possible)
- Introduce route/contract/quest Pydantic models fed from the XML tree
- Keep peak memory bounded for late-game saves (≈2.2M XML lines, 170MB decompressed)

Dependencies: `lxml` (already declared), streaming byte-reader helpers.

### v0.3 — `SessionData` / `BinaryData` decoder (hard part)

Goal: crack the re-embedded binary that holds island details (buildings, stockpiles, population).

- Reverse-engineer the header magic (`04000000018000001D0000…`)
- Identify the five session blocks (Old World / New World / Enbesa / Arctic / Cape)
- Decode GUID references, timestamps, UTF-16LE strings
- Produce island-level data models

This is expected to take significant research. Acceptable to ship partial progress as v0.3.x increments.

### v0.4 — Supply-chain balance sheet

Goal: for each island, compute net production vs. consumption per good.

- Input: island inventory + building count × recipe efficiency
- Output: surplus/deficit table, bottleneck highlighting
- CLI command: `anno-save-analyzer balance <save>`

### v0.5 — Route optimizer (OR-Tools)

Goal: suggest route reassignments that reduce idle ships or unfilled demand.

- MILP formulation over islands × goods × routes
- Respect ship capacity, travel time, and current assignments
- `optimizer` extras group: `pip install anno-save-analyzer[optimizer]`

### v0.6 — Textual TUI dashboard

Goal: zero-install, terminal-based UI for exploring a save file.

- Built on [Textual](https://github.com/Textualize/Textual) (pure Python TUI)
- Screens: overview / islands / routes / quests / balance sheet
- Runs anywhere Python runs; no Electron, no Tauri, no browser
- Keyboard-first navigation

### v1.0 — Public stable release

Goal: first version presentable on PyPI with English-first docs.

- Stable public APIs (semver from here on)
- CHANGELOG.md, MkDocs site or in-repo docs
- Packaged on PyPI as `anno-save-analyzer`
- Example notebooks / saved-data anonymization tooling

## Future (version TBD)

### Anno 117: Pax Romana support

*Anno 117: Pax Romana* ships with the `.a8s` save extension. The engine is expected to share roughly 90% of the format with Anno 1800, but confirmation requires access to a real `.a8s` file once the game is released. The version number for this milestone will be decided after that investigation.

## Intentionally non-goals

- GPU acceleration: the pipeline is I/O- and parse-bound, so a GPU does not help.
- Online / hosted service: save files are local personal assets; requiring an upload would ruin the UX.
- Cheat / save-editing assistance: this project is a **read-only analyzer**. Save editing is left to other projects such as [olescheller/anno1800-retroactive-dlc-activation](https://github.com/olescheller/anno1800-retroactive-dlc-activation).
- Real-time save monitoring: *Anno 1800* autosaves discretely; continuous monitoring adds little value.

## How to follow progress

- GitHub Milestones: https://github.com/yuuka-dev/anno-save-analyzer/milestones
- Issues grouped per milestone track the concrete tasks for each version.
- CHANGELOG.md (added from v0.2 onward) records shipped changes.
