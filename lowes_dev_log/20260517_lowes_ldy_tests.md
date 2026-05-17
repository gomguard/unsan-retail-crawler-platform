# Lowe's LDY Development Log - 2026-05-17

Updated at: 2026-05-17 15:17:37 +09:00

## Scope

Product line: `LDY`

Retailer: `Lowes`

Run root: `lowes/data/ldy/20260517`

Goal: re-run and test Lowe's LDY crawler with small limits, diagnose ZenRows failures, and keep the pipeline usable from BSR through DB load.

## Environment Used

Common limited-test settings:

```powershell
$env:LOWES_PRODUCT_TYPE='LDY'
$env:LOWES_URL_SOURCE='csv'
$env:LOWES_PAGES='1'
$env:LOWES_DETAIL_LIMIT='5'
$env:LOWES_DETAIL_WORKERS='2'
$env:S3_DRY_RUN='1'
```

LDY orchestrator default behavior now sets:

```powershell
$env:LOWES_SEARCH_TERM='washing machine'
$env:LOWES_BSR_PRODUCT_GROUP='LDY'
$env:LOWES_REQUEST_VARIANT='js_premium_block_visual'
```

`js_premium_block_visual` parameters now include:

```text
js_render=true
antibot=true
premium_proxy=true
proxy_country=us
wait=8000
block_resources=image,media,font,stylesheet
custom_headers=true for HTML mode
```

## Test Timeline

### 15:44:44 - Cost-first crawl strategy documented

Context:

- User requested future Amazon, Best Buy, Lowe's, and other crawler work to keep
  at least two approaches available.
- Cost concern: avoid ZenRows until direct or lower-cost collection paths have
  been tested.

Policy added:

- `AGENTS.md`
- `CRAWLER_OPERATION_POLICY.md`

Default future approach:

1. Try low-cost/direct path first:
   - official API or public JSON/GraphQL
   - direct `requests`/curl with stable headers
   - browser/session exported curl
   - copied browser state JSON
   - Playwright without paid proxy
2. Use ZenRows only as fallback:
   - start with cheapest useful mode
   - escalate to `js_render`, `antibot`, `premium_proxy`, and long waits only
     after cheaper attempts fail

Required logging:

- Record direct attempt and ZenRows fallback separately.
- Include request counts, retry counts, timeout, proxy/render flags, status,
  elapsed time, raw artifact paths, and interpretation.

### 15:20 - Development logging policy added

Context:

- User requested automatic recording of all crawler development and site-access
  attempts, including situation, time, conditions, and result, per channel log.
- Existing Lowe's channel log already lives at this file.

Implemented documentation:

- Added repository-level agent instruction: `AGENTS.md`.
- Added formal policy section: `CRAWLER_OPERATION_POLICY.md`.

Required future behavior:

- Any code change, parser investigation, request variant test, ZenRows/API/browser
  attempt, DB/S3 test, or failure bypass attempt must be recorded in the relevant
  `{retailer}_dev_log/{YYYYMMDD}_{retailer}_{product_type}_tests.md` file.
- Per-run machine logs remain under each run root, for example:
  `lowes/data/ldy/20260517/main/logs/run.log`.
- Secrets must be redacted from human-readable development logs.

### 14:55:23 - LDY full limited test, sandbox network blocked

Command:

```powershell
$env:LOWES_PRODUCT_TYPE='LDY'; $env:LOWES_URL_SOURCE='csv'; $env:LOWES_PAGES='1'; $env:LOWES_DETAIL_LIMIT='5'; $env:LOWES_DETAIL_WORKERS='2'; $env:S3_DRY_RUN='1'; $env:LOWES_API_TRANSPORT='curl'; python -m lowes.lowes_orchestrator --product-type LDY --all
```

Result:

- `step01_main_list`: failed immediately with socket access denied.
- `step03_bsr_list`: failed with socket access denied.
- Root cause: sandbox network restriction, not crawler logic.

Error example:

```text
[WinError 10013] 액세스 권한에 의해 숨겨진 소켓에 액세스를 시도했습니다
```

### 14:55:31 - LDY full limited test, escalated network

Command:

```powershell
$env:LOWES_PRODUCT_TYPE='LDY'; $env:LOWES_URL_SOURCE='csv'; $env:LOWES_PAGES='1'; $env:LOWES_DETAIL_LIMIT='5'; $env:LOWES_DETAIL_WORKERS='2'; $env:S3_DRY_RUN='1'; $env:LOWES_API_TRANSPORT='curl'; python -m lowes.lowes_orchestrator --product-type LDY --all
```

