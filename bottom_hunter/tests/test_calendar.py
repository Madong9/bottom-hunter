from __future__ import annotations

from datetime import date

from bottom_hunter.src.config import AppConfig
from bottom_hunter.src.trading_calendar import TradingCalendarService


def test_weekend_is_not_a_us_trading_session() -> None:
    config = AppConfig.load()
    service = TradingCalendarService(config.markets)
    session, reliable = service.latest_completed_session("US", date(2024, 3, 30))
    assert reliable is True
    assert session == date(2024, 3, 28)  # Good Friday was also closed.


def test_quarter_end_window_is_only_one_point() -> None:
    config = AppConfig.load()
    service = TradingCalendarService(config.markets)
    window = service.timing_window("US", date(2024, 3, 28), config.defaults["timing"])
    assert window.quarter_end is True
    assert window.score == 1
