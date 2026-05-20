# Amazon Development Log - 2026-05-17

Updated at: 2026-05-17 15:50:09 +09:00

## Scope

Retailer: `Amazon`

Goal: reduce crawler cost by trying direct/VPN-friendly requests before ZenRows,
and make benchmark CSVs append in realtime.

## Test Timeline

### 16:04:56 - Free direct expansion test plan

Request:

- Spend time testing free Amazon crawl paths if they look viable.
- Keep paid ZenRows out of the test unless explicitly selected later.

Next free-only candidates:

1. Search URL template variants:
   - default clean `https://www.amazon.com/s?k=tv`
   - CSV/search-session URL currently used by config
   - alternate query terms such as `television`
2. BSR-first seed expansion:
   - use BSR direct as the stable seed source
   - test more BSR pages if Amazon returns useful rows
3. Detail endurance:
   - expand from 50 consecutive PDPs to 100+ direct PDP fetches
   - confirm benchmark remains all `transport=direct`

Paid boundary:

- Keep `AMAZON_FETCH_MODE=direct`.
- Keep `AMAZON_DETAIL_FETCH_MODE=direct`.
- No DB/S3 steps.

### 17:23:20 - Clean search URL without interstitial solver

Command:

```powershell
$env:AMAZON_MAIN_RUN_ID='main_direct_clean_tv'
$env:AMAZON_FETCH_MODE='direct'
$env:AMAZON_MAIN_FETCH_MODE='direct'
$env:AMAZON_MAIN_URL_TEMPLATE='https://www.amazon.com/s?k=tv'
$env:AMAZON_MAIN_PAGES='5'
$env:AMAZON_PAGE_WORKERS='1'
$env:AMAZON_MAX_ATTEMPTS='1'
python -m amazon.step01_main_list
```

Result:

- HTTP 200 for 5/5 pages, but response bodies were only about 2.2 KB.
- Parsed rows: 0.
- Response was an Akamai/Amazon interstitial with `bm-verify` and
  `/_sec/verify?provider=interstitial`.

Conclusion:

- Plain direct requests are not enough for search pages.
- This is a free-solvable browser JavaScript proof step, not immediately a
  ZenRows-only problem.

Implemented:

- Added `amazon/step00_direct.py`.
- Added direct interstitial verification:
  - parse `bm-verify`
  - compute `pow`
  - POST to `/_sec/verify?provider=interstitial`
  - retry original URL in the same session

### 17:24:58 - Clean search URL with free interstitial solver

Command:

```powershell
$env:AMAZON_MAIN_RUN_ID='main_direct_clean_tv_verify'
$env:AMAZON_FETCH_MODE='direct'
$env:AMAZON_MAIN_FETCH_MODE='direct'
$env:AMAZON_MAIN_URL_TEMPLATE='https://www.amazon.com/s?k=tv'
$env:AMAZON_MAIN_PAGES='5'
python -m amazon.step01_main_list
```

Result:

- Search pages: 5/5 valid.
- Rows: 108 occurrences.
- Unique ASINs: 92.
- Transport: direct only.
- ZenRows cost: 0.

Conclusion:

- The free interstitial solver works.

### 17:26:03 - 100-detail direct-only endurance test

Input preparation:

```powershell
$env:AMAZON_MAIN_RUN_ID='main_direct_clean_tv_verify'
python -m amazon.step02_main_targets

$env:AMAZON_MAIN_RUN_ID='main_direct_clean_tv_verify'
$env:AMAZON_FINAL_TARGET_SIZE='180'
python -m amazon.step07_final_targets
```

Result:

- Main unique ASINs: 92.
- BSR rows used: 100.
- Final targets: 152.

Detail command:

```powershell
$env:AMAZON_FETCH_MODE='direct'
$env:AMAZON_DETAIL_FETCH_MODE='direct'
$env:AMAZON_DETAIL_FORCE_ALL='1'
$env:AMAZON_DETAIL_USE_RAW_CACHE='0'
$env:AMAZON_DETAIL_LIMIT='100'
$env:AMAZON_DETAIL_MAX_ATTEMPTS='1'
python -m amazon.step08_detail_enrichment
```

