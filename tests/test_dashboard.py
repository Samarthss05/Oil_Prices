from pathlib import Path

import json
import shutil

import numpy as np
import pandas as pd
import yaml


def test_saved_slice_page_renders(tmp_path, monkeypatch):
    """Build synthetic artifacts offline; this must also run in a clean clone."""
    from streamlit.testing.v1 import AppTest
    from retail_outlook.connectors import assumed_release
    from retail_outlook.pipeline import run
    from retail_outlook.news import article_record, save_articles
    from retail_outlook.storage import Store

    project = Path(__file__).resolve().parents[1]
    shutil.copytree(project / "configs", tmp_path / "configs")
    shutil.copy(project / "requirements.lock", tmp_path / "requirements.lock")
    config_path = tmp_path / "configs/slice.yaml"
    config = yaml.safe_load(config_path.read_text())
    config.update(models=["seasonal_naive", "random_walk"], samples=40, bootstrap_repetitions=10)
    config_path.write_text(yaml.safe_dump(config))
    rng = np.random.default_rng(18)
    periods = pd.date_range("2015-01-01", "2025-12-01", freq="MS")
    records = []
    for name, base in [("cpi_cooking_oil", 100), ("palm_oil_usd", 700),
                       ("soy_oil_usd", 800), ("usd_sgd", 1.35)]:
        values = base * np.exp(np.cumsum(rng.normal(0, .01, len(periods))))
        for period, value in zip(periods, values):
            records.append(dict(series_id=name, period=str(period.date()), value=value, source="synthetic",
                unit="test", source_url="https://example.test", retrieved_at="2026-01-01T00:00:00Z",
                raw_hash="synthetic", assumed_available_at=assumed_release(period, 28),
                release_assumption="synthetic fixture"))
    Store(tmp_path).ingest(records)
    save_articles(tmp_path, [article_record(url=f"https://example.test/{number}", title="New biodiesel mandate",
        retrieved_at=retrieved, connector="fixture", raw_path="fixture", permission_url="fixture")
        for number, retrieved in enumerate(["2026-01-01T00:00:00Z", "2099-01-01T00:00:00Z"])])
    result = run(tmp_path, collect_news=False, progress=lambda _: None)
    news = json.loads((Path(result["directory"])/"news.json").read_text())
    assert news["eligible_articles"] == news["oil_stories"] == news["collector_health"]["relevant_stories"] == 1
    monkeypatch.setenv("RETAIL_OUTLOOK_ROOT", str(tmp_path))
    script = project / "src/retail_outlook/dashboard.py"
    app = AppTest.from_file(script).run(timeout=30)
    assert not app.exception
    assert len(app.metric) == 3
    assert len(app.dataframe) >= 4
