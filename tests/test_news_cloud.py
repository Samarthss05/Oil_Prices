import io
import json
import tarfile
import urllib.error
from pathlib import Path

import pytest
import yaml

from retail_outlook.news import (article_record, collector_health, is_oil_relevant,
                                 next_gdelt_attempt, read_articles, retry_after_seconds, save_articles)
from retail_outlook.news_archive import pack, unpack


def test_retry_after_and_persisted_exponential_backoff(monkeypatch):
    monkeypatch.setattr("retail_outlook.news.random.uniform", lambda *args: 0.)
    now = "2026-09-17T00:00:00Z"
    error = urllib.error.HTTPError("https://example.test", 429, "throttle", {"Retry-After": "7200"}, None)
    due, count = next_gdelt_attempt({}, error, {"backoff_base_seconds": 900}, now)
    assert due.startswith("2026-09-17T02:00:00") and count == 1
    due, count = next_gdelt_attempt({"consecutive_failures": 4}, ValueError(), {"backoff_base_seconds": 900}, now)
    assert due.startswith("2026-09-17T04:00:00") and count == 5
    assert retry_after_seconds("Thu, 17 Sep 2026 03:00:00 GMT", now) == 10800


def test_archive_roundtrip_preserves_retrieval_cutoff_and_rejects_conflicts(tmp_path):
    source, destination = tmp_path/"source", tmp_path/"restored"
    a = article_record(url="https://example.test/oil", title="Crude palm oil stocks rise", retrieved_at="2026-09-17T12:00:00Z",
                       connector="fixture", raw_path="data/news/raw/a.bin", permission_url="https://example.test/rss")
    save_articles(source, [a])
    raw = source / "data/news/raw/a.bin"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"raw feed fixture")
    archive = tmp_path/"news.tar.gz"
    pack(source, archive)
    assert unpack(destination, archive) == 2
    assert read_articles(destination, "2026-09-17T11:59:59Z") == []
    assert read_articles(destination, "2026-09-17T12:00:00Z") == [a]
    (destination / "data/news/raw/a.bin").write_bytes(b"conflict")
    with pytest.raises(ValueError, match="Conflicting"):
        unpack(destination, archive)


def test_archive_rejects_path_traversal_and_symlinks(tmp_path):
    for name, kind in [("../escape", tarfile.REGTYPE), ("data/news/link", tarfile.SYMTYPE)]:
        path = tmp_path/"unsafe.tar.gz"
        with tarfile.open(path, "w:gz") as arc:
            info = tarfile.TarInfo(name)
            info.type = kind
            info.linkname = "/etc/passwd" if kind == tarfile.SYMTYPE else ""
            arc.addfile(info, io.BytesIO(b""))
            body = json.dumps({name: "bad"}).encode()
            info = tarfile.TarInfo("checksums.json")
            info.size = len(body)
            arc.addfile(info, io.BytesIO(body))
        with pytest.raises(ValueError, match="Unsafe"):
            unpack(tmp_path/"restored", path)


def test_health_ignores_future_runs_and_reports_schedule_gaps(tmp_path):
    directory = tmp_path/"data/news/runs"
    directory.mkdir(parents=True)
    for index, hour in enumerate([0, 6, 12]):
        value = dict(started_at=f"2026-09-17T{hour:02}:17:00Z", completed_at=f"2026-09-17T{hour:02}:18:00Z",
                     runner="github_actions", trigger="schedule", status="partial", sources=[dict(status="ok"), dict(status="error")])
        (directory/f"{index}.json").write_text(json.dumps(value))
    health = collector_health(tmp_path, "2026-09-17T06:30:00Z")
    assert health["github_runs"] == 2
    assert health["scheduled_expected_slots"] == 3
    assert health["scheduled_uptime_fraction"] == pytest.approx(2/3)
    assert health["source_success_fraction"] == .5


@pytest.mark.parametrize("title", ["CPO stocks fall", "Soybean oil exports", "New biodiesel mandate", "Palm oil export levy", "Cooking oil Singapore", "Minyak Sawit Merah", "Oil palm protection"])
def test_expanded_keyword_relevance(title):
    assert is_oil_relevant(dict(title=title))


def test_workflow_persists_archive_without_pushing_raw_data():
    root = Path(__file__).resolve().parents[1]
    workflow = yaml.load((root/".github/workflows/collect-news.yml").read_text(), Loader=yaml.BaseLoader)
    assert workflow["on"]["schedule"][0]["cron"] == "17 */3 * * *"
    steps = workflow["jobs"]["collect"]["steps"]
    assert any("restore-latest" in s.get("run", "") for s in steps)
    assert any(s.get("uses", "").startswith("actions/upload-artifact@") for s in steps)
    assert not any("git push" in s.get("run", "") for s in steps)
    upload = next(s for s in steps if s.get("id") == "upload")
    assert "steps.pack.outcome == 'success'" in upload["if"]


def test_all_source_failure_is_visible_to_scheduler(monkeypatch, tmp_path):
    from retail_outlook.news import main
    monkeypatch.setattr("sys.argv", ["news", "collect", "--root", str(tmp_path)])
    monkeypatch.setattr("retail_outlook.news.collect", lambda root: {"status": "failed"})
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1


def test_archive_cleanup_requires_current_backup_and_keeps_latest_eight(monkeypatch):
    from retail_outlook.news_archive import prune_superseded
    records = [{"id": i, "name": "news-archive", "expired": False,
                "created_at": f"2026-09-{i+1:02}T00:00:00Z", "workflow_run": {"id": 100+i}} for i in range(10)]
    monkeypatch.setattr("retail_outlook.news_archive.gh_json", lambda args: {"artifacts": records})
    deleted = []
    monkeypatch.setattr("retail_outlook.news_archive.subprocess.run", lambda cmd, **kw: deleted.append(cmd[-1]))
    with pytest.raises(RuntimeError, match="refusing cleanup"):
        prune_superseded("fixture/repo", "unknown")
    assert deleted == []
    result = prune_superseded("fixture/repo", "109")
    assert result == {"retained": 8, "superseded_copies_deleted": 2}
    assert {p.rsplit('/', 1)[-1] for p in deleted} == {"0", "1"}
