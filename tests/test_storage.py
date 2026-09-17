import pandas as pd
import pytest

from retail_outlook.storage import Store


def record(value=100., retrieved="2026-09-17T08:00:00Z", period="2020-01-01"):
    return dict(source="fixture", series_id="cpi_cooking_oil", period=period, value=value, unit="Index",
                retrieved_at=retrieved, raw_hash="fixture-hash", source_url="https://example.test/data",
                assumed_available_at="2020-02-28T15:59:59Z", release_assumption="fixture reconstructed")


def test_historical_values_are_not_prospectively_available(tmp_path):
    s = Store(tmp_path)
    snapshot = s.ingest([record()])
    assert s.as_of("2020-03-01T00:00:00Z").empty
    assert len(s.as_of("2020-03-01T00:00:00Z", "reconstructed", snapshot)) == 1
    assert s.as_of("2020-02-28T15:59:58Z", "reconstructed", snapshot).empty
    with pytest.raises(ValueError, match="frozen snapshot"):
        s.as_of("2020-03-01T00:00:00Z", "reconstructed")


def test_future_revision_does_not_rewrite_prior_information_set(tmp_path):
    s = Store(tmp_path)
    first = s.ingest([record()])
    s.ingest([record(value=999., retrieved="2026-10-01T00:00:00Z")])
    assert s.as_of("2026-09-18T00:00:00Z").value.tolist() == [100.]
    assert s.as_of("2026-10-02T00:00:00Z").value.tolist() == [999.]
    assert s.as_of("2020-03-01T00:00:00Z", "reconstructed", first).value.tolist() == [100.]


def test_raw_files_are_immutable_and_retrievals_append(tmp_path):
    s = Store(tmp_path)
    a = s.save_raw("test", "https://example.test", b"original")
    b = s.save_raw("test", "https://example.test", b"original")
    c = s.save_raw("test", "https://example.test", b"revised")
    assert a["raw_hash"] == b["raw_hash"] != c["raw_hash"]
    assert len(list((s.data / "raw/blobs").iterdir())) == 2
    assert len(list((s.data / "raw/retrievals").iterdir())) == 3


def test_missing_month_is_not_filled(tmp_path):
    s = Store(tmp_path)
    r = record(period="2020-03-01")
    sid = s.ingest([record(), r])
    panel = s.panel("2026-09-18T00:00:00Z", "reconstructed", sid)
    assert pd.isna(panel.loc["2020-02-01", "cpi_cooking_oil"])


def test_snapshot_tampering_is_detected(tmp_path):
    s = Store(tmp_path)
    sid = s.ingest([record()])
    (s.data / "observations" / f"{sid}.parquet").write_bytes(b"changed")
    with pytest.raises(ValueError, match="checksum"):
        s.observations(sid)
    with pytest.raises(ValueError, match="checksum"):
        s.as_of("2026-09-18T00:00:00Z")
