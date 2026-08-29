from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class TimingWindow:
    score: int
    month_end: bool
    month_start: bool
    quarter_end: bool
    quarter_start: bool
    reliable: bool

    @property
    def label(self) -> str:
        labels: list[str] = []
        if self.quarter_end:
            labels.append("季度末")
        if self.quarter_start:
            labels.append("季度初")
        if self.month_end and not self.quarter_end:
            labels.append("月末")
        if self.month_start and not self.quarter_start:
            labels.append("月初")
        return "/".join(labels) if labels else "普通交易日"


class TradingCalendarService:
    CONTINUOUS = "__continuous_24_7__"

    def __init__(self, market_configs: dict[str, dict]):
        self.market_configs = market_configs
        self._calendars: dict[str, object | None] = {}

    def _calendar(self, market: str):
        if market in self._calendars:
            return self._calendars[market]
        name = self.market_configs[market].get("calendar")
        if name == "24/7":
            self._calendars[market] = self.CONTINUOUS
            return self.CONTINUOUS
        try:
            import exchange_calendars as xcals

            calendar = xcals.get_calendar(name)
        except (ImportError, ValueError) as exc:
            LOGGER.warning("交易所日历 %s 不可用: %s", name, exc)
            calendar = None
        self._calendars[market] = calendar
        return calendar

    def latest_completed_session(
        self,
        market: str,
        requested: date | None = None,
        now: datetime | None = None,
    ) -> tuple[date, bool]:
        config = self.market_configs[market]
        calendar = self._calendar(market)
        local_now = now or datetime.now(ZoneInfo(config["timezone"]))
        if local_now.tzinfo is None:
            local_now = local_now.replace(tzinfo=ZoneInfo(config["timezone"]))
        local_now = local_now.astimezone(ZoneInfo(config["timezone"]))
        cutoff = requested or local_now.date()
        if calendar == self.CONTINUOUS:
            last_complete = local_now.date() - timedelta(days=1)
            return min(cutoff, last_complete), True
        if calendar is not None:
            start = pd.Timestamp(cutoff - timedelta(days=14))
            sessions = calendar.sessions_in_range(start, pd.Timestamp(cutoff))
            if requested is None and len(sessions):
                last = sessions[-1]
                close = calendar.session_close(last).to_pydatetime()
                if close.tzinfo is not None:
                    close = close.astimezone(ZoneInfo(config["timezone"]))
                if local_now < close:
                    sessions = sessions[:-1]
            if len(sessions):
                return sessions[-1].date(), True
        # Fail safe: never count a holiday here. Scanner intersects this cutoff with
        # actual bar dates; before local close it also removes the current date.
        if requested is None:
            close_hour, close_minute = map(int, config["close_time"].split(":"))
            if local_now.time() < time(close_hour, close_minute):
                cutoff -= timedelta(days=1)
        return cutoff, False

    def sessions_between(self, market: str, start: date, end: date) -> set[date] | None:
        """Return official sessions, or None when the calendar dependency is unavailable."""
        calendar = self._calendar(market)
        if calendar == self.CONTINUOUS:
            return {stamp.date() for stamp in pd.date_range(pd.Timestamp(start), pd.Timestamp(end), freq="D")}
        if calendar is None:
            return None
        return {stamp.date() for stamp in calendar.sessions_in_range(pd.Timestamp(start), pd.Timestamp(end))}

    def timing_window(self, market: str, session: date, settings: dict) -> TimingWindow:
        calendar = self._calendar(market)
        if calendar == self.CONTINUOUS:
            return TimingWindow(0, False, False, False, False, True)
        if calendar is None:
            return TimingWindow(0, False, False, False, False, False)
        month_start = session.replace(day=1)
        next_month = (pd.Timestamp(month_start) + pd.offsets.MonthBegin(1)).date()
        range_start = pd.Timestamp(month_start - timedelta(days=14))
        range_end = pd.Timestamp(next_month + timedelta(days=14))
        sessions = [stamp.date() for stamp in calendar.sessions_in_range(range_start, range_end)]
        current_month = [item for item in sessions if item.year == session.year and item.month == session.month]
        if session not in current_month:
            return TimingWindow(0, False, False, False, False, True)
        position = current_month.index(session)
        remaining = len(current_month) - position
        from_start = position + 1
        month_end_flag = remaining <= int(settings["month_end_sessions"])
        month_start_flag = from_start <= int(settings["month_start_sessions"])
        quarter_month = session.month in {3, 6, 9, 12}
        quarter_start_month = session.month in {1, 4, 7, 10}
        quarter_end_flag = quarter_month and remaining <= int(settings["quarter_end_sessions"])
        quarter_start_flag = quarter_start_month and from_start <= int(settings["quarter_start_sessions"])
        active = month_end_flag or month_start_flag or quarter_end_flag or quarter_start_flag
        return TimingWindow(
            int(active),
            month_end_flag,
            month_start_flag,
            quarter_end_flag,
            quarter_start_flag,
            True,
        )
