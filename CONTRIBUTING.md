# Contributing

Thanks for your interest in **anno-save-analyzer**. This project is a work-in-progress hobby OSS; contributions are welcome, but please read this document before opening PRs or issues so we stay coordinated.

Japanese contributors: feel free to file issues and PR descriptions in 日本語. Code and inline comments may be in either language; Japanese comments are accepted throughout the codebase.

## Branch strategy

| Branch | Purpose | Merges into |
|---|---|---|
| `main` | Production snapshot (what gets tagged) | — |
| `dev` | Integration branch for ongoing work | `main` via `release/*` |
| `feature/*` | New features | `dev` |
| `fix/*` | Bug fixes | `dev` |
| `docs/*` | Documentation-only changes | `dev` |
| `chore/*` | Non-functional maintenance (CI, tooling, config) | `dev` |
| `release/vX.Y.Z` | Release preparation (version bump, changelog) | `main` (then merge-back to `dev`) |

- Never push directly to `main` or `dev`. Always go through a PR.
- `dev` and paths like `dev/feature/*` cannot coexist by git ref rules, so we use the unprefixed form (`feature/foo`).

## Commit message format

```
<type>(<scope>): <short title>

<optional body>
```

Types: `feat`, `fix`, `update`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`, `ci`.

Japanese commit messages are the default in this repo. English is fine for widely-relevant refactors.

Do **not** append `Co-Authored-By: Claude ...` or `Cursor ...` trailers.

## Pull requests

All PRs must:

1. **Request GitHub Copilot code review.** Add `Copilot` as a reviewer when opening the PR, or use the repo-level ruleset (configured by the maintainer). A Copilot review is a required check before merging.
2. **Pass CI.** Every push triggers `pytest` with coverage on Python 3.12 and 3.13. See `.github/workflows/ci.yml`.
3. **Keep coverage at 100%.** Line and branch coverage for the `anno_save_analyzer` package must stay at 100%. CI enforces this via `pytest --cov-fail-under=100`. New code without tests that cover every branch blocks the merge; defensive checks that are unreachable through normal flow must be exercised via `monkeypatch`, mocked streams, or direct unit tests on the helper function — not excluded with `pragma: no cover`.
4. **Describe the change clearly** using the PR template (`Summary` / `Test plan`). Link any issue with `Closes #N`.
5. **Keep scope tight.** If a change bundles unrelated refactors, split it. The maintainer may request a split before review.

### Review expectations

- Copilot review: automated, covers obvious bugs and style drift.
- Human review (maintainer): architecture, scope, correctness of RDA/FileDB format claims.
- Reviewer may request changes, request format-spec references, or block the PR on missing tests.

## Issues

Every non-`chore` change should start life as an issue. Use the appropriate template:

- `Feature request` for new capabilities (tie to a Milestone where possible)
- `Bug report` for regressions or format-parsing failures

Issues that a PR resolves must be closed with a comment pointing at the PR number and merge commit, per [CLAUDE.md](../CLAUDE.md) convention (checklist confirmation).

## Testing

### Run the full suite

```bash
uv run pytest --cov=anno_save_analyzer --cov-report=term-missing
```

### Synthetic vs. real-save tests

- **Synthetic fixtures** (default, run on CI): no save file required. Tests under `TestSyntheticFixture` / `TestErrorHandling` synthesize RDA bytes in-memory.
- **Real-save tests** (local only): require a `sample.a7s` at repo root or `SAMPLE_A7S=<path>`. Auto-skipped when the file is missing.

### Adding new tests

- New features must ship with tests. PRs without tests for new logic will be requested to add them.
- When extending format support (new version, new flag), add both a synthetic positive case and at least one error case.

## Reverse-engineering format references

When adding parser logic for a new Anno save-format feature:

1. Cite the upstream reference in the commit message or comment (link to `refs/RDAExplorer/...`, Anno mod loader, or equivalent).
2. If no existing reference exists, document the finding in `docs/` before implementing.
3. Do **not** copy code from GPL-licensed projects (e.g., RDAExplorer). Use spec-level understanding only. This project remains MIT-licensed through clean-room reimplementation.

## Code style

- Python 3.12+, type hints on public functions.
- Line length: 100 (ruff default with minor relaxation).
- Lint/format: `ruff check` and `ruff format` (config in `pyproject.toml`).
- Docstrings in Japanese or English are both acceptable.

## License

By contributing, you agree that your contributions will be licensed under the MIT License, matching the rest of the repository.
