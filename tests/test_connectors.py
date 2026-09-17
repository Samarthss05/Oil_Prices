import io

import pandas as pd
import pytest

from retail_outlook.connectors import assumed_release, fetch_singstat, parse_singstat, parse_world_bank

RAW = dict(url="https://example.test/data", retrieved_at="2026-09-17T08:00:00Z", raw_hash="test")


def payload(columns, unit="Index"):
    return {"StatusCode": 200, "Data": {"row": [dict(seriesNo="1.01.5.1", rowText="Vegetable Oils",
                                                    uoM=unit, columns=columns)]}}


def test_units_missing_values_and_release_lag():
    rows, n = parse_singstat(payload([dict(key="2020 Jan", value="100"), dict(key="2020 Feb", value="na")]),
                             "1.01.5.1", "cpi_cooking_oil", "Index", "SingStat", RAW, 28)
    assert n == 2 and len(rows) == 1
    assert rows[0]["assumed_available_at"] == "2020-02-28T15:59:59+00:00"
    assert rows[0]["provenance"] == "reconstructed"
    with pytest.raises(ValueError, match="unit"):
        parse_singstat(payload([], "USD"), "1.01.5.1", "cpi_cooking_oil", "Index", "SingStat", RAW, 28)


def test_pagination_series_can_straddle_pages():
    class Fetch:
        calls = 0

        def get(self, source, url):
            import json
            self.calls += 1
            if self.calls == 1:
                p = payload([dict(key="2020 Jan", value="100")])
                p["Data"]["row"].append(dict(seriesNo="other", columns=[{}] * 4999))
            else:
                assert "offset=5000" in url
                p = payload([dict(key="2020 Feb", value="101")])
            return json.dumps(p).encode(), RAW
    fetch = Fetch()
    rows = fetch_singstat(fetch, "id", "Vegetable Oils", "1.01.5.1", "cpi_cooking_oil", "Index", "SingStat", 28)
    assert fetch.calls == 2 and [r["value"] for r in rows] == [100, 101]


def test_world_bank_parser_uses_named_columns_not_fixed_offsets():
    data = [["Title", None, None], [None, "Soybean oil", "Palm oil"],
            [None, "($/mt)", "($/mt)"], ["2020M01", 800, 700], ["2020M02", 810, 710]]
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame(data).to_excel(writer, sheet_name="Monthly Prices", index=False, header=False)
    rows = parse_world_bank(buffer.getvalue(), RAW)
    assert [r["value"] for r in rows if r["series_id"] == "palm_oil_usd"] == [700, 710]
    assert assumed_release("2020-12-01", 15).startswith("2021-01-15")
