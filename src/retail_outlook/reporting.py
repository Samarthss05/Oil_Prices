"""Deterministic, evidence-linked reporting. Numbers always come from saved model outputs."""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd


def escape_dollars(text: str) -> str:
    return re.sub(r"(?<!\\)\$", r"\\$", text)


def change_label(change_pct: float, direction: str) -> str:
    if direction == "unchanged" or round(change_pct, 2) == 0:
        return "0.00%"
    return f"{change_pct:+.2f}%"


def selected_audit(forecast: dict, effects: pd.DataFrame) -> pd.DataFrame:
    audit = effects[effects.scope == "audit"]
    return pd.DataFrame([audit[(audit.horizon == row["horizon"]) & (audit.model == row["model"])].iloc[0]
                         for row in forecast["forecasts"]])


def outlook_note(forecast: dict, effects: pd.DataFrame, relationships: dict, news: dict) -> str:
    switching = len({row["model"] for row in forecast["forecasts"]}) > 1
    lines = ["# Cooking-oil outlook", "", f"Issued {forecast['issued_at']}. Vegetable Oils CPI (2024=100).",
             f"Last observed CPI: **{forecast['last_cpi']:.3f}**, {forecast['last_cpi_month'][:7]}.", "",
             "[Forecast numbers](forecast.json) · [paired evaluation](effects.csv) · [interval comparison](interval_comparison.csv) · [lineage](manifest.json)", "",
             "| Target month | Months beyond last CPI | Model | Median | 10–90% range | Direction / display change |",
             "|---|---:|---|---:|---|---|"]
    for r in forecast["forecasts"]:
        lines.append(f"| {r['target_month'][:7]} | {r['effective_steps']} | {r['model']} | {r['median']:.3f} | "
                     f"{r['q10']:.3f}–{r['q90']:.3f} | {r['direction']} / {change_label(r['change_pct'], r['direction'])} |")
    lines += ["", "Display changes inside the frozen unchanged band are 0.00%; exact model changes remain in forecast.json.",
              "**Model switching across target months: yes.** Connected medians are not one model's joint path." if switching else
              "One selected model supplies the median path at all target months.",
              "Selection uses development MAE skill versus random walk; uncertainty ties use development interval score.",
              "Reliability: provisional; prospective outcomes have not matured. Reconstructed residual calibration is not verified PIT evidence.",
              "", "## Paired historical diagnostics", "",
              "Reconstructed history; the v1 audit period is reused after deficiencies were known. This is not a new untouched holdout.",
              "Positive reductions mean lower MAE. 95% intervals use 12-month circular blocks; zero-crossing intervals do not establish a gain.", "",
              "| Horizon | Model | MAE reduction vs RW [95%] | vs seasonal naive [95%] | Direction accuracy | Coverage before → after | Width before → after |",
              "|---|---|---|---|---:|---|---|"]
    for _, r in selected_audit(forecast, effects).iterrows():
        lines.append(f"| {r.horizon}m | {r.model} | {r.rw_mae_reduction:+.3f} [{r.rw_mae_lower95:+.3f}, {r.rw_mae_upper95:+.3f}] | "
                     f"{r.sn_mae_reduction:+.3f} [{r.sn_mae_lower95:+.3f}, {r.sn_mae_upper95:+.3f}] | {r.direction_correct:.1%} | "
                     f"{r.before_coverage80:.1%} → {r.coverage80:.1%} | {r.before_width80:.3f} → {r.width80:.3f} |")
    lines += ["", "Before/after holds point models and origins fixed: full-history base uncertainty plus expansion-only correction versus "
              "revised uncertainty plus signed correction. All candidates, MASE skill, interval scores and uncertainty ablations are in the linked CSVs.",
              "", "## Driver relationships and risks", "",
              "Separate palm and soy prices enter as SGD-converted inputs, or as USD inputs plus one FX term. "
              "Quadratic lag profiles cover 0–12 months; no 50/50 basket is imposed. Relationships are conditional associations, not causal effects "
              "or attributions to univariate forecasts. [Coefficient, asymmetry and cointegration diagnostics](relationships.json)."]
    for r in relationships["effects"]:
        if r["months"] == 6 and r["spec"] == "sgd":
            lines.append(f"- {r['driver']} +10%: conditional six-month CPI response {r['retail_effect_pct']:+.2f}% "
                         f"[95% {r['lower95']:+.2f}%, {r['upper95']:+.2f}%].")
    lines += ["", "- Revised historical data and assumed publication dates can alter apparent skill.",
              "- Small samples, correlated inputs and changing retail contracts limit pass-through identification.",
              "- A supply shock or volatility shift can invalidate intervals; news extraction remains unvalidated.",
              "", "## Prospective news", "",
              f"{news['eligible_articles']} eligible records; {news['oil_stories']} keyword-relevant stories; "
              f"{news['recognized_events']} recognized rule events. These are descriptive counts, not validated predictive signals.",
              "Human labelling is **planned**, not completed. GDELT failures mean unknown coverage, not absent news."]
    for a in news["citations"]:
        title = a["title"].replace("[", "(").replace("]", ")")
        lines.append(f"- [{title}]({a['url']}) — supplied feed context, unvalidated.")
    lines += ["", "The view changes with newly released CPI, revised inputs, supported supply events or worsening realized errors.",
        "[SingStat CPI](https://tablebuilder.singstat.gov.sg/table/TS/M213751) · "
        "[World Bank](https://www.worldbank.org/en/research/commodity-markets) · "
        "[MAS FX via SingStat](https://tablebuilder.singstat.gov.sg/table/TS/M700051)."]
    return "\n".join(lines)+"\n"


