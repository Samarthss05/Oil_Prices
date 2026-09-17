from pathlib import Path

import pytest


@pytest.mark.skipif(not Path("artifacts/latest.json").exists(), reason="Run the data pipeline before the UI artifact test")
def test_saved_slice_page_renders():
    from streamlit.testing.v1 import AppTest
    script = Path(__file__).resolve().parents[1] / "src/retail_outlook/dashboard.py"
    app = AppTest.from_file(script).run(timeout=30)
    assert not app.exception
    assert len(app.metric) == 3
    assert len(app.dataframe) >= 4
