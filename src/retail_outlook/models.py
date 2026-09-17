"""Fixed, parsimonious models. All estimation receives only the origin's information set."""
from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.holtwinters import ExponentialSmoothing


@dataclass
class Distribution:
    median: np.ndarray
    samples: np.ndarray  # sample, future month
    diagnostics: dict


def validate_y(y: pd.Series) -> pd.Series:
    y = y.dropna().astype(float)
    if len(y) < 24 or not np.isfinite(y).all() or (y <= 0).any():
        raise ValueError("Need at least 24 positive finite monthly target observations")
    expected = pd.date_range(y.index.min(), y.index.max(), freq="MS")
    if not y.index.equals(expected):
        raise ValueError("Missing or duplicate target months; refusing implicit interpolation")
    return y


def forecast_baseline(name: str, y: pd.Series, steps: int, n_samples: int = 1500,
                      seed: int = 42) -> Distribution:
    y = validate_y(y)
    values = np.log(y.to_numpy())
    rng = np.random.default_rng(seed)
    diagnostic: dict = {"model": name, "training_n": len(y), "fallback": None,
                        "parameter_uncertainty": "not included; matured-error calibration assessed separately"}
    if steps < 1:
        raise ValueError("Positive forecast distance required")
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        try:
            if name == "seasonal_naive":
                center = np.resize(values[-12:], steps)
                error = values[12:] - values[:-12]
                error = error - np.median(error)
                shocks = rng.choice(error, size=(n_samples, steps), replace=True)
                log_samples = center + shocks * np.sqrt(np.ceil(np.arange(1, steps + 1) / 12))
                diagnostic["uncertainty_method"] = "centered historical seasonal errors, marginal bootstrap"
            elif name == "ets":
                fit = ExponentialSmoothing(values, trend="add", damped_trend=True,
                                           seasonal=None, initialization_method="estimated").fit()
                center = np.asarray(fit.forecast(steps))
                # statsmodels returns time x repetitions for multiple simulations.
                innovations = np.asarray(fit.resid) - np.mean(fit.resid)
                # Explicit innovations avoid statsmodels' bootstrap path using global RNG state.
                random_errors = rng.choice(innovations, size=(steps, n_samples))
                log_samples = np.asarray(fit.simulate(steps, repetitions=n_samples, anchor="end",
                                                     random_errors=random_errors, random_state=seed)).T
                diagnostic["uncertainty_method"] = "ETS innovation bootstrap, parameters fixed"
            elif name == "arima":
                fit = ARIMA(values, order=(1, 1, 1), trend="n").fit(method_kwargs={"maxiter": 150})
                if not fit.mle_retvals.get("converged", True):
                    raise RuntimeError("ARIMA optimizer did not converge")
                pred = fit.get_forecast(steps)
                center = np.asarray(pred.predicted_mean)
                log_samples = center + rng.standard_normal((n_samples, steps)) * np.asarray(pred.se_mean)
                diagnostic["uncertainty_method"] = "ARIMA Gaussian marginal predictive variance"
            elif name == "random_walk":
                center = np.repeat(values[-1], steps)
                shocks = rng.choice(np.diff(values) - np.mean(np.diff(values)), size=(n_samples, steps))
                log_samples = center + np.cumsum(shocks, axis=1)
                diagnostic["uncertainty_method"] = "centered innovation bootstrap"
            else:
                raise ValueError(f"Unknown baseline: {name}")
        except (RuntimeError, np.linalg.LinAlgError, FloatingPointError) as error:
            fallback = forecast_baseline("random_walk", y, steps, n_samples, seed)
            fallback.diagnostics.update({"model": name, "fallback": "random_walk", "reason": str(error)})
            return fallback
    diagnostic["warnings"] = sorted({str(w.message) for w in captured})
    if log_samples.shape != (n_samples, steps) or not np.isfinite(log_samples).all():
        raise ValueError("Invalid forecast sample array")
    return Distribution(np.exp(center), np.exp(log_samples), diagnostic)


