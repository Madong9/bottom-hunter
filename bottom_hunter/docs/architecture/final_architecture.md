# Bottom Hunter Final Product Architecture

## 1. Overall architecture

Bottom Hunter uses a one-way presentation architecture. Business and storage
objects never cross the adapter boundary.

```text
Backend / generated snapshots
            |
            v
Read-only adapters / RealMutationPort
            |
            v
Frozen DTO contracts
            |
            v
QObject ViewModels + lifecycle state
            |
            v
QtQuick / QML pages
```

The composition root is `build_production_flow()`. It constructs adapters,
DTO providers, ViewModels, navigation and the Import Controller, then exposes
only presentation-safe objects as QML context properties. QML cannot import
Python business modules, access the database or write files.

The existing QtWidgets application, scanner, backtest and K-line backend remain
independent and frozen. The QML product shell is available through
`bottom-hunter-qml`; it does not replace the legacy GUI entry point.

## 2. Product pages

| Route | Context property | Data source | Product state |
|---|---|---|---|
| `overview` | `overviewState` | Latest report snapshot | Read-only metrics |
| `watchlist` | `watchlistVm` | `watchlist_summary.json` | Read-only assets |
| `research` | `researchVm` | Latest report research snapshot | Read-only research |
| `report` | `reportVm` | Latest JSON daily report | Read-only summary |
| `import` | `importVm` | Preview adapter + transaction controller | Explicit command flow |
| `status` | `statusVm` | Existing health checks and report snapshot | Read-only health |
| `chart` | `chartVm` | `ChartReadAdapter` + existing chart service | Read-only interactive K-line |

Every route has a stable page ID, loader, injected ViewModel position and a
Chinese loading, empty, error or fallback message. Chart reuses the existing
market service behind a read-only adapter; the QML page never imports or
mutates the chart backend.

## 3. Data flow

Read-only pages load existing snapshots only:

```text
JSON snapshot / read helper
        -> page adapter
        -> frozen PageDTO
        -> ViewModel.apply(dto)
        -> notify signals
        -> QML bindings
```

Lifecycle states are explicit. Data pages use `INIT`, `LOADING`, `READY`,
`EMPTY` and `ERROR`; Overview additionally supports `STALE`, and Import has its
transaction states. Adapter failures become safe Chinese UI messages instead
of exceptions escaping into QML.

Chart follows a dedicated read-only asynchronous path:

```text
watchlist_summary.json -> ChartAssetDTO
user selection -> ChartViewModel intent -> ChartController / QThread
-> ChartReadAdapter -> existing MarketChartService
-> ChartDTO -> ChartViewModel -> QML Canvas
```

Indicators are calculated by the existing chart calculation function and
transported as immutable values. QML owns only view controls, the visible-bar
window and non-persistent session annotations.

## 4. AI-agent collaboration workflow

The repository was migrated in bounded phases suitable for human and AI-agent
collaboration:

1. Audit the existing backend and freeze high-risk modules.
2. Identify a read-only snapshot or a narrow command boundary.
3. Define immutable DTO contracts before presentation work.
4. Implement ViewModel lifecycle behavior without backend imports.
5. Connect QML through the composition root and reuse existing primitives.
6. Add isolation, lifecycle, QML smoke and regression tests.
7. Commit one completed phase at a time with an auditable message.

An agent must inspect before editing, avoid speculative refactors, never place
credentials or runtime state in Git, and stop when a change would require a new
business capability. Frozen shader binaries, visual parameters and backend
business rules are protected by architecture tests.

## 5. Transactional import

Import is the only command-oriented page:

```text
User file
  -> read-only preview + fingerprint
  -> ImportCommandDTO
  -> ImportController / QThread worker
  -> RealMutationPort
  -> prepare -> stage -> verify
  -> optional PARTIAL_REVIEW
  -> commit or rollback
  -> ImportResultDTO
  -> ImportViewModel -> QML
```

Preparation is zero-write. Commit artifacts are staged in a transaction
workspace, verified against source and target baselines, backed up, atomically
replaced and rolled back on failure. A cross-process lock prevents concurrent
mutation. `PARTIAL_REVIEW` releases that lock; acceptance reacquires it and
re-verifies the prepared transaction before commit. Cancellation is
cooperative and checked at safe transaction boundaries.

## 6. Test system

The suite combines:

- DTO immutability and serialization tests;
- adapter snapshot and zero-write tests;
- ViewModel lifecycle and error-state tests;
- QML offscreen loading and routing smoke tests;
- asynchronous Import Controller and cancellation tests;
- transaction conflict, backup, rollback and lock tests;
- architecture isolation and frozen-file regression tests;
- full legacy regression tests.

`tests/test_final_architecture.py` is the final product boundary audit. It
checks all seven routes, QML/backend separation, ViewModel isolation, frozen
DTOs, sanctioned adapters, Import Controller isolation and unchanged frozen
modules.

## Frozen boundaries

The following remain outside PHASE 5 changes:

- `src/gui_qt.py` business logic;
- scanner and backtest implementations;
- K-line/chart backend business logic (consumed through the adapter only);
- database schema;
- shader source, `.qsb` binaries and Crystal Glass parameters;
- live or automated trading.
