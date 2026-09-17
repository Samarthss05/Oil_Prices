from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
import subprocess
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="Singapore cooking-oil research slice")
    parser.add_argument("command", choices=["run", "ingest", "collect-news", "extract-news", "annotations", "dashboard"])
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--refresh", action="store_true", help="Retrieve new structured source snapshots")
    parser.add_argument("--no-news", action="store_true", help="Use already collected news; no network collection")
    parser.add_argument("--open", action="store_true", help="Open Streamlit after building artifacts")
    parser.add_argument("--port", type=int, default=8501)
    args = parser.parse_args()
    root = args.root.resolve()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if args.command == "run":
        from retail_outlook.pipeline import run
        result = run(root, args.refresh, not args.no_news)
        print(json.dumps({k: v for k, v in result.items() if k != "forecast"}, indent=2))
    elif args.command == "ingest":
        import yaml
        from retail_outlook.storage import Store
        from retail_outlook.connectors import fetch_all
        store = Store(root)
        config = yaml.safe_load((root / "configs/slice.yaml").read_text())
        print(store.ingest(fetch_all(store, config), config))
    elif args.command in {"collect-news", "extract-news", "annotations"}:
        from retail_outlook.news import collect, extract_all, export_annotations
        result = {"collect-news": collect, "extract-news": extract_all, "annotations": export_annotations}[args.command](root)
        print(json.dumps(result, indent=2))
    if args.command == "dashboard" or (args.command == "run" and args.open):
        env = dict(os.environ, RETAIL_OUTLOOK_ROOT=str(root))
        command = [sys.executable, "-m", "streamlit", "run", str(root / "src/retail_outlook/dashboard.py"),
                   "--server.address", "127.0.0.1", "--server.port", str(args.port),
                   "--browser.gatherUsageStats", "false", "--server.headless", "true"]
        raise SystemExit(subprocess.call(command, cwd=root, env=env))


if __name__ == "__main__":
    main()
