import csv
import json
import os
from datetime import datetime
from pathlib import Path

from .step00_config import DEFAULT_LOWES_RUN_ROOT


RUN_DATE = os.getenv("LOWES_RUN_DATE", datetime.now().strftime("%Y%m%d"))
RUN_ROOT = Path(os.getenv("LOWES_RUN_ROOT", str(DEFAULT_LOWES_RUN_ROOT)))
MAIN_RUN_ID = os.getenv("LOWES_MAIN_RUN_ID", "main")
BSR_RUN_ID = os.getenv("LOWES_BSR_RUN_ID", "bsr")
MAIN_ROOT = RUN_ROOT / MAIN_RUN_ID
BSR_ROOT = RUN_ROOT / BSR_RUN_ID
OUTPUT_ROOT = Path(os.getenv("LOWES_OUTPUT_ROOT", RUN_ROOT / "output"))
MAIN_INPUT = Path(os.getenv("LOWES_FINAL_MAIN_INPUT", MAIN_ROOT / "parsed" / "main_target_occurrences.csv"))
BSR_INPUT = Path(os.getenv("LOWES_FINAL_BSR_INPUT", BSR_ROOT / "parsed" / "bsr_rank_map.csv"))
OUTPUT_CSV = Path(os.getenv("LOWES_FINAL_TARGET_OUTPUT", OUTPUT_ROOT / "lowes_final_targets.csv"))


def read_csv(path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def rank_lookup(rows):
    result = {}
    for row in rows:
        product_id = row.get("omni_item_id") or row.get("item_number") or row.get("product_url")
        if product_id and product_id not in result:
            result[product_id] = row
    return result


def build_final_targets(main_rows, bsr_rows):
    bsr_by_id = rank_lookup(bsr_rows)
    output = []
    seen = set()
    for row in main_rows:
        out = dict(row)
        product_id = out.get("omni_item_id") or out.get("item_number") or out.get("product_url")
        bsr = bsr_by_id.get(product_id, {})
        out["final_target_rank"] = len(output) + 1
        out["bsr_rank"] = bsr.get("bsr_rank", out.get("bsr_rank", ""))
        out["bsr_product_group"] = bsr.get("product_group", out.get("bsr_product_group", ""))
        output.append(out)
        if product_id:
            seen.add(product_id)
    for row in bsr_rows:
        product_id = row.get("omni_item_id") or row.get("item_number") or row.get("product_url")
        if product_id and product_id in seen:
            continue
        out = dict(row)
        out["final_target_rank"] = len(output) + 1
        out.setdefault("target_rank", out["final_target_rank"])
        out.setdefault("selection_source", "bsr")
        out["bsr_rank"] = out.get("bsr_rank", "")
        out["bsr_product_group"] = out.get("product_group", out.get("bsr_product_group", ""))
        output.append(out)
        if product_id:
            seen.add(product_id)
    return output


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = []
    seen = set()
    preferred = [
        "final_target_rank",
        "target_rank",
        "selection_source",
        "main_rank",
        "bsr_rank",
        "bsr_product_group",
        "omni_item_id",
        "item_number",
        "brand",
        "model_id",
        "description",
        "product_url",
        "rating",
        "review_count",
        "selling_price",
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
    main_rows = read_csv(MAIN_INPUT)
    bsr_rows = read_csv(BSR_INPUT)
    final_rows = build_final_targets(main_rows, bsr_rows)
    write_csv(OUTPUT_CSV, final_rows)
    manifest = {
        "run_type": "step07_final_targets",
        "run_date": RUN_DATE,
        "run_root": str(RUN_ROOT),
        "main_input": str(MAIN_INPUT),
        "bsr_input": str(BSR_INPUT),
        "output_csv": str(OUTPUT_CSV),
        "main_rows": len(main_rows),
        "bsr_rows": len(bsr_rows),
        "output_rows": len(final_rows),
    }
    manifest_path = OUTPUT_ROOT / "lowes_final_targets.manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
