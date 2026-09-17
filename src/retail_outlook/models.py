"""Origin-local models; polynomial lag constraints reduce short-sample variance."""
from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from statsmodels.tsa.stattools import adfuller, coint


@dataclass
class Distribution:
    median: np.ndarray
    samples: np.ndarray
    diagnostics: dict
    comparison_samples: np.ndarray | None = None


def validate_y(y: pd.Series) -> pd.Series:
    y = y.dropna().astype(float)
    if len(y) < 24 or not np.isfinite(y).all() or (y <= 0).any():
        raise ValueError("Need at least 24 positive finite monthly target observations")
    if not y.index.equals(pd.date_range(y.index.min(), y.index.max(), freq="MS")):
        raise ValueError("Missing or duplicate target months; refusing implicit interpolation")
    return y


def seasonal_errors(values: np.ndarray, steps: int) -> np.ndarray:
    """Genuine h-step errors from historical origins with >=24 known months.

    Seasonal naive still compares year-apart values for h<=12. Scaling those
    errors by sqrt(h/12) would unfairly change the forecast's error distribution.
    """
    origins = np.arange(23, len(values) - steps)
    if not len(origins):
        raise ValueError("Insufficient matured seasonal-naive errors at this distance")
    reference = origins + 1 + (steps - 1) % 12 - 12
    return values[origins + steps] - values[reference]


def forecast_baseline(name: str, y: pd.Series, steps: int, n_samples: int = 1500,
                      seed: int = 42) -> Distribution:
    y = validate_y(y)
    values = np.log(y.to_numpy())
    rolling = name.endswith("_rolling")
    base = name.removesuffix("_rolling")
    rng = np.random.default_rng(seed)
    diagnostic = {"model": name, "training_n": len(y), "fallback": None,
                  "uncertainty_window": 36 if rolling else "all training history",
                  "parameter_uncertainty": "fixed parameters; matured-error calibration evaluated separately"}
    if steps < 1:
        raise ValueError("Positive forecast distance required")
    def innovations(errors):
        errors = np.asarray(errors)[-36:] if rolling else np.asarray(errors)
        return errors - errors.mean()
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        try:
            if base == "seasonal_naive":
                center = np.resize(values[-12:], steps)
                errors = values[12:] - values[:-12]
                legacy = center + rng.choice(errors - np.median(errors), size=(n_samples, steps)) * np.sqrt(
                    np.ceil(np.arange(1, steps + 1) / 12))
                columns = []
                for h in range(1, steps + 1):
                    error = seasonal_errors(values, h)
                    error = error[-36:] if rolling else error
                    # Bias remains in point-forecast metrics; uncertainty is centered on that point.
                    columns.append(center[h-1] + rng.choice(error - np.median(error), n_samples))
                log_samples = np.column_stack(columns)
                diagnostic["uncertainty_method"] = "matured historical origin-specific h-step seasonal-naive errors"
            elif base == "ets":
                fit = ExponentialSmoothing(values, trend="add", damped_trend=True,
                                           seasonal=None, initialization_method="estimated").fit()
                center = np.asarray(fit.forecast(steps))
                errors = rng.choice(innovations(fit.resid), size=(steps, n_samples))
                log_samples = np.asarray(fit.simulate(steps, repetitions=n_samples, anchor="end",
                                                     random_errors=errors, random_state=seed)).T
            elif base == "arima":
                fit = ARIMA(values, order=(1, 1, 1), trend="n").fit(method_kwargs={"maxiter": 150})
                if not fit.mle_retvals.get("converged", True):
                    raise RuntimeError("ARIMA optimizer did not converge")
                pred = fit.get_forecast(steps)
                center = np.asarray(pred.predicted_mean)
                residual = np.asarray(fit.resid)[max(1, fit.loglikelihood_burn):]
                factor = np.std(residual[-36:], ddof=1) / max(np.std(residual, ddof=1), 1e-12) if rolling else 1.
                log_samples = center + rng.standard_normal((n_samples, steps)) * np.asarray(pred.se_mean) * factor
            elif base == "random_walk":
                center = np.repeat(values[-1], steps)
                shocks = rng.choice(innovations(np.diff(values)), size=(n_samples, steps))
                log_samples = center + np.cumsum(shocks, axis=1)
            else:
                raise ValueError(f"Unknown baseline: {name}")
        except (RuntimeError, np.linalg.LinAlgError, FloatingPointError) as error:
            fallback = forecast_baseline("random_walk_rolling" if rolling else "random_walk", y, steps, n_samples, seed)
            fallback.diagnostics.update(model=name, fallback="random_walk", reason=str(error))
            return fallback
    diagnostic["warnings"] = sorted({str(w.message) for w in captured})
    if log_samples.shape != (n_samples, steps) or not np.isfinite(log_samples).all():
        raise ValueError("Invalid forecast sample array")
    # Keep declared point forecast and sample median consistent.
    log_samples += center - np.median(log_samples, axis=0)
    comparison = np.exp(legacy) if base == "seasonal_naive" else np.exp(log_samples)
    if rolling:
        full = forecast_baseline(base, y, steps, n_samples, seed)
        comparison = full.comparison_samples
    return Distribution(np.exp(center), np.exp(log_samples), diagnostic, comparison)


