import csv
import json
import os
import time
from datetime import datetime
from pathlib import Path

from requests import RequestException

from .step00_config import DEFAULT_BESTBUY_RUN_ROOT, rel_path
from .step00_parse_pdp import absolute_bestbuy_url, nested_get
from .step00_parse_search import merge_dict
from .step00_sponsored_graphql import build_sponsored_payload, post_graphql, sponsored_product_map

RUN_DATE = os.getenv("BESTBUY_RUN_DATE", datetime.now().strftime("%Y%m%d"))
RUN_ID = os.getenv("BESTBUY_MAIN_TARGET_RUN_ID", "main")
RUN_ROOT = Path(os.getenv("BESTBUY_RUN_ROOT", DEFAULT_BESTBUY_RUN_ROOT)) / RUN_ID
INPUT_CSV = Path(os.getenv("BESTBUY_MAIN_TARGET_INPUT", RUN_ROOT / "parsed" / "main_occurrences.csv"))
OUTPUT_CSV = Path(os.getenv("BESTBUY_MAIN_TARGET_OUTPUT", RUN_ROOT / "parsed" / "main_target_occurrences.csv"))
CHUNK_SIZE = int(os.getenv("BESTBUY_SPONSORED_CHUNK_SIZE", "10"))
MAX_ATTEMPTS = int(os.getenv("BESTBUY_SPONSORED_MAX_ATTEMPTS", "3"))
TARGET_CONTAINERS = {"organic_product", "sponsored_ingrid"}


def now():
    return datetime.now().isoformat(timespec="seconds")


def compact_json(value):
    if value in ("", None):
        return ""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def load_rows(path):
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def chunks(values, size):
    for index in range(0, len(values), size):
        yield values[index : index + size]


def sponsored_skus(rows):
    skus = []
    for row in rows:
        if row.get("container_type") != "sponsored_ingrid":
            continue
        sku = str(row.get("sku_id") or "").strip()
        if sku and sku not in skus:
            skus.append(sku)
    return skus


def fetch_sponsored_products(skus):
    products = {}
    raw_dir = RUN_ROOT / "raw" / "sponsored_enrichment"
    raw_dir.mkdir(parents=True, exist_ok=True)
    calls = []
    for chunk_index, sku_chunk in enumerate(chunks(skus, CHUNK_SIZE), 1):
        payload = build_sponsored_payload(sku_chunk)
        request_path = raw_dir / f"chunk_{chunk_index:03d}_request.json"
        response_path = raw_dir / f"chunk_{chunk_index:03d}_response.txt"
        json_path = raw_dir / f"chunk_{chunk_index:03d}_response.json"
        headers_path = raw_dir / f"chunk_{chunk_index:03d}_headers.json"
        request_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

        response_json = {}
        parse_error = ""
        error = ""
        status_code = "ERR"
        elapsed = 0
        headers = {}
        started_at = now()
        finished_at = ""

        for attempt in range(1, MAX_ATTEMPTS + 1):
            started_at = now()
            try:
                response, elapsed = post_graphql(payload)
                finished_at = now()
                status_code = response.status_code
                headers = dict(response.headers)
                response_path.write_text(response.text, encoding="utf-8", errors="replace")
                headers_path.write_text(json.dumps(headers, indent=2, ensure_ascii=False), encoding="utf-8")
                try:
                    response_json = response.json()
                    json_path.write_text(json.dumps(response_json, indent=2, ensure_ascii=False), encoding="utf-8")
                    returned = sponsored_product_map(response_json)
                    merge_dict(products, returned)
                    if status_code == 200 and returned:
                        error = ""
                        break
                    error = json.dumps(response_json.get("errors") or response_json, ensure_ascii=False)[:500]
                except ValueError as exc:
                    parse_error = str(exc)
                    error = parse_error
                if status_code == 200:
                    break
            except RequestException as exc:
                finished_at = now()
                error = str(exc)
            if attempt < MAX_ATTEMPTS:
                time.sleep(min(2 * attempt, 5))

        calls.append(
            {
                "chunk": chunk_index,
                "sku_count": len(sku_chunk),
                "attempts": attempt,
                "started_at": started_at,
                "finished_at": finished_at,
                "elapsed_seconds": elapsed,
                "status_code": status_code,
                "x_request_cost": headers.get("x-request-cost", ""),
                "error_count": len(response_json.get("errors", [])) if isinstance(response_json, dict) else "",
                "parse_error": parse_error,
                "error": error,
                "request_path": rel_path(request_path),
                "response_path": rel_path(json_path if response_json else response_path),
            }
        )
        print(
            f"sponsored_chunk={chunk_index:03d} status={status_code} attempts={attempt} "
            f"skus={len(sku_chunk)} returned={len(sponsored_product_map(response_json))} "
            f"cost={headers.get('x-request-cost', '')}"
        )
    return products, calls


