"""Frozen reconstructed replay and prospective forecasting, with delayed-label calibration."""
from __future__ import annotations

import hashlib
import json
from typing import Callable

import numpy as np
import pandas as pd

from retail_outlook.metrics import direction, effect_table, score, seasonal_scale
from retail_outlook.models import Distribution, forecast_baseline, forecast_distributed_lag, validate_y
from retail_outlook.storage import Store, utc_now, write_json


def origin_timestamp(month: pd.Timestamp, day: int = 28) -> pd.Timestamp:
    return month.to_period("M").to_timestamp().replace(day=day, hour=23, minute=59, second=59).tz_localize(
        "Asia/Singapore").tz_convert("UTC")


def target_month(origin: pd.Timestamp, horizon: int) -> pd.Timestamp:
    local = origin.tz_convert("Asia/Singapore").tz_localize(None)
    return (local.to_period("M") + horizon).to_timestamp()


def forecast_steps(last_month: pd.Timestamp, target: pd.Timestamp) -> int:
    return (target.year - last_month.year) * 12 + target.month - last_month.month


def training_bands(y: pd.Series, horizons: list[int], floor: float = .1) -> dict[str, float]:
    y = validate_y(y)
    logs = np.log(y)
    return {str(h): round(max(floor, .5 * float(logs.diff(h + 1).dropna().std(ddof=1)) * 100), 4)
            for h in horizons}


def freeze_protocol(store: Store, config: dict, snapshot_id: str) -> dict:
    path = store.root / "artifacts/protocol.json"
    if path.exists():
        protocol = json.loads(path.read_text())
        if protocol["config"] != config:
            raise ValueError("Config differs from frozen protocol; create an explicitly separate experiment")
        return protocol
    frame = store.observations(snapshot_id)
    cpi = frame[frame.series_id == "cpi_cooking_oil"].set_index("period").value.sort_index()
    training = cpi.loc[config["training_start"]:config["initial_training_end"]]
    if len(training) < 60:
        raise ValueError("Initial training requires 60 monthly observations")
    end = cpi.index.max() - pd.DateOffset(months=max(config["horizons"]))
    audit_start = end - pd.DateOffset(months=35)
    protocol = {"version": 1, "frozen_at": utc_now(), "config": config, "snapshot_id": snapshot_id,
                "training_end": config["initial_training_end"],
                "training_hash": hashlib.sha256(training.to_json().encode()).hexdigest(),
                "unchanged_band_pct": training_bands(training, config["horizons"],
                                                        config["unchanged_band"]["floor_percentage_points"]),
                "band_recipe": "0.5 x initial-training SD of log changes over h+1 months x100, floor0.1pp; frozen",
                "evaluation_end": str(end.date()), "audit_start": str(audit_start.date()),
                "audit_origins": 36, "history_mode": "reconstructed",
                "model_selection": "lowest development MASE per horizon; audit never used for selection",
                "calibration": "CQR expansion in log space from matured raw OOS scores only; >=24 observations",
                "primary_effect": "paired MAE reduction and 95% circular moving-block bootstrap intervals",
                "interval_caveat": "empirical time-series calibration, no exchangeability guarantee",
                "news": "prospective unvalidated only; not a historical predictive feature"}
    write_json(path, protocol, exclusive=True)
    return protocol


def calibration_correction(prior: list[dict], origin: pd.Timestamp, model: str, horizon: int,
                           minimum: int = 24) -> tuple[float, int]:
    # Read only scores with labels available at this origin. Never reuse in-sample residuals here.
    eligible = [r for r in prior if r["model"] == model and r["horizon"] == horizon
                and pd.Timestamp(r["actual_available_at"]) <= origin
                and pd.Timestamp(r["origin"]) < origin]
    eligible = eligible[-60:]
    n = len(eligible)
    if n < minimum:
        return 0., n
    errors = [max(np.log(r["raw_q10"]) - np.log(r["actual"]),
                  np.log(r["actual"]) - np.log(r["raw_q90"])) for r in eligible]
    # Finite sample order statistic, not interpolated quantile; expansion-only correction.
    rank = min(n, int(np.ceil((n + 1) * .8)))
    return float(max(0., np.sort(errors)[rank - 1])), n


def calibrate(samples: np.ndarray, center: float, correction: float) -> np.ndarray:
    if correction <= 0:
        return samples.copy()
    z = np.log(samples) - np.log(center)
    lo, hi = np.quantile(z, [.1, .9])
    lower_scale = (abs(lo) + correction) / max(abs(lo), 1e-8)
    upper_scale = (abs(hi) + correction) / max(abs(hi), 1e-8)
    return center * np.exp(z * np.where(z < 0, lower_scale, upper_scale))


def make_distributions(panel: pd.DataFrame, origin: pd.Timestamp, config: dict) -> tuple[pd.Series, dict[str, Distribution]]:
    y = validate_y(panel.cpi_cooking_oil.dropna())
    steps = forecast_steps(y.index[-1], target_month(origin, max(config["horizons"])))
    outputs = {}
    for i, name in enumerate(config["models"]):
        seed = config["seed"] + origin.year * 100 + origin.month + i
        if name == "distributed_lag":
            outputs[name] = forecast_distributed_lag(panel, steps, config["samples"], seed, config["max_driver_lag"])
        else:
            outputs[name] = forecast_baseline(name, y, steps, config["samples"], seed)
    return y, outputs


