# Crawler Operation Policy

## Overview

This document is the single operating standard for crawler code, local data folders, DB tables, S3 storage, resume behavior, and retailer extension.

Best Buy is the current reference implementation, but the same structure should be reused for other retailers unless a retailer-specific constraint requires a different approach.

The crawler should be:

- resumable
- auditable
- cheap to rerun
- easy to debug after the crawl
- compatible with S3 and DB loading

## Standard Pipeline Flow

Most retailer crawlers should follow this shape:

```text
input config
  -> main list collection
  -> main target extraction
  -> bsr list collection
  -> bsr rank extraction
  -> promotion collection
  -> trending collection
  -> final target build
  -> detail enrichment
  -> review enrichment
  -> status check
  -> S3 sync
  -> local cleanup
  -> DB table preparation
  -> DB load
```

Not every retailer/category has every source. Missing sources should be skipped cleanly, not treated as failures.

Examples:

- TV may have main, bsr, promotion, trend, detail, review.
- HHP may have main, bsr, promotion, trend, detail, review.
- REF/LDY may only have main and bsr at first.
- Some retailers may not expose review GraphQL and may need HTML review pages.

## Script Naming

Use numeric step prefixes for executable pipeline modules.

Pattern:

```text
stepNN_subject.py
```

Examples:

```text
step01_main_list.py
step02_main_targets.py
step03_bsr_list.py
step04_bsr_rank.py
step05_promotion_deals.py
step06_trending_deals.py
step07_final_targets.py
step08_detail_enrichment.py
step09_review20.py
step10_status_check.py
step11_s3_sync.py
step12_local_cleanup.py
step13_db_prepare.py
step14_db_load.py
```

Rules:

1. Step numbers must be unique.
2. Do not skip numbers without a reason.
3. Keep the step name action-oriented and short.
4. Keep orchestration separate from steps.
5. Shared helpers should not use step numbers unless they are part of the executable flow.

Use `step00_` for shared helper modules used by multiple steps:

```text
step00_config.py
step00_apollo.py
step00_graphql_query.py
step00_parse_search.py
step00_parse_pdp.py
step00_detail_benchmarks.py
```

Each retailer should have one orchestrator:

```text
{retailer}/{retailer}_orchestrator.py
```

Example:

```text
bestbuy/bestbuy_orchestrator.py
```

The orchestrator should support:

- selected steps
- `--all`
- `--from-step`
- `--resume`
- `--dry-run`
- category/product type selection
- optional source skipping when DB URLs are missing

## Data Folder Policy

The default local data layout is:

```text
retailer/data/{product_type}/{run_date}/{subject}/...
```

Example:

```text
bestbuy/data/tv/20260517/main
bestbuy/data/tv/20260517/bsr
bestbuy/data/tv/20260517/promotion
bestbuy/data/tv/20260517/trending
bestbuy/data/tv/20260517/detail
bestbuy/data/tv/20260517/output
```

Rules:

1. Keep retailer-specific data under that retailer folder.
2. Product type comes before date.
3. Date folders use `YYYYMMDD`.
4. Do not repeat the date inside child folder names.
5. Use simple subject names: `main`, `bsr`, `promotion`, `trending`, `detail`, `output`, `status`, `archive`.

Each collection subject should follow this pattern when possible:

```text
{subject}/
  raw/
  parsed/
  benchmarks/
```

## Development Attempt Logging Policy

Every crawler development task and site-access experiment must leave a human
audit trail in the channel development log.

Default path:

```text
{retailer}_dev_log/{YYYYMMDD}_{retailer}_{product_type}_tests.md
```

Examples:

```text
lowes_dev_log/20260517_lowes_ldy_tests.md
bestbuy_dev_log/20260517_bestbuy_hhp_tests.md
```

This log is separate from per-run runtime logs. Runtime logs answer "what did
the script do while running?" Development logs answer "why did we try this, in
what conditions, and what did we learn?"

Record an entry whenever any of these happen:

- crawler code is changed
- selectors, parsers, request headers, cookies, browser settings, proxy options,
  API transports, ZenRows parameters, retry settings, or timeouts are changed
- a collection failure is investigated, bypassed, or retried
- a site/API access path is tested
- DB, S3, or local cleanup behavior is tested
- a run produces a useful success, failure, or partial result

Each entry should include:

