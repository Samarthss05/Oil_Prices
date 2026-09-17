"""A single research page; reads saved artifacts and does not silently retrain."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(os.environ.get("RETAIL_OUTLOOK_ROOT", Path(__file__).resolve().parents[2]))
st.set_page_config(page_title="Cooking oil · Singapore outlook", page_icon="📊", layout="wide")
st.title("Cooking oil · Singapore price outlook")
st.caption("Research slice · historical evaluation is reconstructed · prospective collection is active")

latest = ROOT / "artifacts/latest.json"
if not latest.exists():
    st.info("Run ./run.sh run first to ingest data and create the saved research artifacts.")
    st.stop()
directory = Path(json.loads(latest.read_text())["directory"])
forecast = json.loads((directory / "forecast.json").read_text())
relationships = json.loads((directory / "relationships.json").read_text())
protocol = json.loads((directory / "protocol.json").read_text())
news = json.loads((directory / "news.json").read_text())
manifest = json.loads((directory / "manifest.json").read_text())
effects = pd.read_csv(directory / "effects.csv")
history = pd.read_parquet(directory / "history.parquet").cpi_cooking_oil.dropna()
audit = effects[effects.scope == "audit"]
selected_audit = pd.DataFrame([audit[(audit.horizon == f["horizon"]) & (audit.model == f["model"])].iloc[0]
                               for f in forecast["forecasts"]])

st.write(f"**Latest CPI:** {forecast['last_cpi']:.3f} · reference month {forecast['last_cpi_month'][:7]} · "
         f"forecast issued {forecast['issued_at'][:19]} UTC")
st.subheader("Effect sizes first")
st.caption("Final audit: February 2023–January 2026 forecast origins, 36 per horizon. "
           "Positive MAE reduction means smaller errors than seasonal naive. Intervals use 12-month block resampling.")
table = selected_audit[["horizon", "model", "mae_reduction_cpi_points", "mae_reduction_lower95", "mae_reduction_upper95",
                         "mase_skill_pct", "coverage80", "fallback_count"]].copy()
table.columns = ["Horizon (months)", "Development-selected model", "MAE reduction (CPI pts)", "95% lower", "95% upper",
                 "MASE skill (%)", "80% coverage", "RW fallback origins"]
st.dataframe(table.round(3), hide_index=True, width="stretch")
if ((selected_audit.coverage80 < .72) | (selected_audit.coverage80 > .88)).any():
    st.warning("Calibration target not met: the selected models' audit intervals over-cover. "
               "A nominal 80% range is not yet a calibrated prospective guarantee.")
st.caption("No verified-PIT outcome scores exist yet. A small retrospective audit and revised histories limit the evidence.")

st.subheader("Forecast distribution")
columns = st.columns(3)
for column, row in zip(columns, forecast["forecasts"]):
    with column:
        st.metric(f"{row['horizon']} months · {row['target_month'][:7]}", f"{row['median']:.2f}",
                  f"{row['change_pct']:+.2f}% vs last CPI", delta_color="off")
        st.write(f"10–90%: **{row['q10']:.2f}–{row['q90']:.2f}** · {row['direction']}")
        st.caption(f"{row['model']} · {row['effective_steps']} months beyond the observed CPI. "
                   f"Unchanged band ±{row['unchanged_band_pct']:.2f}%.")
        if row["diagnostics"].get("fallback"):
            st.warning(f"This forecast used {row['diagnostics']['fallback']} fallback: "
                       f"{row['diagnostics'].get('reason', 'model failure')}")

dates = [history.index[-1]] + [pd.Timestamp(f["target_month"]) for f in forecast["forecasts"]]
q10 = [float(history.iloc[-1])] + [f["q10"] for f in forecast["forecasts"]]
q90 = [float(history.iloc[-1])] + [f["q90"] for f in forecast["forecasts"]]
median = [float(history.iloc[-1])] + [f["median"] for f in forecast["forecasts"]]
fig = go.Figure()
fig.add_trace(go.Scatter(x=history.index[-60:], y=history.values[-60:], mode="lines", name="Observed CPI",
                         line=dict(color="#475569", width=2)))
fig.add_trace(go.Scatter(x=dates, y=q90, line=dict(width=0), showlegend=False, hoverinfo="skip"))
fig.add_trace(go.Scatter(x=dates, y=q10, fill="tonexty", fillcolor="rgba(37,99,235,0.16)",
                         line=dict(width=0), name="10–90% range"))
fig.add_trace(go.Scatter(x=dates, y=median, mode="lines+markers", name="Median",
                         line=dict(color="#2563eb", dash="dash", width=2)))
fig.update_layout(height=380, margin=dict(l=15, r=15, t=15, b=15), yaxis_title="CPI (2024=100)",
                  legend=dict(orientation="h", y=1.08), hovermode="x unified")
st.plotly_chart(fig, width="stretch")
st.caption("Quantiles are estimated at the three labelled target months; connecting lines are visual interpolation. "
           "Probability and numerical reliability are different: the reliability score remains provisional.")
if forecast["off_cycle"]:
    st.info("This is an off-cycle forecast. Its CPI publication bridge differs from the monthly backtest. "
            "Current ranges use native model uncertainty; corrections from different effective horizons are not transferred.")

with st.expander("Model-implied direction probabilities and frozen bands"):
    st.dataframe(pd.DataFrame(forecast["forecasts"])[["horizon", "prob_up", "prob_unchanged", "prob_down",
                   "unchanged_band_pct", "calibration_provenance"]], hide_index=True, width="stretch")
    st.write("Bands were frozen using only January 2015–December 2019 CPI. They need not increase monotonically: "
             "they reflect measured multi-month volatility in that training sample.")
    st.json({"frozen_at": protocol["frozen_at"], "recipe": protocol["band_recipe"]})

st.subheader("Upstream relationships")
st.write("Palm oil + soybean oil → assumed equal-weight benchmark basket → retail cooking oil; "
         "SGD per USD enters separately. OLS uses retail persistence and three lagged changes per driver.")
association = pd.DataFrame(relationships["effects"])
st.dataframe(association[association.months == 6].round(3), hide_index=True, width="stretch")
st.caption("Effects describe hypothetical sustained input-price changes, conditional on this small model. "
           "Both six-month coefficient intervals include zero; a stable directional pass-through has not been established. "
           "These are not driver attributions to the selected univariate models.")
with st.expander("Lag coefficients, assumptions and all baseline comparisons"):
    st.dataframe(pd.DataFrame(relationships["coefficients"]).round(4), hide_index=True, width="stretch")
    st.write(relationships["interpretation"])
    st.dataframe(effects.round(4), hide_index=True, width="stretch")

st.subheader("Prospective news")
st.write(f"At this report's cutoff: **{news['eligible_articles']}** eligible records · "
         f"**{news['oil_stories']}** cooking-oil stories · **{news['recognized_events']}** recognized events.")
st.caption("Hourly collection is scheduled in Codex. It requires this local project/runtime to remain available. "
           "Source dates are never substituted for retrieval time; collection gaps are not backdated.")
if not news["oil_stories"]:
    st.info("No usable cooking-oil news evidence yet. GDELT returned unusable/rate-limited responses; its coverage is unknown. "
            "No article-based event claim or news predictive benefit is asserted.")
st.write("Local extraction is unvalidated. Human labels: approximately 50 development + 100 held-out articles, "
         "with 25 independently reviewed. Paid extraction cost: **$0**; development cap: **$50/month**; paid historical backfill disabled.")
with st.expander("Collection status and evidence-linked outlook"):
    st.json(news["latest_collection"])
    st.markdown((directory / "outlook.md").read_text())

st.subheader("Sources and reproducibility")
st.markdown("[SingStat CPI](https://tablebuilder.singstat.gov.sg/table/TS/M213751) · "
            "[World Bank Pink Sheet](https://www.worldbank.org/en/research/commodity-markets) · "
            "[MAS FX through SingStat](https://tablebuilder.singstat.gov.sg/table/TS/M700051)")
buttons = st.columns(4)
for column, name in zip(buttons, ["outlook.md", "forecast.json", "effects.csv", "manifest.json"]):
    column.download_button(name, (directory / name).read_bytes(), file_name=name)
st.caption(f"Saved run {manifest['run_id']} · structured snapshot {manifest['source_snapshot']} · "
           "page reads saved artifacts; refresh data and forecasts explicitly with ./run.sh run --refresh.")
