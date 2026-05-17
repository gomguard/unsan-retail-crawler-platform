import csv
import html as html_lib
import io
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from requests import RequestException
from zenrows import ZenRowsClient

from .step00_config import DEFAULT_LOWES_RUN_ROOT, load_env

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
SCRIPT_DIR = Path(__file__).resolve().parent
LOWES_ROOT = SCRIPT_DIR
PROJECT_ROOT = LOWES_ROOT.parent

load_env(PROJECT_ROOT / ".env")

RUN_DATE = os.getenv("LOWES_RUN_DATE", datetime.now().strftime("%Y%m%d"))
RUN_ROOT = Path(os.getenv("LOWES_RUN_ROOT", str(DEFAULT_LOWES_RUN_ROOT)))
DETAIL_ROOT = Path(os.getenv("LOWES_DETAIL_RUN_ROOT", str(RUN_ROOT / "detail")))
OUTPUT_ROOT = Path(os.getenv("LOWES_OUTPUT_ROOT", str(RUN_ROOT / "output")))
DEFAULT_INPUT_CSV = OUTPUT_ROOT / "lowes_final_targets.csv"
if not DEFAULT_INPUT_CSV.exists():
    DEFAULT_INPUT_CSV = OUTPUT_ROOT / "lowes_parsed_pages_1_3.csv"
INPUT_CSV = Path(os.getenv("LOWES_DETAIL_TARGET_CSV", os.getenv("LOWES_INPUT_CSV", str(DEFAULT_INPUT_CSV))))
DETAIL_DIR = Path(os.getenv("LOWES_DETAIL_DIR", str(DETAIL_ROOT / "raw" / "detail_html")))
DETAIL_CSV = Path(os.getenv("LOWES_DETAIL_CSV", str(DETAIL_ROOT / "parsed" / "detail_enriched_rows.csv")))
DETAIL_FAILURES_CSV = Path(os.getenv("LOWES_DETAIL_FAILURES_CSV", str(DETAIL_ROOT / "parsed" / "detail_failures.csv")))
ENRICHED_CSV = Path(os.getenv("LOWES_FINAL_OUTPUT_CSV", os.getenv("LOWES_ENRICHED_CSV", str(OUTPUT_ROOT / "final_output.csv"))))
OVERRIDES_CSV = Path(os.getenv("LOWES_PRICE_OVERRIDES_CSV", str(OUTPUT_ROOT / "lowes_price_overrides.csv")))
REQUEST_TIMEOUT = int(os.getenv("ZENROWS_TIMEOUT", "180"))
MAX_WORKERS = int(os.getenv("LOWES_DETAIL_WORKERS", "3"))
DETAIL_LIMIT = int(os.getenv("LOWES_DETAIL_LIMIT", "0"))
REFRESH = os.getenv("LOWES_REFRESH_DETAILS", "0") == "1"
DETAIL_TARGET_MODE = os.getenv("LOWES_DETAIL_TARGET_MODE", "missing_price").strip().lower()
REFETCH_IDS = {
    item.strip()
    for item in os.getenv("LOWES_DETAIL_REFETCH_IDS", "").split(",")
    if item.strip()
}


def compact_json(value):
    if value in (None, "", [], {}):
        return ""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def clean_key(value):
    return re.sub(r"[^0-9A-Za-z_]+", "_", str(value).strip()).strip("_").lower()


def money_to_number(value):
    if value in (None, "", False):
        return ""
    if isinstance(value, (int, float)):
        return int(value) if float(value).is_integer() else value
    cleaned = re.sub(r"[^\d.]", "", str(value))
    if not cleaned:
        return ""
    parsed = float(cleaned)
    return int(parsed) if parsed.is_integer() else parsed


def flatten(value, prefix=""):
    result = {}
    if isinstance(value, dict):
        for key, child in value.items():
            child_key = clean_key(key)
            child_prefix = f"{prefix}.{child_key}" if prefix else child_key
            result.update(flatten(child, child_prefix))
    elif isinstance(value, list):
        result[prefix] = compact_json(value)
        result[f"{prefix}.__count"] = len(value)
    else:
        result[prefix] = "" if value is None else value
    return result


