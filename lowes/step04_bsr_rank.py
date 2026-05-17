import csv
import json
import os
from datetime import datetime
from pathlib import Path

from .step00_config import DEFAULT_LOWES_RUN_ROOT


RUN_DATE = os.getenv("LOWES_RUN_DATE", datetime.now().strftime("%Y%m%d"))
RUN_ID = os.getenv("LOWES_BSR_RUN_ID", "bsr")
RUN_ROOT = Path(os.getenv("LOWES_RUN_ROOT", str(DEFAULT_LOWES_RUN_ROOT))) / RUN_ID
INPUT_CSV = Path(os.getenv("LOWES_BSR_INPUT", RUN_ROOT / "parsed" / "main_occurrences.csv"))
OUTPUT_CSV = Path(os.getenv("LOWES_BSR_OUTPUT", RUN_ROOT / "parsed" / "bsr_rank_map.csv"))


def read_csv(path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def numeric(value, fallback=10**9):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return fallback


def build_rank_map(rows):
    output = []
    seen = set()
    sorted_rows = sorted(rows, key=lambda row: numeric(row.get("bsr_rank") or row.get("main_rank")))
    for row in sorted_rows:
        product_id = row.get("omni_item_id") or row.get("item_number") or row.get("product_url")
        if not product_id or product_id in seen:
            continue
        seen.add(product_id)
        rank = numeric(row.get("bsr_rank"), len(output) + 1)
        output.append(
            {
                "product_group": row.get("product_group", ""),
                "bsr_rank": rank,
                "omni_item_id": row.get("omni_item_id", ""),
                "item_number": row.get("item_number", ""),
                "brand": row.get("brand", ""),
                "model_id": row.get("model_id", ""),
                "description": row.get("description", ""),
                "product_url": row.get("product_url", ""),
            }
        )
    return output


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "product_group",
        "bsr_rank",
        "omni_item_id",
        "item_number",
        "brand",
        "model_id",
        "description",
        "product_url",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main():
    rows = read_csv(INPUT_CSV)
    rank_map = build_rank_map(rows)
    write_csv(OUTPUT_CSV, rank_map)
    manifest = {
        "run_type": "step04_bsr_rank",
        "run_date": RUN_DATE,
        "run_root": str(RUN_ROOT),
        "input_csv": str(INPUT_CSV),
        "output_csv": str(OUTPUT_CSV),
        "input_rows": len(rows),
        "output_rows": len(rank_map),
    }
    manifest_path = RUN_ROOT / "manifest_bsr_rank.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
