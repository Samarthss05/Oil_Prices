import numpy as np
import pandas as pd
import pytest

from retail_outlook.evaluation import calibrate, calibration_correction, select_models
from retail_outlook.models import (driver_logs, forecast_baseline, forecast_distributed_lag,
                                   lag_design, lag_weights, polynomial_response, seasonal_errors)
from retail_outlook.reporting import change_label, escape_dollars


def panel():
    rng = np.random.default_rng(35)
    return pd.DataFrame({name: base*np.exp(np.cumsum(rng.normal(0, .01, 90)))
        for name, base in [("cpi_cooking_oil", 100), ("palm_oil_usd", 700),
                           ("soy_oil_usd", 800), ("usd_sgd", 1.35)]},
                        index=pd.date_range("2015-01-01", periods=90, freq="MS"))


def test_signed_calibration_shrinks_and_does_not_cross_median():
    rows = [dict(model="random_walk", horizon=1, origin="2020-01-01T00:00:00Z",
        actual_available_at="2020-03-01T00:00:00Z", raw_q10=80, raw_q90=120, actual=100)] * 24
    correction, n = calibration_correction(rows, pd.Timestamp("2020-04-01T00:00:00Z"), "random_walk", 1)
    assert correction < 0 and n == 24
    raw = np.exp(np.linspace(np.log(80), np.log(125), 1001))
    shrunk = calibrate(raw, 100., correction)
    assert np.ptp(shrunk) < np.ptp(raw)
    assert np.quantile(shrunk, .1) <= 100 <= np.quantile(shrunk, .9)
    assert np.isfinite(calibrate(raw, 100., -100)).all()
    assert calibration_correction(rows, pd.Timestamp("2020-04-01T00:00:00Z"), "random_walk", 1,
                                  expansion_only=True) == (0., 24)


def test_immature_extreme_residuals_cannot_change_signed_correction():
    mature = [dict(model="ets", horizon=3, origin="2020-01-01T00:00:00Z",
        actual_available_at="2020-05-01T00:00:00Z", raw_q10=80, raw_q90=120, actual=100)] * 24
    future = [dict(mature[0], actual_available_at="2099-01-01T00:00:00Z", actual=1e99)] * 100
    cutoff = pd.Timestamp("2020-06-01T00:00:00Z")
    assert calibration_correction(mature+future, cutoff, "ets", 3) == calibration_correction(mature, cutoff, "ets", 3)
    assert calibration_correction(mature[:23]+future, cutoff, "ets", 3) == (0., 23)
    assert calibration_correction(mature, cutoff, "ets", 3, effective_steps=5) == (0., 0)


def test_selection_never_uses_audit_values():
    rows = [dict(scope=s, horizon=1, model=m, rw_mae_reduction=v, interval_score80=1.)
            for s in ["development", "audit"] for m, v in [("random_walk", 0.), ("ets", 1.)]]
    effects = pd.DataFrame(rows)
    first = select_models(effects, [1])
    effects.loc[effects.scope == "audit", "rw_mae_reduction"] = -1e90
    assert select_models(effects, [1]) == first == {"1": "ets"}
    effects.loc[(effects.scope == "development") & (effects.model == "ets"), "rw_mae_reduction"] = -1
    assert select_models(effects, [1]) == {"1": "random_walk"}


def test_seasonal_uncertainty_uses_actual_h_step_errors():
    z = np.log(np.arange(100)+100.)
    for horizon in (1, 7, 14):
        expected = [z[t+horizon]-z[t-11+(horizon-1)%12] for t in range(23, len(z)-horizon)]
        np.testing.assert_allclose(seasonal_errors(z, horizon), expected)
    assert len(seasonal_errors(z, 7)) < len(seasonal_errors(z, 1))


