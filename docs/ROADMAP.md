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

### v0.3 — Trade History Viewer (Anno 117 dogfooding)

> **Scope changed in 2026-04**: the original SessionData / BinaryData decoder
> work was largely subsumed by v0.2 (recursive FileDB hypothesis confirmed) and
> displaced by a more pressing dogfooding need — Anno 117 ships without an
> in-game trade-history UI, and the maintainer wants one.

Goal: a CLI + Textual TUI that exposes per-good and per-route trade activity
extracted from `.a8s` (Anno 117) and `.a7s` (Anno 1800) saves.

- Cross-title abstract data model (`TradeEvent`, `Item`, `Route`, ...)
- Method A: extract from in-save history fields (`<TradedGoods>` etc.)
- Method B: snapshot diff for titles where history is sparse
- 3-column Textual TUI modelled after the Anno 1800 statistics view
- Inline charts via `textual-plotext`
- Bilingual (`name_en` + `name_ja`) GUID dictionary YAMLs

Detailed specification: [`v0.3-trade-history-design.md`](./v0.3-trade-history-design.md)
(Japanese sibling: [`v0.3-trade-history-design.ja.md`](./v0.3-trade-history-design.ja.md)).

The deeper SessionData / BinaryData domain modelling (full island /
building / population schema) is preserved as **v0.6** below.

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

### v0.6 — Island / Building / Population schema deep-dive

> **Scope changed in 2026-04**: the original "Textual TUI dashboard" was
> pulled forward into v0.3 (the trade-history viewer ships its own TUI). The
> v0.6 slot is now used for the deeper schema work that the supply-chain
> balance (v0.4) and route optimizer (v0.5) will consume.

Goal: complete Pydantic models for islands, buildings, and population layers
inside the SessionData inner FileDB. v0.2 / v0.3 already extract the bytes;
v0.6 turns them into typed domain objects.

- Schema for `Island*` / `AreaManager_*` / `AreaPopulationManager`
- Building catalogue (production / consumption per building type)
- Population tier breakdowns (Roman / Italic / etc. for Anno 117)
- Anonymous attrib (`id=0x8000`) context-dependent type resolution
- Anno 1800 ↔ Anno 117 schema diff documentation

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
