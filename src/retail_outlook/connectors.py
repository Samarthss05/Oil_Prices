"""Three public-source adapters for the cooking-oil slice (not vintage archives)."""
from __future__ import annotations

import html
import io
import json
import re
from urllib.parse import urlencode, urljoin

import numpy as np
import pandas as pd

from retail_outlook.http import Fetcher
from retail_outlook.storage import Store

WB_LANDING = "https://www.worldbank.org/en/research/commodity-markets"
WB_VERIFIED_URL = ("https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/"
                   "CMO-Historical-Data-Monthly.xlsx")
SINGSTAT = "https://tablebuilder.singstat.gov.sg/api/table/tabledata/"


def assumed_release(period: str | pd.Timestamp, day: int) -> str:
    month = pd.Timestamp(period).to_period("M") + 1
    return month.to_timestamp().replace(day=day, hour=23, minute=59, second=59).tz_localize(
        "Asia/Singapore").tz_convert("UTC").isoformat()


def observation(series: str, period: pd.Timestamp, value: float, unit: str, source: str,
                raw: dict, day: int) -> dict:
    return {"source": source, "series_id": series, "period": period.strftime("%Y-%m-01"),
            "value": value, "unit": unit, "source_url": raw["url"], "retrieved_at": raw["retrieved_at"],
            "raw_hash": raw["raw_hash"], "assumed_available_at": assumed_release(period, day),
            "release_assumption": f"Reconstructed: next-month day {day}, 23:59:59 Asia/Singapore; not verified",
            "provenance": "reconstructed"}


def parse_singstat(payload: dict, series_no: str, series_id: str, unit: str, source: str,
                   raw: dict, day: int) -> tuple[list[dict], int]:
    if payload.get("StatusCode") != 200 or "row" not in payload.get("Data", {}):
        raise ValueError("Unexpected SingStat API response")
    result = []
    count = 0
    for row in payload["Data"]["row"]:
        count += len(row.get("columns", []))
        if row["seriesNo"] != series_no:
            continue
        if row["uoM"].lower() != unit.lower():
            raise ValueError(f"Unexpected unit for {series_id}: {row['uoM']}")
        for cell in row["columns"]:
            if str(cell["value"]).strip().lower() in {"na", "n.a.", "na*", "-", "..", "…", "", "null"}:
                continue
            period = pd.to_datetime(cell["key"], format="%Y %b")
            value = float(cell["value"])
            if not np.isfinite(value) or value <= 0:
                raise ValueError("Nonpositive/malformed source price")
            result.append(observation(series_id, period, value, unit, source, raw, day))
    return result, count


def fetch_singstat(fetcher: Fetcher, table: str, label: str, series_no: str, series_id: str,
                   unit: str, source: str, day: int) -> list[dict]:
    records: dict[str, dict] = {}
    for offset in range(0, 100_000, 5000):
        url = SINGSTAT + table + "?" + urlencode({"search": label, "limit": 5000, "offset": offset})
        body, raw = fetcher.get(source, url)
        page, count = parse_singstat(json.loads(body), series_no, series_id, unit, source, raw, day)
        for row in page:
            if row["period"] in records and records[row["period"]]["value"] != row["value"]:
                raise ValueError("Conflicting duplicate period across source pages")
            records[row["period"]] = row
        if count < 5000:
            break
    else:
        raise ValueError("Pagination safety limit reached; refusing incomplete series")
    if not records:
        raise ValueError(f"Target series not found: {series_id}")
    ordered = sorted(records.values(), key=lambda r: r["period"])
    periods = pd.DatetimeIndex([r["period"] for r in ordered])
    if len(periods) != len(pd.date_range(periods.min(), periods.max(), freq="MS")):
        raise ValueError(f"Missing months in {series_id}; explicit handling required")
    return ordered


def parse_world_bank(body: bytes, raw: dict, day: int = 15) -> list[dict]:
    frame = pd.read_excel(io.BytesIO(body), sheet_name="Monthly Prices", header=None)
    candidates = [i for i in range(min(20, len(frame))) if "Palm oil" in frame.iloc[i].values]
    if len(candidates) != 1:
        raise ValueError("Cannot identify World Bank monthly-price header")
    header = candidates[0]
    result = []
    for label, series in (("Palm oil", "palm_oil_usd"), ("Soybean oil", "soy_oil_usd")):
        columns = np.where(frame.iloc[header].values == label)[0]
        if len(columns) != 1:
            raise ValueError(f"Missing/ambiguous WB series: {label}")
        col = columns[0]
        if str(frame.iloc[header + 1, col]).strip() != "($/mt)":
            raise ValueError("Expected USD per metric tonne")
        for _, row in frame.iloc[header + 2:].iterrows():
            if not re.fullmatch(r"\d{4}M\d{2}", str(row.iloc[0])):
                continue
            value = pd.to_numeric(row.iloc[col], errors="coerce")
            if pd.isna(value):
                continue
            if value <= 0:
                raise ValueError("Nonpositive WB price")
            period = pd.to_datetime(row.iloc[0], format="%YM%m")
            result.append(observation(series, period, float(value), "USD/metric tonne", "World Bank", raw, day))
    if not result:
        raise ValueError("Empty World Bank workbook")
    return result


def fetch_all(store: Store, config: dict) -> list[dict]:
    fetcher = Fetcher(store)
    days = config["release_days"]
    try:
        cpi = fetch_singstat(fetcher, "M213751", "Vegetable Oils", "1.01.5.1", "cpi_cooking_oil",
                             "Index", "SingStat", days["cpi_cooking_oil"])
        fx = fetch_singstat(fetcher, "M700051", "US Dollar", "1", "usd_sgd",
                            "Singapore Dollar Per US Dollar", "MAS via SingStat", days["usd_sgd"])
        landing, _ = fetcher.get("World Bank discovery", WB_LANDING)
        urls = re.findall(r'href=[\"\']([^\"\']*CMO-Historical-Data-Monthly\.xlsx[^\"\']*)',
                          html.unescape(landing.decode("utf-8")))
        if not urls:
            raise ValueError("World Bank monthly workbook link absent; source layout changed")
        url = urljoin(WB_LANDING, urls[0])
        body, raw = fetcher.get("World Bank", url)
        wb = parse_world_bank(body, raw, days["palm_oil_usd"])
        for series in ("palm_oil_usd", "soy_oil_usd"):
            periods = pd.DatetimeIndex([r["period"] for r in wb if r["series_id"] == series])
            if periods.has_duplicates or len(periods) != len(pd.date_range(periods.min(), periods.max(), freq="MS")):
                raise ValueError(f"Missing/duplicate World Bank months for {series}")
        return cpi + fx + wb
    finally:
        fetcher.close()
