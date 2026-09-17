# Cooking-oil source contracts

All connectors are public read-only retrievals, rate-limited and bounded. Source failures stop mandatory refresh; there is no synthetic-data fallback. World Bank links are discovered from the official landing page. SingStat search narrows requests to the exact target series; pagination still assembles cells across row boundaries and checks conflicting duplicates.

## Normalized records

`source`, `series_id`, monthly `period`, positive `value`, `unit`, `source_url`, `retrieved_at`, `raw_hash`, `assumed_available_at`, `release_assumption`, `available_at`, `provenance`, `snapshot_id`.

Raw response bytes are content-addressed SHA256 blobs with distinct retrieval manifests even on repeated content. Original publisher/table metadata remains in the bytes. Parquet snapshots have checksummed manifests. DuckDB queries normalized Parquet. Prospective queries choose the latest actually retrieved version per series/month before issuance. Reconstructed queries require a frozen snapshot and use the assumed publication clock. Date-only provenance is never silently upgraded into a verified timestamp.

## Source specifics

- SingStat `M213751`, series `1.01.5.1`, **Vegetable Oils**, index2024=100. StartJanuary2015, current lastJuly2026. Parse `%Y %b`; missing sentinels excluded and missing-month continuity checked. Current tables can include revisions and detail first published retrospectively.
- MAS through SingStat `M700051`, series `1`, **US Dollar**, **Singapore Dollar Per US Dollar**. StartJanuary1988, current lastAugust2026. A rise means SGD buys fewer USD. This is an average quotation, not a tradable market price.
- World Bank `Monthly Prices` worksheet, columns **Palm oil** and **Soybean oil**, units **($/mt)**, `%YM%m` periods. Header located by labels, not fixed numeric columns. StartJanuary1960, current lastAugust2026. Nominal USD per metric tonne. No futures contract series.

Known vintage limitations and source rights are in the README. Personal access to a public endpoint does not establish unrestricted redistribution rights. No attempt was made to bypass blocked MAS, publisher or news services. Original API data and feed material are ignored by Git.

## Prospective news sources in slice v2

| Source | Advertised feed / permission | Handling and limits |
|---|---|---|
| GDELT | [DOC API documentation](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/) | Metadata only; 24-hour overlapping query; throttling/invalid payloads mean unknown coverage. Original publisher rights retained. |
| SFA | [RSS subscription page](https://www.sfa.gov.sg/news-publications/newsroom/subscribe-to-sfa-rss-feeds) | Official newsroom/circular RSS; provided descriptions and attribution only; timezone-less publisher dates remain unknown. |
| FAO | [Official RSS](https://www.fao.org/feeds/fao-newsroom-rss) | Publisher-supplied feed only; copyright notices and links retained. Future-dated items are ineligible until their stated publication time. |
| USDA ARS | [Official feed listing](https://www.ars.usda.gov/news-events/rss-feeds/) | Public agency RSS; supplied text only; freshness checked because observed feed material is old. |
| MPOB PALMOILIS (added) | [Publisher home page advertises RSS](https://palmoilis.mpob.gov.my/); [feed](https://palmoilis.mpob.gov.my/feed/) | Government board's advertised syndication feed, used for personal research. Retain attribution; do not infer a licence to scrape/reproduce linked publications. Often technical bulletins rather than market news. |
| ANTARA business/investment (added) | [Publisher RSS service](https://en.antaranews.com/rss); [advertised feed](https://en.antaranews.com/rss/business-investment.xml); [terms](https://www.antaranews.com/ketentuan-penggunaan) | RSS provides title/summary/link syndication; personal, non-commercial research use only. No linked article bodies or redistribution licence asserted. Source notices retained. |
| USDA NASS (disabled) | [Official syndication page](https://data.nass.usda.gov/Newsroom/Syndication/News/index.php) | HTTP403 at initial attempt; no bypass. |

New-feed discovery and a live collector check occurred on 17 September 2026 outside the test suite. Tests use fixtures/mocks and block network connections. No paid commodity-futures connector is enabled. Hosted archive persistence and visibility limits are documented in [news operations](news.md).