def block_indices(n: int, size: int, repetitions: int, block: int, seed: int) -> np.ndarray:
    """Circular moving-block resamples, retaining within-block chronology."""
    if n < 1 or block < 1:
        raise ValueError("Nonempty sample and positive block required")
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, n, size=(repetitions, int(np.ceil(size / block))))
    return ((starts[..., None] + np.arange(block)) % n).reshape(repetitions, -1)[:, :size]


def lag_design(frame: pd.DataFrame, max_lag: int = 3) -> tuple[pd.DataFrame, pd.DataFrame]:
    y = validate_y(frame["cpi_cooking_oil"])
    training = frame.loc[y.index.min():y.index.max()].copy()
    needed = ["cpi_cooking_oil", "palm_oil_usd", "soy_oil_usd", "usd_sgd"]
    if training[needed].isna().any().any():
        raise ValueError("Missing drivers in the training window")
    logs = np.log(training[needed])
    changes = pd.DataFrame({"y": logs.cpi_cooking_oil.diff(),
                            "oil": (0.5 * (logs.palm_oil_usd + logs.soy_oil_usd)).diff(),
                            "fx": logs.usd_sgd.diff()})
    design = pd.DataFrame({"intercept": 1.0, "retail_lag1": changes.y.shift(1)}, index=changes.index)
    for driver in ("oil", "fx"):
        for lag in range(1, max_lag + 1):
            design[f"{driver}_lag{lag}"] = changes[driver].shift(lag)
    joined = pd.concat([changes.y.rename("target"), design], axis=1).dropna()
    if len(joined) < 36:
        raise ValueError("Insufficient complete rows for the lag model")
    return joined, changes


def fit_lag(frame: pd.DataFrame, max_lag: int = 3) -> tuple[np.ndarray, pd.DataFrame, pd.DataFrame, np.ndarray]:
    joined, changes = lag_design(frame, max_lag)
    matrix = joined.drop(columns="target").to_numpy()
    beta, _, rank, _ = np.linalg.lstsq(matrix, joined.target.to_numpy(), rcond=None)
    if rank < matrix.shape[1]:
        raise ValueError("Distributed-lag design is rank deficient")
    residuals = joined.target.to_numpy() - matrix @ beta
    return beta, joined, changes, residuals


def forecast_distributed_lag(frame: pd.DataFrame, steps: int, n_samples: int = 1500,
                             seed: int = 42, max_lag: int = 3) -> Distribution:
    y = validate_y(frame.cpi_cooking_oil)
    beta, joined, changes, residual = fit_lag(frame, max_lag)
    # Draw jointly with regression residuals; center future driver innovations on persistence.
    shocks = changes.loc[joined.index, ["oil", "fx"]].to_numpy()
    shocks = np.column_stack([shocks - shocks.mean(axis=0), residual - residual.mean()])
    samples = shocks[block_indices(len(shocks), steps, n_samples, 3, seed)]
    oil_lags = np.tile(changes.oil.iloc[-max_lag:].to_numpy(), (n_samples, 1))
    fx_lags = np.tile(changes.fx.iloc[-max_lag:].to_numpy(), (n_samples, 1))
    prev_change = np.full(n_samples, changes.y.iloc[-1])
    levels = np.full(n_samples, np.log(y.iloc[-1]))
    forecast = np.empty((n_samples, steps))
    history_oil = 0.5 * np.log(frame.palm_oil_usd * frame.soy_oil_usd)
    history_fx = np.log(frame.usd_sgd)
    last_oil = np.full(n_samples, history_oil.loc[y.index[-1]])
    last_fx = np.full(n_samples, history_fx.loc[y.index[-1]])
    for step in range(steps):
        target = y.index[-1] + pd.DateOffset(months=step + 1)
        features = np.column_stack([np.ones(n_samples), prev_change,
                                    oil_lags[:, ::-1], fx_lags[:, ::-1]])
        delta = features @ beta + samples[:, step, 2]
        levels = levels + delta
        forecast[:, step] = np.exp(levels)
        # Some drivers may already be observed beyond the last released CPI.
        known_oil = history_oil.get(target, np.nan)
        known_fx = history_fx.get(target, np.nan)
        doil = known_oil - last_oil if pd.notna(known_oil) else samples[:, step, 0]
        dfx = known_fx - last_fx if pd.notna(known_fx) else samples[:, step, 1]
        last_oil += doil
        last_fx += dfx
        oil_lags = np.column_stack([oil_lags[:, 1:], doil])
        fx_lags = np.column_stack([fx_lags[:, 1:], dfx])
        prev_change = delta
    diagnostic = {"model": "distributed_lag", "training_n": len(joined), "fallback": None,
                  "driver_assumption": "unknown log-driver changes centered at zero (persistence), joint block bootstrap",
                  "parameter_uncertainty": "not included in forecast; coefficient block intervals reported separately",
                  "coefficients": dict(zip(joined.columns[1:], beta.tolist())),
                  "autoregressive_coefficient": float(beta[1]), "unstable": bool(abs(beta[1]) >= 1)}
    return Distribution(np.median(forecast, axis=0), forecast, diagnostic)