Result:

- Candidate count: 100.
- Detail PDPs: 100/100 HTTP 200 and parsed product name.
- Failure rows: 0.
- Interstitial/captcha flags: 0.
- Transport: direct only.

Implementation fix after this run:

- Detail benchmark CSV should not be cleared on every run.
- Added `AMAZON_DETAIL_CLEAR_BENCHMARKS=1` as the explicit opt-in clear switch.

### 18:26:16 - BSR direct page-depth test

Command:

```powershell
$env:AMAZON_BSR_RUN_ID='bsr_direct_4p'
$env:AMAZON_FETCH_MODE='direct'
$env:AMAZON_BSR_FETCH_MODE='direct'
$env:AMAZON_BSR_PAGES='4'
python -m amazon.step03_bsr_list
```

Result:

- Page 1: HTTP 200, 50 rows.
- Page 2: HTTP 200, 50 rows.
- Page 3: HTTP 400, 0 rows.
- Page 4: HTTP 400, 0 rows.
- Total rows: 100.

Conclusion:

- TV BSR direct is stable for pages 1-2.
- Pages 3+ are not useful for this category URL.

### 18:30:17 - Search 10 pages, no session delay

Command:

```powershell
$env:AMAZON_MAIN_RUN_ID='main_direct_clean_tv_verify_10p'
$env:AMAZON_MAIN_URL_TEMPLATE='https://www.amazon.com/s?k=tv'
$env:AMAZON_MAIN_PAGES='10'
$env:AMAZON_PAGE_WORKERS='1'
python -m amazon.step01_main_list
```

Result:

- Pages 1-6: valid HTTP 200 product HTML.
- Pages 7-10: HTTP 503 short responses.
- Rows: 130 occurrences.
- Unique ASINs: 107.

Conclusion:

- Interstitial solving works, but rapid page progression can trigger later-page
  503s.

Implemented:

- Reused a single direct `requests.Session` across main search pages.
- Added `AMAZON_PAGE_DELAY_SECONDS`.
- Defaulted Amazon main direct page delay to `3` seconds.

### 18:43:30 - Search 10 pages with session reuse and 3s delay

Command:

```powershell
$env:AMAZON_MAIN_RUN_ID='main_direct_clean_tv_session_delay_10p'
$env:AMAZON_MAIN_URL_TEMPLATE='https://www.amazon.com/s?k=tv'
$env:AMAZON_MAIN_PAGES='10'
$env:AMAZON_PAGE_WORKERS='1'
$env:AMAZON_PAGE_DELAY_SECONDS='3'
python -m amazon.step01_main_list
```

Result:

- Pages: 10/10 valid.
- Rows: 219 occurrences.
- Unique ASINs: 138.
- Failed pages: 0.
- Transport: direct only.

Conclusion:

- Session reuse + 3 second delay is the current best free Amazon search method.

### 18:45:08 - Search 20 pages with session reuse and 3s delay

Command:

```powershell
$env:AMAZON_MAIN_RUN_ID='main_direct_clean_tv_session_delay_20p'
$env:AMAZON_MAIN_URL_TEMPLATE='https://www.amazon.com/s?k=tv'
$env:AMAZON_MAIN_PAGES='20'
$env:AMAZON_PAGE_WORKERS='1'
$env:AMAZON_PAGE_DELAY_SECONDS='3'
python -m amazon.step01_main_list
```

Result:

- Pages: 20/20 valid.
- Rows: 425 occurrences.
- Unique ASINs: 221.
- Failed pages: 0.
- Transport: direct only.

Final target rebuild:

```powershell
$env:AMAZON_MAIN_RUN_ID='main_direct_clean_tv_session_delay_20p'
python -m amazon.step02_main_targets

$env:AMAZON_MAIN_RUN_ID='main_direct_clean_tv_session_delay_20p'
$env:AMAZON_FINAL_TARGET_SIZE='300'
python -m amazon.step07_final_targets
```

