"""Checksum-verified transfer of the existing news store via Actions artifacts."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tarfile
import zipfile

MAX_BYTES = 512 * 1024 * 1024
ARTIFACT_NAME = "news-archive"


def pack(root: Path, output: Path) -> dict:
    files = sorted(p for p in (root / "data/news").rglob("*") if p.is_file() and not p.name.startswith("."))
    hashes = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    if sum(p.stat().st_size for p in files) > MAX_BYTES:
        raise ValueError("News archive exceeds 512 MB; move to a larger durable store before continuing")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, "w:gz") as archive:
        for path in files:
            archive.add(path, arcname=path.relative_to(root).as_posix(), recursive=False)
        body = json.dumps(hashes, sort_keys=True).encode()
        info = tarfile.TarInfo("checksums.json")
        info.size = len(body)
        archive.addfile(info, io.BytesIO(body))
    return {"files": len(files), "bytes": output.stat().st_size, "sha256": hashlib.sha256(output.read_bytes()).hexdigest()}


def unpack(root: Path, source: Path) -> int:
    with tarfile.open(source, "r:gz") as archive:
        members = archive.getmembers()
        if sum(m.size for m in members) > MAX_BYTES or len(members) > 100_000:
            raise ValueError("Archive limits exceeded")
        names = [m.name for m in members]
        if len(set(names)) != len(names) or "checksums.json" not in names:
            raise ValueError("Duplicate members or missing checksums")
        for m in members:
            parts = PurePosixPath(m.name).parts
            if not m.isfile() or m.name.startswith("/") or ".." in parts or (m.name != "checksums.json" and parts[:2] != ("data", "news")):
                raise ValueError("Unsafe archive path or type")
        hashes = json.load(archive.extractfile("checksums.json"))
        if set(hashes) != set(names) - {"checksums.json"}:
            raise ValueError("Checksum inventory differs")
        contents = {name: archive.extractfile(name).read() for name in hashes}
        for name, body in contents.items():
            if hashlib.sha256(body).hexdigest() != hashes[name]:
                raise ValueError("Archive checksum mismatch")
            destination = root / name
            if not destination.resolve().is_relative_to(root.resolve() / "data/news"):
                raise ValueError("Archive destination escapes news store")
            if destination.exists() and destination.read_bytes() != body:
                raise ValueError("Conflicting immutable news record")
        for name, body in contents.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                with path.open("xb") as stream:
                    stream.write(body)
    return len(contents)


def gh_json(args: list[str]) -> dict:
    return json.loads(subprocess.check_output(["gh", *args], text=True))


def restore_latest(root: Path, repo: str) -> dict:
    payload = gh_json(["api", f"repos/{repo}/actions/artifacts?name={ARTIFACT_NAME}&per_page=100"])
    candidates = [a for a in payload["artifacts"] if not a["expired"] and a["name"] == ARTIFACT_NAME]
    if not candidates:
        if payload.get("total_count", 0):
            raise RuntimeError("Prior archive expired; refusing to silently reset collection history")
        return {"restored": 0, "bootstrap": True}
    latest = max(candidates, key=lambda a: a["created_at"])
    body = subprocess.check_output(["gh", "api", f"repos/{repo}/actions/artifacts/{latest['id']}/zip"])
    with zipfile.ZipFile(io.BytesIO(body)) as zipped:
        if zipped.namelist() != ["news.tar.gz"] or zipped.getinfo("news.tar.gz").file_size > MAX_BYTES:
            raise ValueError("Unexpected artifact contents")
        target = root / "artifacts/transfer/news.tar.gz"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(zipped.read("news.tar.gz"))
    return {"restored": unpack(root, target), "artifact_id": latest["id"], "created_at": latest["created_at"]}


def prune_superseded(repo: str, current_run_id: str, keep: int = 8) -> dict:
    """Keep eight complete cumulative backups; never delete records from the store."""
    payload = gh_json(["api", f"repos/{repo}/actions/artifacts?name={ARTIFACT_NAME}&per_page=100"])
    items = sorted([a for a in payload["artifacts"] if a["name"] == ARTIFACT_NAME and not a["expired"]],
                   key=lambda a: a["created_at"], reverse=True)
    if not items or str(items[0].get("workflow_run", {}).get("id")) != current_run_id:
        raise RuntimeError("Current run's cumulative backup not confirmed; refusing cleanup")
    for item in items[keep:]:
        subprocess.run(["gh", "api", "--method", "DELETE", f"repos/{repo}/actions/artifacts/{item['id']}"], check=True)
    return {"retained": min(keep, len(items)), "superseded_copies_deleted": max(0, len(items)-keep)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["pack", "unpack", "restore-latest", "prune"])
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--file", type=Path, default=Path("artifacts/transfer/news.tar.gz"))
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", "Samarthss05/Oil_Prices"))
    args = parser.parse_args()
    root = args.root.resolve()
    path = args.file if args.file.is_absolute() else root / args.file
    if args.command == "prune":
        result = prune_superseded(args.repo, os.environ["GITHUB_RUN_ID"])
    elif args.command == "restore-latest":
        result = restore_latest(root, args.repo)
    else:
        result = pack(root, path) if args.command == "pack" else {"restored": unpack(root, path)}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
