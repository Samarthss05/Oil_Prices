# Retail Goods Price Outlook Engine — Phase 1 plan

Research date: 17 September 2026. Status: approved with the amendments below; cooking-oil implementation authorized. These amendments supersede conflicting breadth-first details below.

## Approved amendment: cooking-oil vertical slice first

Deliver cooking oil end-to-end before widening: SingStat Vegetable Oils CPI, World Bank palm/soy oil benchmarks, and MAS USD/SGD through SingStat; an as-of store; seasonal naive/ETS/ARIMA; monthly walk-forward evaluation and leakage tests; a small distributed-lag model; a minimal local news event pipeline; one forecast fan chart and grounded note in a single Streamlit page. Stop for review before widening to the original phases. FAO/FRED/USDA structured connectors, complex ensembles, embedding services and full historical vintage reconstruction are deferred.

Start prospective GDELT and permitted RSS collection immediately, with hourly scheduled pulls. Archive raw responses and permitted feed article text with actual UTC retrieval/first-seen timestamps and publisher dates when supplied. Commercial-news content stays metadata-only. No backdating or bypassing blocked sources. Extraction runs independently from collection.

Historical research uses explicitly **reconstructed** observations with documented conservative release assumptions and is the primary historical view. Strict as-of semantics apply to every new retrieval/version. Prospective results accumulate separately and have no scored performance until outcomes mature. Historical vintage archaeology is optional for this slice.

Electricity and gas are drivers only. Utilities, if scored later, have their own track outside the food denominator. The remaining catalogue has **11 food CPI targets plus experimental onions**. Do not invent a twelfth food to preserve a count. Lead reporting with effect sizes and block-bootstrap intervals; the original 8-of-12 is only a secondary legacy summary, inapplicable until a 12-food panel is agreed.

Development LLM cap: **USD 50 per calendar month**; local extraction and deterministic notes are default. Paid historical backfill stays disabled until the 100-article held-out extraction evaluation passes predefined gates. User labels approximately 50 development and 100 held-out articles; a second reviewer labels 25 for agreement. Split by story and time. No labels or successful validation may be fabricated.

Unchanged bands are horizon-specific, proposed from initial-training CPI volatility and frozen before evaluation with cutoff and recipe. Slice recipe: half the standard deviation of initial-training cumulative log CPI changes over each effective horizon (including publication bridge), with a 0.1 percentage-point floor. Store the computed 1/3/6-month bands in an immutable protocol. No tuning on evaluated outcomes.

Timebox: ten focused working days, targeting two weeks. Days 1–2: collection, three connectors and storage; days 3–4: frozen protocol, baselines and leakage tests; days 5–6: lagged pass-through and effect intervals; days 7–8: local events, annotation exports and outlook; days 9–10: single-page Streamlit, integration verification and review. Simplify components that threaten the timebox. No unattended coding is implied; only the installed collection schedule runs later.

## 1. Scope and feasibility decision

Build a local Python research system for Singapore retail-price baskets, with monthly forecasts at 1, 3 and 6 months, daily source collection where useful, and weekly Markdown/PDF reports. Accuracy, calibration, reproducibility and source traceability take priority over presentation.

The approved catalogue separates flour and bread and retains official poultry and milk labels. Electricity is now a driver/optional separate utilities target; onions remain experimental. Cooking oil is the first delivery gate.

Two requirements cannot yet be promised: an item-level backtest beginning in 2012, and verified historical point-in-time coverage for every input. Most relevant current CPI histories begin in January 2015. Some detailed history was published retrospectively. Current revised downloads do not establish what a forecaster could observe at historical dates.

Do not substitute broad categories into detailed-good scores, silently move evaluation dates, invent missing vintages, or represent hypothetical performance as measured results. The 8-of-12 accuracy objective is a research target, not a guaranteed outcome.

## 2. Verified target catalogue

