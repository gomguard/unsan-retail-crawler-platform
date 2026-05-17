import csv
import json
import os
from datetime import datetime
from pathlib import Path

from .step00_config import DEFAULT_AMAZON_RUN_ROOT, rel_path


RUN_DATE = os.getenv("AMAZON_RUN_DATE", datetime.now().strftime("%Y%m%d"))
RUN_ID = os.getenv("AMAZON_MAIN_RUN_ID", "main")
RUN_ROOT = Path(os.getenv("AMAZON_RUN_ROOT", str(DEFAULT_AMAZON_RUN_ROOT))) / RUN_ID
INPUT_CSV = Path(os.getenv("AMAZON_MAIN_TARGET_INPUT", RUN_ROOT / "parsed" / "main_occurrences.csv"))
OUTPUT_CSV = Path(os.getenv("AMAZON_MAIN_TARGET_OUTPUT", RUN_ROOT / "parsed" / "main_target_occurrences.csv"))
TARGET_LIMIT = int(os.getenv("AMAZON_MAIN_TARGET_LIMIT", "300"))


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


def valid_product_name(name):
    value = str(name or "").strip()
    if not value:
        return False
    lowered = value.lower()
    if lowered in {"sponsored", "featured from amazon brands", "more results"}:
        return False
    if lowered.startswith("rated ") or lowered.endswith(" ratings"):
        return False
    return True


def select_targets(rows):
    output = []
    seen = set()
    sorted_rows = sorted(
        rows,
        key=lambda row: (
            numeric(row.get("main_rank")),
            numeric(row.get("global_visual_rank")),
            numeric(row.get("page")),
            numeric(row.get("rank_in_page")),
        ),
    )
    for row in sorted_rows:
        asin = str(row.get("asin") or row.get("sku_id") or "").strip()
        if not asin or asin in seen:
            continue
        if not valid_product_name(row.get("product_name")):
            continue
        seen.add(asin)
        out = dict(row)
        out["asin"] = asin
        out["sku_id"] = asin
        out["target_rank"] = len(output) + 1
        out["selection_source"] = "main"
        output.append(out)
        if len(output) >= TARGET_LIMIT:
            break
    return output


def write_csv(path, rows):
    preferred = [
        "target_rank",
        "selection_source",
        "main_rank",
        "page",
        "rank_in_page",
        "asin",
        "sku_id",
        "brand",
        "product_name",
        "product_url",
        "detail_url",
        "image_url",
        "rating",
        "review_count",
        "customer_price",
        "is_sponsored",
    ]
    keys = set()
    for row in rows:
        keys.update(row)
    fieldnames = [key for key in preferred if key in keys]
    fieldnames.extend(sorted(keys - set(fieldnames)))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main():
    started_at = datetime.now().isoformat(timespec="seconds")
    rows = read_csv(INPUT_CSV)
    targets = select_targets(rows)
    write_csv(OUTPUT_CSV, targets)
    manifest = {
        "run_type": "step02_main_targets",
        "run_date": RUN_DATE,
        "run_root": rel_path(RUN_ROOT),
        "input_csv": rel_path(INPUT_CSV),
        "output_csv": rel_path(OUTPUT_CSV),
        "input_rows": len(rows),
        "target_limit": TARGET_LIMIT,
        "output_rows": len(targets),
        "unique_asins": len({row.get("asin") for row in targets if row.get("asin")}),
        "started_at": started_at,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
    }
    (RUN_ROOT / "manifest_main_targets.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
