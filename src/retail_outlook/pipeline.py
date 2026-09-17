"""Reproducible slice orchestration, immutable run artifacts and a latest pointer."""
from __future__ import annotations

import json
import platform
from pathlib import Path
from uuid import uuid4

import pandas as pd
import yaml

from retail_outlook.connectors import fetch_all
from retail_outlook.evaluation import current_forecast, freeze_protocol, run_backtest
from retail_outlook.models import fit_pass_through
from retail_outlook.news import (collect, extract_all, news_indices, now_utc,
                                 read_articles)
from retail_outlook.reporting import outlook_note, render_fan
from retail_outlook.storage import Store, digest, utc_now, write_json


def run(root: Path, refresh: bool = False, collect_news: bool = True, progress=print) -> dict:
    root = root.resolve()
    config = yaml.safe_load((root / "configs/slice.yaml").read_text())
    store = Store(root)
    try:
        snapshot = store.latest_snapshot()
    except FileNotFoundError:
        snapshot = None
    if refresh or snapshot is None:
        progress("Fetching three structured sources and recording actual retrieval times")
        snapshot = store.ingest(fetch_all(store, config), config)
    else:
        progress(f"Using immutable source snapshot {snapshot}; --refresh requests new data")
    protocol = freeze_protocol(store, config, snapshot)
    if collect_news:
        progress("Collecting permitted news; source limitations are logged")
        collect(root)
    progress("Running frozen reconstructed-history evaluation")
    result = run_backtest(store, protocol, progress)
    issued_at = pd.Timestamp.now(tz="UTC")
    forecast = current_forecast(store, protocol, result["predictions"], result["selected_models"], issued_at)
    panel = store.panel(issued_at, "prospective").loc[config["training_start"]:]
    relationships = fit_pass_through(panel, config["max_driver_lag"], config["bootstrap_repetitions"], config["seed"])
    # Extraction is a separate prospective operation; freeze the news cutoff after its completion.
    extract_all(root)
    cutoff = now_utc()
    articles = read_articles(root, cutoff)
    events = extract_all(root, cutoff)
    relevant_ids = {event["article_id"] for event in events if event["commodities_affected"]}
    news_runs = sorted((root / "data/news/runs").glob("*.json"))
    news = {"as_of": cutoff, "eligible_articles": len(articles), "oil_stories": len({a["story_id"] for a in articles if a["article_id"] in relevant_ids}),
            "recognized_events": sum(e["event_type"] != "UNKNOWN" for e in events),
            "citations": [{"title": a["title"], "url": a["url"]} for a in articles if a["article_id"] in relevant_ids][:3],
            "indices": news_indices(events, cutoff), "extraction_validation": "pending human labels; unvalidated",
            "latest_collection": json.loads(news_runs[-1].read_text()) if news_runs else None,
            "paid_cost_usd": 0., "monthly_cap_usd": 50, "paid_historical_backfill": False}
    run_id = pd.Timestamp.now(tz="UTC").strftime("%Y%m%dT%H%M%S") + "_" + uuid4().hex[:8]
    directory = root / "artifacts/runs" / run_id
    directory.mkdir(parents=True)
    result["predictions"].to_csv(directory / "predictions.csv", index=False)
    result["predictions"].to_parquet(directory / "predictions.parquet", index=False)
    result["effects"].to_csv(directory / "effects.csv", index=False)
    panel.to_parquet(directory / "history.parquet")
    write_json(directory / "forecast.json", forecast, exclusive=True)
    write_json(directory / "relationships.json", relationships, exclusive=True)
    write_json(directory / "news.json", news, exclusive=True)
    write_json(directory / "protocol.json", protocol, exclusive=True)
    graph = {"nodes": ["palm_oil_usd", "soy_oil_usd", "oil_basket", "usd_sgd", "cpi_cooking_oil"],
             "edges": [{"from": "palm_oil_usd", "to": "oil_basket", "type": "assumed log weight", "weight": .5},
                       {"from": "soy_oil_usd", "to": "oil_basket", "type": "assumed log weight", "weight": .5}] +
             [{"from": "oil_basket" if r["term"].startswith("oil") else "usd_sgd", "to": "cpi_cooking_oil",
               "lag_months": int(r["term"][-1]), "type": "estimated predictive association", **r}
              for r in relationships["coefficients"] if r["term"].startswith(("oil", "fx"))]}
    write_json(directory / "driver_graph.json", graph, exclusive=True)
    (directory / "outlook.md").write_text(outlook_note(forecast, result["effects"], relationships, news))
    render_fan(panel.cpi_cooking_oil.dropna(), forecast, directory / "fan_chart.png")
    source_files = list((root / "src").rglob("*.py"))
    code_hash = digest(b"".join(str(p.relative_to(root)).encode() + p.read_bytes() for p in sorted(source_files)))
    manifest = {"run_id": run_id, "created_at": utc_now(), "source_snapshot": snapshot,
                "historical_snapshot": protocol["snapshot_id"], "code_sha256": code_hash,
                "config": config, "python": platform.python_version(),
                "requirements_sha256": digest((root / "requirements.lock").read_bytes()),
                "artifacts": {p.name: digest(p.read_bytes()) for p in sorted(directory.iterdir()) if p.is_file()},
                "selected_models": result["selected_models"], "strict_pit": result["strict_pit"],
                "historical_mode": "reconstructed", "news_in_historical_forecast": False,
                "scope": "cooking-oil vertical slice only; no food-panel acceptance claim"}
    write_json(directory / "manifest.json", manifest, exclusive=True)
    write_json(root / "artifacts/latest.json", {"run_id": run_id, "directory": str(directory)})
    progress(f"Slice artifacts saved to {directory}")
    return {"run_id": run_id, "directory": str(directory), "forecast": forecast,
            "selected_models": result["selected_models"], "bands": protocol["unchanged_band_pct"]}