The following labels, identifiers and non-missing start dates were checked against the live [SingStat M213751 JSON API](https://tablebuilder.singstat.gov.sg/api/table/tabledata/M213751) and [CPI table](https://tablebuilder.singstat.gov.sg/table/TS/M213751). The current base is 2024=100. Data extend through July 2026; these are observation histories in today's download, not authenticated historical vintages.

| Scored target | Official CPI label | Series number | Current history starts |
|---|---|---|---|
| Rice | Rice | 1.01.1.1 | Jan 2015 |
| Cooking oil | Vegetable Oils | 1.01.5.1 | Jan 2015 |
| Flour | Flour | 1.01.1.2 | Jan 2015 |
| Bread | Bread | 1.01.1.3 | Jan 2015 |
| Sugar | Sugar | 1.01.8.1 | Jan 2015 |
| Eggs | Eggs | 1.01.4.4 | Jan 2015 |
| Poultry | Poultry, Chilled Or Frozen | 1.01.2.4 | Jan 2015 |
| Pork | Pork, Chilled Or Frozen | 1.01.2.1 | Jan 2015 |
| Milk | Milk | 1.01.4.1 | Jan 2015 |
| Coffee | Coffee & Coffee Substitutes | 1.01.10.2 | Jan 2015 |
| Electricity (driver / separate utilities track) | Electricity | 1.03.2.3 | Jan 2015 |
| Seafood | Fish & Other Seafood | 1.01.3 | Jan 2005 |

These targets measure basket price changes, not the cost of a particular supermarket SKU. In particular, poultry is broader than chicken, milk is not an infant-milk-powder index, and packaged coffee is not a café drink.

[SingStat M213761](https://tablebuilder.singstat.gov.sg/table/TS/M213761) provides useful supplementary average retail prices:

| Companion series | Row | Current available history | Treatment |
|---|---|---|---|
| Small Onions (Per Kilogram) | 49 | Jan 2024–Jul 2026; 31 months | Experimental; excluded from the 12-target score |
| Infant Milk Powder (Per 100 Gram) | 32 | Jan 2015–Jul 2026 | Separate actual-price companion |
| Whole Chicken, Chilled (Per Kilogram) | 14 | Jan 2015–Jul 2026 | Separate chicken-specific companion |
| Cooking Oil (Per 2 Kilogram) | 35 | Jan 2015–Jul 2026 | Separate actual-price companion |
| Liquefied Petroleum Gas (LPG) (Per Kilogram) | 84 | Jan 2015–Jul 2026 | Cost-driver companion |

Average retail prices can change with sampled brands, varieties and outlets. They must not be spliced into CPI histories or presented as equivalent measures. Onion forecasts should initially use simple methods and carry an insufficient-history warning; multivariate skill and calibration cannot be established from 31 observations.

The current API capped responses at 5,000 observations even with a larger requested limit. Pages may split a series. Phase 2 must paginate, assemble by series/period, and reconcile completeness against metadata; a successful HTTP response is not evidence of a complete dataset.

Older detailed archives remain unverified. The checked old M212881 endpoint returned 404. SingStat expanded detailed publication substantially across rebasing exercises, so even recoverable back-history needs an original-publication audit. See the [2020 rebasing newsletter](https://www.singstat.gov.sg/-/media/files/publications/reference/newsletter/ssn120.ashx) and [2024-base methodological paper](https://www.singstat.gov.sg/-/media/files/publications/economy/ip-e61.ashx).

## 3. Source register and access decisions

“Included” below means included in the planned connector set; it does not mean an implementation or exhaustive vintage audit has been completed.

| Source | Planned use and access | History / important constraint | Phase |
|---|---|---|---|
| SingStat | Official JSON API; CPI and companion prices | Detailed dates above; archive/rebasing audit required | 2 |
| MAS via SingStat | [M700051 monthly average FX](https://tablebuilder.singstat.gov.sg/table/TS/M700051), source attributed to MAS | SGD per USD from Jan 1988; currency-specific units and starts | 2 |
| FAO | [FFPI CSV/XLS](https://www.fao.org/worldfoodsituation/foodpricesindex/en/): headline, cereals, oils, meat, dairy, sugar | Monthly since 1990; revised releases, especially estimated meat observations | 2 |
| World Bank | [Pink Sheet monthly workbook and report archive](https://www.worldbank.org/en/research/commodity-markets) | Long histories, often from 1960, varying by series; current workbook is not a vintage archive | 2 |
| FRED / ALFRED | [Documented API](https://fred.stlouisfed.org/docs/api/fred/); free registered API key | Audit ALFRED vintage availability per series | 2 |
| USDA WASDE | [Official reports and historical downloads](https://www.usda.gov/about-usda/general-information/staff-offices/office-chief-economist/commodity-markets/wasde-report) | Archived reports; consolidated report-vintage CSV from Apr 2010, posted after the report | 4 |
| USDA PSD | [Official API portal](https://apps.fas.usda.gov/opendataweb/home); free registered key | Marketing-year supply/use balances; current revisions are not historical vintages | 4 |
| NOAA CPC | [ONI tables](https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso/oni/v5/) and dated advisories | ONI from 1950; revisions and retrospective baselines; version ONI/RONI separately | 4 |
| IMF | [Primary Commodity Prices](https://www.imf.org/en/research/commodity-prices); public download, API adapter optional | Monthly from 1980; secondary validation/gap source, not duplicate independent evidence | 4, optional |
| GDELT | [Open data archives](https://gdeltproject.org/data.html), GKG and discovery APIs | GKG 1 starts 2013; GKG 2 starts Feb 2015; not a consistent 2012 article corpus | 5 |
| Official news | SFA RSS, USDA report feeds, FAO releases; add authenticated official policy sources | Retain source terms and content availability per feed | 5 |

Seed FRED candidates are [DCOILBRENTEU](https://fred.stlouisfed.org/series/DCOILBRENTEU), [FEDFUNDS](https://fred.stlouisfed.org/series/FEDFUNDS) and [WPU3013](https://fred.stlouisfed.org/series/WPU3013). The last is US water-freight producer prices, not a Singapore freight quote. Its imperfect geographic and conceptual match must be visible. A freight series will not be treated as useful merely because it is available.

The [ALFRED real-time parameters](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html) provide a genuine vintage mechanism, subject to series coverage. The [NY Fed GSCPI](https://www.newyorkfed.org/newsevents/news/research/2022/20220518) was introduced in 2022; its backfilled earlier observations are ineligible for strict pre-2022 tests.

NOAA's current ONI documentation says RONI is now used for official ENSO monitoring. ONI remains updated, but it is a three-month mean with revisable values and changing historical baselines. Neither the seasonal label nor a retrospectively assigned El Niño classification is an availability date.

MAS direct access returned maintenance during part of the audit. Use the official SingStat channel first and preserve source attribution and retrieval timing. The [MAS exchange-rate service](https://eservices.mas.gov.sg/statistics/msb/exchangerates.aspx) and the [official data.gov.sg mirror](https://data.gov.sg/datasets/d_3c62d5eed03c40aeafbb6d0fa324e976/view) are potential alternatives, with their own publication and mirror delays. The rates carry underlying provider provenance; public access does not establish unrestricted redistribution rights.

Source permissions recorded in the eventual README/configuration must include:

- [SingStat terms](https://www.singstat.gov.sg/terms-of-use), API-specific terms, and underlying MAS notices. Some terms content was inaccessible during this audit; review is an explicit activation gate for the affected feed, not an assumed permission.
- [Singapore data.gov.sg platform and API terms](https://data.gov.sg/privacy-and-terms), which distinguish dataset licensing from API access.
- [FAO database terms](https://www.fao.org/contact-us/terms/db-terms-of-use/en) and [World Bank terms](https://data.worldbank.org/summary-terms-of-use): attribution and dataset-specific exceptions matter.
- [FRED API terms](https://fred.stlouisfed.org/docs/api/terms_of_use.html): retain the required notices and underlying series restrictions. A FRED key does not license every provider's data for every purpose.
- [IMF commodity FAQ](https://www.imf.org/external/np/res/commod/index.htm): revisions and attribution requirements.
- Original USDA/NOAA notices and attribution for government products; check any third-party material separately.
- [SFA RSS channels](https://www.sfa.gov.sg/news-publications/newsroom/subscribe-to-sfa-rss-feeds) and [SFA terms](https://www.sfa.gov.sg/terms-of-use); [USDA NASS report RSS](https://data.nass.usda.gov/Newsroom/Syndication/Todays_Reports/index.php); [FAO newsroom feed information](https://www.fao.org/newsroom/contacts) and content permissions.

GDELT metadata availability does not grant rights to scrape publisher article bodies. Initially extract from permitted official releases and permitted feed text. Store commercial-news metadata/links only unless the source's terms permit the intended retrieval, storage and processing. Missing full text is a measurable coverage limitation. Do not bypass paywalls, authentication, robots restrictions or rate limits. Paid commodity/futures feeds and publishers without suitable permissions are disabled adapters with an explicit README reason; no futures connector is required for the first implementation.

GDELT DOC documentation has changed across releases: its [original documentation](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/) and [later window update](https://blog.gdeltproject.org/doc-2-0-updates-1-5-year-searching-and-updated-mobile-interface/) differ. Treat live API date coverage and truncation as connector capabilities to test, not as a guaranteed historical archive. Use documented bulk archives for historical discovery where feasible, and bound disk/network use rather than download the entire corpus by default.

## 4. Forecast and information-set contract

Let O denote the calendar month containing the issuance timestamp. Run the primary forecast after the actual CPI release. Forecast reference months O+1, O+3 and O+6. Always display the concrete target month.

Let m be the latest published CPI reference month. Models and baselines must bridge m to O+h; when m=O-1, the statistical forecast distance is h+1 observations. A forecast for O is a separately labelled nowcast. Report percentage change and direction relative to the latest released CPI, not an unobserved current-month level. Example: an August issuance using July CPI produces September, November and February targets.

Use actual release schedules and archived timestamps where recoverable. CPI normally releases on the 23rd of the following month or the next working day, not a universal month-end-plus-21-days rule; see the [SingStat methodology](https://www.singstat.gov.sg/-/media/files/publications/economy/ip-e61.ashx). Convert timestamps to UTC; retain Asia/Singapore presentation and original timezone evidence. Date-only timestamps require conservative bounds and a recorded precision flag.

Every structured observation version will retain source, series, reference period, value, unit, seasonal-adjustment status, index base, source release time, source vintage identifier, retrieval time, raw content hash, parser version and provenance quality. Never overwrite an old value with a revision. Every article retains source, canonical URL, publication timestamp or explicit unknown status, first-seen time, retrieval time, content/version hash, rights status and permitted evidence text. GDELT detection time is not automatically publisher publication time.

Use three distinct evidence classes:

1. **Verified historical replay:** authentic release vintages/content and availability evidence support the historical information set. A file retrieved today can qualify only when it demonstrably preserves the original vintage; keep today's retrieval time.
2. **Reconstructed historical research:** revised histories, inferred release dates or unverified original article text. Apply sensible lags, but label the remaining hindsight risk. These results never become strict-PIT claims.
3. **Prospective operational:** snapshots actually retrieved and processed before issuance. This is the strongest test of the implemented operational pipeline.

The user approved both views: reconstructed history is the primary historical research view, while strict PIT accumulates prospectively. Source availability and actual ingestion are different clocks; do not backdate ingestion. Full vintage reconstruction is deferred.

Train an origin using only released target labels, as-of feature vintages and permitted content. No centered rolling windows, backward imputation, future seasonal adjustments, realized future driver paths, future story clusters, full-sample factor transforms or smoothed regime states. Missingness and data age are explicit features. Original release values are the preferred primary scoring truth where available; report latest-vintage scoring as a separate sensitivity analysis. Align index bases without importing future classification or basket information.

## 5. Architecture and proposed repository

```mermaid
flowchart LR
    S[Official data and permitted news] --> C[Connectors and source policies]
    C --> R[Immutable raw snapshots and manifests]
    R --> P[Versioned Parquet and DuckDB catalogue]
    P --> A[As-of views and release calendars]
    A --> F[Lagged drivers and news features]
    F --> B[Walk-forward baselines and candidates]
    B --> E[Evaluation and promotion gates]
    E --> D[Calibrated forecast distributions]
    D --> O[Evidence-linked outlooks and scenarios]
    O --> U[Streamlit and weekly exports]
```

Parquet stores normalized append-only data; original JSON/CSV/XLS/XML/PDF/feed responses remain preserved where permitted. DuckDB is a local catalogue/query layer, not the sole immutable raw archive. Snapshots contain checksums, config hash, code version, dependency lock, model/prompt versions and seeds. Each forecast has lineage to its exact input snapshot and model artifact.

Proposed structure (not created in this phase):

```text
pyproject.toml
uv.lock
.env.example
README.md
configs/
  goods.yaml  sources.yaml  releases.yaml  models.yaml  evaluation.yaml
src/retail_outlook/
  cli.py  config.py  schemas.py
  connectors/       # source discovery, retrieval, parsing, release metadata
  storage/          # immutable blobs, Parquet, catalogue, manifests, as-of queries
  features/         # release-aware alignment, lags, FX conversion, missingness
  news/             # permissions, deduplication, extraction, clustering, indices
  relationships/    # graph, distributed lags, cointegration, stability evidence
  models/           # shared fit/predict-distribution interface and model registry
  backtesting/      # origins, delayed-label splits, metrics, calibration, ablations
  explainability/   # model contributions and evidence bundles
  scenarios/        # explicit driver paths and conditional propagation
  reporting/        # validated notes, Markdown/PDF exports
  dashboard/        # Streamlit views
tests/
  connectors/  point_in_time/  features/  metrics/  evaluation/
notebooks/          # exploration calls package code rather than duplicating logic
data/               # ignored raw snapshots, normalized data and catalogue
artifacts/          # manifests, models, forecasts, graph vintages, evaluation
reports/
docs/               # source register, target definitions, evaluation contract
```

Use Python 3.12+, typed interfaces and Pydantic validation, pandas/NumPy/PyArrow/DuckDB, HTTPX with retry/backoff and per-host rate limits, statsmodels/SciPy/scikit-learn, NetworkX, then LightGBM/SHAP and Streamlit in their relevant phases. Choose and lock exact compatible versions during implementation; the plan does not invent an untested dependency lock. Embeddings are a pinned local model where practical. A deep forecaster is deferred unless the simpler ensemble is demonstrably inadequate and sufficient data exist.

Connector contracts separate discovery, fetch, parse and release-calendar handling. Forecast models share fit(as-of training data) and predict-distribution(target months, permitted driver paths) semantics. Forecast outputs include samples or a sufficiently rich quantile grid, not only three points. Optional feeds fail with explicit status; mandatory target-data failures stop issuance rather than silently fabricate fresh forecasts.

Secrets live in an ignored .env; logs redact keys and request credentials. LLM requests reserve estimated input/output/retry cost before execution and stop at the configured cap. Cache extraction by content hash plus model/prompt/schema version; credibility is joined from versioned configuration. A cache hit must never conceal a changed article version. No paid provider is enabled without configured credentials and the user's spending choice. Local extraction and deterministic report templates remain usable fallbacks, with their own validation limitations.

The eventual one-command entry point will run ingestion, validation, feature construction and forecasts and open the local dashboard, with separate reproducible backtest/report commands. Scheduling support is implemented later; no computer-level automation is installed during planning.

## 6. Models, driver graph and scenarios

Start with seasonal naive, plain random walk, random walk with drift, ETS and a constrained ARIMA search. Every report retains their results even when advanced models win. Introduce complexity only after baseline errors and data constraints are understood.

Seed the graph with domain hypotheses: rice benchmarks to rice; palm/soy oils to vegetable oils; wheat to flour and bread; maize/soy feed to poultry, eggs and pork; dairy benchmarks to milk; coffee benchmarks to coffee; energy/FX/freight to landed costs; weather/policy/disease news to affected supply routes. Imported-input nodes are labelled observed where supported by data and latent/proxy otherwise. Selected seafood benchmarks are incomplete basket proxies, not universal seafood prices. Add Singapore policy and announced utility-price changes when documented.

Convert dollar benchmarks consistently: P_SGD = P_USD × E_SGD-per-USD. Avoid double-counting the same FX movement in both converted commodity prices and an unqualified FX coefficient. Other currencies have explicit unit normalization.

For retail log price p and upstream log landed cost x, a parsimonious candidate is:

    Δp_t = a + φ(L)Δp_(t-1) + Σ[k=0..K] β_k Δx_(t-k) + γ'z_t + ε_t

The sum of β coefficients describes direct cumulative lag contributions; with retail autoregression, compute total dynamic pass-through through the model's impulse response. Do not equate a direct coefficient sum with total long-run response. Fit publication-aligned features, restrict lag search and use shrinkage where needed. Estimate uncertainty with time-series-aware methods and check stability across origins.

Use Engle–Granger/Johansen and a small VECM only when integration order, cointegration, stability and sample size support it. An error-correction term describes adjustment to an estimated long-run relationship; it is not automatic causal identification. If prerequisites fail, report that and retain differenced/distributed-lag models. Store graph edge type, coefficient/response, lag profile, uncertainty, stability, training cutoff and evidence source. Unestimated domain edges remain visibly unestimated.

Granger tests and transfer entropy are supporting predictive diagnostics, with multiplicity controls and finite-sample/permutation checks. With roughly 139 months for most targets, large VARs, extensive lag grids and high-dimensional transfer entropy are unlikely to be well identified. These limitations determine model size.

Later candidates are a small VAR/VECM with correctly handled exogenous paths, a Bayesian structural/state-space or dynamic-factor alternative, filtered Markov regime probabilities, and LightGBM quantile models. Regime probabilities must be filtered using information available at the origin; full-sample smoothing leaks. Panel learning may share information across goods only when every label used was already released.

Unknown future drivers are forecast jointly, simulated or specified as conditional paths, never supplied from realized future data. Unconditional intervals incorporate driver uncertainty as well as model residuals. Test equal-weight ensembles first, then inverse-error weighting and constrained/shrunk stacking using matured out-of-sample errors only.

Scenarios require magnitude, start date, duration and reversion. “Palm oil +20%” is a changed price path. “SGD -5% against USD” must define the quote: a 5% drop in USD per SGD implies SGD per USD rises by 1/0.95−1, approximately 5.26%. “Another export ban” requires country, commodity, exposure and assumed supply/price path; a news label alone does not identify a numerical supply shock. Show conditional impacts and sensitivity ranges, avoid counting the same shock through both news and prices, and label results as model-based conditional scenarios rather than proven causal effects.

## 7. News intelligence and validation

Use exact hashes/canonical URLs plus pinned embeddings and incremental clustering. Stories can gain later corroboration, but later articles must never retroactively alter features recorded for an earlier forecast. Compute novelty relative to prior stories only; normalize counts for changes in monitored-source coverage.

The strict event schema will include all requested fields: event_type, commodities_affected, countries, direction, magnitude, expected_duration, certainty, source_credibility and publish_time. Support multiple events per article and per-commodity direction when effects differ. Add article/story IDs, evidence spans, effective-event date, extraction version and unsupported/unknown markers. Credibility comes from configuration; publication times come from metadata; neither is freely invented by the LLM. Define the 1–5 magnitude rubric and duration units before annotation. When evidence does not support a value, use an explicit unknown/abstention rather than fabricated precision.

Keep all requested event types: trade restrictions, tariffs, disease, weather, harvest, energy, currency, shipping, policy/subsidy and conflict. Economic supply/demand/cost direction is distinct from generic positive/negative news tone. Build daily/weekly event counts, direction indices, supply-shock intensity and novelty with credibility × extraction certainty × relevance × recency weights, capped at story level to limit syndicated duplication. The weights are versioned and sensitivity-tested.

Use at least **100 genuinely human-labelled held-out articles**, plus a separate development set. Split by story cluster and preferably time so syndicated copies and near-duplicates cannot cross the development/test boundary. Include irrelevant/negative examples, several sources and languages where supported, and the event types of interest. A smaller sample cannot establish strong recall for every rare class; report per-class support and uncertainty. A second reviewer adjudicates a subset; measure agreement. LLM-generated labels alone do not satisfy hand labelling. Report event precision/recall/F1, commodity and direction accuracy, schema validity, unsupported claims, and abstention coverage.

Historical publisher pages can be updated, and a modern LLM can contain knowledge of subsequent historical outcomes. Input timestamp filters do not resolve either issue. Use original archived content where allowed, evidence-span extraction, frozen prompts/models and a deterministic comparator; historical modern-LLM results remain retrospective diagnostics. Require prospective evaluation before making strong news-skill claims. This concern is supported by [research on LLM look-ahead bias](https://arxiv.org/abs/2309.17322).

## 8. Evaluation contract and acceptance

Start detailed-target research evaluation after at least 60 monthly training observations: approximately 2020 onward given the currently verified 2015 starts. Eligibility also depends on lag requirements and target publication. A 2012 first origin requires suitable pre-2012 training data, roughly from 2007 or earlier. A separate broad-category 2012 track is possible only where data and vintages support it; it must not count as detailed-item performance.

Use monthly expanding-window outer origins and chronological inner validation. Refit scaling, imputation, factors, lag selection, relationship coefficients, feature selection, model parameters and ensemble rules inside the relevant training window. Fix the experimental protocol before comparing candidates, and reserve the final 36 fully observed monthly origins for an audit where history permits. Keep that audit reserved across Phases 3–5: show development-period performance for modelling choices and open the final comparative audit only after Phase 6 candidate selection is frozen. Report the complete prequential history at final evaluation as well. Adaptive refitting in the audit follows a rule fixed beforehand and uses only newly matured labels; never tune retrospectively to audit outcomes.

At origin o, the seasonal MASE scale is:

    s_(g,o) = mean of |y_t − y_(t−12)| over the training history available at o
    MASE_(g,h) = mean over o of |actual_(g,target(o,h)) − forecast_(g,o,h)| / s_(g,o)

Use identical origins, targets, truth vintages and denominators for paired model comparisons. A zero scale is reported as undefined. **MASE below 1 alone does not prove a win against the evaluated seasonal-naive forecasts**, because the scale is an in-sample seasonal error. Define three-month skill as 1 − MASE_ensemble / MASE_seasonal-naive, and count a win only when this is positive on paired audit origins. Report magnitude and block-bootstrap uncertainty rather than presenting tiny noisy gains as decisive. See [rolling-origin evaluation](https://otexts.com/fpp3/tscv.html) and [MASE](https://otexts.com/fpp2/accuracy.html).

Report MAPE, sMAPE, MASE, directional accuracy, quantile pinball loss, CRPS, empirical 80% coverage, interval width and interval score per good/horizon. Handle zero/near-zero denominators explicitly. CRPS requires predictive samples or a sufficiently rich quantile distribution; three reported quantiles alone do not determine it. The display may show 10/50/90 while the stored distribution is richer. See [distributional evaluation](https://otexts.com/fpp3/distaccuracy.html).

Fit conformal corrections using only previously issued out-of-sample residuals whose target CPI has already been released. A six-month prediction's residual is unavailable until its target publication. Keep calibration selection inside training; track calibration sample counts and avoid claiming validity before sufficient history. Rolling/adaptive methods address shifting data but do not confer unconditional exchangeability guarantees on dependent time series; see [adaptive conformal inference](https://proceedings.neurips.cc/paper/2021/hash/0d441de75945e5acbc865406fc9a2559-Abstract.html).

Check the requested 72–88% empirical coverage band per good/horizon, alongside sample counts, width and uncertainty. Aggregate coverage cannot hide a failed target. Overlapping multi-month errors need block-based uncertainty estimates. Analyse shock versus calmer periods as well.

News ablations compare identical model families, origin sets, structured inputs and tuning budgets on the common news-available period. Compare no news, simple event counts and LLM-extracted indices. Keep shorter news-era results separate from longer structured-only histories. Event studies cover the four requested episodes and distinguish announcement from effective dates. For example, Malaysia's chicken-ban news broke on 23 May 2022, while the restriction took effect on 1 June, according to [Singapore MSE](https://www.mse.gov.sg/latest-news/oral-reply-to-pq-on-food-security/). Those windows are diagnostic cases, not independent proof of causality or a tuning set for the final audit.

Mandatory leakage and correctness tests include:

- Historical as-of joins never select a later release or revised value.
- Truncating or arbitrarily changing future observations/articles leaves prior features and forecasts unchanged.
- Delayed target labels cannot enter direct-horizon training, conformal calibration or ensemble weighting early.
- Future story clusters, preprocessing fits, graph estimates and smoothed regimes cannot flow backward.
- Rebased/classification-changed series do not create artificial history or future basket knowledge.
- Connector pagination, missing sentinels, source revisions, units, duplicate periods, release-time precision and FX quote orientation are validated.
- Metrics agree with hand-computed examples; evaluation model comparisons share the same eligible origins.
- Model failure and missing sources are surfaced, with any predeclared fallback explicitly recorded.

Passing tests demonstrates these information-flow invariants; it does not prove unknown historical source provenance or eliminate LLM pretraining hindsight. Strict results require both tests and audited source evidence.

Lead acceptance reporting with per-food error reductions, coverage/width and block-bootstrap intervals. The current expanded panel is 11 foods; utilities are excluded and onions experimental. Do not silently report an 8-of-12 score on that denominator. Retain failed/ineligible targets and explain them. Deploy a baseline when richer models add no demonstrated value while retaining failed candidate scores.

## 9. Explainability, outlooks and interface

Each forecast artifact contains origin/target months, last observed CPI, median and 10–90% range in index units and percentage change, direction probabilities, model ID, snapshot ID, baseline skill, calibration evidence and model attributions. SHAP explains model dependence, not causality; use coefficient/state decompositions for appropriate econometric models. Explain the final ensemble or make component attribution limits explicit.

Use the horizon-specific training-volatility bands in the approved amendment, frozen before evaluation. Report probabilities of up/unchanged/down separately from any reliability score. A reliability score must expose its provenance, sample, calibration and skill components; absent enough evidence, show unavailable/provisional rather than a fabricated numerical confidence. It is not an LLM self-confidence or probability of correctness.

Outlook notes consume only a validated evidence bundle containing model numbers, supported drivers, source article IDs/URLs and explicit scenario risks. Every quantitative statement links to its forecast record; event assertions cite source articles. Distinguish observed events from possible risks. Include up to three supported drivers and risks; do not manufacture three when the evidence is thinner. Explain what observations or scenario changes would alter the view. Validate numbers/citations automatically and fall back to a deterministic template when generation fails or the cost cap is exhausted.

Streamlit will provide the goods overview, per-good history/fan chart, drivers, news timeline, backtest scorecard, graph and scenario simulator. A weekly report exports the latest validated monthly forecast and timestamped news updates. If weekly forecasts are later desired, they require their own issuance/backtest contract; weekly export alone must not silently change the monthly evaluation protocol.

## 10. Delivery gates

| Phase | Concrete deliverable and stop condition |
|---|---|
| 1 — Plan | This source/target audit, architecture, evaluation contract and open decisions. Stop before implementation. |
| 2 — Data foundation | Five requested source connectors, immutable snapshots/as-of store, source and vintage audit, target coverage/missingness report, notebook with one panel per target and clearly marked experimental onions. Resolve accessible historical detail and terms before declaring PIT coverage. Stop for review. |
| 3 — Baselines | Seasonal naive/random walk/drift/ETS/ARIMA; expanding-window engine, metric tables, baseline intervals, leakage tests, frozen evaluation contract and audit dates. Stop for review. |
| 4 — Relationships | Add WASDE/PSD/NOAA and optional IMF adapter; graph, integration/stability diagnostics, distributed-lag estimates, VECM only where justified, per-good pass-through report including unidentified edges. Stop for review. |
| 5 — News | GDELT and permitted feeds, incremental stories, strict extraction schema, cost ledger, human-labelled evaluation and news indices. Report extraction quality and historical coverage honestly. Stop for review. |
| 6 — Advanced models | State-space/VAR candidates, regimes, quantile boosting, conformal calibration, ensemble selection, matched news ablations, coverage/skill tables and named event studies. Retain simple champions when they win. Stop for review. |
| 7 — Product | Verified attributions, evidence-linked outlooks, scenarios, Streamlit, weekly Markdown/PDF export, documented one-command local run, end-to-end reproducibility check. Stop with acceptance report. |

## 11. Outstanding decisions and risks

Confirmed: split flour and bread into scored CPI targets; keep onions experimental; retain official poultry/milk labels.

Resolved: reconstructed history is primary, strict PIT accumulates prospectively, electricity is driver-only/outside food scores, USD50 monthly development cap, local extraction default, paid historical backfill disabled until held-out validation, and user/second-reviewer annotation responsibilities as above. No further clarification is required to begin the slice.

The largest risks are limited monthly sample sizes; retrospectively published/revised histories; changed CPI baskets; weak freight/seafood proxies; inaccessible original news text; uncertain outlet permissions; LLM historical hindsight; unstable pass-through and policy regimes; and overfitting a small set of famous shocks. These risks are handled by explicit eligibility, parsimonious models, matched backtests, interval diagnostics, frozen audit periods and prospective collection. Forecast performance, calibration and historical coverage remain unmeasured at Phase 1.
