import csv
import json
import os
import time
from datetime import datetime
from pathlib import Path

from zenrows import ZenRowsClient

from .step00_apollo import iter_apollo_push_payloads
from .step00_config import DEFAULT_BESTBUY_RUN_ROOT, PROMOTION_LABELS, has_target_url, load_initial_urls, rel_path

RUN_DATE = os.getenv("BESTBUY_RUN_DATE", datetime.now().strftime("%Y%m%d"))
RUN_ROOT = Path(os.getenv("BESTBUY_PROMOTION_RUN_ROOT", DEFAULT_BESTBUY_RUN_ROOT / "promotion"))
REQUEST_TIMEOUT = int(os.getenv("ZENROWS_TIMEOUT", "180"))
ENDPOINT = os.getenv("BESTBUY_GRAPHQL_ENDPOINT", "https://www.bestbuy.com/gateway/graphql")
PLACEMENT = os.getenv("BESTBUY_PROMOTION_PLACEMENT", "all")
REFERER = os.getenv("BESTBUY_PROMOTION_REFERER", load_initial_urls().get("promotion_tv_home_theater", ""))
QUERY_TEMPLATE_HTML = Path(
    os.getenv("BESTBUY_PROMOTION_QUERY_TEMPLATE_HTML", "references/bestbuy_promotion_page_sample.html")
)


def now():
    return datetime.now().isoformat(timespec="seconds")


def find_started_operation_for_placement(html_text, placement):
    for payload in iter_apollo_push_payloads(html_text):
        for event in payload.get("events", []):
            if event.get("type") != "started":
                continue
            options = event.get("options") or {}
            variables = options.get("variables") or {}
            if variables.get("placement") == placement:
                query = options.get("query") or ""
                operation_name = query.split("{", 1)[0].replace("query", "", 1).strip().split("(", 1)[0]
                return {
                    "operationName": operation_name,
                    "variables": variables,
                    "query": query,
                }
    raise RuntimeError(f"Could not find operation for placement={placement}")


def extract_rows_from_response(response_json, placement):
    promotion_type = PROMOTION_LABELS.get(placement, placement)
    rows = []
    deals = (((response_json.get("data") or {}).get("customer") or {}).get("deals") or {})
    for position, item in enumerate(deals.get("items") or [], 1):
        product = item.get("product") or item.get("featuredProduct") or {}
        sku_id = product.get("skuId")
        if not sku_id:
            continue
        name = product.get("name") or {}
        if isinstance(name, dict):
            name = name.get("short") or name.get("title") or ""
        url = product.get("url") or {}
        relative_url = url.get("relativePdp") if isinstance(url, dict) else ""
        rows.append(
            {
                "promotion_type": promotion_type,
                "promotion_placement": placement,
                "promotion_position": position,
                "sku_id": sku_id,
                "retailer_sku_name": name,
                "product_url": f"https://www.bestbuy.com{relative_url}" if relative_url else "",
            }
        )
    return rows


def safe_part(value):
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in str(value or "").strip()).strip("_") or "na"


def placement_folder(placement, status=None):
    raw_root = RUN_ROOT / "raw"
    placement_part = safe_part(placement)
    if status:
        folder = raw_root / f"{placement_part}_{status}"
        folder.mkdir(parents=True, exist_ok=True)
        return folder
    for suffix in ("success", "fail"):
        folder = raw_root / f"{placement_part}_{suffix}"
        if folder.exists():
            return folder
    return raw_root


def placement_artifact_paths(placement, status=None):
    folder = placement_folder(placement, status)
    placement_part = safe_part(placement)
    return {
        "folder": folder,
        "request": folder / f"{placement_part}_request.json",
        "response": folder / f"{placement_part}_response.txt",
        "headers": folder / f"{placement_part}_headers.json",
        "json": folder / f"{placement_part}_response.json",
    }


def run_one(client, html_text, placement):
    payload = find_started_operation_for_placement(html_text, placement)

    start = time.perf_counter()
    response = client.post(
        ENDPOINT,
        params={
            "custom_headers": "true",
            "premium_proxy": "true",
            "proxy_country": "us",
            "js_render": "true",
        },
        headers={
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
            "origin": "https://www.bestbuy.com",
            "referer": REFERER,
        },
        data=json.dumps(payload),
        timeout=REQUEST_TIMEOUT,
    )
    elapsed = round(time.perf_counter() - start, 3)
    text = response.text
    status = "success" if response.status_code == 200 else "fail"
    paths = placement_artifact_paths(placement, status)
    paths["request"].write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    paths["response"].write_text(text, encoding="utf-8", errors="replace")
    paths["headers"].write_text(json.dumps(dict(response.headers), indent=2, ensure_ascii=False), encoding="utf-8")

    response_json = {}
    parse_error = ""
    try:
        response_json = response.json()
        paths["json"].write_text(
            json.dumps(response_json, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except ValueError as exc:
        parse_error = str(exc)

    rows = extract_rows_from_response(response_json, placement)
    return {
        "summary": {
            "started_at": now(),
            "placement": placement,
            "promotion_type": PROMOTION_LABELS.get(placement, placement),
            "status_code": response.status_code,
            "elapsed_seconds": elapsed,
            "x_request_cost": response.headers.get("x-request-cost", ""),
            "bytes": len(text or ""),
            "parse_error": parse_error,
            "row_count": len(rows),
            "artifact_folder": rel_path(paths["folder"]),
            "response_json_path": rel_path(paths["json"]) if response_json else "",
        },
        "rows": rows,
    }


def write_rows(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "promotion_type",
                "promotion_placement",
                "promotion_position",
                "sku_id",
                "retailer_sku_name",
                "product_url",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def main():
    if not has_target_url("promotion"):
        summary = {
            "started_at": now(),
            "skipped": True,
            "reason": "no promotion URL for category",
            "placements": [],
            "call_count": 0,
            "row_count": 0,
            "total_x_request_cost": 0,
        }
        RUN_ROOT.mkdir(parents=True, exist_ok=True)
        write_rows(RUN_ROOT / "parsed" / "all_promotion_products.csv", [])
        (RUN_ROOT / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return
    api_key = os.getenv("ZENROWS_API_KEY")
    if not api_key:
        raise RuntimeError("Set ZENROWS_API_KEY in .env")
    html_text = QUERY_TEMPLATE_HTML.read_text(encoding="utf-8", errors="ignore")
    client = ZenRowsClient(api_key)
    placements = list(PROMOTION_LABELS) if PLACEMENT.lower() == "all" else [PLACEMENT]

    all_rows = []
    summaries = []
    for placement in placements:
        result = run_one(client, html_text, placement)
        summaries.append(result["summary"])
        all_rows.extend(result["rows"])

    slug = "all" if PLACEMENT.lower() == "all" else PLACEMENT
    out_csv = RUN_ROOT / "parsed" / f"{slug}_promotion_products.csv"
    write_rows(out_csv, all_rows)
    summary = {
        "started_at": now(),
        "placements": placements,
        "call_count": len(placements),
        "row_count": len(all_rows),
        "total_x_request_cost": sum(float(s["x_request_cost"] or 0) for s in summaries),
        "summaries": summaries,
        "csv": rel_path(out_csv),
    }
    (RUN_ROOT / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