Result:

- `step01_main_list`: `413 RESP005` twice.
- `step02_main_targets`: 0 rows.
- `step03_bsr_list`: HTTP 200, response size about 186 KB, but old parser returned 0 rows.
- `step04_bsr_rank`: 0 rows.
- `step07_final_targets`: 0 rows.
- `step08_detail_enrichment`: 0 rows.
- `step11_s3_sync`: dry-run success.
- `step13_db_prepare`: success, target table `public.tmp_lowes_ldy_final_output_20260517`.
- `step14_db_load`: success but inserted 0 rows.

Main search error:

```json
{"code":"RESP005","status":413,"title":"Response data is bigger than the maximum allowed download size for your plan (RESP005)"}
```

Key artifact:

```text
lowes/data/ldy/20260517/main/raw/main_pages/page_001_fail/page_001_response.txt
```

### BSR Parser Investigation

Finding:

- BSR HTML had embedded product data in `window['__PRELOADED_STATE__']`.
- Products were under:

```text
productListCommonNormalizedPageSpecificProducts.productList.products
```

Old parser only checked generic `itemList` and DOM product cards, so it missed the BSR embedded data.

Implemented change:

- `lowes/step03_bsr_list.py`
- Added BSR-specific preloaded-state parser.
- Extracts `omni_item_id`, `brand`, `model_id`, `description`, `product_url`, `rating`, `review_count`, `selling_price`.

### 15:00:01 - Re-run from BSR after parser fix

Command:

```powershell
$env:LOWES_PRODUCT_TYPE='LDY'; $env:LOWES_URL_SOURCE='csv'; $env:LOWES_DETAIL_LIMIT='5'; $env:LOWES_DETAIL_WORKERS='2'; $env:S3_DRY_RUN='1'; python -m lowes.lowes_orchestrator --product-type LDY --from-step 03
```

Result:

- `step03_bsr_list`: HTTP 200, parsed 24 rows.
- Parse source: `bsr_preloaded_state`.
- `step04_bsr_rank`: 24 input rows, 24 output rows.
- `step07_final_targets`: read 24 BSR rows but output 0 rows.

Reason:

- `step07_final_targets.py` only emitted rows from `main_rows`.
- Since main search was 0 rows, BSR-only runs produced no final targets.

Implemented change:

- `lowes/step07_final_targets.py`
- Added BSR-only fallback targets.
- Dedupes by `omni_item_id`, `item_number`, or `product_url`.
- Sets `selection_source=bsr`.

### 15:00:44 - Re-run from final target after BSR fallback

Command:

```powershell
$env:LOWES_PRODUCT_TYPE='LDY'; $env:LOWES_DETAIL_LIMIT='5'; $env:LOWES_DETAIL_WORKERS='2'; $env:S3_DRY_RUN='1'; python -m lowes.lowes_orchestrator --product-type LDY --from-step 07
```

Result:

- `step07_final_targets`: `main_rows=0`, `bsr_rows=24`, `output_rows=24`.
- `step08_detail_enrichment`: attempted 5 detail rows.
- Detail failed due sandbox network restriction.
- `final_output.csv`: 24 rows, but 5 detail rows marked exception.
- `step11_s3_sync`: failed in sandbox with S3 endpoint connection error.

Detail failure root cause:

```text
[WinError 10013] 액세스 권한에 의해 숨겨진 소켓에 액세스를 시도했습니다
```

S3 dry-run failure root cause:

```text
Could not connect to the endpoint URL
```

### 15:04:01 - Detail 5 and DB load with escalated network

Command:

```powershell
$env:LOWES_PRODUCT_TYPE='LDY'; $env:LOWES_DETAIL_LIMIT='5'; $env:LOWES_DETAIL_WORKERS='2'; python -m lowes.lowes_orchestrator --product-type LDY 08 09 10 13 14
```

Result:

- `step08_detail_enrichment`: 5 targets fetched.
- Detail fetch timings:
  - `5014905209`: 9.3s
  - `5014906167`: 17.3s
  - `5016333345`: 10.3s
  - `5014087771`: 28.4s
  - `1000064061`: 143.9s
