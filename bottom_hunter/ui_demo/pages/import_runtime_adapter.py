"""PHASE 4-D3-B — RuntimeActivityPort over an injected status provider."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class RuntimeStatusDTO:
    scanner_running: bool = False
    backtest_running: bool = False
    import_running: bool = False


class RuntimeStatusProvider(Protocol):
    def snapshot(self) -> RuntimeStatusDTO: ...


class RealRuntimeActivityPort:
    """Maps host runtime status to the Controller's activity string contract."""

    def __init__(self, provider: RuntimeStatusProvider) -> None:
        self._provider = provider

    def active_operation(self) -> str:
        status = self._provider.snapshot()
        if status.scanner_running:
            return "扫描"
        if status.backtest_running:
            return "回测"
        if status.import_running:
            return "导入"
        return ""