Result:

- Main target rows: 221.
- BSR rank rows: 100.
- Final target rows: 277.

### 09:17:19 - 150-detail direct-only endurance test

Note:

- A first attempt accidentally used the current date-derived run root
  `amazon/data/tv/20260520` and produced 0 candidates.
- No network detail collection happened in that accidental run.
- The command was rerun with `AMAZON_RUN_DATE=20260517` and
  `AMAZON_RUN_ROOT=.../amazon/data/tv/20260517`.

Command:

```powershell
$env:AMAZON_RUN_DATE='20260517'
$env:AMAZON_RUN_ROOT='C:\Users\gom\samsung_crawl\amazon\data\tv\20260517'
$env:AMAZON_MAIN_RUN_ID='main_direct_clean_tv_session_delay_20p'
$env:AMAZON_FETCH_MODE='direct'
$env:AMAZON_DETAIL_FETCH_MODE='direct'
$env:AMAZON_DETAIL_FORCE_ALL='1'
$env:AMAZON_DETAIL_USE_RAW_CACHE='0'
$env:AMAZON_DETAIL_RERUN_FINAL_TARGETS='1'
$env:AMAZON_DETAIL_LIMIT='150'
$env:AMAZON_DETAIL_MAX_ATTEMPTS='1'
$env:AMAZON_FINAL_TARGET_SIZE='300'
python -m amazon.step08_detail_enrichment
```

Result:

- Candidate count: 150.
- Detail PDPs: 150/150 HTTP 200 and parsed product name.
- Failure rows: 0.
- Transport: direct only.
- Final target rows after rerun: 277.
- Final output rows after status check: 277.
- Raw detail meta files with `transport=direct`: 205.
- Bad raw detail meta count: 0.

Final status:

```text
main_rows=425
main_target_rows=221
bsr_rows=100
bsr_rank_rows=100
final_target_rows=277
final_output_rows=277
detail_success_files=205
detail_failure_rows=0
```

Current selected free method:

```text
Proton VPN US
  -> direct requests
  -> Amazon bm-verify interstitial solver
  -> one requests.Session reused across search pages
  -> AMAZON_PAGE_DELAY_SECONDS=3
  -> BSR pages 1-2 as stable supplemental seed
  -> direct PDP detail collection, single worker
```

ZenRows status:

- Not needed for Amazon TV main/BSR/detail under this VPN condition.
- Keep ZenRows disabled unless this direct path starts returning unsolved
  interstitials, captcha pages, or repeated 503s.

### 15:56:42 - Free direct strategy reset before 50-detail test

Correction:

- The previous limited run was too small to prove operational viability.
- User set the practical success bar to at least 50 consecutive detail pages.
- `AMAZON_FETCH_MODE=auto` is not appropriate for the next discovery test
  because it can touch paid ZenRows fallback.

Selected direction:

- Do not start with raw `requests` as the primary Amazon bypass path.
- Use a free local browser/VPN session first, then reuse the session for direct
  detail collection.

Candidate approach:

```text
local VPN
  -> persistent browser profile
  -> warm up through Amazon search / BSR / a few PDPs
  -> collect listing/detail URLs from rendered browser state or cached HTML
  -> fetch PDP HTML through the same local browser/session path
  -> append detail benchmark per ASIN
  -> prove 50 consecutive PDP parses before considering ZenRows
```

Next test should force:

```text
AMAZON_FETCH_MODE=direct
AMAZON_DETAIL_FETCH_MODE=direct
AMAZON_DETAIL_LIMIT=50
```

Paid boundary:

- ZenRows must not be used in this test.
- If local browser/session direct fails before 50 PDPs, record the exact block
  signal and only then discuss paid fallback.

### 15:58:28 - Amazon TV direct-only CSV cycle, VPN connected

VPN condition from user screenshot:

```text
Provider: Proton VPN
Country: United States
Region/server: Washington / Seattle / US-WA#315
Protocol: WireGuard UDP
VPN IP shown: 159.26.103.74
```

