import csv
import json
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from .step00_config import DEFAULT_BESTBUY_RUN_ROOT, KRW_PER_USD, bestbuy_category, old_pdp_url, rel_path

RUN_DATE = os.getenv("BESTBUY_RUN_DATE", datetime.now().strftime("%Y%m%d"))
MAIN_RUN_ID = os.getenv("BESTBUY_FINAL_MAIN_RUN_ID", "main")
BSR_RUN_ID = os.getenv("BESTBUY_FINAL_BSR_RUN_ID", "bsr")
RUN_ROOT = Path(os.getenv("BESTBUY_RUN_ROOT", DEFAULT_BESTBUY_RUN_ROOT))
MAIN_ROOT = RUN_ROOT / MAIN_RUN_ID
BSR_ROOT = RUN_ROOT / BSR_RUN_ID
OUTPUT_ROOT = Path(os.getenv("BESTBUY_OUTPUT_ROOT", RUN_ROOT / "output"))

MAIN_INPUT = Path(
    os.getenv("BESTBUY_FINAL_MAIN_INPUT", MAIN_ROOT / "parsed" / "main_target_occurrences.csv")
)
BSR_INPUT = Path(os.getenv("BESTBUY_FINAL_BSR_INPUT", BSR_ROOT / "parsed" / "bsr_rank_map.csv"))
PROMOTION_INPUT = Path(
    os.getenv(
        "BESTBUY_FINAL_PROMOTION_INPUT",
        RUN_ROOT / "promotion" / "parsed" / "all_promotion_products.csv",
    )
)
TRENDING_INPUT = Path(
    os.getenv(
        "BESTBUY_FINAL_TRENDING_INPUT",
        RUN_ROOT / "trending" / "parsed" / "trending_products.csv",
    )
)
OUTPUT_CSV = Path(
    os.getenv("BESTBUY_FINAL_TARGET_OUTPUT", OUTPUT_ROOT / "bestbuy_final_targets.csv")
)
PRODUCT_LIST_CSV = Path(
    os.getenv("BESTBUY_PRODUCT_LIST_OUTPUT", OUTPUT_ROOT / "bestbuy_product_list.csv")
)
TARGET_SIZE = int(os.getenv("BESTBUY_FINAL_TARGET_SIZE", "300"))
CATEGORY = bestbuy_category()

PROMOTION_FALLBACK_INPUT = (
    RUN_ROOT / "promotion" / "parsed" / "all_promotion_products.csv"
)
TRENDING_FALLBACK_INPUT = (
    RUN_ROOT / "trending" / "parsed" / "trending_products.csv"
)


def now():
    return datetime.now().isoformat(timespec="seconds")


