"""Metadata-only, prospective news collection and conservative local extraction.

No paid service is invoked. JSON is a YAML subset, making the bundled config
readable without a YAML dependency. All content and collection manifests are
append-only; as-of selection uses the version's retrieval time, never GDELT's
discovery timestamp in place of a publisher's timestamp.
"""
from __future__ import annotations

import argparse
import csv
import dataclasses
import datetime as dt
import email.utils
import fcntl
import hashlib
import html
import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

LOG = logging.getLogger(__name__)
UTC = dt.timezone.utc
SCHEMA_VERSION = 1
LOCAL_EXTRACTOR_VERSION = "local-rules-v1-unvalidated"
DIRECTIONS = {"supply_up", "supply_down", "demand_up", "demand_down", "cost_up", "cost_down", "UNKNOWN"}
EVENT_TYPES = {"export_restriction", "tariff", "disease_outbreak", "weather_shock", "harvest_report", "energy_price_shock", "currency_move", "shipping_disruption", "policy_subsidy_change", "conflict", "price_move", "UNKNOWN"}


def now_utc() -> str:
    return dt.datetime.now(UTC).isoformat().replace("+00:00", "Z")


def timestamp(value: str | None) -> str | None:
    """Normalize aware dates only; never invent a timezone for ambiguous dates."""
    if not value:
        return None
    try:
        if re.fullmatch(r"\d{8}T\d{6}Z", value):
            parsed = dt.datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        else:
            try:
                parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                parsed = email.utils.parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")
    except (ValueError, TypeError, OverflowError):
        return None


def _instant(value: str) -> dt.datetime:
    normalized = timestamp(value)
    if normalized is None:
        raise ValueError(f"UTC-aware timestamp required: {value!r}")
    return dt.datetime.fromisoformat(normalized.replace("Z", "+00:00"))


def digest(value: str | bytes) -> str:
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def canonical_url(url: str) -> str:
    parts = urllib.parse.urlsplit(url.strip())
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname or parts.username:
        raise ValueError("Only public HTTP(S) article URLs are supported")
    query = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
             if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}]
    return urllib.parse.urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or "/", urllib.parse.urlencode(query), ""))


def plain_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value))).strip()


def story_key(title: str) -> str:
    """Exact normalized headline grouping only; no claim of semantic clustering."""
    return digest(re.sub(r"[^\w\s]", "", plain_text(title).casefold()))


def load_config(root: Path) -> dict[str, Any]:
    path = root / "configs/news.yaml"
    text = path.read_text()
    try:
        config = json.loads(text)
    except json.JSONDecodeError:
        import yaml
        config = yaml.safe_load(text)
    if config.get("paid_calls_enabled") or config.get("extraction_backend") != "local_rules":
        raise ValueError("The vertical slice permits local extraction only; no paid backend is implemented")
    if config.get("paid_historical_backfill_enabled"):
        raise ValueError("Paid historical backfill is disabled until independently evaluated and implemented")
    if not 0 <= float(config["monthly_llm_cap_usd"]) <= 50:
        raise ValueError("Development LLM hard cap must be between USD 0 and USD 50")
    return config


@contextmanager
def collection_lock(root: Path) -> Iterator[None]:
    directory = root / "data/news"
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".collector.lock").open("a+") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("Another news collector is already running") from exc
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def write_once(path: Path, value: dict[str, Any]) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False, allow_nan=False)
            handle.write("\n")
        return True
    except FileExistsError:
        return False


def credibility(source: str, config: dict[str, Any]) -> float:
    for domain, score in config.get("source_credibility", {}).items():
        if source == domain or source.endswith("." + domain):
            return min(1.0, max(0.0, float(score)))
    return min(1.0, max(0.0, float(config.get("default_source_credibility", 0.5))))


