"""Offline tests of timestamp boundaries, versioning and abstaining extraction."""
import dataclasses
import json
import urllib.error

import pytest

from retail_outlook.news import (
    NewsEvent, article_record, canonical_url, collection_lock, extract_local,
    load_config, news_indices, parse_gdelt, parse_rss, read_articles,
    save_articles, timestamp,
    event_schema, _fetch,
)


def article(title="Palm oil prices rise", retrieved="2026-09-17T12:00:00Z", url="https://example.com/news", published=None):
    return article_record(url=url, title=title, retrieved_at=retrieved,
                          connector="test", raw_path="fixture", permission_url="fixture", published=published)


def test_timestamp_requires_timezone():
    assert timestamp("2026-09-17T20:00:00+08:00") == "2026-09-17T12:00:00Z"
    assert timestamp("20260917T120000Z") == "2026-09-17T12:00:00Z"
    assert timestamp("Thu, 17 Sep 2026 12:00:00 GMT") == "2026-09-17T12:00:00Z"
    assert timestamp("2026-09-17") is None
    assert timestamp("2026-09-17T12:00:00") is None
    assert timestamp("bad") is None


def test_gdelt_seen_is_never_publisher_date():
    body = json.dumps({"articles": [{"url": "https://example.com/oil", "title": "Palm oil prices rise", "seendate": "20260916T120000Z"}]}).encode()
    record = parse_gdelt(body, "2026-09-17T12:00:00Z", "fixture", {"gdelt": {"permission_url": "fixture"}})[0]
    assert record["publish_time"] is None
    assert record["gdelt_seen_at"] == "2026-09-16T12:00:00Z"
    assert record["available_at"] == "2026-09-17T12:00:00Z"
    assert record["publisher_timestamp_verified"] is False


def test_empty_gdelt_payload_is_unknown_coverage_not_no_news():
    with pytest.raises(ValueError, match="coverage unknown"):
        parse_gdelt(b"{}", "2026-09-17T12:00:00Z", "fixture", {})


def test_rss_uses_published_but_not_atom_updated():
    feed = {"name": "official", "permission_url": "fixture"}
    xml = b'<rss><channel><item><title>Palm oil</title><link>https://example.com/oil</link><description>Official feed summary.</description><pubDate>Thu, 17 Sep 2026 10:00:00 GMT</pubDate></item></channel></rss>'
    record = parse_rss(xml, "2026-09-17T12:00:00Z", "fixture", feed, {})[0]
    assert record["publish_time"] == "2026-09-17T10:00:00Z"
    assert record["feed_description"] == "Official feed summary."
    assert "official_publisher_supplied" in record["rights"]
    atom = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Palm oil</title><link href="https://example.com/oil"/><updated>2026-09-17T10:00:00Z</updated></entry></feed>'
    assert parse_rss(atom, "2026-09-17T12:00:00Z", "fixture", feed, {})[0]["publish_time"] is None


def test_missing_published_still_uses_retrieval(tmp_path):
    save_articles(tmp_path, [article()])
    assert read_articles(tmp_path, "2026-09-17T11:59:59Z") == []
    assert len(read_articles(tmp_path, "2026-09-17T12:00:00Z")) == 1


def test_future_publication_is_not_eligible(tmp_path):
    save_articles(tmp_path, [article(published="2026-09-18T12:00:00Z")])
    assert read_articles(tmp_path, "2026-09-17T12:00:00Z") == []


def test_dedup_and_revision_never_leak_or_overwrite(tmp_path):
    original = article()
    revised = article("Palm oil prices fall", "2026-09-18T12:00:00Z")
    assert save_articles(tmp_path, [original]) == 1
    assert save_articles(tmp_path, [article(retrieved="2026-09-17T13:00:00Z")]) == 0
    assert save_articles(tmp_path, [revised]) == 1
    assert read_articles(tmp_path, "2026-09-17T14:00:00Z")[0]["title"] == original["title"]
    latest = read_articles(tmp_path, "2026-09-18T13:00:00Z")[0]
    assert latest["title"] == revised["title"]
    assert latest["first_seen_at"] == original["first_seen_at"]
    assert latest["available_at"] == revised["retrieved_at"]
    # A subsequent reversion is still a new version, not a reuse of old timing.
    assert save_articles(tmp_path, [article(retrieved="2026-09-19T12:00:00Z")]) == 1
    assert read_articles(tmp_path, "2026-09-19T13:00:00Z")[0]["title"] == original["title"]
    assert len(list((tmp_path / "data/news/articles").glob("*.json"))) == 3


