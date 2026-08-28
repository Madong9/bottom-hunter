from __future__ import annotations

import shutil
from datetime import UTC, date, datetime

import numpy as np
import pandas as pd
from bottom_hunter.src import scanner as scanner_module
from bottom_hunter.src.account_watchlist import AccountWatchlistRepository
from bottom_hunter.src.config import PROJECT_DIR
from bottom_hunter.src.data_provider import MarketDataProvider
from bottom_hunter.src.models import DataResult, Instrument
from bottom_hunter.src.scanner import run_scan


class FakeProvider(MarketDataProvider):
    name = "fake"

    def get_daily_bars(self, instrument: Instrument, start: date, end: date) -> DataResult:
        dates = pd.bdate_range("2023-10-02", "2024-03-28")
        close = 100 + np.sin(np.arange(len(dates)) / 8)
        frame = pd.DataFrame(
            {
                "open": close - 0.1,
                "high": close + 1,
                "low": close - 1,
                "close": close,
                "volume": np.full(len(dates), 1000.0),
            },
            index=dates,
        )
        return DataResult(
            instrument.symbol, frame, self.name, datetime.now(UTC), "complete"
        )


def test_offline_style_full_scan_writes_both_reports(tmp_path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    shutil.copy2(PROJECT_DIR / "config" / "thresholds.yaml", config_dir / "thresholds.yaml")
    source = tmp_path / "account_watchlist.csv"
    source.write_text(
        "symbol,name,industry\nAAPL,Apple,Consumer Electronics\n", encoding="utf-8"
    )
    AccountWatchlistRepository(
        tmp_path, state_dir=tmp_path / "watchlist_state", config_dir=config_dir
    ).import_file("tonghuashun", source, resolve_industries=False)
    output = run_scan(
        requested_date=date(2024, 3, 28),
        config_dir=config_dir,
        data_dir=tmp_path / "data",
        output_dir=tmp_path / "reports",
        state_db=tmp_path / "state" / "signals.db",
        provider=FakeProvider(),
        workers=4,
    )
    assert output.markdown_path.exists()
    assert output.json_path.exists()
    assert output.signals
    text = output.markdown_path.read_text(encoding="utf-8")
    assert "今日没有高质量反弹底部机会" in text
    assert "基本面数据不足" in text


def test_cli_returns_130_on_keyboard_interrupt(monkeypatch) -> None:
    def interrupted(**kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(scanner_module, "run_scan", interrupted)
    assert scanner_module.main([]) == 130