- local timestamp and timezone
- channel/retailer, product type, step, and run root
- command or code path used
- relevant environment variables and request conditions
- request variant, browser/API mode, proxy/header/cookie settings when relevant
- result: success/failure, status code, row counts, elapsed time, and error body
- raw artifact paths and manifest paths
- files changed
- interpretation and next recommended action

Never write secrets to the development log. Redact API keys, passwords, database
URLs, session cookies, authorization headers, and other credentials.

Per-run logs should continue to be written under:

```text
{retailer}/data/{product_type}/{YYYYMMDD}/{subject}/logs/run.log
```

## Raw Artifact Policy

Raw artifacts are grouped by request unit, not dumped flat into one folder.

### Main / BSR GraphQL

Use one folder per page and status:

```text
main/raw/main_graphql/page_001_success/
  page_001_request.json
  page_001_response.txt
  page_001_response.json
  page_001_headers.json
  page_001_meta.json

bsr/raw/main_graphql/page_001_success/
```

Failure:

```text
page_001_fail/
```

### Detail HTML

Use one folder per SKU and status:

```text
detail/raw/detail_html/{main_rank}_{sku_id}_success/
  {sku_id}.html
  {sku_id}_apollo.json
  {sku_id}_headers.json
  {sku_id}_meta.json
```

Failure:

```text
{main_rank}_{sku_id}_fail/
```

### Review GraphQL

Use the same SKU/status pattern:

```text
detail/raw/review20/{main_rank}_{sku_id}_success/
  {sku_id}_request.json
  {sku_id}_response.txt
  {sku_id}_response.json
  {sku_id}_headers.json
  {sku_id}_meta.json
```

### Promotion

Use one folder per promotion placement and status:

```text
promotion/raw/{placement}_success/
  {placement}_request.json
  {placement}_response.txt
  {placement}_response.json
  {placement}_headers.json
```

### Trending

Use the same request-unit principle. If there is one page request:

```text
trending/raw/trending_success/
```

If trending has multiple tabs or placements:

```text
trending/raw/{placement}_success/
```

## Parsed and Output Files

Parsed files are stable interfaces between pipeline steps.

Common parsed files:

```text
main/parsed/main_occurrences.csv
main/parsed/main_target_occurrences.csv
bsr/parsed/bsr_rank_map.csv
promotion/parsed/all_promotion_products.csv
trending/parsed/trending_products.csv
detail/parsed/detail_enriched_rows.csv
detail/parsed/detail_failures.csv
```

DB/S3-facing output files:

```text
output/bestbuy_final_targets.csv
output/bestbuy_product_list.csv
output/final_output.csv
```

Meaning:

- `bestbuy_final_targets.csv`: target rows for detail enrichment.
- `bestbuy_product_list.csv`: listing-level DB output, detail excluded.
- `final_output.csv`: final integrated result with detail and review enrichment.

## DB Policy

The database is the source of operational configuration and the destination for curated outputs. Local files are used for raw audit, resume, parser debugging, and S3 archival.

### Input URLs

Initial crawl URLs should be managed in:

```text
public.dx_target_page_url
```

Expected fields:

```text
corp
product_line
account_name
page_type
url_template
```

Rules:

1. Code should load URLs from DB first.
2. CSV/default URL fallback is only for development or DB outage.
3. If a category has no `promotion` or `trend` URL, the corresponding step must skip cleanly.
4. URL templates may include `{page}`.

### Selectors

HTML selectors should be managed in:

```text
public.dx_xpath_selectors
```

Expected fields:

```text
corp
product_line
account_name
page_type
data_field
xpath
previous_xpath
is_active
```

Rules:

1. GraphQL/Apollo is the primary parser where available.
2. `dx_xpath_selectors` is used as an HTML fallback and product-type-specific enrichment layer.
3. Selectors should be filtered by `product_line`, `account_name`, `page_type`, and `is_active = true`.
4. When selectors change, keep old values in `previous_xpath` or deactivate them instead of deleting history.

### Best Buy Final Tables

Final detail/review-enriched outputs load to:

```text
public.tv_retail_com_bby_v2_test
public.hhp_retail_com_bby_v2_test
public.ref_retail_com_bby
public.ldy_retail_com_bby
```

Notes:

- TV and HHP are test tables because operational tables already exist.
- REF and LDY are new category tables.
- `final_output.csv` must match target DB column names and order exactly.
- Insert tests should omit serial `id` when the table has an auto-increment key.