def test_tracking_parameters_do_not_duplicate_url():
    assert canonical_url("https://example.com/news?utm_source=feed&id=1#anchor") == "https://example.com/news?id=1"
    with pytest.raises(ValueError):
        canonical_url("javascript:alert(1)")


@pytest.mark.parametrize("headline", [
    "Indonesia denies palm oil export ban", "Indonesia may ban palm oil exports",
    "Palm oil prices do not rise", "Will palm oil prices rise?",
    "Indonesia lifts palm oil export ban", "No palm oil price surge",
    "Palm oil prices could rise after flood", "Palm oil is good for cooking",
])
def test_extraction_abstains_when_negated_uncertain_or_unsupported(headline):
    event = extract_local(article(headline))
    assert event.event_type == "UNKNOWN"
    assert event.direction == "UNKNOWN"
    assert event.certainty == "UNKNOWN"
    assert event.magnitude == "UNKNOWN"


def test_extraction_explicit_direction_only():
    event = extract_local(article())
    assert event.direction == "cost_up"
    assert event.event_type == "price_move"
    assert event.evidence_text == "Palm oil prices rise"
    ban = extract_local(article("Indonesia bans palm oil exports"))
    assert ban.event_type == "export_restriction"
    assert ban.direction == "UNKNOWN"  # No price or global supply inference.


def test_extraction_schema_rejects_unknown_fields_and_invalid_values():
    event = dataclasses.asdict(extract_local(article()))
    with pytest.raises(ValueError):
        NewsEvent(**dict(event, direction="bullish"))
    with pytest.raises(TypeError):
        NewsEvent(**dict(event, extra="invented"))
    with pytest.raises(ValueError):
        NewsEvent(**dict(event, magnitude=9))
    with pytest.raises(ValueError):
        NewsEvent(**dict(event, countries="Indonesia"))
    assert event_schema()["additionalProperties"] is False


def test_429_does_not_trigger_immediate_retry(monkeypatch):
    attempts = []

    def throttled(*args, **kwargs):
        attempts.append(1)
        raise urllib.error.HTTPError("https://example.com", 429, "Too Many Requests", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", throttled)
    with pytest.raises(urllib.error.HTTPError):
        _fetch("https://example.com", {"max_attempts": 2})
    assert len(attempts) == 1


def test_story_weight_is_bounded_and_extraction_time_is_enforced():
    first = dataclasses.asdict(extract_local(article(), "2026-09-18T12:00:00Z"))
    second = dataclasses.asdict(extract_local(article(url="https://syndicated.example.com/news"), "2026-09-18T12:00:00Z"))
    first["source_credibility"], second["source_credibility"] = 0.7, 0.9
    assert news_indices([first, second], "2026-09-17T23:00:00Z") == []
    index = news_indices([first, second], "2026-09-18T13:00:00Z")[0]
    assert index["event_count"] == 1
    assert index["weighted_event_count"] == pytest.approx(0.9)
    assert index["weighted_direction"] == pytest.approx(0.9)


def test_collector_lock_rejects_overlap(tmp_path):
    with collection_lock(tmp_path):
        with pytest.raises(RuntimeError):
            with collection_lock(tmp_path):
                pass


def test_paid_backend_cannot_be_enabled(tmp_path):
    (tmp_path / "configs").mkdir()
    config = {"monthly_llm_cap_usd": 50, "extraction_backend": "local_rules", "paid_calls_enabled": True}
    (tmp_path / "configs/news.yaml").write_text(json.dumps(config))
    with pytest.raises(ValueError):
        load_config(tmp_path)
