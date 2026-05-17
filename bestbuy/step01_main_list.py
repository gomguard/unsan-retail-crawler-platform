import csv
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

from zenrows import ZenRowsClient

from .step00_config import (
    DEFAULT_BESTBUY_RUN_ROOT,
    bestbuy_category,
    load_initial_urls,
    rel_path,
    search_term_from_url,
    url_for_page,
)
from .step00_graphql_query import sanitize_product_list_query
from .step00_parse_pdp import absolute_bestbuy_url, extract_apollo_payloads, nested_get
from .step00_parse_search import merge_dict, parse_product as parse_search_product

BESTBUY_BASE_URL = "https://www.bestbuy.com"
GRAPHQL_ENDPOINT = os.getenv("BESTBUY_GRAPHQL_ENDPOINT", "https://www.bestbuy.com/gateway/graphql")
SEARCH_SORT = os.getenv("BESTBUY_SEARCH_SORT", "")
SEARCH_PAGES = int(os.getenv("BESTBUY_MAIN_PAGES", "13"))
ORGANIC_OFFSET = int(os.getenv("BESTBUY_MAIN_ORGANIC_OFFSET", "18"))
REQUEST_TIMEOUT = int(os.getenv("ZENROWS_TIMEOUT", "120"))
RUN_DATE = os.getenv("BESTBUY_RUN_DATE", datetime.now().strftime("%Y%m%d"))
RUN_ID = os.getenv("BESTBUY_MAIN_RUN_ID", "main")
RUN_ROOT = Path(os.getenv("BESTBUY_RUN_ROOT", DEFAULT_BESTBUY_RUN_ROOT)) / RUN_ID
SOURCE_HTML_PATH = Path(os.getenv("BESTBUY_MAIN_SOURCE_HTML", "references/bestbuy_main_search_page_sample.html"))
FORCE_REFRESH = os.getenv("BESTBUY_FORCE_REFRESH", "0").lower() in {"1", "true", "yes", "y"}
CATEGORY = bestbuy_category()
URLS = load_initial_urls()
SEARCH_URL_KEY = "bsr_search" if RUN_ID == "bsr" or SEARCH_SORT == "Best-Selling" else "main_search"
SEARCH_URL_TEMPLATE = os.getenv("BESTBUY_SEARCH_URL", URLS.get(SEARCH_URL_KEY, ""))
SEARCH_TERM = os.getenv("BESTBUY_SEARCH_TERM", search_term_from_url(SEARCH_URL_TEMPLATE) or "tv")


def now():
    return datetime.now().isoformat(timespec="seconds")


def build_search_url(page):
    if SEARCH_URL_TEMPLATE:
        return url_for_page(SEARCH_URL_TEMPLATE, page)
    query = {"id": "pcat17071", "st": SEARCH_TERM, "intl": "nosplash"}
    if SEARCH_SORT:
        query["sp"] = SEARCH_SORT
    if page > 1:
        query["cp"] = page
    return f"{BESTBUY_BASE_URL}/site/searchpage.jsp?{urlencode(query)}"


def operation_name(query):
    if not isinstance(query, str):
        return ""
    match = re.search(r"\bquery\s+([A-Za-z0-9_]+)", query)
    return match.group(1) if match else ""


def find_started_operation(html_text, target_name):
    for payload in extract_apollo_payloads(html_text):
        for event in payload.get("events", []):
            if event.get("type") != "started":
                continue
            options = event.get("options", {})
            query = options.get("query", "")
            if operation_name(query) == target_name:
                return {
                    "operationName": target_name,
                    "query": query,
                    "variables": options.get("variables", {}),
                    "event_id": event.get("id", ""),
                }
    raise RuntimeError(f"Could not find Apollo operation: {target_name}")


