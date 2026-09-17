# Prospective news collection in the cooking-oil slice

Collection started **17 September 2026 at 08:11 UTC**. The first run archived
287 article metadata records: 155 SFA newsroom items, 124 SFA circulars and 8
USDA ARS items. These are an initial feed inventory, not 287 new events today.
All become usable only from the timestamp at which this system retrieved them.
Initial GDELT output was the empty object `{}`; it supplied no usable articles.
That is not evidence that no cooking-oil news occurred.

## Run and schedule

From the project root:

```sh
PYTHONPATH=src .venv/bin/python -m retail_outlook.news collect --root .
PYTHONPATH=src .venv/bin/python -m retail_outlook.news status --root .
PYTHONPATH=src .venv/bin/python -m retail_outlook.news extract --root .
PYTHONPATH=src .venv/bin/python -m retail_outlook.news annotations --root .
```

The active Codex heartbeat `collect-cooking-oil-news` invokes the first command
hourly. The desktop
host must be awake and connected for a local scheduled run. Failures and gaps
remain visible in immutable `data/news/runs/*.json` manifests. Feed windows are
finite; no claim of complete news coverage is made. The 24-hour GDELT window
overlaps normal runs. At 250 matches the manifest flags possible truncation.
A filesystem lock prevents overlapping collectors. Read timeouts, two bounded
attempts for transient server/network failures, five seconds between sources,
and a 4 MB response cap limit load. GDELT additionally enforces at least 15 minutes
between local attempts; HTTP 429 is not immediately retried. Its latest setup
attempt was rate-limited and coverage remains unknown until a later successful
scheduled poll.
No full newspaper article pages are requested.

## Official sources and rights