- `detail_enriched_rows.csv`: 5 rows.
- `detail_failures.csv`: 0 rows.
- `final_output.csv`: 24 rows.
- Resolved detail prices: 5/5.
- `step10_status_check`: final targets 24, final output 24, detail success files 5.
- `step13_db_prepare`: success.
- `step14_db_load`: inserted 24 rows into `public.tmp_lowes_ldy_final_output_20260517`.

### 15:05:11 - Main search with LDY default block_resources variant

Command:

```powershell
$env:LOWES_PRODUCT_TYPE='LDY'; $env:LOWES_URL_SOURCE='csv'; $env:LOWES_PAGES='1'; $env:LOWES_DETAIL_LIMIT='5'; $env:LOWES_DETAIL_WORKERS='2'; $env:S3_DRY_RUN='1'; python -m lowes.lowes_orchestrator --product-type LDY 01
```

Result:

- Variant: `js_premium_block_visual`.
- Attempt 1: `504 CTX0002`, elapsed about 181.24s, 153 bytes.
- Attempt 2: `504 CTX0002`, elapsed about 181.24s, 153 bytes.
- No successful main HTML saved.

Error:

```json
{"code":"CTX0002","instance":"/v1","status":504,"title":"Operation timeout exceeded (CTX0002)","type":"https://docs.zenrows.com/api-error-codes#CTX0002"}
```

Interpretation:

- `block_resources` changed the failure from `413 RESP005` to `504 CTX0002`.
- That suggests response-size pressure was reduced, but Lowe's search page still timed out during browser render / anti-bot / PLP app load.

### 15:12:05 - Main search with stronger resource blocking

Command:

```powershell
$env:LOWES_PRODUCT_TYPE='LDY'; $env:LOWES_URL_SOURCE='csv'; $env:LOWES_PAGES='1'; $env:LOWES_MAX_ATTEMPTS='1'; $env:ZENROWS_TIMEOUT='240'; $env:LOWES_BLOCK_RESOURCES='image,media,font,stylesheet,script,xhr'; python -m lowes.lowes_orchestrator --product-type LDY 01
```

Result:

- User interrupted after about 180s.
- Two Python processes remained:
  - `lowes.lowes_orchestrator --product-type LDY 01`
  - `lowes.step01_main_list`
- Processes were then stopped with escalation.

Note:

- Blocking `script,xhr` may prevent the search PLP app from producing product data at all.
- Use this only as a diagnostic for timeout behavior, not as the preferred collection mode.

## Store Cookie Finding

Important correction:

- Store cookie existed in code, but only for `/search/products` API mode via `api_headers()`.
- The failing `/search?searchTerm=...` HTML mode did not send store cookie or custom headers.

Implemented change:

- `lowes/step01_main_list.py`
- Added `html_headers()` with:
  - browser-like document headers
  - `cookie: build_store_cookie()`
  - `referer: https://www.lowes.com/`
- HTML ZenRows requests now set:

```text
custom_headers=true
```

Request metadata now records:

```text
request_variant
request_params
custom_headers
store_id
store_zip
```

## Why BSR Works But Search Fails

BSR page:

- Response about 186 KB.
- Contains usable product JSON in preloaded state.
- Product extraction does not require full PLP search app behavior.
- Parsed successfully after BSR-specific parser was added.

Search page:

- General search PLP is heavier and more dynamic.
- It is affected by store, inventory, pricing, anti-bot, and browser state.
- ZenRows HTML rendering hit either:
  - `413 RESP005` under lighter `auto` mode, or
  - `504 CTX0002` under `js_render + premium_proxy + block_resources`.

Current interpretation:

- BSR is usable as a stable LDY seed source.
- Main search HTML rendering remains unstable.
- The better next path for search is likely `/search/products` API with a fresh browser/session curl, not rendered HTML.

## Code Changes Made

Files modified:

```text
lowes/lowes_orchestrator.py
lowes/step01_main_list.py
lowes/step03_bsr_list.py
lowes/step07_final_targets.py
```

Summary:

- LDY defaults to `js_premium_block_visual`.
- `block_resources` can be configured with `LOWES_BLOCK_RESOURCES`.
- ZenRows `antibot=true` included in LDY HTML variant.
- HTML mode now sends store cookie and custom headers.
- BSR parser reads Lowe's BSR embedded product state.
- Final target builder supports BSR-only targets when main search has 0 rows.

Validation:

```powershell
python -m py_compile lowes\step01_main_list.py lowes\lowes_orchestrator.py lowes\step03_bsr_list.py lowes\step07_final_targets.py
```