def prepare_product_list_payload(operation, page):
    variables = json.loads(json.dumps(operation["variables"]))
    for key in ("input", "detailedSearchInput"):
        if isinstance(variables.get(key), dict):
            variables[key]["query"] = SEARCH_TERM
            variables[key]["queryType"] = "SEARCH"
            variables[key]["site"] = "WWW"

    variables["categoryId"] = SEARCH_TERM
    variables["isBrowse"] = False
    variables.setdefault("sort", {})
    variables["sort"]["sort"] = SEARCH_SORT
    variables.setdefault("pagination", {})
    variables["pagination"]["pageNumber"] = page
    variables["pagination"]["offset"] = ORGANIC_OFFSET
    variables.setdefault("paginationForDetailedProductSearch", {})
    variables["paginationForDetailedProductSearch"]["pageNumber"] = page
    variables["paginationForDetailedProductSearch"]["offset"] = ORGANIC_OFFSET

    query = operation["query"]
    if os.getenv("BESTBUY_SANITIZE_PRODUCT_LIST_QUERY", "0").lower() in {"1", "true", "yes"}:
        query = sanitize_product_list_query(query)

    return {
        "operationName": operation["operationName"],
        "variables": variables,
        "query": query,
    }


def zenrows_params():
    params = {"custom_headers": "true"}
    if os.getenv("BESTBUY_GRAPHQL_PREMIUM_PROXY", "1").lower() in {"1", "true", "yes"}:
        params["premium_proxy"] = "true"
        params["proxy_country"] = "us"
    if os.getenv("BESTBUY_GRAPHQL_JS_RENDER", "1").lower() in {"1", "true", "yes"}:
        params["js_render"] = "true"
    if os.getenv("BESTBUY_GRAPHQL_MODE_AUTO", "0").lower() in {"1", "true", "yes"}:
        params["mode"] = "auto"
        params["proxy_country"] = "us"
    return params


def post_graphql(client, payload, page):
    headers = {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json",
        "origin": BESTBUY_BASE_URL,
        "referer": build_search_url(page),
    }
    start = time.perf_counter()
    started_at = now()
    response = client.post(
        GRAPHQL_ENDPOINT,
        params=zenrows_params(),
        headers=headers,
        data=json.dumps(payload),
        timeout=REQUEST_TIMEOUT,
    )
    elapsed = time.perf_counter() - start
    return response, started_at, now(), round(elapsed, 3)


def make_dirs():
    for subdir in ("raw/main_graphql", "parsed", "benchmarks"):
        (RUN_ROOT / subdir).mkdir(parents=True, exist_ok=True)


def page_stem(page):
    return f"page_{page:03d}"


def page_folder(page, status=None):
    raw_dir = RUN_ROOT / "raw/main_graphql"
    stem = page_stem(page)
    if status:
        folder = raw_dir / f"{stem}_{status}"
        folder.mkdir(parents=True, exist_ok=True)
        return folder
    for suffix in ("success", "fail"):
        folder = raw_dir / f"{stem}_{suffix}"
        if folder.exists():
            return folder
    return raw_dir


def page_artifact_paths(page, status=None):
    folder = page_folder(page, status)
    stem = page_stem(page)
    return {
        "folder": folder,
        "request": folder / f"{stem}_request.json",
        "response": folder / f"{stem}_response.txt",
        "headers": folder / f"{stem}_headers.json",
        "meta": folder / f"{stem}_meta.json",
        "json": folder / f"{stem}_response.json",
    }


def read_json(path):
    path = Path(path)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {}


def load_cached_page(page):
    if FORCE_REFRESH:
        return None
    paths = page_artifact_paths(page)
    meta = read_json(paths["meta"])
    response_json = read_json(paths["json"])
    if int(meta.get("status_code") or 0) != 200 or not response_json:
        return None
    rows = parse_page_rows(page, response_json)
    if not rows:
        return None
    return response_json, meta, rows


def save_page_artifacts(page, payload, response, started_at, finished_at, elapsed):
    status = "success" if response.status_code == 200 else "fail"
    paths = page_artifact_paths(page, status)
    request_path = paths["request"]
    response_path = paths["response"]
    headers_path = paths["headers"]
    meta_path = paths["meta"]
    json_path = paths["json"]

    request_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    response_path.write_text(response.text, encoding="utf-8", errors="replace")
    headers_path.write_text(json.dumps(dict(response.headers), indent=2, ensure_ascii=False), encoding="utf-8")

    response_json = {}
    parse_error = ""
    try:
        response_json = response.json()
        json_path.write_text(json.dumps(response_json, indent=2, ensure_ascii=False), encoding="utf-8")
    except ValueError as exc:
        parse_error = str(exc)

    meta = {
        "page": page,
        "artifact_folder": rel_path(paths["folder"]),
        "url": build_search_url(page),
        "started_at": started_at,
        "finished_at": finished_at,
        "elapsed_seconds": elapsed,
        "status_code": response.status_code,
        "x_request_cost": response.headers.get("x-request-cost", ""),
        "bytes": len(response.text or ""),
        "parse_error": parse_error,
        "request_path": rel_path(request_path),
        "response_path": rel_path(response_path),
        "response_json_path": rel_path(json_path) if response_json else "",
        "headers_path": rel_path(headers_path),
    }
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return response_json, meta