### Best Buy Listing Tables

Listing-level outputs load to:

```text
public.bby_tv_product_list_v2_test
public.bby_hhp_product_list_v2_test
public.bby_ref_product_list
public.bby_ldy_product_list
```

Purpose:

- Store main/bsr/promotion/trend-level product-list data.
- Exclude detail-page and review-page enrichment.
- Serve as a lightweight daily listing snapshot.

Important schema notes:

- TV listing DDL differs from HHP listing DDL.
- TV has `crawl_datetime` and `promotion_position int4`.
- HHP has `crawl_strdatetime` and includes listing price fields.
- REF/LDY should use their own DDL when provided. Until then, use HHP-like listing schema as a working default.

### Lowe's Final Tables

Lowe's final detail-enriched outputs load to:

```text
public.ref_retail_com_lowes
public.ldy_retail_com_lowes
```

Current Lowe's table contract is a working schema until a wide retailer-specific
DDL is provided:

- preserve the complete `final_output.csv` row in `row_json jsonb`
- project common searchable fields such as `omni_item_id`, `brand`,
  `model_id`, `main_rank`, `final_selling_price`
- delete existing rows for the same `batch_id` before reload when possible
- otherwise truncate on explicit test reloads

Reference DDL:

```text
references/lowes_final_table_ddl.txt
```

### Schema Creation

Always create tables with an explicit schema:

```sql
CREATE TABLE public.table_name (...)
```

Do not rely on `search_path`.

### DB Preparation and Load

DB work is split into two explicit pipeline steps:

```text
step13_db_prepare.py
step14_db_load.py
```

`step13_db_prepare.py` is responsible for schema/table preparation only:

- create missing final tables when allowed
- create missing product-list tables
- create basic indexes for product-list tables
- never insert crawler result rows

`step14_db_load.py` is responsible for final data insertion:

- load `output/final_output.csv` into the category final table
- load `output/bestbuy_product_list.csv` into the category product-list table
- omit serial `id` columns on insert
- match DB columns by column name
- delete existing rows for the same `batch_id` before inserting when the target table has `batch_id`

DB load is intentionally after S3 sync and local cleanup:

```text
generate outputs -> S3 backup -> local retention cleanup -> DB prepare -> DB load
```

This keeps raw artifacts backed up before curated DB rows are committed.

## Promotion Position Standard

Business meaning:

```text
promotion_position = position of the product inside the promotion div/section
```

Internal standard:

```text
promotion_type     = Promo A ||| Promo B
promotion_position = 2 ||| 5
```

This preserves pair order:

```text
Promo A -> 2
Promo B -> 5
```

If a DB table column is integer, only one numeric value can be inserted. In that case:

- Preserve full paired values in upstream CSVs.
- Insert the first numeric value into the integer DB column.
- Prefer changing future listing DDL to `varchar` if multi-promotion preservation is required in DB.

## S3 Policy

Local disk is working cache, not long-term storage. S3 is the long-term artifact store.

### Bucket and Prefix

Crawler backup artifacts are uploaded to:

```text
s3://dx-crawl-fileserver-bucket/retail_backup/{retailer}/{product_type}/{run_date}/...
```

Example:

```text
s3://dx-crawl-fileserver-bucket/retail_backup/bestbuy/tv/20260517/main/
s3://dx-crawl-fileserver-bucket/retail_backup/bestbuy/tv/20260517/detail/
s3://dx-crawl-fileserver-bucket/retail_backup/bestbuy/tv/20260517/output/
```

`retail_backup` is for crawler artifacts:

- raw request/response files
- parsed CSVs
- benchmarks
- manifests
- operational outputs

`retail` is reserved for final curated/consumer-facing result files.

Current environment keys:

```text
AWS_REGION=ap-northeast-2
S3_BUCKET=dx-crawl-fileserver-bucket
S3_PREFIX=retail_backup
S3_UPLOAD_RAW=1
S3_DELETE_EXTRA=0
S3_STORAGE_CLASS=STANDARD
```

Recommended local/S3/DB split:

```text
local: current day and recent cache
S3: raw, parsed, benchmarks, manifests, outputs
DB: final integrated outputs and listing outputs
```

### Upload Step

S3 sync should be a pipeline step:

```text
step11_s3_sync.py
```

S3 sync must:

1. Use AWS CLI or an equivalent S3 client.
2. Retry failed uploads.
3. Write `s3_sync_manifest.json` into the run root.
4. Upload `s3_sync_manifest.json` to S3 with the rest of the run folder.
5. Mark success only after sync succeeds and remote listing verification succeeds.
6. Never delete local files.
7. Avoid `--delete` unless explicitly enabled.

Default retry behavior:

```text
S3_SYNC_MAX_ATTEMPTS=3
S3_SYNC_RETRY_SECONDS=10
S3_VERIFY_AFTER_SYNC=1
```

Dry-run must be used before enabling a new bucket/prefix:

```powershell
$env:S3_DRY_RUN='1'
python -m bestbuy.step11_s3_sync
```

Actual upload:

```powershell
$env:S3_DRY_RUN='0'
python -m bestbuy.step11_s3_sync
```

Observed successful TV example:

```text
source: bestbuy/data/tv/20260517
target: s3://dx-crawl-fileserver-bucket/retail_backup/bestbuy/tv/20260517
objects: 3203
size: 248,230,643 bytes
```

Observed limited category test examples:

```text
HHP target: s3://dx-crawl-fileserver-bucket/retail_backup/bestbuy/hhp/20260517
HHP objects: 509
HHP size: 29,038,528 bytes

REF target: s3://dx-crawl-fileserver-bucket/retail_backup/bestbuy/ref/20260517
REF objects: 517
REF size: 39,524,540 bytes

LDY target: s3://dx-crawl-fileserver-bucket/retail_backup/bestbuy/ldy/20260517
LDY objects: 534
LDY size: 34,378,385 bytes
```

### Upload Success Contract

A run is considered safely backed up only when:

```text
{run_root}/s3_sync_manifest.json
```

contains:

```json
{
  "success": true
}
```

The manifest should include:

- source run root
- target S3 URI
- dry-run flag
- retry attempts
- upload command result
- remote listing verification result
- final success flag

If sync fails after retries, keep local files and rerun the S3 step later.

### Local Retention

Local cleanup should only run after successful S3 verification:

```text
step12_local_cleanup.py
```

Default local retention:

```text
7 days
```

Cleanup rules:

1. Keep local data for 7 days by default.
2. Cleanup runs as part of the pipeline after S3 sync.
3. A date folder can be deleted only when its own `s3_sync_manifest.json` has `success: true`.
4. The current run folder is never deleted.
5. If S3 upload failed or is only partially complete, keep the local folder.

Cleanup dry-run for inspection:

```powershell
$env:LOCAL_CLEANUP_DRY_RUN='1'
python -m bestbuy.step12_local_cleanup
```

Actual cleanup, which is also the pipeline default:

```powershell
$env:LOCAL_CLEANUP_DRY_RUN='0'
python -m bestbuy.step12_local_cleanup
```

The orchestrator should run `step12_local_cleanup.py` immediately after `step11_s3_sync.py`.
This does not delete the current run. It only deletes older date folders that are past
retention and already have a successful S3 manifest.

## Resume and Retry Policy

The crawler should not restart from scratch when rerun on the same day.

Resume logic should:

1. Check expected raw request folders.
2. Treat `*_success` folders with valid meta/response JSON as cache.
3. Retry missing or `*_fail` folders.
4. Rebuild parsed/output CSVs after upstream data changes.
5. Always refresh status checks.

Do not delete successful raw artifacts during normal resume.

## Limited Test Runs

Use limited runs before full production runs for a new product type, new DB table, or new S3 prefix.

Recommended limited Best Buy test:

```powershell
$env:BESTBUY_URL_SOURCE='db'
$env:BESTBUY_MAIN_PAGES='3'
$env:BESTBUY_DETAIL_LIMIT='50'
$env:S3_DRY_RUN='0'

python -m bestbuy.bestbuy_orchestrator --category HHP --all
python -m bestbuy.bestbuy_orchestrator --category REF --all
python -m bestbuy.bestbuy_orchestrator --category LDY --all
```

Meaning:

- `BESTBUY_MAIN_PAGES=3`: collect 3 pages for main and bsr in the current test configuration.
- `BESTBUY_DETAIL_LIMIT=50`: fetch detail/review for the first 50 target SKUs.
- `S3_DRY_RUN=0`: perform real S3 upload.
- `--all`: run the full step chain including S3, cleanup, DB prepare, and DB load.

