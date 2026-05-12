"""Observed Big O growth fitting."""

from __future__ import annotations

import math
import statistics
from collections.abc import Callable

from algoscope.models import ComplexityScore, Measurement


class ComplexityEstimator:
    """Fit measured runtimes to simple Big O feature models."""

    def __init__(self) -> None:
        self._models: dict[str, Callable[[int], float]] = {
            "O(1)": lambda n: 1.0,
            "O(log n)": lambda n: math.log(max(n, 2)),
            "O(n)": lambda n: float(n),
            "O(n log n)": lambda n: n * math.log(max(n, 2)),
            "O(n^2)": lambda n: float(n * n),
        }

    def estimate(self, rows: list[Measurement]) -> tuple[str, list[ComplexityScore]]:
        sizes = [row.size for row in rows]
        times = [row.wall_ms for row in rows]
        scores: list[ComplexityScore] = []

        for name, feature_fn in self._models.items():
            x_values = [feature_fn(n) for n in sizes]
            a, b = self._linear_fit(x_values, times)
            predictions = [a * x + b for x in x_values]
            rmse = math.sqrt(sum((y - yhat) ** 2 for y, yhat in zip(times, predictions)) / len(times))
            scale = statistics.mean(times) or 1.0
            scores.append(
                ComplexityScore(
                    name=name,
                    a=a,
                    b=b,
                    rmse=rmse,
                    normalized_rmse=rmse / scale,
                )
            )

        scores.sort(key=lambda score: score.normalized_rmse)
        return scores[0].name, scores

    @staticmethod
    def _linear_fit(x_values: list[float], y_values: list[float]) -> tuple[float, float]:
        x_mean = statistics.mean(x_values)
        y_mean = statistics.mean(y_values)
        denom = sum((x - x_mean) ** 2 for x in x_values)
        if denom == 0:
            return 0.0, y_mean
        a = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, y_values)) / denom
        b = y_mean - a * x_mean
        return a, b

