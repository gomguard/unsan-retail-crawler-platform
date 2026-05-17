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
