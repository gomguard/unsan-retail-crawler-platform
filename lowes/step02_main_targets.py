import csv
import json
import os
from datetime import datetime
from pathlib import Path

from .step00_config import DEFAULT_LOWES_RUN_ROOT


RUN_DATE = os.getenv("LOWES_RUN_DATE", datetime.now().strftime("%Y%m%d"))
RUN_ID = os.getenv("LOWES_MAIN_RUN_ID", "main")
RUN_ROOT = Path(os.getenv("LOWES_RUN_ROOT", str(DEFAULT_LOWES_RUN_ROOT))) / RUN_ID
INPUT_CSV = Path(os.getenv("LOWES_MAIN_TARGET_INPUT", RUN_ROOT / "parsed" / "main_occurrences.csv"))
OUTPUT_CSV = Path(os.getenv("LOWES_MAIN_TARGET_OUTPUT", RUN_ROOT / "parsed" / "main_target_occurrences.csv"))
TARGET_LIMIT = int(os.getenv("LOWES_MAIN_TARGET_LIMIT", "300"))


def read_csv(path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def numeric(value, fallback=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return fallback


def select_targets(rows):
    seen = set()
    output = []
    sorted_rows = sorted(
        rows,
        key=lambda row: (
            numeric(row.get("main_rank"), 10**9),
            numeric(row.get("page"), 10**9),
            numeric(row.get("rank_in_page"), 10**9),
        ),
    )
    for row in sorted_rows:
        product_id = row.get("omni_item_id") or row.get("item_number") or row.get("product_url")
        if not product_id or product_id in seen:
            continue
        seen.add(product_id)
        out = dict(row)
        out["target_rank"] = len(output) + 1
        out["selection_source"] = "main"
        output.append(out)
        if len(output) >= TARGET_LIMIT:
            break
    return output


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = []
    seen = set()
    preferred = [
        "target_rank",
        "selection_source",
        "main_rank",
        "page",
        "rank_in_page",
        "omni_item_id",
        "item_number",
        "brand",
        "model_id",
        "description",
        "product_url",
        "rating",
        "review_count",
        "selling_price",
        "sponsored",
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


def main():
    started = datetime.now().isoformat(timespec="seconds")
    rows = read_csv(INPUT_CSV)
    targets = select_targets(rows)
    write_csv(OUTPUT_CSV, targets)
    manifest = {
        "run_type": "step02_main_targets",
        "run_date": RUN_DATE,
        "run_root": str(RUN_ROOT),
        "input_csv": str(INPUT_CSV),
        "output_csv": str(OUTPUT_CSV),
        "input_rows": len(rows),
        "target_limit": TARGET_LIMIT,
        "output_rows": len(targets),
        "started_at": started,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
    }
    manifest_path = RUN_ROOT / "manifest_main_targets.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