Command:

```powershell
$env:AMAZON_PRODUCT_TYPE='TV'
$env:AMAZON_MARKETPLACE='US'
$env:AMAZON_FETCH_MODE='direct'
$env:AMAZON_MAIN_FETCH_MODE='direct'
$env:AMAZON_BSR_FETCH_MODE='direct'
$env:AMAZON_DETAIL_FETCH_MODE='direct'
$env:AMAZON_MAIN_PAGES='3'
$env:AMAZON_BSR_PAGES='2'
$env:AMAZON_DETAIL_LIMIT='50'
$env:AMAZON_FINAL_TARGET_SIZE='80'
$env:AMAZON_PAGE_WORKERS='1'
$env:AMAZON_MAX_ATTEMPTS='1'
$env:AMAZON_DETAIL_MAX_ATTEMPTS='1'
$env:ZENROWS_TIMEOUT='90'
python -m amazon.amazon_orchestrator --product-type TV 01 02 03 04 07 08 10
```

Scope:

- CSV/local output only.
- No S3 sync.
- No DB prepare/load.
- ZenRows disabled by mode: `direct`.

Result:

- Main search:
  - 3 direct pages fetched.
  - Page 1: HTTP 200, 2,663 bytes, 0 parsed rows.
  - Page 2: HTTP 200, 2,663 bytes, 0 parsed rows.
  - Page 3: HTTP 200, 1,768,340 bytes, 22 parsed rows.
  - Main rows: 22.
- BSR:
  - 2 direct pages fetched.
  - Page 1: 50 rows.
  - Page 2: 50 rows.
  - BSR rows: 100.
- Final targets:
  - 80 rows.
- Detail:
  - Initial run processed 25 candidates because existing logic only enriched
    rows missing detail-like fields.
  - 25/25 direct PDPs returned HTTP 200 and parsed product names.
  - Failure rows: 0.

Issue found:

- Existing detail candidate selection was too conservative for a 50-consecutive
  proof test.
- Added `AMAZON_DETAIL_FORCE_ALL=1` so final target rows can be forced through
  detail collection even when listing data already has name/image/price.

### 16:01:19 - Amazon TV 50-detail direct-only proof test

Command:

```powershell
$env:AMAZON_PRODUCT_TYPE='TV'
$env:AMAZON_MARKETPLACE='US'
$env:AMAZON_FETCH_MODE='direct'
$env:AMAZON_DETAIL_FETCH_MODE='direct'
$env:AMAZON_DETAIL_FORCE_ALL='1'
$env:AMAZON_DETAIL_USE_RAW_CACHE='0'
$env:AMAZON_DETAIL_LIMIT='50'
$env:AMAZON_DETAIL_MAX_ATTEMPTS='1'
$env:ZENROWS_TIMEOUT='90'
python -m amazon.amazon_orchestrator --product-type TV 08 10
```

Result:

- Candidate count: 50.
- Cache disabled for detail fetch: `AMAZON_DETAIL_USE_RAW_CACHE=0`.
- Transport: direct only.
- Detail benchmark rows: 50.
- `transport=direct`: 50/50.
- HTTP 200 + `detail_status=parsed`: 50/50.
- Interstitial/captcha flags: 0/50.
- Detail failures CSV rows: 0.
- ZenRows request cost: 0, no `x_request_cost` values.
- Final output CSV rows after rerun: 115.

Key artifacts:

```text
amazon/data/tv/20260517/main/benchmarks/page_benchmarks.csv
amazon/data/tv/20260517/bsr/benchmarks/page_benchmarks.csv
amazon/data/tv/20260517/detail/benchmarks/detail_benchmarks.csv
amazon/data/tv/20260517/detail/parsed/detail_map.csv
amazon/data/tv/20260517/detail/parsed/detail_failures.csv
amazon/data/tv/20260517/output/amazon_final_targets.csv
amazon/data/tv/20260517/output/final_output.csv
amazon/data/tv/20260517/status/20260517_status.json
```

Conclusion:

