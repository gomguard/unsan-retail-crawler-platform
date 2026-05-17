import csv
import json
import os
from datetime import datetime
from pathlib import Path

from .step00_config import DEFAULT_BESTBUY_RUN_ROOT, KRW_PER_USD, rel_path
from .step00_detail_benchmarks import write_detail_benchmarks


RUN_DATE = os.getenv("BESTBUY_RUN_DATE", datetime.now().strftime("%Y%m%d"))
RUN_ROOT = Path(os.getenv("BESTBUY_RUN_ROOT", DEFAULT_BESTBUY_RUN_ROOT))
MAIN_RUN_ID = os.getenv("BESTBUY_STATUS_MAIN_RUN_ID", os.getenv("BESTBUY_FINAL_MAIN_RUN_ID", "main"))
MAIN_ROOT = Path(os.getenv("BESTBUY_MAIN_ROOT", RUN_ROOT / MAIN_RUN_ID))
DETAIL_ROOT = Path(os.getenv("BESTBUY_DETAIL_RUN_ROOT", RUN_ROOT / "detail"))
OUTPUT_ROOT = Path(os.getenv("BESTBUY_OUTPUT_ROOT", RUN_ROOT / "output"))
STATUS_DIR = Path(os.getenv("BESTBUY_STATUS_ROOT", RUN_ROOT / "status"))
DETAIL_BENCHMARKS_CSV = DETAIL_ROOT / "benchmarks" / "detail_benchmarks.csv"
DAILY_STATUS_CSV = STATUS_DIR / "daily_status.csv"
LATEST_STATUS_JSON = STATUS_DIR / f"{RUN_DATE}_status.json"


def read_json(path):
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except ValueError:
        return {}


def csv_count(path):
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        next(reader, None)
        return sum(1 for _ in reader)


def csv_unique_count(path, key):
    if not path.exists():
        return 0
    seen = set()
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            value = str(row.get(key) or "").strip()
            if value:
                seen.add(value)
    return len(seen)


def detail_meta_counts():
    raw_dir = DETAIL_ROOT / "raw"
    detail_dir = raw_dir / "detail_html"
    review_dir = raw_dir / "review20"
    detail_success = 0
    detail_failed = 0
    review_success = 0
    review_failed = 0
    detail_cost = 0.0
    review_cost = 0.0

    for path in detail_dir.rglob("*_meta.json"):
        meta = read_json(path)
        if meta.get("success") is True:
            detail_success += 1
        else:
            detail_failed += 1
        detail_cost += float(meta.get("x_request_cost") or 0)

    for path in review_dir.rglob("*_meta.json"):
        meta = read_json(path)
        if meta.get("success") is True:
            review_success += 1
        else:
            review_failed += 1
        review_cost += float(meta.get("x_request_cost") or 0)

    return {
        "detail_success_count": detail_success,
        "detail_failed_count": detail_failed,
        "review_success_count": review_success,
        "review_failed_count": review_failed,
        "cached_detail_cost_usd": round(detail_cost, 6),
        "cached_review_cost_usd": round(review_cost, 6),
        "cached_total_cost_usd": round(detail_cost + review_cost, 6),
        "cached_total_cost_krw_1550": round((detail_cost + review_cost) * KRW_PER_USD, 2),
    }


def append_daily_status(row):
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    exists = DAILY_STATUS_CSV.exists()
    fieldnames = list(row)
    with DAILY_STATUS_CSV.open("a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def build_status():
    final_targets = OUTPUT_ROOT / "bestbuy_final_targets.csv"
    final_output = OUTPUT_ROOT / "final_output.csv"
    failures = DETAIL_ROOT / "parsed" / "detail_failures.csv"
    benchmark_rows = write_detail_benchmarks(final_targets, DETAIL_ROOT, DETAIL_BENCHMARKS_CSV)
    final_manifest = read_json(OUTPUT_ROOT / "bestbuy_final_targets.manifest.json")
    detail_manifest = read_json(DETAIL_ROOT / "manifest_detail_enrichment.json")
    meta_counts = detail_meta_counts()
    target_unique = csv_unique_count(final_targets, "sku_id")
    output_rows = csv_count(final_output)
    failure_rows = csv_count(failures)

    pending_detail = max(target_unique - meta_counts["detail_success_count"], 0)
    pending_review = max(target_unique - meta_counts["review_success_count"], 0)

    return {
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "run_date": RUN_DATE,
        "run_id": MAIN_RUN_ID,
        "run_root": rel_path(RUN_ROOT),
        "main_root": rel_path(MAIN_ROOT),
        "detail_root": rel_path(DETAIL_ROOT),
        "output_root": rel_path(OUTPUT_ROOT),
        "main_unique_count": final_manifest.get("main_unique_count", ""),
        "bsr_count": final_manifest.get("bsr_count", ""),
        "promotion_unique_count": final_manifest.get("promotion_unique_count", ""),
        "trending_unique_count": final_manifest.get("trending_unique_count", ""),
        "target_rows": csv_count(final_targets),
        "target_unique_skus": target_unique,
        "target_needs_more_candidates": final_manifest.get("needs_more_main_candidates", ""),
        "detail_success_count": meta_counts["detail_success_count"],
        "detail_failed_count": meta_counts["detail_failed_count"],
        "review_success_count": meta_counts["review_success_count"],
        "review_failed_count": meta_counts["review_failed_count"],
        "pending_detail_count": pending_detail,
        "pending_review_count": pending_review,
        "final_output_rows": output_rows,
        "detail_failure_rows": failure_rows,
        "latest_detail_run_cost_usd": detail_manifest.get("total_cost_usd_this_run", ""),
        "latest_detail_run_cost_krw_1550": detail_manifest.get("total_cost_krw_1550_this_run", ""),
        "cached_total_cost_usd": meta_counts["cached_total_cost_usd"],
        "cached_total_cost_krw_1550": meta_counts["cached_total_cost_krw_1550"],
        "final_targets_csv": rel_path(final_targets),
        "final_output_csv": rel_path(final_output),
        "failures_csv": rel_path(failures),
        "detail_benchmarks_csv": rel_path(DETAIL_BENCHMARKS_CSV),
        "detail_benchmark_rows": len(benchmark_rows),
    }


def main():
    status = build_status()
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    LATEST_STATUS_JSON.write_text(json.dumps(status, indent=2, ensure_ascii=False), encoding="utf-8")
    append_daily_status(status)
    print(json.dumps(status, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