def extract_preloaded_state_info(page_html):
    match = re.search(r"window\['__PRELOADED_STATE__'\] = (.*?)</script>", page_html, re.S)
    if not match:
        return {}, "missing"
    try:
        return json.loads(match.group(1)), ""
    except json.JSONDecodeError as exc:
        return {}, f"json_decode_error:{exc.msg} at char {exc.pos}"


def extract_preloaded_state(page_html):
    state, _error = extract_preloaded_state_info(page_html)
    return state


def normalize_jsonld_type(value):
    if isinstance(value, list):
        return [normalize_jsonld_type(item) for item in value]
    if isinstance(value, dict):
        return {key: normalize_jsonld_type(child) for key, child in value.items()}
    return value


def extract_jsonld(page_html):
    blocks = []
    for match in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        page_html,
        re.S | re.I,
    ):
        raw = html_lib.unescape(match.group(1).strip())
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, list):
            blocks.extend(parsed)
        else:
            blocks.append(parsed)
    return blocks


def parse_html_visible_prices(page_html, product_id=""):
    result = {
        "detail_html_data_product_price": "",
        "detail_html_now_price": "",
        "detail_html_actual_price": "",
        "detail_html_save_price": "",
        "detail_html_price_source_text": "",
    }

    data_price_match = None
    if product_id:
        for match in re.finditer(r"<button\b[^>]*data-productprice=[\"'][^\"']+[\"'][^>]*>", page_html, re.I | re.S):
            tag = match.group(0)
            if f'data-productid="{product_id}"' in tag or f"data-productid='{product_id}'" in tag:
                data_price_match = re.search(r'data-productprice=["\']([^"\']+)["\']', tag, re.I)
                break
    if not data_price_match:
        data_price_match = re.search(r'data-productprice=["\']([^"\']+)["\']', page_html, re.I)
    if data_price_match:
        result["detail_html_data_product_price"] = money_to_number(data_price_match.group(1))

    text = re.sub(r"<[^>]+>", " ", page_html)
    text = html_lib.unescape(" ".join(text.split()))
    for stop_phrase in [
        "Here are some similar items",
        "BETTER TOGETHER",
        "COMPLETE THE SUITE",
        "Complete Your Kitchen",
    ]:
        idx = text.find(stop_phrase)
        if idx != -1:
            text = text[:idx]
            break

    now_match = re.search(r"\bNow\b.{0,80}?\$\s*([0-9][0-9,]*(?:\.[0-9]{2})?)", text, re.I)
    if now_match:
        result["detail_html_now_price"] = money_to_number(now_match.group(1))

    actual_match = re.search(
        r"(?:Actual price was|Was|actual price).{0,80}?\$\s*([0-9][0-9,]*(?:\.[0-9]{2})?)",
        text,
        re.I,
    )
    if actual_match:
        result["detail_html_actual_price"] = money_to_number(actual_match.group(1))

    save_match = re.search(r"(?:You save|Save).{0,80}?\$\s*([0-9][0-9,]*(?:\.[0-9]{2})?)", text, re.I)
    if save_match:
        result["detail_html_save_price"] = money_to_number(save_match.group(1))

    for key in ["detail_html_data_product_price", "detail_html_now_price"]:
        if result[key]:
            result["detail_html_price_source_text"] = key
            break

    return result


def first_jsonld_product(blocks):
    for block in blocks:
        if isinstance(block, dict) and block.get("@type") == "Product":
            return block
    return {}


def jsonld_by_type(blocks, type_name):
    matches = []
    for block in blocks:
        if isinstance(block, dict) and block.get("@type") == type_name:
            matches.append(block)
    return matches


def spec_map(specs, prefix):
    result = {}
    if not isinstance(specs, list):
        return result
    for spec in specs:
        if not isinstance(spec, dict):
            continue
        key = clean_key(str(spec.get("key", "")).rstrip(":"))
        if key:
            result[f"{prefix}_{key}"] = spec.get("value", "")
    return result


def as_dict(value):
    return value if isinstance(value, dict) else {}