def is_sponsored_doc(document):
    if not isinstance(document, dict):
        return False
    if document.get("source"):
        return True
    for key in document:
        if key.startswith("on") and "Beacon" in key:
            return True
    return False


def parse_product_occurrence(product, occurrence, extra=None):
    row = parse_search_product(product, occurrence)
    if row.get("product_url"):
        row["product_url"] = absolute_bestbuy_url(row["product_url"])
    if extra:
        row.update(extra)
    return row


def parse_page_rows(page, response_json):
    data = response_json.get("data", {}) if isinstance(response_json, dict) else {}
    rows = []
    products = {}
    visual_rank = 0

    documents = nested_get(data, ["detailedProductSearch", "documents"], [])
    if isinstance(documents, list):
        for organic_rank, document in enumerate(documents, 1):
            product = document.get("product") if isinstance(document, dict) else None
            if not isinstance(product, dict) or not product.get("skuId"):
                continue
            sku = str(product["skuId"])
            products.setdefault(sku, {})
            merge_dict(products[sku], product)
            visual_rank += 1
            occurrence = {
                "page": page,
                "visual_rank": visual_rank,
                "organic_rank": organic_rank,
                "container_type": "organic_product",
                "is_sponsored": False,
                "placement": "detailedProductSearch.documents",
                "source_event_id": "graphql_product_list",
                "sku_id": sku,
            }
            rows.append(
                parse_product_occurrence(
                    products[sku],
                    occurrence,
                    {
                        "placement_name": "ORGANIC",
                        "placement_index": "",
                        "sponsored_rank": "",
                        "source_doc_index": "",
                        "global_organic_rank": (page - 1) * ORGANIC_OFFSET + organic_rank,
                    },
                )
            )

    placements = nested_get(data, ["search", "withBestMedia", "placements"], [])
    if isinstance(placements, list):
        for placement_index, placement in enumerate(placements):
            if not isinstance(placement, dict):
                continue
            placement_name = placement.get("name", "")
            if placement_name == "SEARCH_SPONSORED_INGRID":
                sponsored_rank = 0
                sponsored_documents = nested_get(placement, ["documentsGridView", "sponsoredDocuments"], [])
                if not isinstance(sponsored_documents, list):
                    continue
                for source_index, document in enumerate(sponsored_documents, 1):
                    if not is_sponsored_doc(document):
                        continue
                    product = document.get("product") if isinstance(document, dict) else None
                    if not isinstance(product, dict) or not product.get("skuId"):
                        continue
                    sku = str(product["skuId"])
                    products.setdefault(sku, {})
                    merge_dict(products[sku], product)
                    sponsored_rank += 1
                    visual_rank += 1
                    occurrence = {
                        "page": page,
                        "visual_rank": visual_rank,
                        "organic_rank": "",
                        "container_type": "sponsored_ingrid",
                        "is_sponsored": True,
                        "placement": "SEARCH_SPONSORED_INGRID",
                        "source_event_id": "graphql_product_list",
                        "sku_id": sku,
                    }
                    rows.append(
                        parse_product_occurrence(
                            products[sku],
                            occurrence,
                            {
                                "placement_name": placement_name,
                                "placement_index": placement_index,
                                "sponsored_rank": sponsored_rank,
                                "source_doc_index": source_index,
                                "global_organic_rank": "",
                                "ad_source": document.get("source", ""),
                            },
                        )
                    )
            elif placement_name == "SEARCH_SPONSORED_CAROUSEL_DEFAULT":
                documents = placement.get("documents", [])
                if not isinstance(documents, list):
                    continue
                for sponsored_rank, document in enumerate(documents, 1):
                    product = document.get("product") if isinstance(document, dict) else None
                    if not isinstance(product, dict) or not product.get("skuId"):
                        continue
                    sku = str(product["skuId"])
                    products.setdefault(sku, {})
                    merge_dict(products[sku], product)
                    visual_rank += 1
                    occurrence = {
                        "page": page,
                        "visual_rank": visual_rank,
                        "organic_rank": "",
                        "container_type": "sponsored_carousel",
                        "is_sponsored": True,
                        "placement": "SEARCH_SPONSORED_CAROUSEL_DEFAULT",
                        "source_event_id": "graphql_product_list",
                        "sku_id": sku,
                    }
                    rows.append(
                        parse_product_occurrence(
                            products[sku],
                            occurrence,
                            {
                                "placement_name": placement_name,
                                "placement_index": placement_index,
                                "sponsored_rank": sponsored_rank,
                                "source_doc_index": sponsored_rank,
                                "global_organic_rank": "",
                                "ad_source": document.get("source", ""),
                            },
                        )
                    )

    for row in rows:
        row["category_key"] = CATEGORY
        row["global_visual_rank"] = (page - 1) * 1000 + int(row.get("visual_rank") or 0)
    return rows