Result: passed.

## Lowe's Cost Policy: UC First, ZenRows Fallback

Decision:

- ZenRows has direct API cost.
- UC/browser collection does not add ZenRows call cost.
- For Lowe's, use UC first wherever practical and keep ZenRows as fallback only.

Code changes:

- `lowes/lowes_orchestrator.py`
  - Default `LOWES_MAIN_LIST_MODULE=lowes.lowes_main_list_uc_api` for Lowe's categories.
  - Default `LOWES_BSR_TRANSPORT=uc_first`.
  - Default `LOWES_BSR_FALLBACK_ZENROWS=1`.
  - Default `LOWES_DETAIL_TRANSPORT=uc_first`.
  - Default `LOWES_DETAIL_FALLBACK_ZENROWS=1`.

- `lowes/step03_bsr_list.py`
  - Added UC BSR fetch mode.
  - `LOWES_BSR_TRANSPORT=uc_first` tries UC first.
  - If UC fails and fallback is enabled, ZenRows is used as paid fallback.
  - UC artifacts mark `transport=uc` and `x_request_cost=0`.

- `lowes/step08_detail_enrichment.py`
  - Added UC detail fetch mode.
  - `LOWES_DETAIL_TRANSPORT=uc_first` fetches PDP pages with UC first.
  - Failed UC detail fetches can fall back to ZenRows when `LOWES_DETAIL_FALLBACK_ZENROWS=1`.
  - Detail benchmark JSON now records `detail_transport` and `fallback_zenrows`.
  - UC artifacts mark `transport=uc` and `x_request_cost=0`.

Next tests:

1. LDY failed detail IDs with UC-first:

```powershell
$env:LOWES_PRODUCT_TYPE='LDY'
$env:LOWES_DETAIL_TRANSPORT='uc_first'
$env:LOWES_DETAIL_FALLBACK_ZENROWS='1'
$env:LOWES_DETAIL_REFETCH_IDS='5013548885,1000704380,5014906275,5016333377,5014349161,5017781001,5017759985,5017970755'
python -m lowes.lowes_orchestrator --product-type LDY 08 10
```

2. REF UC-first detail sample:

```powershell
$env:LOWES_PRODUCT_TYPE='REF'
$env:LOWES_DETAIL_TRANSPORT='uc_first'
$env:LOWES_DETAIL_FALLBACK_ZENROWS='1'
$env:LOWES_DETAIL_TARGET_MODE='all'
$env:LOWES_DETAIL_LIMIT='50'
python -m lowes.lowes_orchestrator --product-type REF 08 10
```

3. BSR UC-first comparison:

```powershell
$env:LOWES_PRODUCT_TYPE='LDY'
$env:LOWES_BSR_TRANSPORT='uc_first'
python -m lowes.lowes_orchestrator --product-type LDY 03 04
```

Verification:

```powershell
python -m py_compile lowes\lowes_orchestrator.py lowes\step03_bsr_list.py lowes\step08_detail_enrichment.py
$env:LOWES_PRODUCT_TYPE='LDY'; python -m lowes.lowes_orchestrator --product-type LDY --dry-run 01 03 08
```

Result: passed. Dry-run shows main uses `lowes.lowes_main_list_uc_api`; BSR/detail run through modules that now default to UC-first with ZenRows fallback.

## Main Realtime Benchmark Backfill and Fix

Issue found:

- `lowes/data/ldy/20260517/main/benchmarks` existed, but UC main did not write benchmark files.
- The completed LDY main run only had `manifest.json`, raw page files, `main_occurrences.csv`, and `main_page_summary.csv`.

Fix:

- Updated `lowes/lowes_main_list_uc_api.py` to write realtime main benchmark artifacts during future UC main runs.

New main artifacts:

```text
lowes/data/ldy/20260517/main/benchmarks/main_fetch_progress.csv
lowes/data/ldy/20260517/main/benchmarks/main_fetch_progress.json
lowes/data/ldy/20260517/main/benchmarks/main_fetch_summary.json
```

Behavior:

- `main_fetch_progress.csv` is reset at run start and receives one row per fetched search API page.
- `main_fetch_progress.json` is rewritten after every completed page with counts, rate, ETA, last page count, and last item.
- `main_fetch_summary.json` is written after the run finishes.

Backfill:

- Generated the three main benchmark files from the existing `lowes/data/ldy/20260517/main/manifest.json`.
- Backfilled summary:
  - pages_requested: 13
  - pages_fetched: 13
  - successful_http_pages: 13
  - failed_pages: 0
  - rows: 312
  - unique_omni_item_id: 193

Verification:

```powershell
python -m py_compile lowes\lowes_main_list_uc_api.py
```

Result: passed.

## Current Best Known LDY Status

Successful:

- BSR listing fetch: 24 rows.
- BSR rank map: 24 rows.
- Final targets from BSR fallback: 24 rows.
- Detail enrichment limited to 5: 5/5 success.
- Final output: 24 rows.
- DB prepare: success.
- DB load: inserted 24 rows into `public.tmp_lowes_ldy_final_output_20260517`.

Unresolved:

- Main search HTML ZenRows render still fails:
  - `auto`: `413 RESP005`.
  - `js_premium_block_visual`: `504 CTX0002`.
- Need fresh test after HTML store-cookie fix.
- Need revisit `/search/products` API with fresh browser/session curl.

## Additional Test After Store Cookie Fix

### 15:19:02 - Main search HTML with store cookie and custom headers

Command:

```powershell
$env:LOWES_PRODUCT_TYPE='LDY'; $env:LOWES_URL_SOURCE='csv'; $env:LOWES_PAGES='1'; $env:LOWES_MAX_ATTEMPTS='1'; $env:ZENROWS_TIMEOUT='240'; python -m lowes.lowes_orchestrator --product-type LDY 01
```

Result:

- Started: `2026-05-17T15:19:02`
- Finished: `2026-05-17T15:22:03`
- Elapsed: `181.071s`
- Status: `504 CTX0002`
- Response bytes: `153`
- Rows: 0

Request params recorded in `page_001_request.json`:

```json
{
  "js_render": "true",
  "antibot": "true",
  "premium_proxy": "true",
  "proxy_country": "us",
  "wait": "8000",
  "block_resources": "image,media,font,stylesheet",
  "custom_headers": "true"
}
```

Store context recorded:

```text
store_id=0289
store_zip=99503
custom_headers=true
```

Conclusion:

- The HTML request now does include the intended store cookie/custom headers path.
- Even with `js_render + antibot + premium_proxy + proxy_country=us + block_resources + custom_headers`, Lowe's search HTML still times out inside ZenRows.
- Next practical path is `/search/products` API or browser-captured session replay, not full HTML rendering.

### 15:25:05 - Main search HTML with ZenRows UI-like simple params

Reason:

- User showed ZenRows UI where Lowe's URL is configured with JavaScript Rendering, Premium Proxies, and wait selector `.content` / `2500ms`.
- Added local request variant `js_premium_content_fast` to match that lighter UI-style request.

Command:

```powershell
$env:LOWES_PRODUCT_TYPE='LDY'; $env:LOWES_URL_SOURCE='csv'; $env:LOWES_PAGES='1'; $env:LOWES_MAX_ATTEMPTS='1'; $env:ZENROWS_TIMEOUT='240'; $env:LOWES_REQUEST_VARIANT='js_premium_content_fast'; $env:LOWES_HTML_CUSTOM_HEADERS='0'; python -m lowes.lowes_orchestrator --product-type LDY 01
```

Request params:

```json
{
  "js_render": "true",
  "premium_proxy": "true",
  "wait_for": ".content",
  "wait": "2500"
}
```

Result:

- Started: `2026-05-17T15:25:05`
- Finished: `2026-05-17T15:28:06`
- Elapsed: `181.245s`
- Status: `504 CTX0002`
- Response bytes: `153`
- Rows: 0

Conclusion:

- The failure is not caused only by extra params such as `antibot`, custom headers, US proxy pinning, or block resources.
- Even the simpler ZenRows UI-like request times out for Lowe's search HTML.
- Direct local browser display is not equivalent to ZenRows remote browser extraction; the remote browser session still appears to hang or be challenged before ZenRows returns HTML.

### 15:29:19 - Parse saved local main search HTML

Input file:

```text
lowes/references/lowes_ldy_main_page.html
```

File size:

```text
9,303,192 bytes on disk
9,302,718 bytes read as HTML text in parser
```

Finding:

- The local HTML contains `window['__PRELOADED_STATE__']`.
- Existing Lowe's search parser can read it.
- Parsed `itemList=24`.
- Parsed `html_prices=24`.
- Page-level product count is `151`.

Implemented change:

- Added `LOWES_MAIN_SOURCE=local_html`.
- Added `LOWES_MAIN_LOCAL_HTML=<path>` to feed a saved HTML file into `step01_main_list` without a network request.

Command:

```powershell
$env:LOWES_PRODUCT_TYPE='LDY'; $env:LOWES_MAIN_SOURCE='local_html'; $env:LOWES_MAIN_LOCAL_HTML='C:\Users\gom\samsung_crawl\lowes\references\lowes_ldy_main_page.html'; $env:LOWES_PAGES='1'; python -m lowes.lowes_orchestrator --product-type LDY 01 02 07 10
```

Result:

- `step01_main_list`: 24 rows, 24 unique omni item IDs.
- `step02_main_targets`: 24 input rows, 24 output rows.
- `step07_final_targets`: 24 main rows + 24 BSR rows -> 31 final target rows after dedupe.
- `step10_status_check`: main rows 24, main target rows 24, BSR rows 24, final target rows 31.

Interpretation:

- This proves the saved browser HTML is enough to recover main listing data.
- The original ZenRows `RESP005` is plausible because the working browser HTML is about 9.3 MB.
- If ZenRows returns the fully rendered HTML body, the response can exceed plan limits or take long enough to hit CTX0002.
- Short-term workaround: save browser HTML snapshots and run `LOWES_MAIN_SOURCE=local_html`.
- Better long-term path: capture/replay the `/search/products` JSON API instead of full HTML.

### 15:31:07 - UC browser API test succeeds

Command:

```powershell
$env:LOWES_PRODUCT_TYPE='LDY'; $env:LOWES_SEARCH_TERM='washing machine'; $env:LOWES_PAGES='1'; $env:LOWES_UC_HEADLESS='0'; $env:LOWES_UC_BOOT_WAIT_SECONDS='15'; $env:LOWES_UC_API_WAIT_SECONDS='60'; python -m lowes.lowes_main_list_uc_api
```

Result:

- UC Chrome launched visible.
- Store cookies seeded for `0289 / 99503`.
- Opened:

```text
https://www.lowes.com/search?searchTerm=washing+machine
```

- Browser title:

```text
Washing machine at Lowes.com: Search Results
```

- Browser-session API request:

```text
https://www.lowes.com/search/products?searchTerm=washing+machine&offset=0&nearByStores=1633,2955,2512&ac=false&algoRulesAppliedInPageLoad=false
```

- API status: `200`
- API elapsed: `0.729s`
- API response bytes: `432,505`
- `itemList`: 24
- `productCount`: 191
- `adjustedNextOffset`: 22
- `pagination_page_count`: 8
- Parsed rows: 24
- Unique omni item IDs: 24

Artifacts:

```text
lowes/data/ldy/20260517/main_uc_api/raw/main_pages/page_001_success/page_001_response.json
lowes/data/ldy/20260517/main_uc_api/parsed/main_occurrences.csv
lowes/data/ldy/20260517/main_uc_api/manifest.json
```

Conclusion:

- UC browser-session API is the working equivalent of the BestBuy GraphQL approach for Lowe's search.
- Full search HTML rendering through ZenRows is the wrong path.
- For LDY, orchestrator now defaults `step01 main_list` to `lowes.lowes_main_list_uc_api`.

### 15:33:45 - LDY dry-run collection 01-10 with UC main

Command:

```powershell
$env:LOWES_PRODUCT_TYPE='LDY'; $env:LOWES_SEARCH_TERM='washing machine'; $env:LOWES_URL_SOURCE='csv'; $env:LOWES_PAGES='13'; $env:LOWES_MAIN_TARGET_LIMIT='300'; $env:LOWES_UC_HEADLESS='0'; $env:LOWES_UC_BOOT_WAIT_SECONDS='15'; $env:LOWES_UC_API_WAIT_SECONDS='60'; $env:LOWES_DETAIL_LIMIT='300'; $env:LOWES_DETAIL_WORKERS='3'; $env:ZENROWS_TIMEOUT='240'; $env:S3_DRY_RUN='1'; python -m lowes.lowes_orchestrator --product-type LDY 01 02 03 04 05 06 07 08 09 10
```

Main result:

- UC browser launched successfully.
- Search URL opened successfully.
- `/search/products` succeeded for 13 requested pages.
- Each API page returned `status=200`, `itemList=24`.
- API-reported `productCount=192`.
- API-reported `pagination_page_count=8`.
- Parsed occurrences: 312.
- Unique `omni_item_id`: 193.
- `step02_main_targets`: 193 rows.

