import csv
import json
import os
from datetime import datetime
from pathlib import Path

from .step00_config import DEFAULT_AMAZON_RUN_ROOT, rel_path


RUN_DATE = os.getenv("AMAZON_RUN_DATE", datetime.now().strftime("%Y%m%d"))
RUN_ID = os.getenv("AMAZON_BSR_RUN_ID", "bsr")
RUN_ROOT = Path(os.getenv("AMAZON_RUN_ROOT", str(DEFAULT_AMAZON_RUN_ROOT))) / RUN_ID
INPUT_CSV = Path(os.getenv("AMAZON_BSR_INPUT", RUN_ROOT / "parsed" / "main_occurrences.csv"))
OUTPUT_CSV = Path(os.getenv("AMAZON_BSR_OUTPUT", RUN_ROOT / "parsed" / "bsr_rank_map.csv"))
TARGET_LIMIT = int(os.getenv("AMAZON_BSR_TARGET_LIMIT", "100"))


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


def build_rank_rows(rows):
    output = []
    seen = set()
    sorted_rows = sorted(
        rows,
        key=lambda row: (
            numeric(row.get("bsr_rank")),
            numeric(row.get("page")),
            numeric(row.get("rank_in_page")),
        ),
    )
    for row in sorted_rows:
        asin = str(row.get("asin") or row.get("sku_id") or "").strip()
        if not asin or asin in seen:
            continue
        seen.add(asin)
        out = dict(row)
        out["asin"] = asin
        out["sku_id"] = asin
        out["bsr_rank"] = len(output) + 1
        output.append(out)
        if len(output) >= TARGET_LIMIT:
            break
    return output


def write_csv(path, rows):
    preferred = [
        "bsr_rank",
        "source_page",
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
    output = build_rank_rows(rows)
    write_csv(OUTPUT_CSV, output)
    manifest = {
        "run_type": "step04_bsr_rank",
        "run_date": RUN_DATE,
        "run_root": rel_path(RUN_ROOT),
        "input_csv": rel_path(INPUT_CSV),
        "output_csv": rel_path(OUTPUT_CSV),
        "input_rows": len(rows),
        "target_limit": TARGET_LIMIT,
        "output_rows": len(output),
        "unique_asins": len({row.get("asin") for row in output if row.get("asin")}),
        "started_at": started_at,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
    }
    (RUN_ROOT / "manifest_bsr_rank.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