def local_plp_price(row):
    page = row.get("page")
    product_id = row.get("omni_item_id", "")
    if not page or not product_id:
        return ""
    html_path = RUN_ROOT / "archive" / "legacy_data" / f"lowes_page_{page}.html"
    if not html_path.exists():
        return ""
    text = html_path.read_text(encoding="utf-8", errors="replace")
    for match in re.finditer(r'<button\b[^>]*data-testid=["\']add-to-cart-button["\'][^>]*>', text, re.S):
        tag = match.group(0)
        if f'data-productid="{product_id}"' not in tag and f"data-productid='{product_id}'" not in tag:
            continue
        price_match = re.search(r'data-productprice=["\']([^"\']+)["\']', tag)
        if price_match:
            return money_to_number(price_match.group(1))
    return ""


def detail_unit_name(product_id, rank, status_name):
    try:
        rank_text = f"{int(float(rank)):03d}"
    except (TypeError, ValueError):
        rank_text = "000"
    return f"{rank_text}_{product_id}_{status_name}"


def detail_artifact_paths(product_id, rank):
    success_dir = DETAIL_DIR / detail_unit_name(product_id, rank, "success")
    fail_dir = DETAIL_DIR / detail_unit_name(product_id, rank, "fail")
    return {
        "success_dir": success_dir,
        "fail_dir": fail_dir,
        "html_path": success_dir / f"{product_id}.html",
        "failed_path": fail_dir / f"{product_id}_failed.txt",
        "headers_success_path": success_dir / f"{product_id}_headers.json",
        "headers_fail_path": fail_dir / f"{product_id}_headers.json",
        "meta_success_path": success_dir / f"{product_id}_meta.json",
        "meta_fail_path": fail_dir / f"{product_id}_meta.json",
        "legacy_html_path": DETAIL_DIR / f"{product_id}.html",
        "legacy_failed_path": DETAIL_DIR / f"{product_id}_failed.txt",
        "legacy_headers_path": DETAIL_DIR / f"{product_id}_headers.json",
        "legacy_meta_path": DETAIL_DIR / f"{product_id}_meta.json",
    }