def article_record(*, url: str, title: str, retrieved_at: str, connector: str,
                   raw_path: str, permission_url: str, published: str | None = None,
                   seen: str | None = None, feed_description: str = "", config: dict[str, Any] | None = None) -> dict[str, Any]:
    url = canonical_url(url)
    retrieved_at = timestamp(retrieved_at) or ""
    if not retrieved_at:
        raise ValueError("Retrieval timestamp must be timezone aware")
    source = urllib.parse.urlsplit(url).hostname or "unknown"
    title = plain_text(title)[:4000]
    feed_description = plain_text(feed_description)[:20000]
    pub_time = timestamp(published)
    content_hash = digest(json.dumps({"url": url, "title": title, "feed_description": feed_description, "publish_time": pub_time}, sort_keys=True))
    return {
        "schema_version": SCHEMA_VERSION,
        "article_id": digest(url), "content_hash": content_hash,
        "story_id": story_key(title), "url": url, "source": source,
        "title": title, "feed_description": feed_description, "publish_time": pub_time,
        "publish_time_raw": published, "publisher_timestamp_verified": pub_time is not None,
        "publish_time_provenance": "publisher_rss_timestamp" if pub_time else "unknown",
        "gdelt_seen_at": timestamp(seen), "retrieved_at": retrieved_at,
        "first_seen_at": retrieved_at, "available_at": max([retrieved_at] + ([pub_time] if pub_time else []), key=_instant),
        "connector": connector, "raw_path": raw_path, "permission_url": permission_url,
        "rights": "official_publisher_supplied_rss_metadata_and_description; publisher_rights_retained" if feed_description else "metadata_and_link_only; original publisher retains article rights",
        "source_credibility": credibility(source, config or {}),
        "history_mode": "verified_pit_from_retrieval",
    }


def parse_gdelt(body: bytes, retrieved_at: str, raw_path: str, config: dict[str, Any]) -> list[dict[str, Any]]:
    payload = json.loads(body)
    if not isinstance(payload, dict) or "articles" not in payload or not isinstance(payload["articles"], list):
        raise ValueError("GDELT missing articles schema (including empty {}): effective coverage unknown, not a successful zero-news result")
    output = []
    for item in payload.get("articles", []):
        try:
            output.append(article_record(url=item["url"], title=item.get("title", ""),
                retrieved_at=retrieved_at, connector="gdelt_doc", raw_path=raw_path,
                permission_url=config["gdelt"]["permission_url"], seen=item.get("seendate"), config=config))
        except (ValueError, KeyError, TypeError):
            LOG.warning("Skipped malformed GDELT article")
    return output


def parse_rss(body: bytes, retrieved_at: str, raw_path: str, feed: dict[str, Any], config: dict[str, Any]) -> list[dict[str, Any]]:
    # ElementTree does not resolve external entities. Reject declarations anyway.
    if b"<!DOCTYPE" in body.upper() or b"<!ENTITY" in body.upper():
        raise ValueError("XML declarations with entities are not accepted")
    root = ET.fromstring(body)
    def local_name(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]
    if local_name(root.tag) not in {"rss", "feed", "RDF"}:
        raise ValueError("Response is not RSS/Atom")
    output = []
    for item in root.iter():
        if local_name(item.tag) not in {"item", "entry"}:
            continue
        fields: dict[str, str] = {}
        for child in item:
            name = local_name(child.tag)
            text = "".join(child.itertext()).strip()
            if name == "link" and child.get("href") and child.get("rel", "alternate") == "alternate":
                fields["link"] = child.attrib["href"]
            elif name not in fields:
                fields[name] = text
        try:
            output.append(article_record(url=fields["link"], title=fields.get("title", ""),
                retrieved_at=retrieved_at, connector=feed["name"], raw_path=raw_path,
                permission_url=feed["permission_url"],
                published=fields.get("pubDate") or fields.get("published") or fields.get("date"),
                feed_description=fields.get("description") or fields.get("summary") or fields.get("content") or "", config=config))
        except (ValueError, KeyError):
            LOG.warning("Skipped malformed RSS item from %s", feed["name"])
    return output


def save_articles(root: Path, articles: list[dict[str, Any]]) -> int:
    directory = root / "data/news/articles"
    directory.mkdir(parents=True, exist_ok=True)
    saved = 0
    for article in articles:
        existing = list(directory.glob(article["article_id"] + "_*.json"))
        if existing:
            versions = [json.loads(p.read_text()) for p in existing]
            article["first_seen_at"] = min([article["first_seen_at"]] + [v["first_seen_at"] for v in versions], key=_instant)
            latest = max(versions, key=lambda v: _instant(v["retrieved_at"]))
            if latest["content_hash"] == article["content_hash"]:
                continue
        # Include retrieval identity so an article reverting to an earlier title
        # remains a new version without overwriting its original occurrence.
        version_id = digest(article["content_hash"] + article["retrieved_at"])
        saved += write_once(directory / f"{article['article_id']}_{version_id}.json", article)
    return saved


