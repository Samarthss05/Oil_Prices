"""Immutable snapshots. Historical reconstruction and actual availability never share a clock."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import duckdb
import numpy as np
import pandas as pd


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def write_json(path: Path, value: Any, *, exclusive: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, indent=2, default=str, allow_nan=False) + "\n"
    if exclusive:
        with path.open("x") as stream:
            stream.write(text)
    else:
        temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
        temporary.write_text(text)
        temporary.replace(path)


class Store:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.data = self.root / "data"
        for directory in ("raw/blobs", "raw/retrievals", "observations", "snapshots"):
            (self.data / directory).mkdir(parents=True, exist_ok=True)

    def save_raw(self, source: str, url: str, body: bytes, metadata: dict | None = None) -> dict:
        raw_hash = digest(body)
        path = self.data / "raw/blobs" / raw_hash
        try:
            with path.open("xb") as stream:
                stream.write(body)
        except FileExistsError:
            if digest(path.read_bytes()) != raw_hash:
                raise ValueError("Raw content integrity failure")
        record = {"source": source, "url": url, "raw_hash": raw_hash,
                  "raw_path": str(path.relative_to(self.root)), "retrieved_at": utc_now(),
                  "metadata": metadata or {}}
        write_json(self.data / "raw/retrievals" / f"{uuid4().hex}.json", record, exclusive=True)
        return record

    def ingest(self, records: list[dict], config: dict | None = None) -> str:
        frame = pd.DataFrame(records)
        required = {"series_id", "period", "value", "source", "retrieved_at", "raw_hash",
                    "assumed_available_at", "release_assumption", "source_url", "unit"}
        if not required.issubset(frame):
            raise ValueError(f"Missing observation fields: {required - set(frame)}")
        frame["period"] = pd.to_datetime(frame.period)
        if (frame.period.dt.day != 1).any() or frame.duplicated(["series_id", "period"]).any():
            raise ValueError("Expected unique monthly observations at month start")
        if not np.isfinite(frame.value).all() or (frame.value <= 0).any():
            raise ValueError("Slice price observations must be finite and positive")
        for col in ("retrieved_at", "assumed_available_at"):
            frame[col] = pd.to_datetime(frame[col], utc=True)
        frame["available_at"] = frame.retrieved_at  # Never the historical inferred date.
        frame["provenance"] = "reconstructed"
        snapshot_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "_" + uuid4().hex[:12]
        frame["snapshot_id"] = snapshot_id
        path = self.data / "observations" / f"{snapshot_id}.parquet"
        frame.to_parquet(path, index=False)
        manifest = {"snapshot_id": snapshot_id, "created_at": utc_now(), "rows": len(frame),
                    "file": str(path.relative_to(self.root)), "file_sha256": digest(path.read_bytes()),
                    "raw_hashes": sorted(frame.raw_hash.unique().tolist()), "config": config or {},
                    "history_status": "reconstructed; prospective availability starts at retrieval"}
        write_json(self.data / "snapshots" / f"{snapshot_id}.json", manifest, exclusive=True)
        return snapshot_id

    def latest_snapshot(self) -> str:
        paths = sorted((self.data / "snapshots").glob("*.json"))
        if not paths:
            raise FileNotFoundError("No observations. Run ingest first.")
        return max(paths, key=lambda p: pd.Timestamp(json.loads(p.read_text())["created_at"])).stem

    def observations(self, snapshot_id: str | None = None) -> pd.DataFrame:
        if snapshot_id:
            manifest = json.loads((self.data / "snapshots" / f"{snapshot_id}.json").read_text())
            path = self.root / manifest["file"]
            if digest(path.read_bytes()) != manifest["file_sha256"]:
                raise ValueError("Snapshot checksum changed")
            paths = [str(path)]
        else:
            paths = []
            for entry in sorted((self.data / "snapshots").glob("*.json")):
                manifest = json.loads(entry.read_text())
                path = self.root / manifest["file"]
                if digest(path.read_bytes()) != manifest["file_sha256"]:
                    raise ValueError("Snapshot checksum changed")
                paths.append(str(path))
        if not paths:
            return pd.DataFrame()
        with duckdb.connect() as db:
            return db.execute("SELECT * FROM read_parquet(?, union_by_name=true)", [paths]).df()

    def as_of(self, origin: str | pd.Timestamp, mode: Literal["prospective", "reconstructed"] = "prospective",
              snapshot_id: str | None = None) -> pd.DataFrame:
        if mode not in {"prospective", "reconstructed"}:
            raise ValueError("Unknown information-set mode")
        if mode == "reconstructed" and not snapshot_id:
            raise ValueError("Reconstructed replay requires an explicit frozen snapshot ID")
        frame = self.observations(snapshot_id)
        if frame.empty:
            return frame
        cutoff = pd.Timestamp(origin)
        if cutoff.tzinfo is None:
            raise ValueError("Origin must include a timezone")
        clock = "available_at" if mode == "prospective" else "assumed_available_at"
        selected = frame.loc[frame[clock] <= cutoff].copy()
        selected = selected.sort_values(["retrieved_at", "snapshot_id"])
        selected = selected.drop_duplicates(["series_id", "period"], keep="last")
        selected["information_set"] = mode
        return selected.sort_values(["series_id", "period"]).reset_index(drop=True)

    def panel(self, origin: str | pd.Timestamp, mode: str, snapshot_id: str | None = None) -> pd.DataFrame:
        rows = self.as_of(origin, mode, snapshot_id)
        if rows.empty:
            return pd.DataFrame()
        panel = rows.pivot(index="period", columns="series_id", values="value").sort_index()
        return panel.asfreq("MS")  # Missing months remain missing; never back-fill.