def block_indices(n: int, size: int, repetitions: int, block: int, seed: int) -> np.ndarray:
    """Circular moving-block resamples, retaining within-block chronology."""
    if n < 1 or block < 1:
        raise ValueError("Nonempty sample and positive block required")
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, n, size=(repetitions, int(np.ceil(size / block))))
    return ((starts[..., None] + np.arange(block)) % n).reshape(repetitions, -1)[:, :size]


def driver_logs(frame: pd.DataFrame, spec: str = "sgd") -> pd.DataFrame:
    logs = np.log(frame[["palm_oil_usd", "soy_oil_usd", "usd_sgd"]])
    if spec == "sgd":
        return pd.DataFrame({"palm_sgd": logs.palm_oil_usd + logs.usd_sgd,
                             "soy_sgd": logs.soy_oil_usd + logs.usd_sgd})
    if spec == "usd_fx":
        return logs.rename(columns={"palm_oil_usd": "palm_usd", "soy_oil_usd": "soy_usd", "usd_sgd": "fx"})
    raise ValueError(f"Unknown driver specification: {spec}")


def cointegration_gate(y: pd.Series, drivers: pd.DataFrame) -> dict:
    """Train-window Engle–Granger; ECM also requires integration-order support.

    Two predeclared currency specifications: Bonferroni EG alpha=.025 each.
    These are low-power supporting diagnostics, never causal identification.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            series = pd.concat([np.log(y).rename("retail"), drivers], axis=1).dropna()
            levels = {c: float(adfuller(series[c], maxlag=3, autolag="AIC")[1]) for c in series}
            differences = {c: float(adfuller(series[c].diff().dropna(), maxlag=3, autolag="AIC")[1]) for c in series}
            p = float(coint(series.retail, series.drop(columns="retail"), maxlag=3, autolag="AIC")[1])
            supported = p < .025 and all(v >= .05 for v in levels.values()) and all(v < .05 for v in differences.values())
            return {"supported": supported, "engle_granger_p": p, "threshold": .025,
                    "level_adf_p": levels, "difference_adf_p": differences,
                    "training_end": str(series.index[-1].date()), "n": len(series)}
        except (ValueError, np.linalg.LinAlgError) as exc:
            return {"supported": False, "engle_granger_p": None, "reason": str(exc)}


def lag_basis(max_lag: int = 12) -> np.ndarray:
    """Degree-two Legendre/Almon constraint: 13 lag weights, only 3 parameters."""
    if max_lag < 2:
        raise ValueError("Polynomial lags require at least two lags")
    z = np.linspace(-1, 1, max_lag + 1)
    return np.column_stack([np.ones_like(z), z, (3*z*z - 1)/2])


def lag_design(frame: pd.DataFrame, max_lag: int = 12, spec: str = "sgd",
               asymmetric: bool = False, ecm: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    y = validate_y(frame.cpi_cooking_oil)
    training = frame.loc[y.index.min():y.index.max()]
    if training[["cpi_cooking_oil", "palm_oil_usd", "soy_oil_usd", "usd_sgd"]].isna().any().any():
        raise ValueError("Missing drivers in the training window")
    levels = driver_logs(training, spec)
    changes = levels.diff()
    changes.insert(0, "y", np.log(y).diff())
    design = pd.DataFrame({"intercept": 1., "retail_lag1": changes.y.shift(1)}, index=changes.index)
    basis = lag_basis(max_lag)
    for driver in levels:
        parts = {driver: changes[driver]} if not asymmetric else {
            driver + "_positive": changes[driver].clip(lower=0), driver + "_negative": changes[driver].clip(upper=0)}
        for part, values in parts.items():
            lags = pd.concat([values.shift(lag) for lag in range(max_lag+1)], axis=1)
            for degree in range(3):
                design[f"{part}_p{degree}"] = lags.to_numpy() @ basis[:, degree]
    gate = cointegration_gate(y, levels) if ecm else {"supported": False, "not_requested": True}
    long_run = None
    if ecm and gate["supported"]:
        long_run = np.linalg.lstsq(np.column_stack([np.ones(len(levels)), levels]), np.log(y), rcond=None)[0]
        error = np.log(y) - (long_run[0] + levels.to_numpy() @ long_run[1:])
        design["ecm_lag1"] = error.shift(1)
    joined = pd.concat([changes.y.rename("target"), design], axis=1).dropna()
    if len(joined) < max(30, design.shape[1] + 12):
        raise ValueError("Insufficient complete rows for the polynomial lag model")
    joined.attrs.update(spec=spec, asymmetric=asymmetric, max_lag=max_lag,
                        cointegration=gate, long_run=long_run, drivers=list(levels))
    return joined, changes


def fit_lag(frame: pd.DataFrame, max_lag: int = 12, spec: str = "sgd", asymmetric: bool = False,
            ecm: bool = False) -> tuple[np.ndarray, pd.DataFrame, pd.DataFrame, np.ndarray]:
    joined, changes = lag_design(frame, max_lag, spec, asymmetric, ecm)
    matrix = joined.drop(columns="target").to_numpy()
    beta = np.linalg.lstsq(matrix, joined.target.to_numpy(), rcond=None)[0]
    return beta, joined, changes, joined.target.to_numpy() - matrix @ beta


def lag_weights(beta: np.ndarray, joined: pd.DataFrame, driver: str) -> np.ndarray:
    terms = dict(zip(joined.columns[1:], beta))
    return lag_basis(joined.attrs["max_lag"]) @ np.array([terms[f"{driver}_p{k}"] for k in range(3)])


def forecast_distributed_lag(frame: pd.DataFrame, steps: int, n_samples: int = 1500,
                             seed: int = 42, max_lag: int = 12, spec: str = "sgd",
                             asymmetric: bool = False, ecm: bool = False) -> Distribution:
    y = validate_y(frame.cpi_cooking_oil)
    beta, joined, changes, residual = fit_lag(frame, max_lag, spec, asymmetric, ecm)
    drivers = joined.attrs["drivers"]
    terms = dict(zip(joined.columns[1:], beta))
    levels_history = driver_logs(frame, spec)
    innovations = changes.loc[joined.index, drivers].to_numpy()
    shocks = np.column_stack([innovations - innovations.mean(axis=0), residual - residual.mean()])
    sampled = shocks[block_indices(len(shocks), steps, n_samples, 3, seed)]
    histories = {d: np.tile(changes[d].dropna().iloc[-max_lag:].to_numpy(), (n_samples, 1)) for d in drivers}
    driver_level = {d: np.full(n_samples, levels_history.loc[y.index[-1], d]) for d in drivers}
    retail_level = np.full(n_samples, np.log(y.iloc[-1]))
    prev_change = np.full(n_samples, changes.y.dropna().iloc[-1])
    forecast = np.empty((n_samples, steps))
    for step in range(steps):
        target = y.index[-1] + pd.DateOffset(months=step + 1)
        # Lag zero is a simulated unknown or a genuinely known driver at this origin.
        before_levels = np.column_stack([driver_level[d] for d in drivers])
        windows = {}
        for j, driver in enumerate(drivers):
            known = levels_history[driver].get(target, np.nan)
            delta = known - driver_level[driver] if pd.notna(known) else sampled[:, step, j]
            windows[driver] = np.column_stack([delta, histories[driver][:, ::-1]])
            driver_level[driver] += delta
            histories[driver] = np.column_stack([histories[driver][:, 1:], delta])
        delta_y = terms["intercept"] + terms["retail_lag1"] * prev_change + sampled[:, step, -1]
        for driver, window in windows.items():
            if asymmetric:
                delta_y += window.clip(min=0) @ lag_weights(beta, joined, driver + "_positive")
                delta_y += window.clip(max=0) @ lag_weights(beta, joined, driver + "_negative")
            else:
                delta_y += window @ lag_weights(beta, joined, driver)
        if "ecm_lag1" in terms:
            lr = joined.attrs["long_run"]
            delta_y += terms["ecm_lag1"] * (retail_level - lr[0] - before_levels @ lr[1:])
        retail_level += delta_y
        forecast[:, step] = np.exp(retail_level)
        prev_change = delta_y
    if not np.isfinite(forecast).all():
        raise ValueError("Nonfinite driver forecast")
    return Distribution(np.median(forecast, axis=0), forecast,
        {"model": "distributed_lag", "spec": spec, "asymmetric": asymmetric,
         "training_n": len(joined), "fallback": None, "max_lag": max_lag,
         "constraint": "quadratic polynomial lag profile (3 parameters per driver)",
         "cointegration": joined.attrs["cointegration"], "ecm_used": "ecm_lag1" in terms,
         "driver_assumption": "joint centered innovations; known drivers used only from the supplied as-of panel",
         "coefficients": {k: float(v) for k, v in terms.items()}}, forecast.copy())


def impulse_effect(beta: np.ndarray, driver: str, months: int, shock: float, max_lag: int = 3) -> float:
    """Legacy v1 impulse reader retained for old coefficient artifacts."""
    offset = 2 if driver == "oil" else 2 + max_lag
    growth, total = 0., 0.
    for month in range(1, months+1):
        growth = beta[1]*growth + (beta[offset+month-1]*shock if month <= max_lag else 0.)
        total += growth
    return float(np.expm1(total)*100)


def polynomial_response(beta: np.ndarray, joined: pd.DataFrame, driver: str, months: int,
                         shock: float = np.log1p(.1)) -> float:
    """Cumulative log response through months 0..h-1 to a permanent level step."""
    weights = lag_weights(beta, joined, driver)
    growth, total = 0., 0.
    for month in range(months):
        growth = beta[1]*growth + (weights[month]*shock if month < len(weights) else 0.)
        total += growth
    return float(total)


def fit_pass_through(frame: pd.DataFrame, max_lag: int = 12, bootstrap: int = 1000, seed: int = 42) -> dict:
    effects, coefficients, diagnostics, asymmetry = [], [], [], []
    for spec in ("sgd", "usd_fx"):
        y = validate_y(frame.cpi_cooking_oil)
        gate = cointegration_gate(y, driver_logs(frame.loc[y.index], spec))
        beta, joined, _, residual = fit_lag(frame, max_lag, spec)
        matrix, response = joined.drop(columns="target").to_numpy(), joined.target.to_numpy()
        ids = block_indices(len(joined), len(joined), bootstrap, 12, seed)
        boot = np.array([np.linalg.lstsq(matrix[i], response[i], rcond=None)[0] for i in ids])
        diagnostics.append({"spec": spec, "cointegration": gate, "n": len(joined),
                            "residual_sd": float(np.std(residual)), "training_end": str(joined.index[-1].date()),
                            "unstable_bootstrap_fraction": float(np.mean(np.abs(boot[:, 1]) >= 1))})
        for driver in joined.attrs["drivers"]:
            weights = lag_weights(beta, joined, driver)
            boot_weights = np.array([lag_weights(b, joined, driver) for b in boot])
            for lag, weight in enumerate(weights):
                coefficients.append({"spec": spec, "driver": driver, "lag_months": lag, "estimate": float(weight),
                    "lower95": float(np.quantile(boot_weights[:, lag], .025)),
                    "upper95": float(np.quantile(boot_weights[:, lag], .975))})
            for months in (3, 6, 12):
                sims = np.expm1([polynomial_response(b, joined, driver, months) for b in boot])*100
                effects.append({"spec": spec, "driver": driver, "months": months,
                    "input_shock_pct": 10., "retail_effect_pct": float(np.expm1(polynomial_response(beta, joined, driver, months))*100),
                    "lower95": float(np.quantile(sims, .025)), "upper95": float(np.quantile(sims, .975)),
                    "cointegration_supported": gate["supported"], "engle_granger_p": gate["engle_granger_p"]})
        a_beta, a_join, _, _ = fit_lag(frame, max_lag, spec, asymmetric=True)
        ax, ay = a_join.drop(columns="target").to_numpy(), a_join.target.to_numpy()
        a_ids = block_indices(len(a_join), len(a_join), bootstrap, 12, seed)
        a_boot = np.array([np.linalg.lstsq(ax[i], ay[i], rcond=None)[0] for i in a_ids])
        for driver in a_join.attrs["drivers"]:
            def gap(b):
                return (polynomial_response(b, a_join, driver+"_positive", 12, 1.) -
                        polynomial_response(b, a_join, driver+"_negative", 12, 1.))
            values = [gap(b) for b in a_boot]
            lo, hi = np.quantile(values, [.025, .975])
            asymmetry.append({"spec": spec, "driver": driver, "months": 12,
                "positive_minus_negative_cumulative_elasticity": gap(a_beta), "lower95": float(lo), "upper95": float(hi),
                "supported": bool(lo > 0 or hi < 0), "test": "exploratory 95% block interval; no multiplicity adjustment"})
    return {"model": "quadratic polynomial distributed lags 0–12 plus retail AR(1)",
        "specifications": {"sgd": "separate palm/soy USD prices multiplied by SGD per USD; no extra FX regressor",
                           "usd_fx": "separate palm/soy USD prices and one explicit FX regressor"},
        "effects": effects, "coefficients": coefficients, "asymmetry": asymmetry, "diagnostics": diagnostics,
        "bootstrap_repetitions": bootstrap, "block_months": 12,
        "effect_timing": "permanent +10% driver level step at month 0; cumulative through month h-1",
        "interpretation": "Conditional associations; lag-shape constraints, short sample and reconstructed vintages limit inference. "
                          "Bootstrap is conditional on the fixed polynomial specification. ECM is forecast only when each training-window gate passes."}