Important:

- A limited test can still produce more target rows than detailed rows.
- DB rows may contain blank detail fields for unprocessed SKUs when `BESTBUY_DETAIL_LIMIT` is set.
- Production DB loads should decide whether to insert all target rows or only detail-success rows.
- If bsr page count needs to differ from main page count, split the environment controls before production use.

## Error Handling

Each request unit should have a meta file with:

```text
status_code
success
attempt
elapsed_seconds
x_request_cost
error
bytes
started_at
finished_at
```

Parsed failure outputs should include:

```text
sku_id or page/placement
stage
attempt
status_code
error
retryable
```

## Raw Storage Policy

Store enough raw artifacts for audit and parser debugging, but keep them slim.

Preferred:

- GraphQL request/response JSON
- response text when useful
- headers
- meta
- slim HTML
- extracted Apollo JSON

Avoid storing full rendered HTML when slim HTML plus Apollo JSON is enough.

The reason raw is retained is to allow parser fixes after the crawl without paying for another fetch.

## Archive Policy

Use `archive/` for old experiments, abandoned structures, probes, or pre-refactor runs.

Do not mix archive data with the current operational path.

Example:

```text
bestbuy/data/tv/20260517/archive/{reason_or_old_run_name}/...
```

## Retailer Extension Rules

When adding another retailer:

1. Create a retailer folder.
2. Copy the same step structure where applicable.
3. Keep input URLs in DB.
4. Keep selectors in DB.
5. Use retailer-specific parser helpers only when unavoidable.
6. Keep final output DB schemas as the contract.
7. Add retailer-specific notes only where behavior diverges.

Example:

```text
walmart/
  walmart_orchestrator.py
  step00_config.py
  step01_main_list.py
  ...

amazon/
  amazon_orchestrator.py
  step00_config.py
  step01_main_list.py
  ...
```

## Best Buy Reference Flow

Current Best Buy flow:

```text
step01_main_list
step02_main_targets
step03_bsr_list
step04_bsr_rank
step05_promotion_deals
step06_trending_deals
step07_final_targets
step08_detail_enrichment
step09_review20
step10_status_check
step11_s3_sync
step12_local_cleanup
step13_db_prepare
step14_db_load
```

Best Buy currently uses:

```text
main/bsr: GraphQL/Apollo
promotion: GraphQL/Apollo
trending: page/Apollo or HTML card extraction
detail: Apollo first, selector fallback
review20: GraphQL from PDP Apollo query
```

Latest limited test status:

```text
HHP: ran main 3 pages, bsr 3 pages, detail/review limit 50, S3 upload, DB load.
REF: ran main 3 pages, bsr 3 pages, detail/review limit 50, S3 upload, DB load.
LDY: ran main 3 pages, bsr 3 pages, detail/review limit 50, S3 upload, DB load.
TV: full prior run exists; skipped in this limited test.
```

Limited test DB inserts:

```text
HHP final table: public.hhp_retail_com_bby_v2_test, 118 rows
HHP product list: public.bby_hhp_product_list_v2_test, 118 rows

REF final table: public.ref_retail_com_bby, 109 rows
REF product list: public.bby_ref_product_list, 109 rows

LDY final table: public.ldy_retail_com_bby, 102 rows
LDY product list: public.bby_ldy_product_list, 102 rows
```

Known follow-up:

```text
HHP promotion/trending must be reviewed before production because the current promotion/trend collection can still use TV-oriented placement/label assumptions.
REF/LDY currently skip promotion/trending when DB target URLs are absent.
```

## Lowe's Current Status

Current Lowe's flow follows the same step numbering as Best Buy:

```text
step01_main_list
step02_main_targets
step03_bsr_list
step04_bsr_rank
step05_promotion_deals
step06_trending_deals
step07_final_targets
step08_detail_enrichment
step09_review20
step10_status_check
step11_s3_sync
step12_local_cleanup
step13_db_prepare
step14_db_load
```

Current Lowe's DB output tables:

```text
REF: public.ref_retail_com_lowes
LDY: public.ldy_retail_com_lowes
```

Latest LDY note:

```text
LDY table exists: public.ldy_retail_com_lowes
LDY /search/products ZenRows API test returned repeated HTTP 504.
Next LDY collection should use a fresh browser/session curl and LOWES_API_TRANSPORT=curl.
```