def read_articles(root: Path, as_of: str | None = None) -> list[dict[str, Any]]:
    cutoff = _instant(as_of or now_utc())
    latest: dict[str, dict[str, Any]] = {}
    for path in sorted((root / "data/news/articles").glob("*.json")):
        item = json.loads(path.read_text())
        if _instant(item["available_at"]) > cutoff:
            continue
        previous = latest.get(item["article_id"])
        if previous is None or _instant(item["retrieved_at"]) > _instant(previous["retrieved_at"]):
            latest[item["article_id"]] = item
    return sorted(latest.values(), key=lambda row: (row["available_at"], row["article_id"]))


def _fetch(url: str, config: dict[str, Any]) -> tuple[bytes, dict[str, str]]:
    request = urllib.request.Request(url, headers={"User-Agent": "RetailOutlookResearch/0.1 (metadata-only personal research)", "Accept": "application/json, application/rss+xml, application/atom+xml, application/xml;q=0.9"})
    for attempt in range(int(config.get("max_attempts", 2))):
        try:
            with urllib.request.urlopen(request, timeout=int(config.get("timeout_seconds", 25))) as response:
                limit = int(config.get("max_response_bytes", 4_000_000))
                body = response.read(limit + 1)
                if len(body) > limit:
                    raise ValueError("Response exceeds configured size cap")
                return body, {"content_type": response.headers.get("Content-Type", ""), "etag": response.headers.get("ETag", ""), "last_modified": response.headers.get("Last-Modified", ""), "final_url": response.url}
        except urllib.error.HTTPError as exc:
            # A throttled API is retried at the next scheduled collection, never
            # immediately hammered again or worked around with another endpoint.
            if exc.code not in {500, 502, 503, 504} or attempt + 1 >= int(config.get("max_attempts", 2)):
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt + 1 >= int(config.get("max_attempts", 2)):
                raise
        time.sleep(min(10.0, 2.0 ** (attempt + 1)))
    raise RuntimeError("No fetch attempts configured")


def collect(root: Path) -> dict[str, Any]:
    root = root.resolve()
    config = load_config(root)
    with collection_lock(root):
        started_at = now_utc()
        run_id = started_at.replace(":", "").replace("-", "") + "_" + uuid.uuid4().hex[:8]
        summary: dict[str, Any] = {"run_id": run_id, "started_at": started_at, "sources": [], "new_article_versions": 0, "paid_cost_usd": 0}
        sources = []
        if config["gdelt"].get("enabled"):
            gdelt = config["gdelt"]
            params = {"query": gdelt["query"], "mode": "artlist", "format": "json", "timespan": gdelt["timespan"], "maxrecords": min(250, int(gdelt["maxrecords"])), "sort": "datedesc"}
            sources.append({"name": "gdelt_doc", "url": gdelt["url"] + "?" + urllib.parse.urlencode(params), "kind": "gdelt"})
        sources += [dict(feed, kind="rss") for feed in config["rss"] if feed.get("enabled")]
        for i, source in enumerate(sources):
            if i:
                time.sleep(float(config.get("minimum_request_interval_seconds", 5)))
            source_status: dict[str, Any] = {"source": source["name"], "url": source["url"]}
            if source["kind"] == "gdelt":
                last_attempt = None
                for path in sorted((root / "data/news/runs").glob("*.json"), reverse=True):
                    prior = json.loads(path.read_text())
                    match = next((s for s in prior["sources"] if s["source"] == "gdelt_doc" and s.get("status") != "deferred"), None)
                    if match:
                        last_attempt = match.get("retrieved_at") or match.get("recorded_at")
                        break
                if last_attempt and (_instant(now_utc()) - _instant(last_attempt)).total_seconds() < int(config["gdelt"].get("minimum_poll_interval_seconds", 900)):
                    source_status.update(status="deferred", reason="GDELT minimum poll interval; retry on next hourly schedule", previous_attempt_at=last_attempt)
                    summary["sources"].append(source_status)
                    continue
            try:
                body, headers = _fetch(source["url"], config)
                retrieved = now_utc()
                base = root / "data/news/raw" / run_id / re.sub(r"\W+", "_", source["name"])
                base.parent.mkdir(parents=True, exist_ok=True)
                with base.with_suffix(".bin").open("xb") as handle:
                    handle.write(body)
                raw_relative = str(base.with_suffix(".bin").relative_to(root))
                write_once(base.with_suffix(".json"), {"url": source["url"], "retrieved_at": retrieved, "sha256": digest(body), "headers": headers, "raw_path": raw_relative})
                articles = parse_gdelt(body, retrieved, raw_relative, config) if source["kind"] == "gdelt" else parse_rss(body, retrieved, raw_relative, source, config)
                new = save_articles(root, articles)
                source_status.update(status="ok", retrieved_at=retrieved, article_count=len(articles), new_article_versions=new, truncated_possible=source["kind"] == "gdelt" and len(articles) >= int(config["gdelt"]["maxrecords"]))
                source_status["known_publisher_timestamps"] = sum(a["publish_time"] is not None for a in articles)
                newest = max((a["publish_time"] for a in articles if a["publish_time"]), default=None)
                source_status["latest_known_publish_time"] = newest
                source_status["freshness_warning"] = "No usable articles returned; this is not evidence of absent news" if not articles else "Latest known publication older than 30 days" if newest and (_instant(retrieved) - _instant(newest)).days > 30 else "Publisher timestamps lack timezone; raw values retained" if not newest else None
                summary["new_article_versions"] += new
            except Exception as exc:  # One unavailable source must not halt other prospective feeds.
                source_status.update(status="error", error=f"{type(exc).__name__}: {exc}", recorded_at=now_utc())
                LOG.warning("News source %s failed: %s", source["name"], exc)
            summary["sources"].append(source_status)
        summary["completed_at"] = now_utc()
        summary["status"] = "ok" if all(s["status"] == "ok" for s in summary["sources"]) else "partial" if any(s["status"] == "ok" for s in summary["sources"]) else "failed"
        write_once(root / "data/news/runs" / (run_id + ".json"), summary)
        return summary