def render_fan(history: pd.Series, forecast: dict, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    values = forecast["forecasts"]
    dates = [history.index[-1]] + [pd.Timestamp(r["target_month"]) for r in values]
    median = [history.iloc[-1]] + [r["median"] for r in values]
    low = [history.iloc[-1]] + [r["q10"] for r in values]
    high = [history.iloc[-1]] + [r["q90"] for r in values]
    fig, ax = plt.subplots(figsize=(10, 5), constrained_layout=True)
    ax.plot(history.index[-60:], history.iloc[-60:], color="#34495e", label="Observed CPI")
    ax.fill_between(dates, low, high, color="#2c7fb8", alpha=.18, label="10–90% range")
    switching = len({r["model"] for r in values}) > 1
    ax.plot(dates, median, "o--", color="#2c7fb8", label="Median (models switch)" if switching else "Median")
    for index, (r, date) in enumerate(zip(values, dates[1:])):
        ax.annotate(f"{date:%b %y}\n+{r['effective_steps']}m", (date, r["median"]),
                    xytext=(0, 12 + 24*(index % 2)), textcoords="offset points", fontsize=7, ha="center")
    ax.set(title="Singapore cooking oil · exploratory forecast", ylabel="CPI (2024=100)")
    ax.grid(alpha=.18)
    ax.legend(loc="upper left")
    fig.text(.02, -.035, "+m = months after last CPI. Lines interpolate target-month quantiles. " +
             ("Models switch across horizons; this is not a joint median path." if switching else "Prospective calibration unmeasured."), fontsize=8)
    fig.savefig(path, dpi=170, bbox_inches="tight")
    plt.close(fig)


def results_markdown(directory: Path) -> str:
    """Generate the checkpoint tables from immutable artifacts, never manual cells."""
    import json
    forecast = json.loads((directory/"forecast.json").read_text())
    relations = json.loads((directory/"relationships.json").read_text())
    manifest = json.loads((directory/"manifest.json").read_text())
    effects = pd.read_csv(directory/"effects.csv")
    predictions = pd.read_parquet(directory/"predictions.parquet")
    selected = selected_audit(forecast, effects)
    lines = ["# Slice v2 computed results", "", f"Run `{manifest['run_id']}`; source snapshot `{manifest['historical_snapshot']}`.",
             f"Code SHA256 `{manifest['code_sha256']}`.",
             "Reconstructed history; reused historical audit, not a fresh holdout. All cells are generated by `./run.sh report`.", "",
             "| Horizon | Selected model | MAE reduction vs RW [95% block CI] | vs SN [95% block CI] | Direction accuracy | Coverage before → after | Mean width before → after |",
             "|---|---|---|---|---:|---|---|"]
    for _, r in selected.iterrows():
        lines.append(f"| {r.horizon}m | {r.model} | {r.rw_mae_reduction:+.3f} [{r.rw_mae_lower95:+.3f}, {r.rw_mae_upper95:+.3f}] | "
                     f"{r.sn_mae_reduction:+.3f} [{r.sn_mae_lower95:+.3f}, {r.sn_mae_upper95:+.3f}] | {r.direction_correct:.1%} | "
                     f"{r.before_coverage80:.1%} → {r.coverage80:.1%} | {r.before_width80:.3f} → {r.width80:.3f} |")
    lines += ["", "Errors and widths are CPI points. Before/after holds models/origins fixed; see the methodology for the uncertainty ablation.",
              "", "| Horizon | MASE skill vs RW [95%] | MASE skill vs SN [95%] | RW / SN direction accuracy | Interval score before → after |",
              "|---|---|---|---|---|"]
    for _, r in selected.iterrows():
        lines.append(f"| {r.horizon}m | {r.rw_mase_skill_pct:+.2f}% [{r.rw_skill_lower95:+.2f}, {r.rw_skill_upper95:+.2f}] | "
                     f"{r.sn_mase_skill_pct:+.2f}% [{r.sn_skill_lower95:+.2f}, {r.sn_skill_upper95:+.2f}] | "
                     f"{r.rw_directional_accuracy:.1%} / {r.sn_directional_accuracy:.1%} | {r.before_interval_score80:.3f} → {r.interval_score80:.3f} |")
    lines += ["", "## Pass-through", "", "Permanent +10% input level shock at month zero; effects are cumulative retail CPI percent changes.", "",
              "| Driver | Specification | 3m effect [95%] | 6m effect [95%] | 12m effect [95%] | Asymmetry (12m elasticity gap CI) | Cointegration |",
              "|---|---|---|---|---|---|---|"]
    for (spec, driver), group in pd.DataFrame(relations["effects"]).groupby(["spec", "driver"], sort=False):
        cells = []
        for h in (3, 6, 12):
            r = group[group.months == h].iloc[0]
            cells.append(f"{r.retail_effect_pct:+.2f}% [{r.lower95:+.2f}, {r.upper95:+.2f}]")
        a = next(r for r in relations["asymmetry"] if r["spec"] == spec and r["driver"] == driver)
        c = next(r["cointegration"] for r in relations["diagnostics"] if r["spec"] == spec)
        lines.append(f"| {driver} | {spec} | {' | '.join(cells)} | "
                     f"{'supported' if a['supported'] else 'unsupported'} [{a['lower95']:+.3f}, {a['upper95']:+.3f}] | "
                     f"{'supported' if c['supported'] else 'unsupported'}, EG p={c['engle_granger_p']:.3f} |")
    lines += ["", "## Driver candidates versus RW", "",
              "| Horizon | Candidate | MAE reduction [95% block CI] | ECM-used origins |",
              "|---|---|---|---:|"]
    drivers = effects[(effects.scope == "audit") & effects.model.str.startswith("distributed_lag")]
    for _, r in drivers.iterrows():
        used = predictions[(predictions.scope == "audit") & (predictions.horizon == r.horizon) & (predictions.model == r.model)].ecm_used.sum()
        lines.append(f"| {r.horizon}m | {r.model} | {r.rw_mae_reduction:+.3f} [{r.rw_mae_lower95:+.3f}, {r.rw_mae_upper95:+.3f}] | {used} |")
    lines += ["", "No driver candidate beats RW with a 95% MAE-reduction interval excluding zero." if not (drivers.rw_mae_lower95 > 0).any()
              else "Some driver candidates have positive intervals; inspect matched-origin results above.",
              "", "## Seasonal-naive fairness and uncertainty ablation", "",
              "| Horizon | Legacy native SN width | Horizon-specific native SN width | Signed-calibrated SN width |",
              "|---|---:|---:|---:|"]
    for h, group in predictions[(predictions.scope == "audit") & (predictions.model == "seasonal_naive")].groupby("horizon"):
        lines.append(f"| {h}m | {(group.before_raw_q90-group.before_raw_q10).mean():.3f} | {group.raw_width80.mean():.3f} | {group.width80.mean():.3f} |")
    lines += ["", "Full-history versus trailing-36-month uncertainty; audit results are descriptive, not used for choosing variants.", "",
              "| Horizon | Candidate | Native coverage / width | Calibrated coverage / width | Interval score |",
              "|---|---|---|---|---:|"]
    for _, r in effects[(effects.scope == "audit") & ~effects.model.str.startswith("distributed_lag")].iterrows():
        lines.append(f"| {r.horizon}m | {r.model} | {r.raw_coverage80:.1%} / {r.raw_width80:.3f} | {r.coverage80:.1%} / {r.width80:.3f} | {r.interval_score80:.3f} |")
    failures = selected[(selected.coverage80 < .72) | (selected.coverage80 > .88)].horizon.astype(int).tolist()
    lines += ["", f"Selected-model calibration failures (72–88% band): {failures or 'none'} months.",
              f"Intervals with a clamped/collapsed half-width in the audit: {int(predictions.query('scope == \'audit\'').calibration_collapsed.sum())}.",
              "No selected candidate establishes a RW improvement with a positive 95% lower bound." if not (selected.rw_mae_lower95 > 0).any()
              else "See candidate-specific positive lower bounds above; prospective confirmation remains required.",
              "", "The hosted collector's deployment check and uptime are reported separately; keyword mentions are not validated market events."]
    return "\n".join(lines)+"\n"
