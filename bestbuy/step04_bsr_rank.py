import csv
import json
import os
from datetime import datetime
from pathlib import Path

from .step00_config import DEFAULT_BESTBUY_RUN_ROOT, rel_path

RUN_DATE = os.getenv("BESTBUY_RUN_DATE", datetime.now().strftime("%Y%m%d"))
RUN_ROOT = Path(os.getenv("BESTBUY_RUN_ROOT", DEFAULT_BESTBUY_RUN_ROOT)) / os.getenv("BESTBUY_BSR_RUN_ID", "bsr")
INPUT_CSV = Path(os.getenv("BESTBUY_BSR_INPUT", RUN_ROOT / "parsed" / "main_occurrences.csv"))
OUTPUT_CSV = Path(os.getenv("BESTBUY_BSR_OUTPUT", RUN_ROOT / "parsed" / "bsr_rank_map.csv"))
LIMIT = int(os.getenv("BESTBUY_BSR_LIMIT", "100"))


def load_rows(path):
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def main():
    rows = load_rows(INPUT_CSV)
    organic = [row for row in rows if row.get("container_type") == "organic_product"]
    organic.sort(key=lambda row: int(row.get("global_organic_rank") or row.get("visual_rank") or 999999))
    carry_fields = [
        "category_key",
        "brand",
        "image_url",
        "rating",
        "review_count",
        "customer_price",
        "regular_price",
        "total_savings",
        "total_savings_percent",
        "shipping_eligible",
        "pickup_eligible",
        "offer_count",
        "buying_options_json",
        "deal_expiration",
        "is_reviewable",
        "pickup_quantity",
        "restricted_price_message",
        "syndicated_review_summary_json",
    ]
    seen = set()
    output = []
    for row in organic:
        sku = str(row.get("sku_id") or "").strip()
        if not sku or sku in seen:
            continue
        seen.add(sku)
        rank = len(output) + 1
        item = {
            "sku_id": sku,
            "bsin": row.get("bsin", ""),
            "product_name": row.get("product_name", ""),
            "product_url": row.get("product_url", ""),
            "bsr_rank": rank,
            "source_page": row.get("page", ""),
            "source_global_organic_rank": row.get("global_organic_rank", ""),
        }
        for field in carry_fields:
            item[field] = row.get(field, "")
        output.append(item)
        if rank >= LIMIT:
            break

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "sku_id",
        "bsin",
        "product_name",
        "product_url",
        "bsr_rank",
        "source_page",
        "source_global_organic_rank",
        *carry_fields,
    ]
    with OUTPUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(output)

    manifest = {
        "run_type": "step04_bsr_rank",
        "input_csv": rel_path(INPUT_CSV),
        "output_csv": rel_path(OUTPUT_CSV),
        "limit": LIMIT,
        "input_organic_rows": len(organic),
        "output_rows": len(output),
    }
    manifest_path = RUN_ROOT / "manifest_bsr_rank.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"output={OUTPUT_CSV}")
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
