"""Deterministic, evidence-linked outputs; no paid LLM and no unsupported article claims."""
from __future__ import annotations

from pathlib import Path

import pandas as pd


def outlook_note(forecast: dict, effects: pd.DataFrame, relationships: dict, news: dict) -> str:
    lines = ["# Cooking-oil outlook", "", f"Issued {forecast['issued_at']}. Target: Singapore Vegetable Oils CPI (2024=100).",
        f"Latest published CPI in this snapshot: **{forecast['last_cpi']:.3f}**, reference month {forecast['last_cpi_month'][:7]}.",
        "", "All percentage changes below are relative to that last observed CPI. Numerical evidence: [forecast.json](forecast.json).",
        "", "| Horizon / target | Model | Median CPI | 10–90% CPI | Median change | Direction |",
        "|---|---|---:|---|---:|---|"]
    for row in forecast["forecasts"]:
        lines.append(f"| {row['horizon']}m / {row['target_month'][:7]} | {row['model']} | {row['median']:.3f} | "
                     f"{row['q10']:.3f}–{row['q90']:.3f} | {row['change_pct']:+.2f}% | {row['direction']} |")
    lines += ["", "Models were selected on development-period MASE, before the final audit comparison. These are "
              "model-implied ranges, not verified 80% prospective guarantees. Reliability score: **provisional / unavailable** "
              "until prospective outcomes mature.", "", "## Evidence and drivers", "",
              "The univariate forecasts depend on CPI history. The distributed-lag candidate uses an assumed equal-weight "
              "geometric palm/soy benchmark basket and SGD per USD. Its estimated relationships are predictive associations, "
              "not proof of causal pass-through; they do not become attributions to an ETS or ARIMA forecast."]
    for scenario in ("Palm/soy benchmark basket +10%", "SGD purchasing value -5% vs USD"):
        row = next(r for r in relationships["effects"] if r["scenario"] == scenario and r["months"] == 6)
        lines.append(f"- Conditional six-month association for **{scenario}**: {row['retail_effect_pct']:+.2f}% retail CPI "
                     f"(95% moving-block coefficient interval {row['lower95']:+.2f}% to {row['upper95']:+.2f}%).")
    lines += ["", "Relationship evidence: [relationships.json](relationships.json). Input lineage: [manifest.json](manifest.json).",
        "Sources: [SingStat CPI](https://tablebuilder.singstat.gov.sg/table/TS/M213751), "
        "[World Bank Pink Sheet](https://www.worldbank.org/en/research/commodity-markets), "
        "[MAS FX via SingStat](https://tablebuilder.singstat.gov.sg/table/TS/M700051).", "", "## Historical evidence", "",
        "Primary historical view: **reconstructed**, with current-vintage values and assumed publication lags. "
        "Effect sizes are paired against seasonal naive; uncertainty uses 12-month circular block resampling. "
        "[Full evaluation table](effects.csv) and [origin-level predictions](predictions.csv) retain all candidates."]
    for fc in forecast["forecasts"]:
        row = effects[(effects.scope == "audit") & (effects.horizon == fc["horizon"]) & (effects.model == fc["model"])].iloc[0]
        lines.append(f"- {fc['horizon']}m selected {fc['model']}: MAE reduction {row.mae_reduction_cpi_points:+.3f} CPI points "
                     f"(95% interval {row.mae_reduction_lower95:+.3f} to {row.mae_reduction_upper95:+.3f}); "
                     f"MASE skill {row.mase_skill_pct:+.1f}%; 80% interval coverage {row.coverage80:.1%} across {int(row.n)} audit origins.")
    lines += ["", "## News and risks", "",
        f"{news['eligible_articles']} currently eligible prospective feed/metadata records; "
        f"{news['oil_stories']} relevant cooking-oil stories; {news['recognized_events']} recognized local-rule events. "
        "Extraction is unvalidated and news does not enter the historical model."]
    if news["citations"]:
        for item in news["citations"]:
            title = str(item["title"]).replace("[", "(").replace("]", ")")
            lines.append(f"- [{title}]({item['url']}) — supplied feed context only; unvalidated.")
    else:
        lines.append("No usable cooking-oil article evidence has been collected yet; no event assertions are made. "
                     "GDELT coverage is unknown when responses fail or are rate limited, not evidence of no news.")
    lines += ["", "- Historical revisions and assumed release dates can change measured skill; these results are not strict-PIT history.",
        "- Retail basket composition, contracts and policy may change pass-through; coefficient intervals show estimation uncertainty.",
        "- A new supply shock or a shift in volatility can invalidate historical intervals. News coverage is incomplete and unvalidated.",
        "", "The view would change with newly released CPI, updated benchmarks/FX, a supported supply event, or a sustained deterioration "
        "in realized forecast errors. Unknown future driver changes are simulated around persistence, never replaced by future realized prices.",
        "", "A current off-cycle issuance can have a longer CPI publication bridge than the monthly backtest; see effective_steps in forecast.json. "
        "Unchanged bands are frozen from initial-training volatility, not chosen to improve evaluation."]
    return "\n".join(lines) + "\n"


def render_fan(history: pd.Series, forecast: dict, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    values = forecast["forecasts"]
    dates = [history.index[-1]] + [pd.Timestamp(row["target_month"]) for row in values]
    median = [history.iloc[-1]] + [row["median"] for row in values]
    lower = [history.iloc[-1]] + [row["q10"] for row in values]
    upper = [history.iloc[-1]] + [row["q90"] for row in values]
    fig, ax = plt.subplots(figsize=(10, 5), constrained_layout=True)
    recent = history.iloc[-60:]
    ax.plot(recent.index, recent.values, color="#34495e", linewidth=1.7, label="Observed CPI")
    ax.fill_between(dates, lower, upper, color="#2c7fb8", alpha=.18, label="10–90% forecast range")
    ax.plot(dates, median, color="#2c7fb8", marker="o", linestyle="--", label="Median")
    ax.set(title="Singapore cooking oil · forecast outlook", ylabel="Vegetable Oils CPI (2024=100)")
    ax.grid(alpha=.18)
    ax.legend(loc="upper left")
    fig.text(.02, -.035, "Forecast quantiles at 1/3/6 months; connecting lines are visual interpolation. Prospective calibration unmeasured.", fontsize=8)
    fig.savefig(path, dpi=170, bbox_inches="tight")
    plt.close(fig)