def write_csv(path, rows):
    keys = set()
    for row in rows:
        keys.update(row)
    preferred = [
        "category_key",
        "page",
        "visual_rank",
        "global_visual_rank",
        "organic_rank",
        "global_organic_rank",
        "container_type",
        "is_sponsored",
        "placement",
        "placement_name",
        "placement_index",
        "sponsored_rank",
        "source_doc_index",
        "ad_source",
        "sku_id",
        "bsin",
        "brand",
        "product_name",
        "product_url",
        "image_url",
        "rating",
        "review_count",
        "customer_price",
        "regular_price",
        "total_savings",
        "total_savings_percent",
        "shipping_eligible",
        "pickup_eligible",
        "offer_count",
    ]
    fieldnames = [key for key in preferred if key in keys]
    fieldnames.extend(sorted(keys - set(fieldnames)))
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def page_summary(page, rows, meta, response_json):
    errors = response_json.get("errors", []) if isinstance(response_json, dict) else []
    organic = [row for row in rows if row.get("container_type") == "organic_product"]
    ingrid = [row for row in rows if row.get("container_type") == "sponsored_ingrid"]
    carousel = [row for row in rows if row.get("container_type") == "sponsored_carousel"]
    return {
        "page": page,
        "started_at": meta["started_at"],
        "finished_at": meta["finished_at"],
        "elapsed_seconds": meta["elapsed_seconds"],
        "status_code": meta["status_code"],
        "x_request_cost": meta["x_request_cost"],
        "bytes": meta["bytes"],
        "error_count": len(errors),
        "organic_count": len(organic),
        "sponsored_ingrid_count": len(ingrid),
        "sponsored_carousel_count": len(carousel),
        "total_occurrence_count": len(rows),
        "unique_sku_count": len({row.get("sku_id") for row in rows if row.get("sku_id")}),
        "organic_price_missing": sum(1 for row in organic if row.get("customer_price") in ("", None)),
        "sponsored_price_missing": sum(
            1 for row in ingrid + carousel if row.get("customer_price") in ("", None)
        ),
        "response_path": meta["response_json_path"] or meta["response_path"],
    }