def run_backtest(store: Store, protocol: dict, progress: Callable[[str], None] | None = None) -> dict:
    config = protocol["config"]
    snapshot = protocol["snapshot_id"]
    observations = store.observations(snapshot)
    truth = observations[observations.series_id == "cpi_cooking_oil"].set_index("period")
    rows: list[dict] = []
    months = pd.date_range(config["evaluation_start"], protocol["evaluation_end"], freq="MS")
    for number, month in enumerate(months):
        origin = origin_timestamp(month, config["origin_day"])
        panel = store.panel(origin, "reconstructed", snapshot)
        panel = panel.loc[config["training_start"]:]
        y, outputs = make_distributions(panel, origin, config)
        if len(y) < 60:
            continue
        scale = seasonal_scale(y.to_numpy())
        for model, dist in outputs.items():
            for horizon in config["horizons"]:
                target = target_month(origin, horizon)
                steps = forecast_steps(y.index[-1], target)
                raw = dist.samples[:, steps - 1]
                median = float(dist.median[steps - 1])
                correction, count = calibration_correction(rows, origin, model, horizon, config["calibration_minimum"])
                calibrated = calibrate(raw, median, correction)
                q10, q90 = np.quantile(calibrated, [.1, .9])
                value = float(truth.loc[target, "value"])
                row = {"origin": origin.isoformat(), "target_month": str(target.date()), "model": model,
                       "horizon": horizon, "effective_steps": steps, "median": median,
                       "q10": float(q10), "q90": float(q90), "raw_q10": float(np.quantile(raw, .1)),
                       "raw_q90": float(np.quantile(raw, .9)), "actual": value,
                       "actual_available_at": truth.loc[target, "assumed_available_at"].isoformat(),
                       "last_cpi_month": str(y.index[-1].date()), "last_cpi": float(y.iloc[-1]),
                       "scale": scale, "calibration_n": count, "calibration_log_expansion": correction,
                       "fallback": dist.diagnostics.get("fallback"), "history_mode": "reconstructed",
                       "scope": "audit" if month >= pd.Timestamp(protocol["audit_start"]) else "development",
                       "raw_coverage80": int(np.quantile(raw, .1) <= value <= np.quantile(raw, .9))}
                row.update(score(value, median, calibrated, scale, float(y.iloc[-1]),
                                 protocol["unchanged_band_pct"][str(horizon)]))
                rows.append(row)
        if progress and (number % 12 == 0 or number == len(months) - 1):
            progress(f"Completed {number+1}/{len(months)} reconstructed origins through {month:%Y-%m}")
    predictions = pd.DataFrame(rows)
    effects = effect_table(predictions, config["bootstrap_repetitions"], config["bootstrap_block_months"], config["seed"])
    selected = {}
    for horizon in config["horizons"]:
        dev = effects[(effects.scope == "development") & (effects.horizon == horizon)]
        selected[str(horizon)] = str(dev.sort_values(["mase", "model"]).iloc[0].model)
    return {"predictions": predictions, "effects": effects, "selected_models": selected,
            "strict_pit": {"scored_forecasts": 0, "reason": "Collection began today; future targets have not matured."}}


def current_forecast(store: Store, protocol: dict, prior: pd.DataFrame, selected: dict,
                     origin: pd.Timestamp | None = None) -> dict:
    origin = origin or pd.Timestamp.now(tz="UTC")
    config = protocol["config"]
    panel = store.panel(origin, "prospective").loc[config["training_start"]:]
    y, distributions = make_distributions(panel, origin, config)
    prior_rows = prior.to_dict("records")
    forecasts = []
    for horizon in config["horizons"]:
        model = selected[str(horizon)]
        target = target_month(origin, horizon)
        step = forecast_steps(y.index[-1], target)
        dist = distributions[model]
        median = float(dist.median[step-1])
        # Calibration is research-derived even though this forecast's inputs are observed prospectively.
        correction, n = calibration_correction(prior_rows, origin, model, horizon, config["calibration_minimum"])
        calibration_status = "matured_reconstructed_errors"
        if step != horizon + 1:
            # The saved errors have a different statistical forecast distance. Do not transfer
            # their correction silently to an off-cycle/stale-target issuance.
            correction, n = 0.0, 0
            calibration_status = "native_interval_only_effective_horizon_differs_from_backtest"
        samples = calibrate(dist.samples[:, step-1], median, correction)
        q10, q90 = np.quantile(samples, [.1, .9])
        band = protocol["unchanged_band_pct"][str(horizon)]
        changes = (samples / y.iloc[-1] - 1) * 100
        forecasts.append({"horizon": horizon, "target_month": str(target.date()), "effective_steps": step,
            "model": model, "median": median, "q10": float(q10), "q90": float(q90),
            "change_pct": float((median/y.iloc[-1]-1)*100), "lower_change_pct": float((q10/y.iloc[-1]-1)*100),
            "upper_change_pct": float((q90/y.iloc[-1]-1)*100), "unchanged_band_pct": band,
            "direction": direction((median/y.iloc[-1]-1)*100, band),
            "prob_up": float(np.mean(changes > band)), "prob_down": float(np.mean(changes < -band)),
            "prob_unchanged": float(np.mean(np.abs(changes) <= band)), "calibration_n": n,
            "confidence_score": None, "confidence_status": "provisional: no prospective outcomes yet",
            "calibration_provenance": calibration_status,
            "diagnostics": dist.diagnostics})
    return {"issued_at": origin.isoformat(), "good": "cooking_oil", "target_name": "Vegetable Oils CPI (2024=100)",
            "last_cpi_month": str(y.index[-1].date()), "last_cpi": float(y.iloc[-1]),
            "input_availability": "actual retrieval before issuance", "history_for_estimation": "current-vintage history",
            "protocol_snapshot": protocol["snapshot_id"], "forecasts": forecasts,
            "off_cycle": origin.tz_convert("Asia/Singapore").day != config["origin_day"],
            "note": "Forecasts are exploratory; probabilities are model-implied and prospective calibration is unmeasured."}
