import csv
import json
from pathlib import Path

from .step00_config import rel_path


DETAIL_BENCHMARK_FIELDS = [
    "sku_id",
    "product_name",
    "product_url",
    "main_rank",
    "bsr_rank",
    "trend_rank",
    "promotion_type",
    "is_sponsored",
    "detail_success",
    "detail_status_code",
    "detail_attempt",
    "detail_elapsed_seconds",
    "detail_x_request_cost",
    "detail_bytes",
    "detail_stored_bytes",
    "detail_html_mode",
    "detail_apollo_payload_count",
    "detail_started_at",
    "detail_finished_at",
    "detail_error",
    "detail_html_path",
    "detail_apollo_path",
    "review_success",
    "review_status_code",
    "review_attempt",
    "review_elapsed_seconds",
    "review_x_request_cost",
    "review_bytes",
    "review_count_returned",
    "review_started_at",
    "review_finished_at",
    "review_error",
    "review_response_path",
    "total_x_request_cost",
    "total_elapsed_seconds",
]


def read_json(path):
    path = Path(path)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except ValueError:
        return {}


def load_csv(path):
    path = Path(path)
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=DETAIL_BENCHMARK_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def as_float(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def find_detail_file(detail_dir, sku, suffix):
    nested = sorted(
        Path(detail_dir).glob(f"*_{sku}_*/{sku}{suffix}"),
        key=lambda path: (
            0 if path.parent.name.endswith("_success") else 1 if path.parent.name.endswith("_fail") else 2,
            path.parent.name,
        ),
    )
    if nested:
        return nested[0]
    return Path(detail_dir) / f"{sku}{suffix}"


def find_review_file(review_dir, sku, suffix):
    nested = sorted(
        Path(review_dir).glob(f"*_{sku}_*/{sku}{suffix}"),
        key=lambda path: (
            0 if path.parent.name.endswith("_success") else 1 if path.parent.name.endswith("_fail") else 2,
            path.parent.name,
        ),
    )
    if nested:
        return nested[0]
    return Path(review_dir) / f"{sku}{suffix}"


def benchmark_row(target, detail_root):
    sku = str(target.get("sku_id") or "").strip()
    detail_dir = Path(detail_root) / "raw" / "detail_html"
    review_dir = Path(detail_root) / "raw" / "review20"
    detail_meta_path = find_detail_file(detail_dir, sku, "_meta.json")
    review_meta_path = find_review_file(review_dir, sku, "_meta.json")
    detail_html_path = find_detail_file(detail_dir, sku, ".html")
    detail_apollo_path = find_detail_file(detail_dir, sku, "_apollo.json")
    review_response_path = find_review_file(review_dir, sku, "_response.json")

    dmeta = read_json(detail_meta_path)
    rmeta = read_json(review_meta_path)
    detail_cost = as_float(dmeta.get("x_request_cost"))
    review_cost = as_float(rmeta.get("x_request_cost"))
    detail_elapsed = as_float(dmeta.get("elapsed_seconds"))
    review_elapsed = as_float(rmeta.get("elapsed_seconds"))

    return {
        "sku_id": sku,
        "product_name": target.get("product_name", ""),
        "product_url": target.get("product_url", ""),
        "main_rank": target.get("main_rank", ""),
        "bsr_rank": target.get("bsr_rank", ""),
        "trend_rank": target.get("trend_rank", ""),
        "promotion_type": target.get("promotion_type", ""),
        "is_sponsored": target.get("is_sponsored", ""),
        "detail_success": dmeta.get("success", ""),
        "detail_status_code": dmeta.get("status_code", ""),
        "detail_attempt": dmeta.get("attempt", ""),
        "detail_elapsed_seconds": dmeta.get("elapsed_seconds", ""),
        "detail_x_request_cost": dmeta.get("x_request_cost", ""),
        "detail_bytes": dmeta.get("bytes", ""),
        "detail_stored_bytes": dmeta.get("stored_bytes", ""),
        "detail_html_mode": dmeta.get("html_mode", ""),
        "detail_apollo_payload_count": dmeta.get("apollo_payload_count", ""),
        "detail_started_at": dmeta.get("started_at", ""),
        "detail_finished_at": dmeta.get("finished_at", ""),
        "detail_error": dmeta.get("error", ""),
        "detail_html_path": rel_path(detail_html_path) if detail_html_path.exists() else "",
        "detail_apollo_path": rel_path(detail_apollo_path) if detail_apollo_path.exists() else "",
        "review_success": rmeta.get("success", ""),
        "review_status_code": rmeta.get("status_code", ""),
        "review_attempt": rmeta.get("attempt", ""),
        "review_elapsed_seconds": rmeta.get("elapsed_seconds", ""),
        "review_x_request_cost": rmeta.get("x_request_cost", ""),
        "review_bytes": rmeta.get("bytes", ""),
        "review_count_returned": rmeta.get("review_count_returned", ""),
        "review_started_at": rmeta.get("started_at", ""),
        "review_finished_at": rmeta.get("finished_at", ""),
        "review_error": rmeta.get("error", ""),
        "review_response_path": rel_path(review_response_path) if review_response_path.exists() else "",
        "total_x_request_cost": round(detail_cost + review_cost, 7),
        "total_elapsed_seconds": round(detail_elapsed + review_elapsed, 3),
    }


def build_detail_benchmarks(target_csv, detail_root):
    rows = []
    seen = set()
    for target in load_csv(target_csv):
        sku = str(target.get("sku_id") or "").strip()
        if not sku or sku in seen:
            continue
        seen.add(sku)
        rows.append(benchmark_row(target, detail_root))
    return rows


def write_detail_benchmarks(target_csv, detail_root, output_csv):
    rows = build_detail_benchmarks(target_csv, detail_root)
    write_csv(output_csv, rows)
    return rows