def main():
    api_key = os.getenv("ZENROWS_API_KEY")
    if not api_key:
        raise RuntimeError("Set ZENROWS_API_KEY in .env")
    make_dirs()
    run_started_at = now()
    run_start = time.perf_counter()

    html_text = SOURCE_HTML_PATH.read_text(encoding="utf-8", errors="replace")
    operation = find_started_operation(html_text, "PlpView_ProductList_Init")
    client = ZenRowsClient(api_key)

    all_rows = []
    page_benchmarks = []
    raw_search = []

    print(f"RUN_ROOT={RUN_ROOT}")
    print(f"SEARCH_TERM={SEARCH_TERM} pages={SEARCH_PAGES} endpoint={GRAPHQL_ENDPOINT}")
    print(f"benchmark_start={run_started_at}")

    for page in range(1, SEARCH_PAGES + 1):
        cached = load_cached_page(page)
        if cached:
            response_json, meta, rows = cached
            source = "cache"
        else:
            payload = prepare_product_list_payload(operation, page)
            response, started_at, finished_at, elapsed = post_graphql(client, payload, page)
            response_json, meta = save_page_artifacts(page, payload, response, started_at, finished_at, elapsed)
            rows = parse_page_rows(page, response_json) if response.status_code == 200 else []
            source = "network"
        all_rows.extend(rows)
        summary = page_summary(page, rows, meta, response_json)
        summary["source"] = source
        page_benchmarks.append(summary)
        raw_search.append(
            {
                "page": page,
                "url": build_search_url(page),
                "meta": meta,
                "summary": summary,
            }
        )
        print(
            f"page={page:03d} source={source} status={meta['status_code']} elapsed={meta['elapsed_seconds']}s "
            f"cost={meta['x_request_cost']} organic={summary['organic_count']} "
            f"ingrid={summary['sponsored_ingrid_count']} carousel={summary['sponsored_carousel_count']} "
            f"rows={summary['total_occurrence_count']}"
        )

    parsed_dir = RUN_ROOT / "parsed"
    benchmarks_dir = RUN_ROOT / "benchmarks"
    write_csv(parsed_dir / "main_occurrences.csv", all_rows)
    write_csv(benchmarks_dir / "page_benchmarks.csv", page_benchmarks)
    (parsed_dir / "main_page_summary.json").write_text(
        json.dumps(page_benchmarks, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (RUN_ROOT / "raw_search_summary.json").write_text(
        json.dumps(raw_search, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    run_elapsed = round(time.perf_counter() - run_start, 3)
    total_cost = 0.0
    for summary in page_benchmarks:
        try:
            total_cost += float(summary.get("x_request_cost") or 0)
        except ValueError:
            pass
    manifest = {
        "run_type": "step01_main_list",
        "run_root": rel_path(RUN_ROOT),
        "run_started_at": run_started_at,
        "run_finished_at": now(),
        "elapsed_seconds": run_elapsed,
        "search_term": SEARCH_TERM,
        "search_sort": SEARCH_SORT,
        "search_pages": SEARCH_PAGES,
        "organic_offset": ORGANIC_OFFSET,
        "graphql_endpoint": GRAPHQL_ENDPOINT,
        "source_html": rel_path(SOURCE_HTML_PATH),
        "expected_post_calls": SEARCH_PAGES,
        "actual_post_calls": len(page_benchmarks),
        "total_x_request_cost": round(total_cost, 7),
        "main_occurrences": len(all_rows),
        "unique_skus": len({row.get("sku_id") for row in all_rows if row.get("sku_id")}),
        "organic_occurrences": sum(1 for row in all_rows if row.get("container_type") == "organic_product"),
        "sponsored_ingrid_occurrences": sum(1 for row in all_rows if row.get("container_type") == "sponsored_ingrid"),
        "sponsored_carousel_occurrences": sum(1 for row in all_rows if row.get("container_type") == "sponsored_carousel"),
        "outputs": {
            "main_occurrences": rel_path(parsed_dir / "main_occurrences.csv"),
            "page_benchmarks": rel_path(benchmarks_dir / "page_benchmarks.csv"),
            "main_page_summary": rel_path(parsed_dir / "main_page_summary.json"),
        },
    }
    (RUN_ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    print("=" * 80)
    print(f"benchmark_end={manifest['run_finished_at']}")
    print(
        f"elapsed={run_elapsed}s calls={manifest['actual_post_calls']} "
        f"cost={manifest['total_x_request_cost']} rows={manifest['main_occurrences']} "
        f"unique_skus={manifest['unique_skus']}"
    )
    print(f"main_csv={parsed_dir / 'main_occurrences.csv'}")
    print(f"benchmarks_csv={benchmarks_dir / 'page_benchmarks.csv'}")
    print(f"manifest={RUN_ROOT / 'manifest.json'}")


if __name__ == "__main__":
    main()