Important note:

- 18 pages are not needed for this run.
- Page 8 already reports `pagination_page_count=8`.
- Pages 9-13 returned data but were beyond the reported page count and produced duplicates/repeated tail data.
- Code updated so UC main can stop when reported `pagination_page_count` is exceeded (`LOWES_UC_STOP_AT_PAGE_COUNT=1` by default).

BSR result:

- BSR HTTP 200 through ZenRows.
- BSR parsed rows: 24.
- BSR rank map rows: 24.

Promotion/trending/review:

- Promotion skipped by design: source not configured.
- Trending skipped by design: source not configured.
- Review20 skipped by design: source not configured.

Final target result:

- `main_rows`: 193.
- `bsr_rows`: 24.
- `final_target_rows`: 193.
- BSR did not add extra unique rows beyond main after dedupe.

Detail first pass result:

- Default detail mode was `missing_price`.
- Main rows already had prices, so detail target rows were 0.
- This did not satisfy the intended "fetch all details" run.

### 15:35:45-16:27:54 - Detail all-target run

Command:

```powershell
$env:LOWES_PRODUCT_TYPE='LDY'; $env:LOWES_DETAIL_TARGET_MODE='all'; $env:LOWES_DETAIL_LIMIT='300'; $env:LOWES_DETAIL_WORKERS='3'; $env:ZENROWS_TIMEOUT='240'; python -m lowes.lowes_orchestrator --product-type LDY 08 09 10
```

Detail result:

- Detail target mode: `all`.
- Detail target rows: 193.
- Unique detail pages: 193.
- Detail output rows: 193.
- Detail failure rows: 8.
- Status check `detail_success_files`: 188.
- Resolved detail prices: 167/193.
- `final_output.csv`: 193 rows.

Failures:

All 8 failures were ZenRows `422 RESP001` and marked retryable:

```text
5013548885
1000704380
5014906275
5016333377
5014349161
5017781001
5017759985
5017970755
```

Failure file:

```text
lowes/data/ldy/20260517/detail/parsed/detail_failures.csv
```

Interpretation:

- Main collection should be UC-first.
- Detail currently uses ZenRows; failures are isolated to 8 PDP URLs.
- A future improvement should add UC/browser-session fallback for detail failures, then ZenRows as fallback only if UC fails.

### 17:23:36 - S3 dry-run

Command:

```powershell
$env:LOWES_PRODUCT_TYPE='LDY'; $env:S3_DRY_RUN='1'; python -m lowes.step11_s3_sync
```

Result:

- S3 dry-run command succeeded.
- No files were uploaded because `--dryrun` was enabled.
- Target URI:

```text
s3://dx-crawl-fileserver-bucket/retail_backup/lowes/ldy/20260517
```

S3 settings:

```text
bucket=dx-crawl-fileserver-bucket
prefix=retail_backup
retailer=lowes
product_type=ldy
run_date=20260517
upload_raw=true
storage_class=STANDARD
delete_extra=false
dry_run=true
```

S3 manifest:

```text
lowes/data/ldy/20260517/s3_sync_manifest.json
```

### DB destination status

DB prepare/load were not run after the 193-row detail-all result because this was treated as a dry run.

If DB steps are run with current configuration, target destination is:

```text
schema=public
table=tmp_lowes_ldy_final_output_20260517
csv=lowes/data/ldy/20260517/output/final_output.csv
rows_now=193
```

Previous DB load before full detail run:

- Time: `15:04:13-15:04:26`
- CSV rows: 24
- Inserted: 24
- Table: `public.tmp_lowes_ldy_final_output_20260517`

Current latest DB load manifest is stale relative to the new 193-row `final_output.csv`; do not treat it as proof that the 193-row output has been loaded.

## Current Recommended Lowe's Strategy

1. Main listing: UC/browser-session `/search/products` first.
2. Stop main listing at API-reported `pagination.pageCount`; do not blindly run to 18+ pages.
3. BSR: ZenRows is currently okay because BSR page is small and includes preloaded product state.
4. Detail: current ZenRows path mostly works but has retryable 422s. Add UC fallback for failed PDP detail URLs.
5. ZenRows full search HTML should remain disabled for main because it hits `RESP005`/`CTX0002`.

### Browser-loaded page extraction plan