def enrich_sponsored_row(row, product):
    if not isinstance(product, dict):
        return row
    row = dict(row)
    row["bsin"] = row.get("bsin") or product.get("bsin", "")
    row["product_name"] = row.get("product_name") or nested_get(product, ["name", "short"])
    row["image_url"] = row.get("image_url") or nested_get(product, ["primaryImage", "piscesHref"]) or nested_get(
        product, ["primaryImage", "href"]
    )
    row["product_url"] = row.get("product_url") or absolute_bestbuy_url(
        nested_get(product, ["url", "skuSpecificUrl"])
        or nested_get(product, ["url", "pdp"])
        or nested_get(product, ["url", "relativePdp"])
    )
    review_info = product.get("reviewInfo", {}) if isinstance(product.get("reviewInfo"), dict) else {}
    row["rating"] = row.get("rating") or review_info.get("averageRating", "")
    row["review_count"] = row.get("review_count") or review_info.get("reviewCount", "")
    row["is_reviewable"] = row.get("is_reviewable") or review_info.get("isReviewable", "")

    try:
        raw_product = json.loads(row.get("raw_product_json") or "{}")
    except ValueError:
        raw_product = {}
    merge_dict(raw_product, product)
    row["raw_product_json"] = compact_json(raw_product)
    return row


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = set()
    for row in rows:
        keys.update(row)
    preferred = [
        "page",
        "visual_rank",
        "global_visual_rank",
        "organic_rank",
        "global_organic_rank",
        "container_type",
        "is_sponsored",
        "placement",
        "placement_name",
        "sponsored_rank",
        "source_doc_index",
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
        "offer_count",
    ]
    fieldnames = [key for key in preferred if key in keys]
    fieldnames.extend(sorted(keys - set(fieldnames)))
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main():
    started_at = now()
    rows = load_rows(INPUT_CSV)
    target_rows = [row for row in rows if row.get("container_type") in TARGET_CONTAINERS]
    skus = sponsored_skus(target_rows)
    products, calls = fetch_sponsored_products(skus) if skus else ({}, [])
    enriched = []
    for row in target_rows:
        if row.get("container_type") == "sponsored_ingrid":
            row = enrich_sponsored_row(row, products.get(str(row.get("sku_id"))))
        enriched.append(row)
    write_csv(OUTPUT_CSV, enriched)

    cost = sum(float(call.get("x_request_cost") or 0) for call in calls)
    manifest = {
        "run_type": "step02_main_targets",
        "run_root": rel_path(RUN_ROOT),
        "input_csv": rel_path(INPUT_CSV),
        "output_csv": rel_path(OUTPUT_CSV),
        "started_at": started_at,
        "finished_at": now(),
        "target_containers": sorted(TARGET_CONTAINERS),
        "input_row_count": len(rows),
        "target_row_count": len(enriched),
        "target_unique_sku_count": len({row.get("sku_id") for row in enriched if row.get("sku_id")}),
        "sponsored_unique_sku_count": len(skus),
        "sponsored_call_count": len(calls),
        "sponsored_cost_usd": cost,
        "sponsored_cost_krw_1550": round(cost * 1550, 2),
        "calls": calls,
    }
    manifest_path = RUN_ROOT / "manifest_main_targets.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"target_csv={OUTPUT_CSV}")
    print(
        f"target_rows={manifest['target_row_count']} unique_skus={manifest['target_unique_sku_count']} "
        f"sponsored_skus={len(skus)} sponsored_calls={len(calls)} cost_krw={manifest['sponsored_cost_krw_1550']}"
    )
    print(f"manifest={manifest_path}")


if __name__ == "__main__":
    main()