| Source | Advertised access and handling |
|---|---|
| GDELT DOC API | [Official API documentation](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/); oil-related title, URL, source and discovery metadata only. Publisher article rights remain with the publisher. |
| Singapore Food Agency | [Official RSS subscription page](https://www.sfa.gov.sg/news-publications/newsroom/subscribe-to-sfa-rss-feeds); newsroom and circular feed metadata, attribution and links retained. These feeds currently expose timestamp strings without a timezone. |
| FAO | [Official newsroom](https://www.fao.org/newsroom/en) advertises [FAO newsroom RSS](https://www.fao.org/feeds/fao-newsroom-rss). The newsroom HTML blocked a direct request, but the advertised RSS feed returned HTTP 200. Only supplied feed data is archived and title/link metadata is normalized. |
| USDA ARS | [Official RSS listing](https://www.ars.usda.gov/news-events/rss-feeds/) advertises research-news feed. The initial feed's latest article is January 2025: this is a stale supplementary source, not current market coverage. |
| USDA NASS | [Official subscription page](https://data.nass.usda.gov/Newsroom/Syndication/News/index.php) advertises a feed that returned HTTP 403. Disabled after the first attempt; no access-control bypass. |

Settings and subjective source credibility weights are in `configs/news.yaml`.
Official-agency metadata defaults to 0.95, other outlets to 0.50. These are
configurable judgement weights, not estimated truth probabilities. Raw RSS may
contain publisher-supplied descriptions; normalized articles preserve a plain-text
feed description (capped at 20,000 characters), and rule extraction can use that
description alongside the title. The feed supplied the descriptions; article-page
bodies are never fetched.
This archive is for personal research; no redistribution right
to third-party article text is inferred from GDELT indexing.

## Point-in-time contract

* `publish_time`: normalized UTC only when the source supplies a timezone-aware
  publisher timestamp; otherwise null, with the original string preserved.
* `gdelt_seen_at`: GDELT discovery time. It is never renamed publication time.
* `retrieved_at`: completion time of the actual response download.
* `first_seen_at`: earliest local retrieval of the URL, preserved across revisions.
* `available_at`: the later of this article version's retrieval and any known
  future publisher timestamp. A revised title cannot inherit the first version's
  eligibility date.
* Source responses are immutable bytes plus SHA-256 and retrieval manifests in
  `data/news/raw/`. Each article revision is immutable JSON in
  `data/news/articles/`; unchanged re-pulls are deduplicated. A title reverting to
  an older value creates a new revision with a new retrieval time.
* `read_articles(root, as_of)` returns the latest **eligible** revision. It does
  not backdate today's initial feed inventory to older publication dates.
* Prospective event indices require both article availability and extraction
  completion by the requested cutoff. Historical post-hoc extraction is not
  silently treated as a feature that the running system already possessed.

## Local event pipeline

The initial deterministic extractor is deliberately conservative and **has not
passed human validation**. It detects some explicit export restrictions, weather,
harvest, tariff, subsidy, conflict and price moves in supplied titles/descriptions.
Text containing negation, speculation, questions or reversals abstains. It infers a price/supply/demand
direction only from an explicit subject-and-move phrase. For example:

* “Palm oil prices rise” → `price_move`, `cost_up`.
* “Indonesia bans palm oil exports” → `export_restriction`, direction `UNKNOWN`.
* “Indonesia may ban palm oil exports” → `UNKNOWN`.

Strict `NewsEvent` fields cover event type, affected commodities, countries,
direction, magnitude, duration, certainty, credibility, publication time,
evidence text, article identity, source URL and extraction provenance. Magnitude,
duration and certainty stay `UNKNOWN` unless supported; the local rules do not
manufacture them. No LLM is currently called. Extraction caches use article
content hash plus extractor version. The enforceable current call cost is $0;
config rejects paid backends, paid historical backfill, or a cap above $50/month.
Any future paid integration must implement a reservation ledger before network
calls and must preserve the development cap.

Exact normalized-headline clusters bound each day's story contribution to the
highest source-credibility weight in the cluster. This is a cheap duplicate
baseline; paraphrased syndicated articles will remain duplicates until a later
validated clustering improvement. Daily counts, weighted direction, explicit
supply-shock intensity and novel-story counts are descriptive outputs. Novelty
means a previously unseen headline cluster, **not statistically measured surprise**.
These unvalidated indices are excluded from the cooking-oil forecasting models.

## Human evaluation hand-off

The annotation export creates a new immutable batch each time, with no prefilled
machine labels. It chooses at most 150 unique oil-related headline clusters
using a deterministic hash order, assigns 100 to held-out evaluation and 50 to
development, and marks 25 held-out items for a second reviewer. A shortage is
explicitly reported; unrelated SFA items are not used to pad the sample. Select
one complete batch, freeze it, and do not change story splits during tuning.
The user labels all 150; a second reviewer independently labels the 25 marked
items using a separate blank `second_reviewer.csv`, without seeing the first
reviewer or extractor labels.

Precision/recall and inter-reviewer agreement are **pending**, not estimated from
synthetic fixtures. After labels are returned, report per-field and event-type
precision/recall, abstention/coverage, error examples, and Cohen's kappa plus raw
agreement on the second-reviewer subset. Keep the 100 held-out labels hidden
while developing rules on the 50 development examples. Paid historical backfill
stays disabled until the agreed held-out evaluation passes; no numerical pass
threshold was approved yet. Proposed thresholds to freeze before labels: at least
100 held-out stories, event-type precision >= 0.80, direction precision >= 0.90,
and event-type macro recall >= 0.60. Report denominator and bootstrap uncertainty
for every metric; a zero prediction denominator is undefined and cannot pass.
These are proposed research gates, not measured results or user-approved criteria.
Source-news evidence may inform an explicitly
descriptive outlook section, but validated predictive value requires later
prospective ablation tests.

## Offline verification

```sh
PYTHONPATH=src .venv/bin/python -m pytest tests/test_news.py -q
```

Tests cover aware timestamps, missing/timezone-less publication times, GDELT
discovery provenance, future-dated items, article revision leakage, reversion,
tracking-link deduplication, unsupported and negated extraction, strict event
schema validation, extraction-time cutoffs, duplicate weight caps, overlapping
collectors and blocked paid backends.
Empty GDELT objects without an `articles` list are recorded as an explicit source
error with unknown effective coverage, not as a successful zero-news result.
