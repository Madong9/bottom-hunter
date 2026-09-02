"""PHASE 4-D5 — asynchronous Import UI command-flow tests."""

from __future__ import annotations

import os
import time
from pathlib import Path
from threading import Event

from bottom_hunter.src.import_lock import ImportProcessLock
from bottom_hunter.ui_demo.pages.import_backend_adapter import build_production_import_flow
from bottom_hunter.ui_demo.pages.import_contracts import (
    FileFingerprintDTO,
    ImportCommandDTO,
    ImportErrorDTO,
    ImportPreviewDTO,
    ImportResultDTO,
)
from bottom_hunter.ui_demo.pages.import_controller import (
    ImportCommandGate,
    ImportController,
    StagedImportDTO,
)
from bottom_hunter.ui_demo.pages.import_runtime_adapter import RealRuntimeActivityPort, RuntimeStatusDTO
from bottom_hunter.ui_demo.pages.import_viewmodel import ImportViewModel
from PySide6.QtCore import QCoreApplication, QObject, QTimer, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

PAGES_DIR = Path(__file__).resolve().parent.parent / "ui_demo" / "pages"
FINGERPRINT = FileFingerprintDTO(size=42, mtime_ns=99, sha256="preview-sha")


class IdleRuntime:
    def active_operation(self) -> str:
        return ""


class IdleRuntimeProvider:
    def snapshot(self) -> RuntimeStatusDTO:
        return RuntimeStatusDTO()


class MemoryWorkspace:
    def __init__(self) -> None:
        self.prepared = False
        self.discarded = False
        self.committed = False
        self.released_for_review = False
        self.reacquired_for_commit = False

    def prepare(self, _command: ImportCommandDTO) -> None:
        self.prepared = True

    def stage(self, _staged: StagedImportDTO) -> None:
        pass

    def verify(self, _staged: StagedImportDTO) -> None:
        pass

    def release_for_review(self) -> None:
        self.released_for_review = True

    def reacquire_for_commit(self) -> None:
        self.reacquired_for_commit = True

    def commit(self, _staged: StagedImportDTO) -> None:
        self.committed = True

    def rollback(self) -> None:
        pass

    def discard(self) -> None:
        self.discarded = True


class MemoryMutation:
    def __init__(
        self,
        staged: StagedImportDTO | None = None,
        *,
        entered: Event | None = None,
        release: Event | None = None,
        delay: float = 0,
    ) -> None:
        self.staged = staged or StagedImportDTO(imported_count=1, merged_count=1)
        self.entered = entered
        self.release = release
        self.delay = delay

    def current_fingerprint(self, _file_path: str) -> FileFingerprintDTO:
        return FINGERPRINT

    def stage(self, _command: ImportCommandDTO, workspace: MemoryWorkspace) -> StagedImportDTO:
        if self.entered is not None:
            self.entered.set()
        if self.release is not None:
            self.release.wait(timeout=2)
        if self.delay:
            time.sleep(self.delay)
        workspace.stage(self.staged)
        return self.staged

    def verify(self, staged: StagedImportDTO, workspace: MemoryWorkspace) -> None:
        workspace.verify(staged)


def _app() -> QGuiApplication:
    os.environ.setdefault("QSG_RHI_BACKEND", "software")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    existing = QCoreApplication.instance()
    if existing is not None:
        assert isinstance(existing, QGuiApplication)
        return existing
    return QGuiApplication([])


def _wait_until(predicate, timeout: float = 4) -> None:
    app = _app()
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.002)
    app.processEvents()
    assert predicate(), "timed out waiting for Qt async flow"


def _command(command_id: str = "cmd-ui") -> ImportCommandDTO:
    return ImportCommandDTO(
        command_id=command_id,
        preview_id=f"preview-{command_id}",
        source="tonghuashun",
        file_path="/virtual/watchlist.csv",
        file_fingerprint=FINGERPRINT,
        requested_at="2026-09-02T00:00:00+00:00",
    )


def _controller(mutation: MemoryMutation, workspace: MemoryWorkspace | None = None) -> ImportController:
    workspace = workspace or MemoryWorkspace()
    return ImportController(
        mutation,
        lambda: workspace,
        IdleRuntime(),
        ImportCommandGate(),
    )


