from __future__ import annotations


def actual_return(*, entry_price: float, exit_price: float) -> float:
    if entry_price <= 0:
        return 0.0
    return round((exit_price - entry_price) / entry_price, 12)


def expected_return(benchmark_returns: dict[str, float], *, momentum_return: float, weights: dict[str, float]) -> float:
    total = sum(
        float(benchmark_returns.get(key, 0.0)) * float(weight)
        for key, weight in weights.items()
        if key != "momentum"
    )
    total += float(momentum_return) * float(weights.get("momentum", 0.0))
    return round(total, 12)


def abnormal_return(actual: float, expected: float) -> float:
    return round(actual - expected, 12)


def normalized_outcome(abnormal: float, *, realized_vol: float) -> float:
    denom = max(abs(realized_vol), 1e-6)
    return max(-1.0, min(round(abnormal / denom, 12), 1.0))