def impulse_effect(beta: np.ndarray, driver: str, months: int, shock: float, max_lag: int = 3) -> float:
    offset = 2 if driver == "oil" else 2 + max_lag
    effects = []
    prev = 0.0
    for month in range(1, months + 1):
        direct = beta[offset + month - 1] * shock if month <= max_lag else 0.0
        prev = beta[1] * prev + direct
        effects.append(prev)
    return float(np.expm1(np.sum(effects)) * 100)


def fit_pass_through(frame: pd.DataFrame, max_lag: int = 3, bootstrap: int = 1000,
                     seed: int = 42) -> dict:
    beta, joined, _, residuals = fit_lag(frame, max_lag)
    matrix = joined.drop(columns="target").to_numpy()
    response = joined.target.to_numpy()
    indices = block_indices(len(joined), len(joined), bootstrap, 12, seed)
    boot = np.asarray([np.linalg.lstsq(matrix[i], response[i], rcond=None)[0] for i in indices])
    coefficients = [{"term": term, "estimate": float(beta[j]),
                     "lower95": float(np.quantile(boot[:, j], .025)),
                     "upper95": float(np.quantile(boot[:, j], .975))}
                    for j, term in enumerate(joined.columns[1:])]
    effects = []
    for driver, label, shock in (("oil", "Palm/soy benchmark basket +10%", np.log1p(.1)),
                                 ("fx", "SGD purchasing value -5% vs USD", np.log(1 / .95))):
        for months in (1, 3, 6, 12):
            values = [impulse_effect(b, driver, months, shock, max_lag) for b in boot]
            effects.append({"scenario": label, "months": months,
                            "retail_effect_pct": impulse_effect(beta, driver, months, shock, max_lag),
                            "lower95": float(np.quantile(values, .025)), "upper95": float(np.quantile(values, .975))})
    return {"model": "OLS log-difference AR(1), oil basket and FX lags 1–3",
            "oil_basket": "equal-weight geometric palm/soy USD benchmarks (assumed, not measured retail recipe)",
            "training_start": str(joined.index[0].date()), "training_end": str(joined.index[-1].date()),
            "n": len(joined), "bootstrap_repetitions": bootstrap, "block_months": 12,
            "coefficients": coefficients, "effects": effects,
            "residual_sd": float(np.std(residuals, ddof=matrix.shape[1])),
            "interpretation": "Conditional predictive associations, not identified causal effects; estimates use reconstructed history.",
            "unstable_bootstrap_fraction": float(np.mean(np.abs(boot[:, 1]) >= 1)),
            "forecast_driver_assumption": "persistence-centered joint driver innovations"}
