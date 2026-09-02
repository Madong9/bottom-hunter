"""PHASE 3.5 — architecture audit & freeze regression tests.

Enforce the frozen layering contract so no future change silently breaks it:

    Backend (bottom_hunter/src, read-only)
      ↓  adapter boundary ONLY (launcher _wire / pages/contracts.py)
    DTO (frozen dataclass contracts)
      ↓
    ViewModel (QObject, display state)
      ↓
    QML (presentation)

Rules asserted:
  - UI layer never imports business modules (except the two sanctioned
    adapter boundaries).
  - No reverse dependency: backend never imports QtQml/QtQuick.
  - No direct DB access from the UI layer.
  - No shader/qsb change since the freeze (checked via git, when available).
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

# git repo root is one level above bottom_hunter/ (tests/ -> bottom_hunter/ -> root)
REPO = Path(__file__).resolve().parent.parent.parent
UI_DEMO = REPO / "bottom_hunter" / "ui_demo"
SRC = REPO / "bottom_hunter" / "src"
# PHASE 1.6 hardening commit — shaders/qsb frozen from here on
FROZEN_COMMIT = os.environ.get("BH_FROZEN_COMMIT", "785e08f")

# The two sanctioned adapter boundaries (allowed to reference the backend
# inside function bodies only — never at module import time).
SANCTIONED_ADAPTERS = {
    "overview_shell_launcher.py",
    "contracts.py",
    "import_preview_adapter.py",
    "import_backend_adapter.py",
}


def _ui_py_files():
    return [p for p in UI_DEMO.rglob("*.py") if "__pycache__" not in p.parts]


# ---- 1. UI layer -> business import boundary --------------------------------

def test_ui_layer_business_import_boundary() -> None:
    for path in _ui_py_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        # a business reference may only appear at function-body indentation
        # inside a sanctioned adapter, never at module level
        for m in re.finditer(r"from\s+bottom_hunter\.src\b", text):
            line_start = text.rfind("\n", 0, m.start()) + 1
            line = text[line_start:m.end()]
            indent = line[: len(line) - len(line.lstrip())]
            assert path.name in SANCTIONED_ADAPTERS, (
                f"{path.name}: business import outside sanctioned adapter")
            assert indent != "", (
                f"{path.name}: business import at module level (must be "
                f"deferred inside a function)")


# ---- 2. no reverse dependency (backend -> QML/QtQuick) ----------------------

def test_no_reverse_dependency() -> None:
    forbidden = re.compile(r"QtQml|QtQuick", re.I)
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        assert not forbidden.search(text), (
            f"reverse dependency: {path.name} imports QML/QtQuick")


# ---- 3. no DB access from UI layer ------------------------------------------

def test_no_database_access_from_ui() -> None:
    # sqlite3 / StateStore / raw connect() must not appear in UI-layer modules;
    # the adapter boundary may call read-only helpers that internally use them
    forbidden = re.compile(r"sqlite3|StateStore|sqlite", re.I)
    for path in _ui_py_files():
        if path.name in SANCTIONED_ADAPTERS:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        assert not forbidden.search(text), f"DB access in UI layer {path.name}"


# ---- 4. DTO contracts are pure (no Qt, no business) -------------------------

def test_dto_contracts_are_pure() -> None:
    contract_files = [
        UI_DEMO / "overview_shell" / "contracts" / "__init__.py",
        UI_DEMO / "pages" / "contracts.py",
        UI_DEMO / "pages" / "import_contracts.py",
    ]
    forbidden = re.compile(r"PySide6|QtQuick|QObject", re.I)
    for path in contract_files:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        assert not forbidden.search(text), f"{path.name}: DTO must not depend on Qt"


# ---- 5. page registry integrity --------------------------------------------

def test_page_registry_integrity() -> None:
    from bottom_hunter.ui_demo.pages import PAGES

    ids = [pid for pid, _t, _g in PAGES]
    assert len(ids) == len(set(ids)) == 7, "page ids must be unique"
    glyphs = [g for _i, _t, g in PAGES]
    assert len(set(glyphs)) == 7, "page glyphs must be unique"


# ---- 6. shader/qsb freeze (git-based, skip when git unavailable) ------------

def test_shader_freeze_since_phase16() -> None:
    """No .frag/.qsb changed after the PHASE 1.6 freeze commit."""
    if not (REPO / ".git").exists():
        pytest.skip("not a git checkout")
    r = subprocess.run(
        ["git", "diff", "--name-only", FROZEN_COMMIT, "HEAD",
         "--", "bottom_hunter/ui_demo"],
        capture_output=True, text=True, cwd=REPO, timeout=30,
    )
    if r.returncode != 0:
        pytest.skip("git diff failed (history may be shallow)")
    changed = [
        line for line in r.stdout.splitlines()
        if line.endswith(".frag") or line.endswith(".qsb")
    ]
    assert changed == [], f"shader/qsb files changed after freeze: {changed}"


# ---- 7. QML imports nothing but QtQuick / local UI --------------------------

def test_qml_import_boundary() -> None:
    # allowed: QtQuick family, or a local relative directory import ("x" or
    # "../x"). Disallowed: any foreign/absolute module (e.g. business).
    # allowed: QtQuick family (unquoted module), or any quoted local/relative
    # directory import. Disallowed: foreign unquoted namespaced modules.
    allowed = re.compile(r'^import\s+QtQuick(\.[A-Za-z][\w.]*)?\s*$|^import\s+"', re.M)
    for qml in UI_DEMO.rglob("*.qml"):
        for line in qml.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("import "):
                assert allowed.match(line), (
                    f"{qml.name}: unexpected QML import: {line}")


# ---- 8. import command mutation boundary -----------------------------------

def test_import_adapter_is_the_only_allowed_mutation_boundary() -> None:
    adapter = UI_DEMO / "pages" / "import_backend_adapter.py"
    assert adapter.exists(), "Import mutation adapter boundary is missing"

    mutation_calls = re.compile(
        r"\b(import_file|add_manual_asset|clear_source|refresh_linked_files|"
        r"rebuild_active_watchlist)\s*\(",
    )
    allowed = {adapter.resolve()}
    for path in UI_DEMO.rglob("*"):
        if path.suffix not in {".py", ".qml"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if mutation_calls.search(text):
            assert path.resolve() in allowed, (
                f"backend mutation outside import adapter: {path.name}"
            )


def test_import_ui_cannot_depend_on_mutation_adapter() -> None:
    files = [
        UI_DEMO / "pages" / "import_viewmodel.py",
        UI_DEMO / "pages" / "import" / "Import.qml",
    ]
    forbidden = re.compile(
        r"import_backend_adapter|RealMutationPort|BackendPreparationPort|"
        r"AccountWatchlistRepository|bottom_hunter\.src",
    )
    for path in files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        assert not forbidden.search(text), (
            f"{path.name}: UI must not depend on the mutation adapter"
        )


def test_controller_depends_only_on_command_protocols() -> None:
    controller = UI_DEMO / "pages" / "import_controller.py"
    text = controller.read_text(encoding="utf-8", errors="ignore")
    forbidden = re.compile(
        r"import_backend_adapter|RealMutationPort|AccountWatchlistRepository|"
        r"bottom_hunter\.src",
    )
    assert not forbidden.search(text)
