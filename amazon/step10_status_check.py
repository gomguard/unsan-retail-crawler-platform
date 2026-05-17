import csv
import json
import os
from datetime import datetime
from pathlib import Path

from .step00_config import DEFAULT_AMAZON_RUN_ROOT, amazon_marketplace, amazon_run_date


RUN_DATE = amazon_run_date()
RUN_ROOT = Path(os.getenv("AMAZON_RUN_ROOT", str(DEFAULT_AMAZON_RUN_ROOT)))
MAIN_ROOT = RUN_ROOT / os.getenv("AMAZON_MAIN_RUN_ID", "main")
BSR_ROOT = RUN_ROOT / os.getenv("AMAZON_BSR_RUN_ID", "bsr")
DETAIL_ROOT = Path(os.getenv("AMAZON_DETAIL_RUN_ROOT", RUN_ROOT / "detail"))
OUTPUT_ROOT = Path(os.getenv("AMAZON_OUTPUT_ROOT", RUN_ROOT / "output"))
STATUS_DIR = Path(os.getenv("AMAZON_STATUS_ROOT", RUN_ROOT / "status"))
DAILY_STATUS_CSV = STATUS_DIR / "daily_status.csv"
LATEST_STATUS_JSON = STATUS_DIR / f"{RUN_DATE}_status.json"


def csv_count(path):
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return sum(1 for _ in csv.DictReader(f))


def file_count(path, pattern="*"):
    if not path.exists():
        return 0
    return len(list(path.rglob(pattern)))


def append_daily_status(row):
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    exists = DAILY_STATUS_CSV.exists()
    fieldnames = list(row.keys())
    with DAILY_STATUS_CSV.open("a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def build_status():
    final_targets = OUTPUT_ROOT / "amazon_final_targets.csv"
    final_output = OUTPUT_ROOT / "final_output.csv"
    detail_failures = DETAIL_ROOT / "parsed" / "detail_failures.csv"
    return {
        "run_date": RUN_DATE,
        "marketplace": amazon_marketplace(),
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "run_root": str(RUN_ROOT),
        "main_rows": csv_count(MAIN_ROOT / "parsed" / "main_occurrences.csv"),
        "main_target_rows": csv_count(MAIN_ROOT / "parsed" / "main_target_occurrences.csv"),
        "bsr_rows": csv_count(BSR_ROOT / "parsed" / "main_occurrences.csv"),
        "bsr_rank_rows": csv_count(BSR_ROOT / "parsed" / "bsr_rank_map.csv"),
        "final_target_rows": csv_count(final_targets),
        "final_output_rows": csv_count(final_output),
        "detail_success_files": file_count(DETAIL_ROOT / "raw" / "detail_html", "*.html"),
        "detail_failure_rows": csv_count(detail_failures),
        "final_targets_csv": str(final_targets),
        "final_output_csv": str(final_output),
    }


def main():
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    status = build_status()
    LATEST_STATUS_JSON.write_text(json.dumps(status, indent=2, ensure_ascii=False), encoding="utf-8")
    append_daily_status(status)
    print(json.dumps(status, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