- Selected free Amazon TV path: Proton VPN US + direct requests.
- The strongest stable seed source in this run is BSR direct pages, not search
  page 1/2.
- Direct detail PDP collection passed the requested 50 consecutive product-page
  proof test.
- Keep ZenRows disabled for Amazon TV detail unless direct starts producing
  block/interstitial failures.

### 15:55:14 - TV CSV-only full-cycle test started

Request:

- Run Amazon TV through one full crawler cycle.
- Keep outputs as CSV/local artifacts only.
- Do not run S3 sync or DB prepare/load.
- Clearly distinguish free/direct crawling from paid ZenRows crawling.

Planned steps:

```text
01 main_list
02 main_targets
03 bsr_list
04 bsr_rank
05 promotion_deals
06 trending_deals
07 final_targets
08 detail_enrichment
09 review20
10 status_check
```

Excluded steps:

```text
11 s3_sync
12 local_cleanup
13 db_prepare
14 db_load
```

Cost-control conditions:

```text
AMAZON_PRODUCT_TYPE=TV
AMAZON_MARKETPLACE=US
AMAZON_FETCH_MODE=auto
AMAZON_MAIN_PAGES=1
AMAZON_BSR_PAGES=1
AMAZON_DETAIL_LIMIT=5
AMAZON_FINAL_TARGET_SIZE=20
AMAZON_PAGE_WORKERS=1
AMAZON_MAX_ATTEMPTS=1
AMAZON_DETAIL_MAX_ATTEMPTS=1
ZENROWS_TIMEOUT=120
```

Interpretation:

- `direct` transport is free/local/VPN-friendly.
- `zenrows` transport is paid and should only appear if direct fails to produce
  usable rows while `AMAZON_FETCH_MODE=auto`.
- Benchmark and meta files should record `transport`.

### 15:50:09 - Cost-first transport and realtime benchmarks

Context:

- User requested Amazon and BestBuy crawlers to start with free/direct paths
  before using ZenRows because of cost.
- User requested benchmark files to append during main/detail collection.

Implemented changes:

- `amazon/step01_main_list.py`
  - Added `AMAZON_MAIN_FETCH_MODE` / `AMAZON_FETCH_MODE`.
  - Supported modes:
    - `direct`
    - `auto`, `direct_first`, `fallback`
    - `zenrows`
  - Direct mode uses browser-like headers and optional `AMAZON_COOKIE`.
  - Benchmark rows append to `main/benchmarks/page_benchmarks.csv` as pages
    complete.
- `amazon/step03_bsr_list.py`
  - Added the same cost-first transport modes for BSR pages.
  - Appends `bsr/benchmarks/page_benchmarks.csv` page by page.
- `amazon/step08_detail_enrichment.py`
  - Added `AMAZON_DETAIL_FETCH_MODE` / `AMAZON_FETCH_MODE`.
  - Detail requests try direct first by default, with optional ZenRows fallback.
  - Appends `detail/benchmarks/detail_benchmarks.csv` per ASIN.
  - Detail output now includes `detail_transport`.

Transport behavior:

```text
direct: direct requests only
auto/direct_first/fallback: direct first, ZenRows second if configured
zenrows: ZenRows only
```

Validation:

```powershell
python -m py_compile amazon\step01_main_list.py amazon\step03_bsr_list.py amazon\step08_detail_enrichment.py bestbuy\step00_detail_benchmarks.py bestbuy\step01_main_list.py bestbuy\step08_detail_enrichment.py
```

Result: passed.

Recommended limited test:

```powershell
$env:AMAZON_FETCH_MODE='direct'
$env:AMAZON_MAIN_PAGES='1'
python -m amazon.step01_main_list

$env:AMAZON_DETAIL_FETCH_MODE='direct'
$env:AMAZON_DETAIL_LIMIT='2'
python -m amazon.step08_detail_enrichment
```

Fallback test:

```powershell
$env:AMAZON_FETCH_MODE='auto'
```

This records direct attempts first and uses ZenRows only if needed.
