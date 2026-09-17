import numpy as np
import pandas as pd
import pytest

from retail_outlook.models import forecast_baseline, impulse_effect


def test_seasonal_naive_point_forecast_is_exact():
    y = pd.Series(np.arange(48) + 100., index=pd.date_range("2015-01-01", periods=48, freq="MS"))
    result = forecast_baseline("seasonal_naive", y, 14, n_samples=50)
    np.testing.assert_allclose(result.median, np.resize(y.iloc[-12:].to_numpy(), 14))
    assert result.samples.shape == (50, 14) and (result.samples > 0).all()


def test_missing_month_is_rejected():
    y = pd.Series(np.ones(48)*100., index=pd.date_range("2015-01-01", periods=48, freq="MS")).drop(pd.Timestamp("2016-01-01"))
    with pytest.raises(ValueError, match="Missing"):
        forecast_baseline("ets", y, 3)


def test_pass_through_includes_autoregressive_propagation():
    # y growth autoregression .5 and a single .1 input elasticity at lag1.
    beta = np.array([0., .5, .1, 0., 0., 0., 0., 0.])
    expected = np.expm1(np.log(1.1)*.1*(1+.5+.25))*100
    assert impulse_effect(beta, "oil", 3, np.log(1.1)) == pytest.approx(expected)