def test_viewmodel_emits_intents_and_maps_result_states(tmp_path: Path) -> None:
    selected = tmp_path / "watchlist.csv"
    selected.write_text("symbol,name,industry\n600519,贵州茅台,食品饮料\n", encoding="utf-8")
    vm = ImportViewModel()
    imports: list[tuple[str, str]] = []
    cancellations: list[bool] = []
    partials: list[bool] = []
    retries: list[bool] = []
    vm.importRequested.connect(lambda path, source, _fingerprint: imports.append((path, source)))
    vm.cancelRequested.connect(lambda: cancellations.append(True))
    vm.partialAccepted.connect(lambda: partials.append(True))
    vm.retryRequested.connect(lambda: retries.append(True))

    vm.requestPreview(str(selected), "tonghuashun")
    vm.confirmImport()
    assert imports == [(str(selected), "tonghuashun")]
    assert vm.lifecycle == "IMPORTING"

    partial = ImportResultDTO(
        command_id="cmd-partial",
        source="tonghuashun",
        filename=selected.name,
        status="PARTIAL_REVIEW",
        imported_count=1,
        unresolved_industry_count=1,
    )
    vm.applyResult(partial)
    assert vm.lifecycle == "PARTIAL_REVIEW"
    assert vm.result["unresolvedIndustryCount"] == 1
    vm.cancelImport()
    vm.acceptPartial()
    assert cancellations == [True]
    assert partials == [True]

    vm.applyResult(
        ImportResultDTO(
            command_id="cmd-failed",
            source="tonghuashun",
            filename=selected.name,
            status="FAILED",
            error=ImportErrorDTO("TEST", "STAGING", "测试失败", True),
        )
    )
    vm.retryImport()
    assert vm.lifecycle == "IMPORTING"
    assert retries == [True]


def test_controller_async_does_not_block_qt_event_loop() -> None:
    _app()
    controller = _controller(MemoryMutation(delay=0.12))
    completed: list[ImportResultDTO | None] = []
    timer_fired: list[bool] = []
    controller.asyncFinished.connect(completed.append)

    started = time.monotonic()
    assert controller.submitAsync(_command()) is True
    returned_in = time.monotonic() - started
    QTimer.singleShot(10, lambda: timer_fired.append(True))

    _wait_until(lambda: bool(timer_fired) and bool(completed) and not controller.asyncRunning)
    assert returned_in < 0.05
    assert completed[0] is not None and completed[0].status == "SUCCESS"
    assert controller.progress == 100


def test_async_cancel_discards_staging_workspace() -> None:
    _app()
    entered = Event()
    release = Event()
    workspace = MemoryWorkspace()
    controller = _controller(MemoryMutation(entered=entered, release=release), workspace)
    completed: list[ImportResultDTO | None] = []
    controller.asyncFinished.connect(completed.append)

    assert controller.submitAsync(_command("cmd-cancel")) is True
    _wait_until(entered.is_set)
    assert controller.cancelActive() is True
    release.set()
    _wait_until(lambda: bool(completed) and not controller.asyncRunning)

    assert completed[0] is not None and completed[0].status == "CANCELLED"
    assert workspace.discarded is True
    assert workspace.committed is False


def test_partial_review_releases_then_reacquires_workspace_lock() -> None:
    _app()
    staged = StagedImportDTO(imported_count=2, unresolved_industry_count=1)
    workspace = MemoryWorkspace()
    controller = _controller(MemoryMutation(staged), workspace)
    completed: list[ImportResultDTO | None] = []
    accept_requests: list[bool] = []
    controller.asyncFinished.connect(completed.append)

    def accept_as_soon_as_result_arrives(result: ImportResultDTO) -> None:
        if result.status == "PARTIAL_REVIEW":
            accept_requests.append(controller.acceptPartialAsync())

    controller.resultReady.connect(accept_as_soon_as_result_arrives)

    assert controller.submitAsync(_command("cmd-partial")) is True
    _wait_until(lambda: len(completed) == 2 and not controller.asyncRunning)
    assert completed[0] is not None and completed[0].status == "PARTIAL_REVIEW"
    assert workspace.released_for_review is True
    assert accept_requests == [True]
    assert workspace.reacquired_for_commit is True
    assert completed[1] is not None and completed[1].status == "SUCCESS"


def test_worker_boundary_converts_unexpected_exception_to_dto(monkeypatch) -> None:
    _app()
    controller = _controller(MemoryMutation())
    results: list[ImportResultDTO] = []
    controller.resultReady.connect(results.append)

    def fail(_command: ImportCommandDTO) -> ImportResultDTO:
        raise RuntimeError("private backend detail")

    monkeypatch.setattr(controller, "submit", fail)
    assert controller.submitAsync(_command("cmd-unexpected")) is True
    _wait_until(lambda: bool(results) and not controller.asyncRunning)

    assert results[0].status == "FAILED"
    assert results[0].error is not None
    assert results[0].error.code == "UNEXPECTED_ERROR"
    assert "private backend detail" not in results[0].error.message


