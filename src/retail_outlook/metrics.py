"""Forecast metrics and paired moving-block effect intervals."""
from __future__ import annotations

import numpy as np
import pandas as pd

from retail_outlook.models import block_indices


def seasonal_scale(y: np.ndarray) -> float:
    y = np.asarray(y, dtype=float)
    if len(y) <= 12:
        return float("nan")
    scale = float(np.mean(np.abs(y[12:] - y[:-12])))
    return scale if scale > 0 else float("nan")


def pinball(actual: float, prediction: float, quantile: float) -> float:
    delta = actual - prediction
    return float(max(quantile * delta, (quantile - 1) * delta))


def crps(actual: float, samples: np.ndarray) -> float:
    ordered = np.sort(np.asarray(samples, dtype=float))
    n = len(ordered)
    return float(np.mean(np.abs(ordered - actual)) - np.sum((2 * np.arange(1, n + 1) - n - 1) * ordered) / n**2)


def direction(change_pct: float, band_pct: float) -> str:
    return "up" if change_pct > band_pct else "down" if change_pct < -band_pct else "unchanged"


def score(actual: float, median: float, samples: np.ndarray, scale: float,
          last: float, band_pct: float) -> dict:
    low, high = np.quantile(samples, [.1, .9])
    error = abs(actual - median)
    width = high - low
    return {"absolute_error": float(error), "mase": float(error / scale) if scale > 0 else None,
            "mape": float(100 * error / abs(actual)) if actual else None,
            "smape": float(200 * error / (abs(actual) + abs(median))) if actual or median else None,
            "pinball": float(np.mean([pinball(actual, float(np.quantile(samples, q)), q) for q in (.1, .5, .9)])),
            "crps": crps(actual, samples), "coverage80": int(low <= actual <= high),
            "width80": float(width), "interval_score80": float(width + 10 * max(low-actual, 0) + 10 * max(actual-high, 0)),
            "direction_correct": int(direction((actual / last - 1) * 100, band_pct) ==
                                     direction((median / last - 1) * 100, band_pct))}


def effect_table(predictions: pd.DataFrame, repetitions: int = 1000, block: int = 12,
                 seed: int = 42) -> pd.DataFrame:
    rows = []
    for (scope, horizon), group in predictions.groupby(["scope", "horizon"]):
        baseline = group[group.model == "seasonal_naive"].set_index("origin")
        for model, candidate in group.groupby("model"):
            pair = candidate.set_index("origin").join(baseline[["mase", "absolute_error"]],
                                                     how="inner", rsuffix="_baseline").sort_index()
            n = len(pair)
            if not n:
                continue
            ids = block_indices(n, n, repetitions, min(block, n), seed + int(horizon))
            ae = pair.absolute_error.to_numpy()
            ba = pair.absolute_error_baseline.to_numpy()
            cm = pair.mase.to_numpy(dtype=float)
            bm = pair.mase_baseline.to_numpy(dtype=float)
            difference = ba[ids].mean(axis=1) - ae[ids].mean(axis=1)
            denom = bm[ids].mean(axis=1)
            skill_boot = 100 * (1 - cm[ids].mean(axis=1) / np.where(denom > 0, denom, np.nan))
            row = {"scope": scope, "horizon": int(horizon), "model": model, "n": n,
                   "mae_reduction_cpi_points": float(np.mean(ba - ae)),
                   "mae_reduction_lower95": float(np.quantile(difference, .025)),
                   "mae_reduction_upper95": float(np.quantile(difference, .975)),
                   "mase_skill_pct": float(100 * (1 - np.mean(cm) / np.mean(bm))) if np.mean(bm) > 0 else None,
                   "skill_lower95": float(np.nanquantile(skill_boot, .025)),
                   "skill_upper95": float(np.nanquantile(skill_boot, .975)),
                   "fallback_count": int(pair.fallback.notna().sum()),
                   "calibrated_n": int((pair.calibration_n >= 24).sum()),
                   "coverage80_lower95": float(np.quantile(pair.coverage80.to_numpy()[ids].mean(axis=1), .025)),
                   "coverage80_upper95": float(np.quantile(pair.coverage80.to_numpy()[ids].mean(axis=1), .975))}
            for metric in ("mase", "mape", "smape", "pinball", "crps", "coverage80", "width80",
                           "interval_score80", "direction_correct", "raw_coverage80"):
                row[metric] = float(pair[metric].mean())
            rows.append(row)
    return pd.DataFrame(rows)
