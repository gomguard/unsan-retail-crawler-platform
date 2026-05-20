# BestBuy Development Log - 2026-05-17

Updated at: 2026-05-17 15:50:09 +09:00

## Scope

Retailer: `BestBuy`

Goal: reduce crawler cost by trying direct/VPN-friendly collection before
ZenRows, and make benchmark CSVs append in realtime during long runs.

## Test Timeline

### 15:50:09 - Cost-first transport and realtime benchmarks

Context:

- User provided an external Best Buy VPN/browser crawler pattern that collects
  PDP data without ZenRows.
- User requested future crawls to keep at least two approaches and avoid
  ZenRows unless cheaper paths fail.
- User additionally requested main/detail benchmark files to append while the
  crawl runs instead of being written only at the end.

Implemented changes:

- `bestbuy/step01_main_list.py`
  - Added `BESTBUY_GRAPHQL_FETCH_MODE` / `BESTBUY_FETCH_MODE`.
  - Supported modes:
    - `direct`: post GraphQL directly with browser-like headers.
    - `auto`, `direct_first`, `fallback`: try direct first, then ZenRows.
    - `zenrows`: force ZenRows.
  - Added `transport` and `fetch_mode` metadata.
  - Appends `benchmarks/page_benchmarks.csv` page by page during the run.
- `bestbuy/step08_detail_enrichment.py`
  - Added `BESTBUY_DETAIL_FETCH_MODE` / `BESTBUY_FETCH_MODE`.
  - Detail HTML and review GraphQL now support direct first with ZenRows
    fallback.
  - Added transport/fetch mode metadata to detail and review meta files.
  - Appends `detail/benchmarks/detail_benchmarks.csv` per SKU during the run.
  - Uses a lock around benchmark append when workers run in parallel.
- `bestbuy/step00_detail_benchmarks.py`
  - Added append helper for realtime detail benchmark rows.
  - Added `detail_transport` and `review_transport` fields.

Validation:

```powershell
python -m py_compile amazon\step01_main_list.py amazon\step03_bsr_list.py amazon\step08_detail_enrichment.py bestbuy\step00_detail_benchmarks.py bestbuy\step01_main_list.py bestbuy\step08_detail_enrichment.py
```

Result: passed.

Recommended limited test:

```powershell
$env:BESTBUY_CATEGORY='TV'
$env:BESTBUY_GRAPHQL_FETCH_MODE='direct'
$env:BESTBUY_MAIN_PAGES='1'
python -m bestbuy.step01_main_list

$env:BESTBUY_DETAIL_FETCH_MODE='direct'
$env:BESTBUY_DETAIL_LIMIT='2'
$env:BESTBUY_DETAIL_WORKERS='1'
python -m bestbuy.step08_detail_enrichment
```

Fallback test:

```powershell
$env:BESTBUY_FETCH_MODE='auto'
```

This tries direct first and only uses ZenRows when direct collection does not
produce usable rows.