def fetch_detail(task):
    product_id, url, rank = task
    DETAIL_DIR.mkdir(parents=True, exist_ok=True)
    paths = detail_artifact_paths(product_id, rank)
    html_path = paths["html_path"]
    failed_path = paths["failed_path"]
    headers_path = paths["headers_success_path"]
    meta_path = paths["meta_success_path"]

    refetch = REFRESH or product_id in REFETCH_IDS

    if html_path.exists() and not refetch:
        return product_id, "cached", html_path, headers_path, ""
    if paths["legacy_html_path"].exists() and not refetch:
        return product_id, "cached", paths["legacy_html_path"], paths["legacy_headers_path"], ""
    if failed_path.exists() and not refetch:
        return product_id, "cached_failed", failed_path, headers_path, failed_path.read_text(
            encoding="utf-8",
            errors="replace",
        )[:500]
    if paths["legacy_failed_path"].exists() and not refetch:
        return product_id, "cached_failed", paths["legacy_failed_path"], paths["legacy_headers_path"], paths[
            "legacy_failed_path"
        ].read_text(
            encoding="utf-8",
            errors="replace",
        )[:500]

    client = ZenRowsClient(os.environ["ZENROWS_API_KEY"])
    params = {"mode": "auto", "proxy_country": "us"}
    start = time.time()
    started_at = datetime.now().isoformat(timespec="seconds")
    try:
        response = client.get(url, params=params, timeout=REQUEST_TIMEOUT)
    except RequestException as exc:
        paths["fail_dir"].mkdir(parents=True, exist_ok=True)
        meta_path = paths["meta_fail_path"]
        meta_path.write_text(
            json.dumps(
                {
                    "sku_id": product_id,
                    "url": url,
                    "stage": "detail",
                    "attempt": 1,
                    "status_code": "",
                    "success": False,
                    "elapsed_seconds": round(time.time() - start, 3),
                    "x_request_cost": "",
                    "error": str(exc),
                    "bytes": 0,
                    "started_at": started_at,
                    "finished_at": datetime.now().isoformat(timespec="seconds"),
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return product_id, "exception", html_path, headers_path, str(exc)

    elapsed = time.time() - start
    if response.status_code == 200:
        paths["success_dir"].mkdir(parents=True, exist_ok=True)
        suffix_path = html_path
        headers_path = paths["headers_success_path"]
        meta_path = paths["meta_success_path"]
    else:
        paths["fail_dir"].mkdir(parents=True, exist_ok=True)
        suffix_path = failed_path
        headers_path = paths["headers_fail_path"]
        meta_path = paths["meta_fail_path"]
    suffix_path.write_text(response.text, encoding="utf-8", errors="replace")
    headers_path.write_text(
        json.dumps(dict(response.headers), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    meta_path.write_text(
        json.dumps(
            {
                "sku_id": product_id,
                "url": url,
                "stage": "detail",
                "attempt": 1,
                "status_code": response.status_code,
                "success": response.status_code == 200,
                "elapsed_seconds": round(elapsed, 3),
                "x_request_cost": response.headers.get("x-request-cost", ""),
                "error": "" if response.status_code == 200 else response.text[:500],
                "bytes": len(response.text),
                "started_at": started_at,
                "finished_at": datetime.now().isoformat(timespec="seconds"),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    if response.status_code != 200:
        return product_id, f"http_{response.status_code}", suffix_path, headers_path, response.text[:500]
    return product_id, f"fetched_{elapsed:.1f}s", html_path, headers_path, ""


def parse_detail(product_id, page_html):
    state, state_error = extract_preloaded_state_info(page_html)
    blocks = extract_jsonld(page_html)
    html_prices = parse_html_visible_prices(page_html, product_id)
    product_ld = first_jsonld_product(blocks)
    docs = jsonld_by_type(blocks, "DownloadAction")
    videos = jsonld_by_type(blocks, "VideoObject")
    images = jsonld_by_type(blocks, "ImageObject")

    product_details = state.get("productDetails", {}) if isinstance(state, dict) else {}
    detail = product_details.get(product_id) or product_details.get(str(product_id)) or {}
    if not detail and isinstance(product_details, dict) and product_details:
        detail = next(iter(product_details.values()))

    product = as_dict(detail.get("product", {})) if isinstance(detail, dict) else {}
    location = as_dict(detail.get("location", {})) if isinstance(detail, dict) else {}
    mfe_price = as_dict(as_dict(detail.get("mfePrice", {})).get("price", {})) if isinstance(detail, dict) else {}
    price_extra = as_dict(mfe_price.get("additionalData", {}))
    location_price = as_dict(location.get("price", {}))
    inventory = as_dict(detail.get("itemInventory")) or as_dict(location.get("itemInventory", {})) if isinstance(detail, dict) else {}
    offer = as_dict(product_ld.get("offers", {})) if isinstance(product_ld, dict) else {}
    aggregate = as_dict(product_ld.get("aggregateRating", {})) if isinstance(product_ld, dict) else {}
    unavailable_phrase = bool(re.search(r"THIS ITEM IS CURRENTLY UNAVAILABLE", page_html, re.I))
    unavailable_token = "unavailable" in page_html.lower()

    row = {
        "omni_item_id": product_id,
        "detail_parse_status": "parsed",
        "detail_preloaded_state_error": state_error,
        "detail_product_id": state.get("productId", "") if isinstance(state, dict) else "",
        "detail_brand": product.get("brand", "") or product_ld.get("brand", {}).get("name", ""),
        "detail_model_id": product.get("modelId", ""),
        "detail_item_number": product.get("itemNumber", ""),
        "detail_title": product.get("title", "") or product_ld.get("name", ""),
        "detail_description": product.get("description", "") or product_ld.get("description", ""),
        "detail_pd_url": product.get("pdURL", ""),
        "detail_rating": product.get("rating", "") or aggregate.get("ratingValue", ""),
        "detail_review_count": product.get("reviewCount", "") or aggregate.get("reviewCount", ""),
        "detail_selling_price": money_to_number(price_extra.get("sellingPrice", "")),
        "detail_retail_price": money_to_number(price_extra.get("retailPrice", "")),
        "detail_was_price": money_to_number(price_extra.get("wasPrice", "")),
        "detail_map_price": money_to_number(price_extra.get("mapPrice", "")),
        "detail_final_price_ui": mfe_price.get("finalPriceForUi", ""),
        "detail_final_price_cent_ui": mfe_price.get("finalPriceCentForUi", ""),
        "detail_savings_base_price": mfe_price.get("savings", {}).get("basePrice", "") if isinstance(mfe_price, dict) else "",
        "detail_savings_total": mfe_price.get("savings", {}).get("totalSaving", "") if isinstance(mfe_price, dict) else "",
        "detail_savings_percentage": mfe_price.get("savings", {}).get("totalPercentage", "") if isinstance(mfe_price, dict) else "",
        "detail_display_type": price_extra.get("displayType", ""),
        "detail_display_price_type": price_extra.get("displayPriceType", ""),
        "detail_location_selling_price": money_to_number(location_price.get("sellingPrice", "")),
        "detail_location_was_price": money_to_number(location_price.get("wasPrice", "")),
        "detail_jsonld_offer_price": money_to_number(offer.get("price", "")) if isinstance(offer, dict) else "",
        "detail_jsonld_offer_currency": offer.get("priceCurrency", "") if isinstance(offer, dict) else "",
        **html_prices,
        "detail_is_buyable": product.get("isBuyable", ""),
        "detail_is_oos": product.get("isOOS", ""),
        "detail_is_not_available": product.get("isNotAvailable", ""),
        "detail_show_atc": product.get("showATC", ""),
        "detail_unavailable_phrase": unavailable_phrase,
        "detail_unavailable_token": unavailable_token,
        "detail_is_sos": product.get("isSOS", ""),
        "detail_vendor_direct": product.get("vendorDirect", ""),
        "detail_major_appliance": product.get("majorAppliance", ""),
        "detail_energy_star": product.get("energyStar", product.get("energyStarQualified", "")),
        "detail_color": product_ld.get("color", "") if isinstance(product_ld, dict) else "",
        "detail_material": product_ld.get("material", "") if isinstance(product_ld, dict) else "",
        "detail_width": product_ld.get("width", "") if isinstance(product_ld, dict) else "",
        "detail_height": product_ld.get("height", "") if isinstance(product_ld, dict) else "",
        "detail_weight": product_ld.get("weight", "") if isinstance(product_ld, dict) else "",
        "detail_breadcrumbs_json": compact_json(state.get("breadcrumbs", [])) if isinstance(state, dict) else "",
        "detail_search_terms_json": compact_json(state.get("searchTerms", [])) if isinstance(state, dict) else "",
        "detail_documents_json": compact_json(docs),
        "detail_videos_json": compact_json(videos),
        "detail_images_json": compact_json(product_ld.get("image", []) if isinstance(product_ld, dict) else []),
        "detail_image_objects_json": compact_json(images),
        "detail_marketing_bullets_json": compact_json(product.get("marketingBullets", "")),
        "detail_guides_json": compact_json(product.get("guides", "")),
        "detail_groups_json": compact_json(product.get("groups", "")),
        "detail_categories_json": compact_json(product.get("categories", "")),
        "detail_variants_json": compact_json(product.get("productVariantsV3", "")),
        "detail_inventory_json": compact_json(inventory),
        "detail_location_json": compact_json(location),
        "detail_raw_product_detail_json": compact_json(detail),
        "detail_jsonld_product_json": compact_json(product_ld),
        "detail_jsonld_all_json": compact_json(blocks),
    }

    row.update(spec_map(product.get("featuredSpecs"), "detail_spec"))
    row.update(spec_map(product.get("specs"), "detail_full_spec"))
    row.update(flatten(detail, "detail"))
    return row


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = []
    seen = set()
    preferred = [
        "omni_item_id",
        "source_page",
        "source_main_rank",
        "source_brand",
        "source_model_id",
        "source_description",
        "source_product_url",
        "local_plp_price",
        "detail_selling_price",
        "detail_was_price",
        "detail_retail_price",
        "detail_map_price",
        "detail_final_price_ui",
        "detail_final_price_cent_ui",
        "detail_html_now_price",
        "detail_html_actual_price",
        "detail_html_save_price",
        "detail_html_data_product_price",
        "resolved_selling_price",
        "resolved_price_source",
        "detail_title",
        "detail_rating",
        "detail_review_count",
        "detail_is_buyable",
        "detail_is_oos",
        "detail_is_not_available",
        "detail_show_atc",
        "detail_unavailable_phrase",
        "detail_unavailable_token",
        "detail_inventory_json",
        "detail_raw_product_detail_json",
    ]
    for key in preferred:
        if any(key in row for row in rows):
            fieldnames.append(key)
            seen.add(key)
    for row in rows:
        for key in row:
            if key not in seen:
                fieldnames.append(key)
                seen.add(key)

    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_failure_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "sku_id",
        "stage",
        "attempt",
        "status_code",
        "error",
        "retryable",
        "source_product_url",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def load_overrides():
    if not OVERRIDES_CSV.exists():
        return {}
    with OVERRIDES_CSV.open(encoding="utf-8-sig", newline="") as f:
        return {row.get("omni_item_id", ""): row for row in csv.DictReader(f) if row.get("omni_item_id")}


def main():
    if not os.getenv("ZENROWS_API_KEY"):
        raise RuntimeError("ZENROWS_API_KEY is missing. Put it in .env or environment.")

    rows = list(csv.DictReader(INPUT_CSV.open(encoding="utf-8-sig", newline="")))
    overrides = load_overrides()
    if DETAIL_TARGET_MODE in {"all", "all_targets", "full"}:
        detail_targets = list(rows)
    elif DETAIL_TARGET_MODE in {"missing", "missing_price", "missing_prices"}:
        detail_targets = [row for row in rows if not row.get("selling_price")]
    else:
        raise ValueError("LOWES_DETAIL_TARGET_MODE must be 'missing_price' or 'all'")
    if DETAIL_LIMIT:
        detail_targets = detail_targets[:DETAIL_LIMIT]

    tasks = {}
    source_by_id = {}
    for row in detail_targets:
        product_id = row.get("omni_item_id", "")
        if not product_id or product_id in tasks:
            continue
        rank = row.get("final_target_rank") or row.get("target_rank") or row.get("main_rank") or ""
        tasks[product_id] = (row.get("product_url", ""), rank)
        source_by_id[product_id] = row

    print(f"Detail target mode: {DETAIL_TARGET_MODE}")
    print(f"Detail target rows: {len(detail_targets)}")
    print(f"Unique detail pages to fetch/parse: {len(tasks)}")
    if REFETCH_IDS:
        print(f"Forced detail refetch IDs: {len(REFETCH_IDS)}")

    statuses = {}
    with ThreadPoolExecutor(max_workers=max(1, MAX_WORKERS)) as executor:
        futures = [
            executor.submit(fetch_detail, (product_id, url_rank[0], url_rank[1]))
            for product_id, url_rank in tasks.items()
        ]
        for future in as_completed(futures):
            product_id, status, html_path, headers_path, error = future.result()
            statuses[product_id] = {
                "status": status,
                "html_path": str(html_path),
                "headers_path": str(headers_path),
                "error": error,
            }
            print(f"  {product_id}: {status}")

    detail_rows_by_id = {}
    failure_rows = []
    for product_id, info in statuses.items():
        html_path = Path(info["html_path"])
        if not html_path.exists() or html_path.suffix != ".html":
            detail_rows_by_id[product_id] = {
                "omni_item_id": product_id,
                "detail_fetch_status": info["status"],
                "detail_fetch_error": info["error"],
            }
            failure_rows.append(
                {
                    "sku_id": product_id,
                    "stage": "detail_fetch",
                    "attempt": 1,
                    "status_code": info["status"].replace("http_", "") if info["status"].startswith("http_") else "",
                    "error": info["error"],
                    "retryable": True,
                    "source_product_url": tasks.get(product_id, ("", ""))[0],
                }
            )
            continue
        page_html = html_path.read_text(encoding="utf-8", errors="replace")
        try:
            detail_row = parse_detail(product_id, page_html)
        except Exception as exc:
            detail_row = {
                "omni_item_id": product_id,
                "detail_parse_status": "parse_failed",
                "detail_parse_error": f"{type(exc).__name__}: {exc}",
            }
            failure_rows.append(
                {
                    "sku_id": product_id,
                    "stage": "detail_parse",
                    "attempt": 1,
                    "status_code": "",
                    "error": detail_row["detail_parse_error"],
                    "retryable": False,
                    "source_product_url": tasks.get(product_id, ("", ""))[0],
                }
            )
        detail_row["detail_fetch_status"] = info["status"]
        detail_row["detail_html_path"] = info["html_path"]
        detail_row["detail_headers_path"] = info["headers_path"]
        detail_rows_by_id[product_id] = detail_row

    detail_output_rows = []
    for row in detail_targets:
        product_id = row.get("omni_item_id", "")
        plp_price = local_plp_price(row)
        detail = dict(detail_rows_by_id.get(product_id, {"omni_item_id": product_id}))
        detail.update(
            {
                "source_page": row.get("page", ""),
                "source_main_rank": row.get("main_rank", ""),
                "source_brand": row.get("brand", ""),
                "source_model_id": row.get("model_id", ""),
                "source_description": row.get("description", ""),
                "source_product_url": row.get("product_url", ""),
                "local_plp_price": plp_price,
            }
        )
        resolved = (
            detail.get("detail_selling_price")
            or detail.get("detail_location_selling_price")
            or detail.get("detail_jsonld_offer_price")
            or detail.get("detail_html_now_price")
            or detail.get("detail_html_data_product_price")
            or plp_price
        )
        override = overrides.get(product_id, {})
        if override and override.get("override_selling_price"):
            resolved = money_to_number(override.get("override_selling_price"))
            detail["manual_override_selling_price"] = money_to_number(override.get("override_selling_price"))
            detail["manual_override_was_price"] = money_to_number(override.get("override_was_price"))
            detail["manual_override_total_saving"] = money_to_number(override.get("override_total_saving"))
            detail["manual_override_source"] = override.get("override_source", "")
            detail["manual_override_note"] = override.get("override_note", "")
        detail["resolved_selling_price"] = resolved
        detail["resolved_price_source"] = (
            "manual_override"
            if override and override.get("override_selling_price")
            else
            "detail_mfe_price"
            if detail.get("detail_selling_price")
            else "detail_location_price"
            if detail.get("detail_location_selling_price")
            else "detail_jsonld"
            if detail.get("detail_jsonld_offer_price")
            else "detail_html_visible_price"
            if detail.get("detail_html_now_price")
            else "detail_html_data_productprice"
            if detail.get("detail_html_data_product_price")
            else "plp_html_data_productprice"
            if plp_price
            else ""
        )
        detail_output_rows.append(detail)

    write_csv(DETAIL_CSV, detail_output_rows)
    write_failure_csv(DETAIL_FAILURES_CSV, failure_rows)

    enriched_rows = []
    for row in rows:
        enriched = dict(row)
        product_id = row.get("omni_item_id", "")
        matching_detail = next((d for d in detail_output_rows if d.get("omni_item_id") == product_id), {})
        override = overrides.get(product_id, {})
        for key, value in matching_detail.items():
            if key == "omni_item_id":
                continue
            enriched[f"missing_price_{key}"] = value
        override_price = money_to_number(override.get("override_selling_price", "")) if override else ""
        enriched["manual_override_selling_price"] = override_price
        enriched["manual_override_was_price"] = money_to_number(override.get("override_was_price", "")) if override else ""
        enriched["manual_override_total_saving"] = money_to_number(override.get("override_total_saving", "")) if override else ""
        enriched["manual_override_source"] = override.get("override_source", "") if override else ""
        enriched["manual_override_note"] = override.get("override_note", "") if override else ""
        enriched["final_selling_price"] = row.get("selling_price") or override_price or matching_detail.get("resolved_selling_price", "")
        enriched["final_price_source"] = (
            row.get("price_source")
            or ("manual_override" if override_price else "")
            or matching_detail.get("resolved_price_source", "")
            or ("original_csv" if row.get("selling_price") else "")
        )
        enriched_rows.append(enriched)

    write_csv(ENRICHED_CSV, enriched_rows)

    resolved_count = sum(1 for row in detail_output_rows if row.get("resolved_selling_price"))
    print("=" * 80)
    print(f"Detail rows saved -> {DETAIL_CSV} ({len(detail_output_rows)} rows)")
    print(f"Detail failures saved -> {DETAIL_FAILURES_CSV} ({len(failure_rows)} rows)")
    print(f"Enriched full CSV saved -> {ENRICHED_CSV} ({len(enriched_rows)} rows)")
    print(f"Resolved detail prices -> {resolved_count}/{len(detail_output_rows)}")
    print(f"Detail HTML cache -> {DETAIL_DIR}")


if __name__ == "__main__":
    main()
