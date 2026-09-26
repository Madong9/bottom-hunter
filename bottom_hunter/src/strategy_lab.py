"""Experimental factor, supervised-learning and reinforcement-learning research.

This module only evaluates historical local bars. It never places orders and
keeps the final chronological segment out of model fitting.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd

FEATURES = ("ret5", "ret20", "vol20", "ma20_gap", "volume_ratio", "rsi14")
FACTOR_LABELS = {
    "momentum_20": "20日动量",
    "reversal_5": "5日反转",
    "low_volatility": "低波动",
    "rsi_reversal": "RSI反转",
    "volume_confirmation": "量价确认",
}


@dataclass(frozen=True)
class StrategyLabResult:
    generated_at: str
    asset_count: int
    sample_count: int
    factors: tuple[dict[str, Any], ...]
    machine_learning: dict[str, Any]
    reinforcement_learning: dict[str, Any]
    caveats: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_strategy_research(bars_by_symbol: dict[str, pd.DataFrame]) -> StrategyLabResult:
    """Rank candidate factors, fit ridge regression and evaluate a Q policy."""
    frames = {
        str(symbol): _features(frame)
        for symbol, frame in bars_by_symbol.items()
        if isinstance(frame, pd.DataFrame) and len(frame) >= 80
    }
    if not frames:
        raise ValueError("本地可用日K不足 80 根；请先完成行情扫描或缓存历史数据。")

    factors = _factor_report(frames)
    ml = _machine_learning_report(frames)
    rl = _reinforcement_learning_report(frames)
    samples = sum(int(frame["fwd5"].notna().sum()) for frame in frames.values())
    generated_at = pd.Timestamp.now(tz="UTC").isoformat(timespec="seconds")
    return StrategyLabResult(
        generated_at=generated_at,
        asset_count=len(frames),
        sample_count=samples,
        factors=tuple(factors),
        machine_learning=ml,
        reinforcement_learning=rl,
        caveats=(
            "研究只使用本地日K，按时间顺序划分训练段与测试段；结果不代表未来表现。",
            "未计入涨跌停、成交容量、税费和盘中成交顺序；模型策略仅作研究，不会下单。",
            "因子相关性和机器学习结果受自选标的数量、行情质量与样本区间影响。",
        ),
    )


def _features(raw: pd.DataFrame) -> pd.DataFrame:
    frame = raw.copy()
    frame.columns = [str(column).strip().lower().replace(" ", "_") for column in frame.columns]
    if "date" in frame.columns:
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
        frame = frame.set_index("date")
    frame.index = pd.to_datetime(frame.index, errors="coerce")
    frame = frame.loc[~frame.index.isna()].sort_index()
    frame = frame.loc[~frame.index.duplicated(keep="last")]
    if "adj_close" in frame.columns:
        frame["close"] = frame["adj_close"]
    required = {"close", "volume"}
    if not required.issubset(frame.columns):
        raise ValueError(f"日K 缺少字段：{sorted(required - set(frame.columns))}")
    close = pd.to_numeric(frame["close"], errors="coerce")
    volume = pd.to_numeric(frame["volume"], errors="coerce").fillna(0).clip(lower=0)
    result = pd.DataFrame(index=frame.index)
    result["close"] = close
    result["daily_return"] = close.pct_change()
    result["ret5"] = close.pct_change(5)
    result["ret20"] = close.pct_change(20)
    result["vol20"] = result["daily_return"].rolling(20, min_periods=15).std() * np.sqrt(252)
    ma20 = close.rolling(20, min_periods=15).mean()
    result["ma20_gap"] = close / ma20 - 1
    mean_volume = volume.rolling(20, min_periods=15).mean()
    result["volume_ratio"] = volume / mean_volume.replace(0, np.nan)
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14, min_periods=10).mean()
    loss = -delta.clip(upper=0).rolling(14, min_periods=10).mean()
    result["rsi14"] = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    result["rsi14"] = result["rsi14"].fillna(50)
    result["fwd5"] = close.shift(-5) / close - 1
    result["fwd20"] = close.shift(-20) / close - 1
    result["fwd_date"] = pd.Series(result.index, index=result.index).shift(-5)
    result["momentum_20"] = result["ret20"]
    result["reversal_5"] = -result["ret5"]
    result["low_volatility"] = -result["vol20"]
    result["rsi_reversal"] = (50 - result["rsi14"]) / 50
    result["volume_confirmation"] = result["ret5"] * np.log1p(result["volume_ratio"].clip(lower=0))
    return result.replace([np.inf, -np.inf], np.nan)


def _factor_report(frames: dict[str, pd.DataFrame]) -> list[dict[str, Any]]:
    factor_columns = tuple(FACTOR_LABELS)
    rows: list[dict[str, Any]] = []
    panel = pd.concat(
        [frame[list(factor_columns) + ["fwd5"]].assign(symbol=symbol) for symbol, frame in frames.items()]
    )
    panel["date"] = panel.index
    for factor in factor_columns:
        daily_ic = []
        for _day, group in panel[[factor, "fwd5", "symbol"]].groupby(panel["date"]):
            valid = group[[factor, "fwd5"]].dropna()
            if len(valid) >= 3 and valid[factor].nunique() > 1 and valid["fwd5"].nunique() > 1:
                value = valid[factor].rank(method="average").corr(
                    valid["fwd5"].rank(method="average")
                )
                if pd.notna(value):
                    daily_ic.append(float(value))
        mean_ic = float(np.mean(daily_ic)) if daily_ic else 0.0
        dispersion = float(np.std(daily_ic, ddof=1)) if len(daily_ic) > 1 else 0.0
        rows.append(
            {
                "factor": factor,
                "label": FACTOR_LABELS[factor],
                "mean_ic": mean_ic,
                "icir": mean_ic / dispersion if dispersion > 1e-12 else 0.0,
                "periods": len(daily_ic),
                "direction": "正相关" if mean_ic >= 0 else "负相关",
            }
        )
    return sorted(rows, key=lambda item: abs(item["mean_ic"]), reverse=True)


def _ml_samples(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    samples = []
    for symbol, frame in frames.items():
        sample = frame[list(FEATURES) + ["fwd5", "fwd_date"]].copy()
        sample["symbol"] = symbol
        sample["sample_date"] = sample.index
        samples.append(sample.dropna(subset=[*FEATURES, "fwd5", "fwd_date"]))
    if not samples:
        return pd.DataFrame()
    return pd.concat(samples, ignore_index=True).sort_values("sample_date")


def _machine_learning_report(frames: dict[str, pd.DataFrame]) -> dict[str, Any]:
    samples = _ml_samples(frames)
    dates = sorted(samples["sample_date"].unique()) if not samples.empty else []
    if len(dates) < 30:
        return {"status": "样本不足", "train_samples": 0, "test_samples": 0}
    split_date = pd.Timestamp(dates[int(len(dates) * 0.70)])
    train = samples.loc[samples["fwd_date"] < split_date]
    test = samples.loc[samples["sample_date"] >= split_date]
    if len(train) < 100 or len(test) < 30:
        return {"status": "可用样本不足", "train_samples": len(train), "test_samples": len(test)}

    x_train = train[list(FEATURES)].to_numpy(dtype=float)
    x_test = test[list(FEATURES)].to_numpy(dtype=float)
    y_train = train["fwd5"].to_numpy(dtype=float)
    y_test = test["fwd5"].to_numpy(dtype=float)
    mean = x_train.mean(axis=0)
    scale = x_train.std(axis=0)
    scale[scale < 1e-9] = 1.0
    x_train = np.column_stack([np.ones(len(x_train)), (x_train - mean) / scale])
    x_test = np.column_stack([np.ones(len(x_test)), (x_test - mean) / scale])
    penalty = np.eye(x_train.shape[1]) * 1.0
    penalty[0, 0] = 0.0
    coefficients = np.linalg.solve(x_train.T @ x_train + penalty, x_train.T @ y_train)
    predictions = x_test @ coefficients
    mae = float(np.mean(np.abs(predictions - y_test)))
    direction_accuracy = float(np.mean((predictions > 0) == (y_test > 0)))
    cutoff = float(np.quantile(predictions, 0.80))
    selected = y_test[predictions >= cutoff]
    return {
        "status": "完成",
        "model": "Ridge 回归（numpy）",
        "train_samples": len(train),
        "test_samples": len(test),
        "test_start": split_date.date().isoformat(),
        "mae_5d_return": mae,
        "direction_accuracy": direction_accuracy,
        "top_quantile_samples": len(selected),
        "top_quantile_mean_5d_return": float(np.mean(selected)) if len(selected) else 0.0,
    }


def _rl_state(frame: pd.DataFrame) -> np.ndarray:
    above_trend = (frame["ma20_gap"].fillna(0).to_numpy() >= 0).astype(int)
    momentum_up = (frame["ret5"].fillna(0).to_numpy() >= 0).astype(int)
    return above_trend * 2 + momentum_up


def _reinforcement_learning_report(frames: dict[str, pd.DataFrame]) -> dict[str, Any]:
    episodes = []
    for symbol, frame in frames.items():
        valid = frame[["daily_return", "fwd5"]].copy()
        valid["state"] = _rl_state(frame)
        valid = valid.dropna(subset=["daily_return"])
        if len(valid) >= 80:
            episodes.append((symbol, valid))
    if not episodes:
        return {"status": "样本不足", "train_days": 0, "test_days": 0}

    q_values = np.zeros((4, 2), dtype=float)
    learning_rate = 0.12
    discount = 0.90
    rng = np.random.default_rng(2026)
    train_lengths = [int(len(frame) * 0.70) for _symbol, frame in episodes]
    for _ in range(50):
        for (_symbol, frame), train_length in zip(episodes, train_lengths):
            states = frame["state"].to_numpy(dtype=int)
            returns = frame["daily_return"].to_numpy(dtype=float)
            previous_action = 0
            for index in range(max(0, train_length - 1)):
                state = int(states[index])
                if rng.random() < 0.08:
                    action = int(rng.integers(0, 2))
                else:
                    action = int(np.argmax(q_values[state]))
                reward = action * returns[index + 1] - (0.001 * abs(action - previous_action))
                next_state = int(states[index + 1])
                target = reward + discount * float(np.max(q_values[next_state]))
                q_values[state, action] += learning_rate * (target - q_values[state, action])
                previous_action = action

    policy_returns: list[float] = []
    benchmark_returns: list[float] = []
    trades = 0
    for (_symbol, frame), train_length in zip(episodes, train_lengths):
        states = frame["state"].to_numpy(dtype=int)
        returns = frame["daily_return"].to_numpy(dtype=float)
        previous_action = 0
        for index in range(train_length, len(frame)):
            action = int(np.argmax(q_values[int(states[index])]))
            daily = action * returns[index] - (0.001 * abs(action - previous_action))
            policy_returns.append(float(daily))
            benchmark_returns.append(float(returns[index]))
            trades += int(action != previous_action)
            previous_action = action
    if not policy_returns:
        return {"status": "测试区间不足", "train_days": 0, "test_days": 0}
    policy = np.asarray(policy_returns, dtype=float)
    benchmark = np.asarray(benchmark_returns, dtype=float)
    equity = np.cumprod(1 + policy)
    peak = np.maximum.accumulate(equity)
    max_drawdown = float(np.min(equity / np.maximum(peak, 1e-12) - 1))
    return {
        "status": "完成",
        "algorithm": "Q-learning（多空仅做空仓/持有）",
        "train_days": int(sum(train_lengths)),
        "test_days": len(policy),
        "test_start": min(
            frame.index[min(train_length, len(frame) - 1)].date().isoformat()
            for (_symbol, frame), train_length in zip(episodes, train_lengths)
        ),
        "strategy_return": float(equity[-1] - 1),
        "benchmark_return": float(np.prod(1 + benchmark) - 1),
        "max_drawdown": max_drawdown,
        "action_changes": trades,
        "cost_per_action": 0.001,
    }
