"""Single saved-artifact research page; no implicit network access or retraining."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from retail_outlook.reporting import change_label, escape_dollars, selected_audit

ROOT = Path(os.environ.get("RETAIL_OUTLOOK_ROOT", Path(__file__).resolve().parents[2]))
st.set_page_config(page_title="Cooking oil · Singapore outlook", page_icon="📊", layout="wide")
st.title("Cooking oil · Singapore price outlook")
st.caption("Reconstructed historical diagnostics · prospective information uses actual retrieval timestamps")
latest = ROOT / "artifacts/latest.json"
if not latest.exists():
    st.info("Run ./run.sh run to create the research artifacts.")
    st.stop()
directory = Path(json.loads(latest.read_text())["directory"])
forecast = json.loads((directory / "forecast.json").read_text())
relationships = json.loads((directory / "relationships.json").read_text())
protocol = json.loads((directory / "protocol.json").read_text())
news = json.loads((directory / "news.json").read_text())
manifest = json.loads((directory / "manifest.json").read_text())
effects = pd.read_csv(directory / "effects.csv")
if "rw_mae_reduction" not in effects:
    st.info("These are v1 artifacts. Run ./run.sh run --no-news to create the separate v2 experiment.")
    st.stop()
history = pd.read_parquet(directory / "history.parquet").cpi_cooking_oil.dropna()
selected = selected_audit(forecast, effects)
st.write(f"**Latest CPI:** {forecast['last_cpi']:.3f} · {forecast['last_cpi_month'][:7]} · issued {forecast['issued_at'][:19]} UTC")
st.subheader("Effect sizes first")
st.caption("Random walk is the primary benchmark. Positive paired MAE reductions mean improvement; "
           "95% intervals use 12-month circular blocks. Reused historical audit: diagnostic, not an untouched holdout.")
columns = ["horizon", "model", "rw_mae_reduction", "rw_mae_lower95", "rw_mae_upper95", "rw_mase_skill_pct",
           "sn_mae_reduction", "sn_mae_lower95", "sn_mae_upper95", "sn_mase_skill_pct", "direction_correct", "coverage80"]
st.dataframe(selected[columns].round(3), hide_index=True, width="stretch")
if ((selected.coverage80 < .72) | (selected.coverage80 > .88)).any():
    st.warning("Selected-model coverage is outside the requested 72–88% band at one or more horizons.")
if not (selected.rw_mae_lower95 > 0).any():
    st.info("No selected forecast establishes an improvement over random walk with a 95% interval excluding zero.")
st.caption("Verified-PIT outcome scores and calibrated reliability scores are unavailable until future targets mature.")
with st.expander("Uncertainty before and after; all candidates and baselines"):
    st.dataframe(pd.read_csv(directory / "interval_comparison.csv").round(3), hide_index=True, width="stretch")
    st.caption(protocol["comparison_definition"])
    st.dataframe(effects.round(3), hide_index=True, width="stretch")

st.subheader("Forecast distribution")
for column, row in zip(st.columns(3), forecast["forecasts"]):
    with column:
        label = change_label(row["change_pct"], row["direction"])
        unchanged = label == "0.00%"
        st.metric(f"{row['target_month'][:7]} · {row['effective_steps']} months after last CPI", f"{row['median']:.2f}",
                  delta=None if unchanged else label, delta_color="off")
        if unchanged:
            st.caption("0.00% · unchanged (no directional arrow)")
        st.write(f"10–90%: **{row['q10']:.2f}–{row['q90']:.2f}** · {row['direction']}")
        st.caption(f"{row['horizon']}m from issuance · {row['model']} · unchanged band ±{row['unchanged_band_pct']:.2f}%")
        if row["diagnostics"].get("fallback"):
            st.warning(f"Fallback: {row['diagnostics']['fallback']}")
values = forecast["forecasts"]
switching = len({r["model"] for r in values}) > 1
dates = [history.index[-1]] + [pd.Timestamp(r["target_month"]) for r in values]
fig = go.Figure()
fig.add_trace(go.Scatter(x=history.index[-60:], y=history.values[-60:], mode="lines", name="Observed CPI"))
fig.add_trace(go.Scatter(x=dates, y=[history.iloc[-1]]+[r["q90"] for r in values], line=dict(width=0), showlegend=False))
fig.add_trace(go.Scatter(x=dates, y=[history.iloc[-1]]+[r["q10"] for r in values], fill="tonexty",
                         fillcolor="rgba(37,99,235,.16)", line=dict(width=0), name="10–90% range"))
fig.add_trace(go.Scatter(x=dates, y=[history.iloc[-1]]+[r["median"] for r in values], mode="lines+markers",
                         name="Median · models switch" if switching else "Median",
                         text=["Last observation"]+[f"{r['model']} · {r['effective_steps']}m after CPI" for r in values],
                         hovertemplate="%{x|%Y-%m}: %{y:.3f}<br>%{text}<extra></extra>", line=dict(dash="dash")))
fig.update_layout(height=380, yaxis_title="CPI (2024=100)", legend=dict(orientation="h", y=1.08))
st.plotly_chart(fig, width="stretch")
if switching:
    st.warning("Models switch across target months. Connected medians are visual interpolation, not one model's joint path.")
else:
    st.caption("One selected model supplies all three target-month medians; connecting lines interpolate quantiles.")
if forecast["off_cycle"]:
    st.info("Off-cycle issuance: current ranges use native uncertainty when the effective distance differs from available calibration errors.")
with st.expander("Model probabilities and frozen direction bands"):
    st.dataframe(pd.DataFrame(values)[["target_month", "effective_steps", "prob_up", "prob_unchanged", "prob_down",
                                      "unchanged_band_pct", "calibration_provenance"]], hide_index=True)
    st.caption("Exact unrounded changes remain in forecast.json; display changes inside the unchanged band are 0.00%.")

st.subheader("Pass-through: separate inputs, lags 0–12")
st.write("SGD specification: palm and soy prices × SGD per USD, without an extra FX regressor. "
         "USD+FX specification: separate USD palm/soy prices plus one FX term. Quadratic lag constraints reduce parameter count.")
st.dataframe(pd.DataFrame(relationships["effects"]).round(3), hide_index=True, width="stretch")
with st.expander("Asymmetry, cointegration and lag coefficients"):
    st.dataframe(pd.DataFrame(relationships["asymmetry"]).round(3), hide_index=True)
    st.json(relationships["diagnostics"])
    st.dataframe(pd.DataFrame(relationships["coefficients"]).round(4), hide_index=True)
st.caption(relationships["interpretation"])

st.subheader("Prospective news")
st.write(f"**{news['eligible_articles']}** eligible records · **{news['oil_stories']}** keyword-relevant stories · "
         f"**{news['recognized_events']}** unvalidated rule events")
st.caption("Scheduled on GitHub Actions every 3 hours; cumulative raw archives persist as Actions artifacts. "
           "Scheduling delays, finite retention and source failures limit coverage.")
st.markdown(escape_dollars("Human labelling: **planned, not completed** (50 development + 100 held-out; 25 second-reviewer). "
                          "Local extraction cost **$0**; development cap **$50/month**; paid backfill disabled."))
with st.expander("Collector uptime and grounded outlook"):
    st.json(news["collector_health"])
    st.json(news["latest_collection"])
    st.markdown(escape_dollars((directory / "outlook.md").read_text()))

st.subheader("Sources and reproducibility")
st.markdown("[SingStat CPI](https://tablebuilder.singstat.gov.sg/table/TS/M213751) · "
            "[World Bank](https://www.worldbank.org/en/research/commodity-markets) · "
            "[MAS FX via SingStat](https://tablebuilder.singstat.gov.sg/table/TS/M700051)")
for column, name in zip(st.columns(4), ["outlook.md", "forecast.json", "effects.csv", "manifest.json"]):
    column.download_button(name, (directory/name).read_bytes(), file_name=name)
st.caption(f"Saved run {manifest['run_id']} · snapshot {manifest['source_snapshot']} · no implicit retraining")
