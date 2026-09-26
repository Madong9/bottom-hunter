"""Dispatch bundled command-line workers without opening the Qt shell."""

from __future__ import annotations


def dispatch_internal(arguments: list[str]) -> int | None:
    """Run scanner or backtest entry points for a frozen application process."""

    if len(arguments) < 2 or arguments[1] not in {"--internal-scan", "--internal-backtest"}:
        return None
    command, command_arguments = arguments[1], arguments[2:]
    if command == "--internal-scan":
        from bottom_hunter.src.scanner import main as scanner_main

        return scanner_main(command_arguments)
    from bottom_hunter.src.backtest import main as backtest_main

    return backtest_main(command_arguments)


__all__ = ["dispatch_internal"]