def test_production_partial_review_does_not_hold_process_lock(tmp_path: Path) -> None:
    _app()
    project = tmp_path / "project"
    selected = tmp_path / "watchlist.csv"
    selected.write_text(
        "symbol,name,industry\n600519,贵州茅台,食品饮料\n,坏行,\n",
        encoding="utf-8",
    )
    runtime = RealRuntimeActivityPort(IdleRuntimeProvider())
    flow = build_production_import_flow(
        runtime,
        str(project),
        state_dir=str(project / "state"),
        config_dir=str(project / "config"),
    )
    vm = flow.view_model
    controller = flow.controller

    vm.requestPreview(str(selected), "tonghuashun")
    vm.confirmImport()
    _wait_until(lambda: vm.lifecycle == "PARTIAL_REVIEW" and not controller.asyncRunning)
    lock_path = project / "state" / ".import.lock"
    assert not lock_path.exists()

    competing = ImportProcessLock(project / "state", "test-competing-command")
    competing.acquire()
    competing.release()
    vm.acceptPartial()
    _wait_until(lambda: vm.lifecycle == "SUCCESS" and not controller.asyncRunning)

    assert vm.result["committed"] is True
    assert not lock_path.exists()


def test_file_changed_after_preview_is_rejected_before_staging(tmp_path: Path) -> None:
    _app()
    project = tmp_path / "project"
    selected = tmp_path / "watchlist.csv"
    selected.write_text(
        "symbol,name,industry\n600519,贵州茅台,食品饮料\n",
        encoding="utf-8",
    )
    flow = build_production_import_flow(
        RealRuntimeActivityPort(IdleRuntimeProvider()),
        str(project),
        state_dir=str(project / "state"),
        config_dir=str(project / "config"),
    )
    results: list[ImportResultDTO] = []
    flow.controller.resultReady.connect(results.append)

    flow.view_model.requestPreview(str(selected), "tonghuashun")
    selected.write_text(
        "symbol,name,industry\nAAPL,Apple,Technology Hardware\n",
        encoding="utf-8",
    )
    flow.view_model.confirmImport()
    _wait_until(lambda: bool(results) and not flow.controller.asyncRunning)

    assert results[0].status == "FAILED"
    assert results[0].error is not None and results[0].error.code == "FILE_CHANGED"
    assert not (project / "state" / ".import.lock").exists()
    assert not (project / "state" / "watchlists" / "tonghuashun.json").exists()


def test_import_qml_exposes_command_controls() -> None:
    app = _app()
    vm = ImportViewModel()
    vm.apply(ImportPreviewDTO(filename="watchlist.csv", format="CSV", detected_count=1, valid_count=1))
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("importVm", vm)
    engine.load(QUrl.fromLocalFile(str(PAGES_DIR / "import" / "Import.qml")))
    roots = engine.rootObjects()
    try:
        assert roots
        confirm = roots[0].findChild(QObject, "confirmImportButton")
        assert confirm is not None and confirm.property("visible") is True

        vm.applyResult(
            ImportResultDTO(
                command_id="cmd-qml",
                source="tonghuashun",
                filename="watchlist.csv",
                status="PARTIAL_REVIEW",
                unresolved_industry_count=2,
            )
        )
        app.processEvents()
        accept = roots[0].findChild(QObject, "acceptPartialButton")
        cancel = roots[0].findChild(QObject, "cancelImportButton")
        assert accept is not None and accept.property("visible") is True
        assert cancel is not None and cancel.property("visible") is True
    finally:
        for root in roots:
            root.deleteLater()
        engine.deleteLater()
        app.processEvents()


def test_import_ui_architecture_keeps_threads_and_backend_out_of_viewmodel() -> None:
    viewmodel = (PAGES_DIR / "import_viewmodel.py").read_text(encoding="utf-8")
    controller = (PAGES_DIR / "import_controller.py").read_text(encoding="utf-8")
    qml = (PAGES_DIR / "import" / "Import.qml").read_text(encoding="utf-8")

    assert "QThread" not in viewmodel
    assert "QThread" in controller
    for text in (viewmodel, qml):
        assert "AccountWatchlistRepository" not in text
        assert "bottom_hunter.src" not in text
        assert "import_backend_adapter" not in text