Issue:

- The page can load in a normal browser, but full HTML download is unreliable or too large.
- The useful product data is already present in browser memory as `window.__PRELOADED_STATE__.itemList`.

Implemented:

- Added browser console snippet:

```text
lowes/references/lowes_copy_search_state_snippet.js
```

- Added crawler input mode:

```text
LOWES_MAIN_SOURCE=local_state_json
LOWES_MAIN_LOCAL_STATE_JSON=<path to copied JSON>
```

Manual extraction workflow:

1. Open Lowe's search page in the browser.
2. Open DevTools Console.
3. Paste and run `lowes/references/lowes_copy_search_state_snippet.js`.
4. The snippet copies a compact JSON object containing `itemList`, `productCount`, pagination, store context, and offsets.
5. Paste that clipboard content into:

```text
lowes/references/lowes_ldy_main_state.json
```

6. Run:

```powershell
$env:LOWES_PRODUCT_TYPE='LDY'
$env:LOWES_MAIN_SOURCE='local_state_json'
$env:LOWES_MAIN_LOCAL_STATE_JSON='C:\Users\gom\samsung_crawl\lowes\references\lowes_ldy_main_state.json'
$env:LOWES_PAGES='1'
python -m lowes.lowes_orchestrator --product-type LDY 01 02 07 10
```

Reason:

- This avoids downloading or storing the full 9.3 MB rendered HTML.
- It extracts only the JSON state needed by the existing parser.

## Important Artifacts

```text
lowes/data/ldy/20260517/main/logs/run.log
lowes/data/ldy/20260517/main/raw/main_pages/page_001_fail/page_001_response.txt
lowes/data/ldy/20260517/main/raw/main_pages/page_001_fail/page_001_meta.json
lowes/data/ldy/20260517/main/raw/main_pages/page_001_fail/page_001_request.json
lowes/data/ldy/20260517/bsr/raw/main_pages/bsr_ldy_success/bsr_ldy_response.html
lowes/data/ldy/20260517/bsr/parsed/main_occurrences.csv
lowes/data/ldy/20260517/bsr/parsed/bsr_rank_map.csv
lowes/data/ldy/20260517/output/lowes_final_targets.csv
lowes/data/ldy/20260517/detail/parsed/detail_enriched_rows.csv
lowes/data/ldy/20260517/detail/parsed/detail_failures.csv
lowes/data/ldy/20260517/output/final_output.csv
lowes/data/ldy/20260517/output/db_load_manifest.json
lowes/data/ldy/20260517/status/20260517_status.json
```

## Recommended Next Tests

1. Re-test main search HTML after store-cookie/custom-header fix:

```powershell
$env:LOWES_PRODUCT_TYPE='LDY'
$env:LOWES_URL_SOURCE='csv'
$env:LOWES_PAGES='1'
$env:LOWES_MAX_ATTEMPTS='1'
$env:ZENROWS_TIMEOUT='240'
python -m lowes.lowes_orchestrator --product-type LDY 01
```

2. If still `CTX0002`, prefer API mode:

```powershell
$env:LOWES_PRODUCT_TYPE='LDY'
$env:LOWES_MAIN_SOURCE='api'
$env:LOWES_API_TRANSPORT='curl'
$env:LOWES_PAGES='1'
python -m lowes.lowes_orchestrator --product-type LDY 01
```

3. Keep BSR as current stable seed source for LDY until search is reliable.

## Detail Realtime Benchmark Update

Added realtime benchmark output to `lowes/step08_detail_enrichment.py`.

New detail artifacts:

```text
lowes/data/ldy/20260517/detail/benchmarks/detail_fetch_progress.csv
lowes/data/ldy/20260517/detail/benchmarks/detail_fetch_progress.json
lowes/data/ldy/20260517/detail/benchmarks/detail_fetch_summary.json
```

Behavior:

- `detail_fetch_progress.csv` is reset at the start of each detail run and gets one row appended as each PDP fetch finishes.
- `detail_fetch_progress.json` is rewritten after each completed PDP with latest counts, rate, ETA, worker count, timeout, and last item.
- `detail_fetch_summary.json` is written at the end with final fetch/detail counts and output paths.
- Cached detail pages are recorded with `from_cache=true`.
- Failed HTTP/exception rows are recorded immediately, before final parsing.

Verification:

```powershell
python -m py_compile lowes\step08_detail_enrichment.py
```

Result: passed.
