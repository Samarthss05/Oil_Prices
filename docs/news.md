# Prospective news operations

News is a descriptive, unvalidated layer. Collection time is the information boundary: publication dates and GDELT discovery times never substitute for actual retrieval. All revisions, response bytes and extraction versions remain immutable. The earliest local archive began on 17 September 2026; the hosted archive starts at deployment without backdating earlier local records.

## Scheduler and persistence

`.github/workflows/collect-news.yml` runs on GitHub-hosted Linux at minute 17 every three hours UTC, or through `gh workflow run collect-news.yml`. Collection uses the standard library: no model fitting, paid LLM, dependency download or Codex session is involved. A concurrency group prevents overlapping cloud runs; the existing filesystem lock prevents overlap within a store.

Each run restores the previous `news-archive` Actions artifact, validates its path inventory and SHA256 checksums, and merges only missing/identical files. It collects into the existing `data/news/` format and uploads a cumulative `news.tar.gz` archive. Thus records persist after the ephemeral runner disappears. Archive traversal, symlinks, conflicting bytes and oversized payloads are rejected before writes.

The latest eight complete cumulative backups are retained, each expiring after 90 days. Superseded *copies* are pruned only after the current run's upload is confirmed; every retained archive still contains the complete accumulated records. Neither `data/` nor `artifacts/` is committed to the main branch. The workflow token needs `contents: read` and `actions: write` for archive retrieval and cleanup, not permission to push repository contents.

Limits: [GitHub can delay/drop scheduled jobs or disable schedules in inactive public repositories](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule). An outage longer than retention, manual artifact deletion or storage quotas can destroy hosted history. The collector refuses known expired archives but cannot reconstruct already purged inventory. Keep an independent backup. A 512 MB archive cap fails explicitly rather than truncating records. Artifact access follows repository visibility; no commercial article bodies are scraped or packaged.

Local commands:

```sh
./run.sh collect-news
./run.sh extract-news
./run.sh annotations
PYTHONPATH=src .venv/bin/python -m retail_outlook.news_archive pack --root .
PYTHONPATH=src .venv/bin/python -m retail_outlook.news_archive restore-latest --root .
```

The second archive command needs an authenticated GitHub CLI. The local pre-deployment archive remains intact; cloud restore merges new records without pretending those records had been collected earlier.

## Access and backoff

GDELT has a 24-hour overlapping window, at most 250 results, and flags possible truncation. Its combined query covers palm oil, crude palm oil, CPO, soybean oil, stocks, exports, export levy, biodiesel mandate and cooking oil (including Singapore/Malaysia/Indonesia). Global terms avoid excluding a supply shock outside those countries. Local relevance additionally recognizes `oil palm` and `minyak sawit`. These are keyword counts, not validated market-event counts.

There are at most two in-run attempts for transient server/network failures, with exponential delay plus jitter and a 4 MB response cap. HTTP429 is **not** retried immediately. GDELT failures persist an exponential cooldown across scheduled runs (15-minute base, increasing to 24 hours, plus jitter). A server `Retry-After`, including an HTTP date, is a lower bound and is never truncated. Polls before the stored deadline are explicitly deferred. Successful feeds continue when another source fails.

GDELT `{}` or another invalid schema is an error with unknown coverage, not a successful zero-news response. RSS without publisher timezone retains the raw date and a null normalized publication time. A future publisher date delays eligibility even when a response has already arrived.

## Rights and source limitations

See [the source register](sources.md) for permission/discovery links. Only publisher-supplied RSS and GDELT metadata are accessed; linked commercial article pages are never fetched. Titles, links, source notices, descriptions and response hashes are retained. A readable URL does not imply unrestricted redistribution rights.

MPOB PALMOILIS RSS supplies Malay/English publication titles, often older technical/consumer material rather than current market events. ANTARA's business RSS is a broad feed and may have no oil stories in a poll. USDA ARS has returned stale material. SFA publisher dates have lacked timezones. These limitations remain in each run manifest. NASS remains disabled after HTTP403, without bypass.

## Measured operations

`collector_health(root, as_of)` reports completed hosted runs, runs with a usable feed, per-source success, expected/occupied three-hour UTC schedule bins, last completion and keyword-relevant story counts. Future runs and future-dated articles are excluded. The uptime fraction is unavailable until a scheduled run exists; a successful manual deployment check does not establish scheduler uptime. Missed slots remain gaps, not reconstructed records.

Raw feeds can expose article bodies as descriptions. This implementation stores only what the permitted feed supplies and never requests the linked page. Credibility weights are configurable judgement priors, not calibrated truth probabilities.

## Extraction and human labels

The strict `NewsEvent` schema and conservative local rules are unchanged in purpose: unsupported magnitude/duration/certainty stay UNKNOWN; negation, speculation and ambiguous reversals abstain. The cache key includes article content and extractor version. Prospective news indices require both article availability and extraction completion by the cutoff. These indices are not used in historical forecasts.

Human labelling is **planned**, not completed: approximately 50 development and 100 held-out stories, with a second reviewer independently labelling 25 held-out stories. The export writes blank, deterministic story-separated packs and reports insufficiency. Do not infer precision/recall from synthetic tests or count technical keyword mentions as market events. Precision/recall, abstention and reviewer agreement remain unmeasured.

No paid backend exists; configuration rejects enabling one or exceeding the USD50 monthly development cap. Paid historical backfill remains disabled until independent evaluation and a separate implementation are approved. The current LLM cost is zero.