def test_rolling_uncertainty_preserves_point_forecast():
    y = panel().cpi_cooking_oil
    a = forecast_baseline("random_walk", y, 7, 200)
    b = forecast_baseline("random_walk_rolling", y, 7, 200)
    np.testing.assert_array_equal(a.median, b.median)
    assert not np.array_equal(a.samples, b.samples)


def test_currency_conversion_has_no_duplicate_fx_and_lag_zero_is_present():
    frame = panel()
    logs = driver_logs(frame, "sgd")
    np.testing.assert_allclose(np.exp(logs.palm_sgd), frame.palm_oil_usd*frame.usd_sgd)
    joined, changes = lag_design(frame, 12)
    assert not any("fx" in c for c in joined)
    assert "palm_sgd_p0" in joined and "soy_sgd_p0" in joined
    last = joined.index[-1]
    assert joined.loc[last, "palm_sgd_p0"] == pytest.approx(changes.palm_sgd.iloc[-13:].sum())
    usd, _ = lag_design(frame, 12, spec="usd_fx")
    assert "fx_p0" in usd and "palm_usd_p0" in usd


def test_known_post_cpi_driver_cannot_change_training_fit_but_can_change_forecast():
    frame = panel()
    frame.loc[frame.index[-1], "cpi_cooking_oil"] = np.nan
    other = frame.copy()
    other.loc[other.index[-1], "palm_oil_usd"] *= 2
    a, _ = lag_design(frame)
    b, _ = lag_design(other)
    pd.testing.assert_frame_equal(a, b)
    fa = forecast_distributed_lag(frame, 3, 100)
    fb = forecast_distributed_lag(other, 3, 100)
    assert fa.diagnostics["coefficients"] == fb.diagnostics["coefficients"]
    assert not np.array_equal(fa.samples, fb.samples)


def test_ecm_cannot_be_used_without_training_window_support(monkeypatch):
    monkeypatch.setattr("retail_outlook.models.cointegration_gate", lambda *a: {"supported": False})
    a, _ = lag_design(panel(), ecm=True)
    assert "ecm_lag1" not in a
    forecast = forecast_distributed_lag(panel(), 3, 100, ecm=True)
    assert forecast.diagnostics["ecm_used"] is False
    monkeypatch.setattr("retail_outlook.models.cointegration_gate", lambda *a: {"supported": True})
    b, _ = lag_design(panel(), ecm=True)
    assert "ecm_lag1" in b
    # Future driver rows do not enter the gate or long-run regression.
    extended = pd.concat([panel(), pd.DataFrame({"palm_oil_usd": [1e9]}, index=[pd.Timestamp("2022-07-01")])])
    c, _ = lag_design(extended, ecm=True)
    pd.testing.assert_frame_equal(b, c, check_freq=False)


def test_polynomial_impulse_includes_lag_zero_and_autoregression():
    joined, _ = lag_design(panel())
    beta = np.zeros(len(joined.columns)-1)
    beta[1] = .5
    beta[list(joined.columns[1:]).index("palm_sgd_p0")] = .1
    np.testing.assert_allclose(lag_weights(beta, joined, "palm_sgd"), .1)
    assert polynomial_response(beta, joined, "palm_sgd", 3, 1.) == pytest.approx(.1+.15+.175)


def test_asymmetry_separates_positive_and_negative_changes():
    joined, _ = lag_design(panel(), asymmetric=True)
    assert "palm_sgd_positive_p0" in joined and "palm_sgd_negative_p0" in joined
    assert (joined.palm_sgd_positive_p0 >= 0).all()
    assert (joined.palm_sgd_negative_p0 <= 0).all()


def test_display_zero_and_dollar_escaping():
    assert change_label(-.00001, "unchanged") == "0.00%"
    assert change_label(.7, "unchanged") == "0.00%"
    assert change_label(-2, "down") == "-2.00%"
    assert escape_dollars("$0 and $50/month") == r"\$0 and \$50/month"
    assert escape_dollars(r"\$0") == r"\$0"
