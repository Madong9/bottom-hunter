"""Read-only chart migration: DTO, adapter, async lifecycle and QML smoke."""

from __future__ import annotations

import json
import time
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest
from bottom_hunter.src.charting import ChartResult
from bottom_hunter.ui_demo.pages.chart_adapter import ChartReadAdapter, load_chart_assets
from bottom_hunter.ui_demo.pages.chart_contracts import ChartAssetDTO, ChartBarDTO, ChartDTO
from bottom_hunter.ui_demo.pages.chart_controller import ChartController
from bottom_hunter.ui_demo.pages.chart_viewmodel import ChartViewModel
from PySide6.QtCore import QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWidgets import QApplication

PAGES_DIR = Path(__file__).resolve().parent.parent / "ui_demo" / "pages"


def test_chart_dtos_are_frozen_transport_values() -> None:
    bar = ChartBarDTO("2026-09-01T00:00:00", 10, 12, 9, 11, 100, ma5=10.5)
    dto = ChartDTO(canonical_id="equity:US:AAPL", bars=(bar,), provider="fake")
    assert dto.as_dict()["bars"][0]["ma5"] == 10.5
    with pytest.raises(FrozenInstanceError):
        dto.provider = "changed"  # type: ignore[misc]


def test_chart_asset_snapshot_adapter_is_read_only(tmp_path: Path) -> None:
    path = tmp_path / "watchlist_summary.json"
    path.write_text(
        json.dumps(
            {
                "assets": [
                    {
                        "canonical_id": "crypto:BTC",
                        "symbol": "BTC-USDT",
                        "name": "Bitcoin",
                        "market": "CRYPTO",
                        "category": "crypto",
                        "source_symbols": {"okx": "BTC-USDT"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    before = path.read_bytes()
    assets = load_chart_assets(path)
    assert assets[0].canonical_id == "crypto:BTC"
    assert assets[0].source_symbols == (("okx", "BTC-USDT"),)
    assert path.read_bytes() == before
    assert list(tmp_path.iterdir()) == [path]


def test_chart_adapter_maps_backend_result_without_exposing_dataframe() -> None:
    asset = ChartAssetDTO("equity:US:AAPL", "AAPL", "Apple", "US", "global_equity")
    index = pd.date_range("2026-01-01", periods=65, freq="D")
    frame = pd.DataFrame(
        {
            "open": range(100, 165),
            "high": range(102, 167),
            "low": range(98, 163),
            "close": range(101, 166),
            "volume": [1000] * 65,
        },
        index=index,
    )

    class Service:
        def fetch(self, mapping, timeframe, limit):
            assert mapping["symbol"] == "AAPL"
            assert (timeframe, limit) == ("1d", 60)
            return ChartResult(
                canonical_id=asset.canonical_id,
                symbol=asset.symbol,
                name=asset.name,
                timeframe=timeframe,
                bars=frame.tail(limit),
                provider="fake-feed",
                updated_at=datetime(2026, 9, 5, tzinfo=UTC),
                note="read-only",
            )

    dto = ChartReadAdapter(service=Service(), assets=(asset,)).fetch(asset.canonical_id, "1d", 60)
    assert len(dto.bars) == 60
    assert dto.provider == "fake-feed"
    assert dto.bars[-1].ma20 is not None
    assert not hasattr(dto, "dataframe")


def test_chart_viewmodel_lifecycle_and_selection() -> None:
    assets = (
        ChartAssetDTO("equity:US:AAPL", "AAPL", "Apple", "US", "global_equity"),
        ChartAssetDTO("crypto:BTC", "BTC-USDT", "Bitcoin", "CRYPTO", "crypto"),
    )
    vm = ChartViewModel(assets)
    requests = []
    vm.loadRequested.connect(lambda *args: requests.append(args))
    assert vm.lifecycle == "INIT"
    vm.activate()
    assert requests[-1] == ("equity:US:AAPL", "1d", 160)
    vm.markLoading("equity:US:AAPL", "1d")
    assert vm.lifecycle == "LOADING"
    vm.apply(
        ChartDTO(
            canonical_id="equity:US:AAPL",
            timeframe="1d",
            bars=(ChartBarDTO("2026-09-01", 10, 12, 9, 11, 100),),
        )
    )
    assert vm.lifecycle == "READY" and vm.barCount == 1
    vm.selectAsset(1)
    assert vm.selectedMarket == "CRYPTO"
    assert requests[-1][0] == "crypto:BTC"
    vm.applyError("network")
    assert vm.lifecycle == "ERROR" and vm.error == "network"


def test_chart_controller_runs_port_off_ui_thread(monkeypatch) -> None:
    asset = ChartAssetDTO("equity:US:AAPL", "AAPL", "Apple", "US", "global_equity")

    class Port:
        assets = (asset,)

        def fetch(self, canonical_id, timeframe, limit):
            return ChartDTO(canonical_id=canonical_id, timeframe=timeframe, provider=f"fake-{limit}")

    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    controller = ChartController(Port())
    received = []
    controller.loadSucceeded.connect(lambda dto: received.append(dto))
    controller.request(asset.canonical_id, "1d", 80)
    deadline = time.monotonic() + 3
    while (not received or controller._thread is not None) and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.002)
    app.processEvents()
    assert received and received[0].provider == "fake-80"
    app.processEvents()


def test_chart_qml_loads_empty_state_without_backend(monkeypatch) -> None:
    monkeypatch.setenv("QSG_RHI_BACKEND", "software")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    vm = ChartViewModel()
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("chartVm", vm)
    engine.load(QUrl.fromLocalFile(str(PAGES_DIR / "chart" / "Chart.qml")))
    roots = engine.rootObjects()
    try:
        assert roots and roots[0].objectName() == "chartPage"
        assert vm.lifecycle == "EMPTY"
    finally:
        for root in roots:
            root.deleteLater()
        engine.deleteLater()
        app.processEvents()


def test_chart_qml_supports_indicators_drawing_and_ctrl_wheel() -> None:
    source = (PAGES_DIR / "chart" / "Chart.qml").read_text(encoding="utf-8")
    assert all(name in source for name in ("MA", "BOLL", "MACD", "RSI", "KDJ"))
    assert "Qt.ControlModifier" in source
    assert "trend" in source and "horizontal" in source
    assert "Timer {" in source
