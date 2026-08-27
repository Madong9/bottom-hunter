from __future__ import annotations

from .runtime_bootstrap import reexec_with_runtime


def main() -> int:
    reexec_with_runtime()
    from .gui_qt import main as gui_main

    return gui_main()