def load_rows(path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def existing_path(primary, fallback):
    return primary if primary.exists() else fallback


def int_value(value, default=999999):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def first_non_empty(*values):
    for value in values:
        if value not in ("", None):
            return value
    return ""


def unique_main_rows(rows):
    sorted_rows = sorted(
        rows,
        key=lambda row: (
            int_value(row.get("global_visual_rank")),
            int_value(row.get("page")),
            int_value(row.get("visual_rank")),
        ),
    )
    seen = set()
    output = []
    for row in sorted_rows:
        sku = str(row.get("sku_id") or "").strip()
        if not sku or sku in seen:
            continue
        seen.add(sku)
        out = dict(row)
        out["main_rank"] = len(output) + 1
        out["target_source"] = "main"
        output.append(out)
    return output


def main_attribute_map(rows):
    attrs = {}
    sorted_rows = sorted(
        rows,
        key=lambda row: (
            0 if row.get("container_type") == "organic_product" else 1,
            int_value(row.get("global_visual_rank")),
            int_value(row.get("page")),
            int_value(row.get("visual_rank")),
        ),
    )
    fill_keys = [
        "bsin",
        "brand",
        "product_name",
        "product_url",
        "image_url",
        "rating",
        "review_count",
        "customer_price",
        "regular_price",
        "total_savings",
        "total_savings_percent",
        "buying_options_json",
        "is_reviewable",
        "syndicated_review_summary_json",
    ]
    for row in sorted_rows:
        sku = str(row.get("sku_id") or "").strip()
        if not sku:
            continue
        target = attrs.setdefault(sku, {})
        for key in fill_keys:
            if not target.get(key) and row.get(key):
                target[key] = row.get(key)
    return attrs


def build_bsr_map(rows):
    result = {}
    sorted_rows = sorted(rows, key=lambda row: int_value(row.get("bsr_rank")))
    for row in sorted_rows:
        sku = str(row.get("sku_id") or "").strip()
        if sku and sku not in result:
            result[sku] = dict(row)
    return result


def bsr_page_map(rows):
    result = {}
    for row in rows:
        sku = str(row.get("sku_id") or "").strip()
        if sku and sku not in result:
            result[sku] = row.get("source_page", "")
    return result


def promotion_map(rows):
    grouped = defaultdict(list)
    for row in rows:
        sku = str(row.get("sku_id") or "").strip()
        promo = str(row.get("promotion_type") or "").strip()
        if not sku or not promo:
            continue
        position = str(row.get("promotion_position") or "").strip()
        grouped[sku].append((promo, position))

    result = {}
    for sku, values in grouped.items():
        deduped = []
        seen = set()
        for promo, position in values:
            key = (promo, position)
            if key in seen:
                continue
            seen.add(key)
            deduped.append((promo, position))
        result[sku] = {
            "promotion_type": " ||| ".join(promo for promo, _ in deduped),
            "promotion_position": " ||| ".join(position for _, position in deduped if position),
            "promotion_detail": " ||| ".join(
                f"{promo}:{position}" if position else promo for promo, position in deduped
            ),
        }
    return result


def trending_map(rows):
    result = {}
    for row in sorted(rows, key=lambda item: int_value(item.get("trend_rank"))):
        sku = str(row.get("sku_id") or "").strip()
        if sku and sku not in result:
            result[sku] = dict(row)
    return result


def choose_final_rows(main_rows, bsr_rows, target_size):
    bsr = build_bsr_map(bsr_rows)
    main_by_sku = {str(row.get("sku_id")): row for row in main_rows if row.get("sku_id")}
    bsr_only = [row for sku, row in bsr.items() if sku not in main_by_sku]

    if len(main_rows) >= target_size:
        keep_main_count = max(0, target_size - len(bsr_only))
        final_rows = main_rows[:keep_main_count]
        for bsr_row in bsr_only[: target_size - len(final_rows)]:
            final_rows.append(row_from_bsr_only(bsr_row))
    else:
        final_rows = list(main_rows)
        for bsr_row in bsr_only:
            if len(final_rows) >= target_size:
                break
            final_rows.append(row_from_bsr_only(bsr_row))

    return final_rows, bsr


def row_from_bsr_only(row):
    sku = str(row.get("sku_id") or "").strip()
    output = {
        "sku_id": sku,
        "bsin": row.get("bsin", ""),
        "product_name": row.get("product_name", ""),
        "product_url": row.get("product_url", ""),
        "main_rank": "",
        "target_source": "bsr_only_backfill",
    }
    for key, value in row.items():
        if key not in output:
            output[key] = value
    return output


def enrich_rows(rows, bsr, promotions, trends, main_attrs):
    output = []
    for index, row in enumerate(rows, 1):
        sku = str(row.get("sku_id") or "").strip()
        out = dict(row)
        out["category_key"] = first_non_empty(out.get("category_key"), CATEGORY)
        out["final_target_rank"] = index
        out["sku_id"] = sku
        out["detail_url"] = old_pdp_url(sku) if sku else ""
        out["bsr_rank"] = (bsr.get(sku) or {}).get("bsr_rank", "")
        out["promotion_type"] = (promotions.get(sku) or {}).get("promotion_type", "")
        out["promotion_position"] = (promotions.get(sku) or {}).get("promotion_position", "")
        out["trend_rank"] = (trends.get(sku) or {}).get("trend_rank", "")
        attrs = main_attrs.get(sku) or {}
        for key, value in attrs.items():
            out[key] = first_non_empty(out.get(key), value)
        bsr_attrs = bsr.get(sku) or {}
        for key, value in bsr_attrs.items():
            out[key] = first_non_empty(out.get(key), value)
        out["product_name"] = first_non_empty(out.get("product_name"), bsr_attrs.get("product_name"))
        out["product_url"] = first_non_empty(out.get("product_url"), bsr_attrs.get("product_url"))
        output.append(out)
    return output


def write_csv(path, rows, preferred=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = set()
    for row in rows:
        keys.update(row)
    preferred = preferred or [
        "category_key",
        "final_target_rank",
        "target_source",
        "main_rank",
        "bsr_rank",
        "promotion_type",
        "promotion_position",
        "trend_rank",
        "sku_id",
        "bsin",
        "brand",
        "product_name",
        "product_url",
        "detail_url",
        "container_type",
        "is_sponsored",
        "page",
        "visual_rank",
        "global_visual_rank",
        "organic_rank",
        "global_organic_rank",
        "placement_name",
        "sponsored_rank",
        "rating",
        "review_count",
        "customer_price",
        "regular_price",
        "total_savings",
        "offer_count",
    ]
    fieldnames = [key for key in preferred if key in keys]
    fieldnames.extend(sorted(keys - set(fieldnames)))
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def money(value):
    if value in ("", None):
        return ""
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value)


def money_int(value):
    if value in ("", None):
        return ""
    try:
        return f"${int(round(float(value))):,}"
    except (TypeError, ValueError):
        return str(value)


def int_or_empty(value):
    try:
        return str(int(str(value).split("|||", 1)[0].strip()))
    except (TypeError, ValueError):
        return ""


def calendar_week():
    return f"w{datetime.now().isocalendar().week}"


def batch_id_from_datetime(value):
    return f"b_{value.strftime('%Y%m%d_%H%M%S')}"


def page_type(row):
    return "bsr" if row.get("target_source") == "bsr_only_backfill" else "main"


def product_list_rows(rows, bsr_pages):
    crawl_dt_obj = datetime.now()
    crawl_dt = crawl_dt_obj.strftime("%Y-%m-%d %H:%M")
    batch_id = batch_id_from_datetime(crawl_dt_obj)
    output = []
    for row in rows:
        sku = str(row.get("sku_id") or "").strip()
        common = {
            "account_name": "Bestbuy",
            "page_type": page_type(row),
            "retailer_sku_name": row.get("product_name", ""),
            "offer": row.get("offer_count", ""),
            "pick_up_availability": row.get("pick_up_availability", ""),
            "fastest_delivery": row.get("fastest_delivery", ""),
            "delivery_availability": row.get("delivery_availability", ""),
            "sku_status": "Sponsored" if row.get("is_sponsored") in {"1", "true", "True"} else "",
            "promotion_type": row.get("promotion_type", ""),
            "trend_rank": row.get("trend_rank", ""),
            "main_rank": row.get("main_rank", ""),
            "bsr_rank": row.get("bsr_rank", ""),
            "product_url": row.get("product_url", ""),
            "calendar_week": calendar_week(),
            "batch_id": batch_id,
            "main_page_number": row.get("page", "") if row.get("main_rank") else "",
            "bsr_page_number": bsr_pages.get(sku, ""),
            "sku_id": sku,
            "category_key": row.get("category_key", CATEGORY),
            "final_target_rank": row.get("final_target_rank", ""),
        }
        if CATEGORY == "TV":
            common["crawl_datetime"] = crawl_dt
            common["promotion_position"] = int_or_empty(row.get("promotion_position", ""))
        else:
            common["final_sku_price"] = money(row.get("customer_price"))
            common["savings"] = money_int(row.get("total_savings"))
            common["comparable_pricing"] = money(row.get("regular_price"))
            common["crawl_strdatetime"] = crawl_dt
        output.append(common)
    return output


def product_list_fields():
    if CATEGORY == "TV":
        return [
            "account_name",
            "page_type",
            "retailer_sku_name",
            "offer",
            "pick_up_availability",
            "fastest_delivery",
            "delivery_availability",
            "sku_status",
            "promotion_type",
            "trend_rank",
            "main_rank",
            "bsr_rank",
            "product_url",
            "calendar_week",
            "crawl_datetime",
            "batch_id",
            "main_page_number",
            "bsr_page_number",
            "promotion_position",
            "sku_id",
            "category_key",
            "final_target_rank",
        ]
    return [
        "account_name",
        "page_type",
        "retailer_sku_name",
        "final_sku_price",
        "savings",
        "comparable_pricing",
        "offer",
        "pick_up_availability",
        "fastest_delivery",
        "delivery_availability",
        "sku_status",
        "promotion_type",
        "trend_rank",
        "main_rank",
        "bsr_rank",
        "product_url",
        "calendar_week",
        "crawl_strdatetime",
        "batch_id",
        "main_page_number",
        "bsr_page_number",
        "sku_id",
        "category_key",
        "final_target_rank",
    ]


def main():
    started_at = now()
    main_input_rows = load_rows(MAIN_INPUT)
    bsr_rows = load_rows(BSR_INPUT)
    promotion_input = existing_path(PROMOTION_INPUT, PROMOTION_FALLBACK_INPUT)
    trending_input = existing_path(TRENDING_INPUT, TRENDING_FALLBACK_INPUT)
    promotion_rows = load_rows(promotion_input)
    trending_rows = load_rows(trending_input)

    main_rows = unique_main_rows(main_input_rows)
    selected_rows, bsr = choose_final_rows(main_rows, bsr_rows, TARGET_SIZE)
    final_rows = enrich_rows(
        selected_rows,
        bsr,
        promotion_map(promotion_rows),
        trending_map(trending_rows),
        main_attribute_map(main_input_rows),
    )
    write_csv(OUTPUT_CSV, final_rows)
    listing_rows = product_list_rows(final_rows, bsr_page_map(bsr_rows))
    write_csv(PRODUCT_LIST_CSV, listing_rows, product_list_fields())

    manifest = {
        "run_type": "step07_final_targets",
        "started_at": started_at,
        "finished_at": now(),
        "target_size": TARGET_SIZE,
        "main_input": rel_path(MAIN_INPUT),
        "bsr_input": rel_path(BSR_INPUT),
        "promotion_input": rel_path(promotion_input),
        "trending_input": rel_path(trending_input),
        "output_csv": rel_path(OUTPUT_CSV),
        "product_list_csv": rel_path(PRODUCT_LIST_CSV),
        "main_unique_count": len(main_rows),
        "bsr_count": len(bsr),
        "promotion_unique_count": len({row.get("sku_id") for row in promotion_rows if row.get("sku_id")}),
        "trending_unique_count": len({row.get("sku_id") for row in trending_rows if row.get("sku_id")}),
        "final_row_count": len(final_rows),
        "final_unique_sku_count": len({row.get("sku_id") for row in final_rows if row.get("sku_id")}),
        "product_list_row_count": len(listing_rows),
        "needs_more_main_candidates": len(final_rows) < TARGET_SIZE,
        "krw_per_usd": KRW_PER_USD,
    }
    manifest_path = OUTPUT_CSV.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"output={OUTPUT_CSV}")
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