@dataclasses.dataclass(frozen=True)
class NewsEvent:
    event_type: str
    commodities_affected: list[str]
    countries: list[str]
    direction: str
    magnitude: int | str
    expected_duration: str
    certainty: float | str
    source_credibility: float
    publish_time: str | None
    article_id: str
    content_hash: str
    story_id: str
    evidence_text: str
    source_url: str
    available_at: str
    extracted_at: str
    extractor_version: str = LOCAL_EXTRACTOR_VERSION
    validation_status: str = "unvalidated_do_not_train"

    def __post_init__(self) -> None:
        for name in ("commodities_affected", "countries"):
            values = getattr(self, name)
            if not isinstance(values, list) or not all(isinstance(v, str) and v for v in values):
                raise ValueError(f"{name} must be a list of nonempty strings")
        for name in ("event_type", "direction", "expected_duration", "article_id", "content_hash", "story_id", "evidence_text", "source_url", "available_at", "extracted_at", "extractor_version", "validation_status"):
            if not isinstance(getattr(self, name), str):
                raise ValueError(f"{name} must be a string")
        if self.event_type not in EVENT_TYPES or self.direction not in DIRECTIONS:
            raise ValueError("Invalid event type/direction")
        if self.magnitude != "UNKNOWN" and (type(self.magnitude) is not int or not 1 <= self.magnitude <= 5):
            raise ValueError("Magnitude must be 1–5 or UNKNOWN")
        if self.certainty != "UNKNOWN" and (type(self.certainty) not in (int, float) or not 0 <= self.certainty <= 1):
            raise ValueError("Certainty must be 0–1 or UNKNOWN")
        if type(self.source_credibility) not in (int, float) or not 0 <= self.source_credibility <= 1:
            raise ValueError("Credibility must be 0–1")
        for field in [self.available_at, self.extracted_at] + ([self.publish_time] if self.publish_time else []):
            _instant(field)


