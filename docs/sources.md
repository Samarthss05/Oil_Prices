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
