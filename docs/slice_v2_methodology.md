# Slice v2 methodology

This is a separately frozen diagnostic experiment on the same reconstructed history as v1. It is not an independent holdout: the user requested these changes after reviewing v1 audit failures. Source, information-clock and training-only direction-band rules are unchanged. No historical news is used.

## Benchmarks and selection

Random walk: log-price forecast stays at the last observed log CPI, with centered observed innovations for base uncertainty. Seasonal naive: repeat the final 12 observed monthly values. ETS remains damped additive log trend, ARIMA remains (1,1,1); optimization failures explicitly use RW. We report paired MAE reductions and MASE skill against both RW and seasonal naive, along with candidate and baseline directional accuracy. All comparisons use identical origins and 12-month circular moving-block resampling, 1,000 draws.

For each horizon, select the largest development mean paired MAE reduction against RW. Ties within ten decimal places use the smallest development interval score, then model name. RW has zero self-skill, so a model with negative development skill cannot win. This rule is fixed before the v2 audit is computed. Report audit failure without selecting anew from audit performance. The research-agent plan's future CI-gated publishing rule is not implemented in this slice.

## Seasonal-naive uncertainty and calibration

At historical training origin t with at least 24 observations, the h-step prediction is the value at t−11+((h−1) mod12). The calibration pool contains errors log(y[t+h])−log(prediction[t,h]) only where t+h is already in the supplied training sample. Different horizons have different matured pools. For h≤12 these remain year-apart differences, as required by the seasonal point forecast; multiplying their scale by sqrt(h/12) would manufacture artificially narrow intervals. Width need not fall before conformal correction.

The raw marginal error pools are median-centered. Baseline sample medians are aligned with the declared point forecast. Rolling variants use the last 36 observations/errors in each origin's training data. ETS simulates sampled recent innovations; ARIMA scales its native prediction variance by recent/full residual standard deviation; RW resamples recent increments. Their full-history counterparts remain in the scored panel. Both uncertainty variants keep the same baseline point forecast.

For released out-of-sample labels, CQR score s=max(log(q10)−log(y), log(y)−log(q90)). Use the ceil((n+1)*0.8)-th sorted score, n≥24 and at most 60 most recent eligible origins. A negative score shrinks the interval; a positive score expands it. Filter both prior issuance time and actual/assumed label availability, and match effective forecast distance. Transform the log samples around their declared median to attain the adjusted tails. Clamp each half-width at zero to avoid crossing the median; report collapse frequency. There is no independent time-series coverage guarantee.

Before/after is a controlled comparison **for the same candidate point model and origins**: before uses full-history base uncertainty, legacy annual-error pooling for seasonal naive, and expansion-only CQR; after uses revised uncertainty and signed CQR. This is not a comparison that silently substitutes the old v1 selected model at a horizon. Native pre-conformal metrics, all rolling variants and the original v1 outputs are retained. Coverage, width and interval-score changes are code-generated, not hand-edited.

## Pass-through

Fit monthly log CPI changes on an intercept, lagged CPI change and each driver's lags 0…12. Constrain a driver's 13 weights to a degree-two Legendre (Almon) polynomial: w(l)=a0+a1*z(l)+a2*(3*z(l)^2−1)/2, z(l)=2l/12−1. Estimate the three parameters per driver by constrained least squares. This is dimensional shrinkage through a fixed lag-shape constraint, not unrestricted 13-lag OLS, and requires no data-selected hyperparameter. The same constraint is refitted in every training window.

- SGD: log(palm USD × SGD/USD), log(soy USD × SGD/USD). No extra FX term.
- USD+FX: separate log palm USD, log soy USD and log SGD/USD.
- Asymmetry: split each input change into positive and negative parts before applying the same lag basis. Report the block-bootstrap interval for the difference between 12-month cumulative positive and negative elasticities. These are exploratory intervals without multiplicity adjustment.

Lag-zero forecasting never substitutes future realized inputs. Inputs beyond the latest CPI may be used only if they are in the supplied as-of panel; otherwise future changes are jointly block-resampled and centered on persistence. Future regressors and retail innovations propagate recursively. A paired test confirms that changing genuinely known post-CPI drivers affects the forecast but cannot change the estimated historical coefficients.

An ECM candidate is enabled only when that origin's training sample passes Engle–Granger plus integration-order checks: EG p<0.025 (two predeclared currency specifications), levels fail ADF rejection at 5% and first differences reject. The long-run regression is estimated on that training sample and its residual enters with lag one. Unsupported windows use the polynomial difference specification, explicitly logged. [Statsmodels Engle–Granger documentation](https://www.statsmodels.org/stable/generated/statsmodels.tsa.stattools.coint.html) describes the test's I(1) assumption; short-sample non-rejections are weak evidence, not proof.

For cumulative effects, apply a permanent +10% driver-level step at month zero; report CPI change accumulated over months 0…h−1 for h=3,6,12, including autoregressive propagation. Bootstrap complete response/design rows in circular 12-month blocks and refit the constrained coefficients. The intervals condition on the fixed polynomial specification. They are predictive associations, not identified causal effects or attributions to univariate forecasts. Estimated FX and oil effects are not added across the two alternative specifications.