def event_schema() -> dict[str, Any]:
    """JSON Schema for future structured extractors; no additional keys allowed."""
    properties: dict[str, Any] = {field.name: {"type": "string"} for field in dataclasses.fields(NewsEvent)}
    properties.update({
        "event_type": {"enum": sorted(EVENT_TYPES)}, "direction": {"enum": sorted(DIRECTIONS)},
        "commodities_affected": {"type": "array", "items": {"type": "string"}},
        "countries": {"type": "array", "items": {"type": "string"}},
        "magnitude": {"anyOf": [{"type": "integer", "minimum": 1, "maximum": 5}, {"const": "UNKNOWN"}]},
        "certainty": {"anyOf": [{"type": "number", "minimum": 0, "maximum": 1}, {"const": "UNKNOWN"}]},
        "source_credibility": {"type": "number", "minimum": 0, "maximum": 1},
        "publish_time": {"type": ["string", "null"], "format": "date-time"},
        "available_at": {"type": "string", "format": "date-time"},
        "extracted_at": {"type": "string", "format": "date-time"},
    })
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", "title": "RetailOutlookNewsEvent", "type": "object", "additionalProperties": False, "required": list(properties), "properties": properties}


def extract_local(article: dict[str, Any], extracted_at: str | None = None) -> NewsEvent:
    """High-abstention supplied-text rules, unvalidated; no causal inference."""
    evidence = article["title"] + ("\n" + article["feed_description"] if article.get("feed_description") else "")
    text = evidence.casefold()
    commodities = [name for name, pattern in [("palm_oil", r"palm oil"), ("soybean_oil", r"soy(?:bean|a)? oil"), ("cooking_oil", r"(?:cooking|vegetable|edible) oil")] if re.search(pattern, text)]
    countries = [country for country, pattern in [("Indonesia", r"indonesia[n]?"), ("Malaysia", r"malaysia[n]?"), ("Singapore", r"singapore"), ("India", r"india[n]?"), ("China", r"china|chinese"), ("United States", r"united states"), ("Brazil", r"brazil"), ("Argentina", r"argentina") ] if re.search(r"\b(?:" + pattern + r")\b", text)]
    if "United States" not in countries and re.search(r"\bUS\b|\bU\.S\.", evidence):
        countries.append("United States")
    event_type, direction = "UNKNOWN", "UNKNOWN"
    # Entire-title abstention deliberately sacrifices recall when scope is ambiguous.
    uncertain = re.search(r"\b(no|not|never|denies?|denied|denial|unlikely|may|might|could|would|consider\w*|plan\w*|propos\w*|rumou?r\w*|lift\w*|end\w*|ease\w*|cancel\w*)\b|\?", text)
    if commodities and not uncertain:
        rules = [("export_restriction", r"export (?:ban|restriction)|ban\w* .{0,30}exports"), ("tariff", r"\btariff\b"), ("weather_shock", r"\bflood\w*|\bdrought\b"), ("harvest_report", r"\bharvest\b|crop report"), ("shipping_disruption", r"shipping disruption|port closure"), ("policy_subsidy_change", r"\bsubsid\w*"), ("conflict", r"\bwar\b|armed conflict")]
        event_type = next((kind for kind, pattern in rules if re.search(pattern, text)), "UNKNOWN")
        # Must name the subject and explicit move in the same short phrase.
        for subject, prefix in [("supply|supplies", "supply"), ("demand", "demand"), ("prices?|costs?", "cost")]:
            match = re.search(r"\b(?:palm|soybean|soya|cooking|vegetable|edible) oil (?:" + subject + r") (?:\w+\s+){0,2}(rise\w*|increase\w*|surge\w*|fall\w*|decrease\w*|drop\w*)\b", text)
            if match:
                direction = prefix + ("_up" if re.match(r"rise|increase|surge", match[1]) else "_down")
                if event_type == "UNKNOWN":
                    event_type = "price_move" if prefix == "cost" else "UNKNOWN"
                break
    return NewsEvent(event_type, commodities, countries, direction, "UNKNOWN", "UNKNOWN", "UNKNOWN", float(article["source_credibility"]), article["publish_time"], article["article_id"], article["content_hash"], article["story_id"], evidence, article["url"], article["available_at"], extracted_at or now_utc())


def extract_all(root: Path, as_of: str | None = None) -> list[dict[str, Any]]:
    load_config(root)  # Enforce backend and cost policy even for local calls.
    output = []
    for article in read_articles(root, as_of):
        path = root / "data/news/events" / f"{article['content_hash']}_{LOCAL_EXTRACTOR_VERSION}.json"
        if path.exists():
            value = json.loads(path.read_text())
        else:
            value = dataclasses.asdict(extract_local(article))
            write_once(path, value)
        output.append(value)
    return output


def news_indices(events: list[dict[str, Any]], as_of: str) -> list[dict[str, Any]]:
    """Descriptive only. Deduplicated story weight <= strongest source credibility.

    Requires both article and extraction to exist at the cutoff, preventing a
    later extraction from silently entering earlier prospective features.
    """
    cutoff = _instant(as_of)
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    seen_stories: set[tuple[str, str]] = set()
    for event in sorted(events, key=lambda e: e["available_at"]):
        if _instant(event["available_at"]) > cutoff or _instant(event["extracted_at"]) > cutoff:
            continue
        if event["event_type"] == "UNKNOWN":
            continue
        for commodity in event["commodities_affected"]:
            groups[(event["available_at"][:10], commodity)].append(event)
    output = []
    for (date, commodity), members in sorted(groups.items()):
        representatives: dict[str, dict[str, Any]] = {}
        for event in members:
            prior = representatives.get(event["story_id"])
            if prior is None or event["source_credibility"] > prior["source_credibility"]:
                representatives[event["story_id"]] = event
        unique = list(representatives.values())
        weighted = sum(e["source_credibility"] for e in unique)
        up = {"supply_down", "demand_up", "cost_up"}
        down = {"supply_up", "demand_down", "cost_down"}
        signed = sum(e["source_credibility"] * (1 if e["direction"] in up else -1 if e["direction"] in down else 0) for e in unique)
        output.append({"date": date, "commodity": commodity, "event_count": len(unique), "weighted_event_count": weighted, "weighted_direction": signed, "supply_shock_intensity": sum(e["source_credibility"] for e in unique if e["direction"] == "supply_down"), "novel_story_count": sum((commodity, e["story_id"]) not in seen_stories for e in unique), "validation_status": "unvalidated_descriptive_only"})
        seen_stories.update((commodity, e["story_id"]) for e in unique)
    return output


def export_annotations(root: Path) -> dict[str, Any]:
    """Freeze one story per item; blank human labels, deterministic split order."""
    stories: dict[str, dict[str, Any]] = {}
    for article in read_articles(root):
        if extract_local(article).commodities_affected:
            stories.setdefault(article["story_id"], article)
    ordered = sorted(stories.values(), key=lambda a: digest("label-split-seed-2026" + a["story_id"]))[:150]
    batch_id = now_utc().replace(":", "").replace("-", "")
    directory = root / "data/news/annotations" / batch_id
    directory.mkdir(parents=True)
    fields = ["article_id", "story_id", "split", "second_reviewer", "source", "url", "title", "feed_description", "publish_time", "retrieved_at", "event_type", "commodities_affected", "countries", "direction", "magnitude", "expected_duration", "certainty", "evidence", "reviewer_id"]
    rows = []
    with (directory / "labels.csv").open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for i, article in enumerate(ordered):
            row = {key: article.get(key, "") for key in fields}
            row.update(split="heldout" if i < 100 else "dev", second_reviewer="yes" if i < 25 else "no")
            writer.writerow(row)
            rows.append(row)
    with (directory / "second_reviewer.csv").open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows[:25])
    manifest = {"created_at": now_utc(), "path": str(directory / "labels.csv"), "unique_stories": len(ordered), "heldout": min(100, len(ordered)), "dev": max(0, len(ordered) - 100), "second_reviewer": min(25, len(ordered)), "status": "ready" if len(ordered) == 150 else "insufficient_articles_do_not_claim_validation"}
    write_once(directory / "manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["collect", "extract", "annotations", "status"])
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--as-of")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    if args.command == "collect":
        result = collect(args.root)
    elif args.command == "extract":
        events = extract_all(args.root, args.as_of)
        result = {"events": len(events), "recognized_events": sum(e["event_type"] != "UNKNOWN" for e in events), "cost_usd": 0, "validation_status": "unvalidated_do_not_train", "indices": news_indices(events, args.as_of or now_utc())}
    elif args.command == "annotations":
        result = export_annotations(args.root)
    else:
        articles = read_articles(args.root, args.as_of)
        runs = sorted((args.root / "data/news/runs").glob("*.json"))
        result = {"articles": len(articles), "latest_run": json.loads(runs[-1].read_text()) if runs else None, "first_retrieval": min((a["first_seen_at"] for a in articles), default=None)}
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
