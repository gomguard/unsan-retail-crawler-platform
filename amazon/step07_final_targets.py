import csv
import json
import os
import re
from datetime import datetime
from pathlib import Path

from .step00_config import CONFIG_DIR, DEFAULT_AMAZON_RUN_ROOT, amazon_product_type, rel_path


RUN_DATE = os.getenv("AMAZON_RUN_DATE", datetime.now().strftime("%Y%m%d"))
RUN_ROOT = Path(os.getenv("AMAZON_RUN_ROOT", str(DEFAULT_AMAZON_RUN_ROOT)))
MAIN_RUN_ID = os.getenv("AMAZON_MAIN_RUN_ID", "main")
BSR_RUN_ID = os.getenv("AMAZON_BSR_RUN_ID", "bsr")
MAIN_ROOT = RUN_ROOT / MAIN_RUN_ID
BSR_ROOT = RUN_ROOT / BSR_RUN_ID
OUTPUT_ROOT = Path(os.getenv("AMAZON_OUTPUT_ROOT", RUN_ROOT / "output"))
MAIN_INPUT = Path(os.getenv("AMAZON_FINAL_MAIN_INPUT", MAIN_ROOT / "parsed" / "main_target_occurrences.csv"))
BSR_INPUT = Path(os.getenv("AMAZON_FINAL_BSR_INPUT", BSR_ROOT / "parsed" / "bsr_rank_map.csv"))
OUTPUT_CSV = Path(os.getenv("AMAZON_FINAL_TARGET_OUTPUT", OUTPUT_ROOT / "amazon_final_targets.csv"))
PRODUCT_LIST_CSV = Path(os.getenv("AMAZON_PRODUCT_LIST_OUTPUT", OUTPUT_ROOT / "amazon_product_list.csv"))
EXCLUDED_CSV = Path(os.getenv("AMAZON_FINAL_EXCLUDED_OUTPUT", OUTPUT_ROOT / "amazon_final_targets_excluded.csv"))
DETAIL_INPUT = Path(os.getenv("AMAZON_DETAIL_INPUT", RUN_ROOT / "detail" / "parsed" / "detail_map.csv"))
TARGET_SIZE = int(os.getenv("AMAZON_FINAL_TARGET_SIZE", "300"))
HHP_ACCESSORY_BANLIST = Path(os.getenv("AMAZON_HHP_ACCESSORY_BANLIST", CONFIG_DIR / "hhp_accessory_banlist.txt"))

HHP_PHONE_INCLUDE_RE = re.compile(
    r"\b("
    r"smartphone|cell phone|cellphone|mobile phone|phone|unlocked|locked|renewed|"
    r"5g|4g lte|lte|android phone|iphone|galaxy|pixel|motorola|moto g|oneplus|nokia|tcl|samsung"
    r")\b",
    re.I,
)

def load_regex_list(path):
    if not path.exists():
        return []
    patterns = []
    for line in path.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        patterns.append(re.compile(value, re.I))
    return patterns


HHP_ACCESSORY_PATTERNS = load_regex_list(HHP_ACCESSORY_BANLIST)


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


def first_non_empty(*values):
    for value in values:
        if value not in ("", None):
            return value
    return ""


def is_hhp():
    return amazon_product_type().lower() == "hhp"


def unique_main_rows(rows):
    output = []
    seen = set()
    sorted_rows = sorted(rows, key=lambda row: (numeric(row.get("target_rank")), numeric(row.get("main_rank"))))
    for row in sorted_rows:
        asin = str(row.get("asin") or row.get("sku_id") or "").strip()
        if not asin or asin in seen:
            continue
        seen.add(asin)
        out = dict(row)
        out["asin"] = asin
        out["sku_id"] = asin
        out["main_rank"] = out.get("main_rank") or len(output) + 1
        out["target_source"] = "main"
        output.append(out)
    return output


def bsr_map(rows):
    result = {}
    for row in sorted(rows, key=lambda item: numeric(item.get("bsr_rank"))):
        asin = str(row.get("asin") or row.get("sku_id") or "").strip()
        if asin and asin not in result:
            result[asin] = dict(row)
    return result


def detail_map(rows):
    result = {}
    for row in rows:
        asin = str(row.get("asin") or row.get("sku_id") or "").strip()
        if asin and asin not in result:
            result[asin] = dict(row)
    return result


def row_from_bsr_only(row):
    asin = str(row.get("asin") or row.get("sku_id") or "").strip()
    return {
        "asin": asin,
        "sku_id": asin,
        "brand": row.get("brand", ""),
        "product_name": row.get("product_name", ""),
        "product_url": row.get("product_url", ""),
        "detail_url": row.get("detail_url", ""),
        "image_url": row.get("image_url", ""),
        "rating": row.get("rating", ""),
        "review_count": row.get("review_count", ""),
        "customer_price": row.get("customer_price", ""),
        "main_rank": "",
        "target_source": "bsr_only_backfill",
    }


def merged_row(row, bsr_row, detail_row=None):
    out = dict(row)
    detail_row = detail_row or {}
    for key in ["brand", "product_name", "product_url", "detail_url", "image_url", "rating", "review_count", "customer_price"]:
        out[key] = first_non_empty(out.get(key), bsr_row.get(key), detail_row.get(key))
    return out


def hhp_exclusion_reason(row):
    if not is_hhp():
        return ""
    name = str(row.get("product_name") or "").strip()
    if not name:
        return "missing_product_name_needs_enrichment"
    if any(pattern.search(name) for pattern in HHP_ACCESSORY_PATTERNS):
        return "hhp_accessory_keyword"
    if not HHP_PHONE_INCLUDE_RE.search(name):
        return "hhp_not_phone_like"
    return ""


def choose_hhp_final_rows(main_rows, bsr_rows, bsr, details):
    main_by_asin = {row["asin"]: row for row in main_rows if row.get("asin")}
    bsr_only = [row for asin, row in bsr.items() if asin not in main_by_asin]
    candidates = list(main_rows)
    candidates.extend(row_from_bsr_only(row) for row in bsr_only)

    selected = []
    excluded = []
    seen = set()
    for row in candidates:
        asin = str(row.get("asin") or row.get("sku_id") or "").strip()
        if not asin or asin in seen:
            continue
        bsr_row = bsr.get(asin) or {}
        check_row = merged_row(row, bsr_row, details.get(asin))
        reason = hhp_exclusion_reason(check_row)
        if reason:
            excluded_row = dict(check_row)
            excluded_row["asin"] = asin
            excluded_row["sku_id"] = asin
            excluded_row["exclusion_reason"] = reason
            excluded_row["bsr_rank"] = bsr_row.get("bsr_rank", "")
            excluded.append(excluded_row)
            seen.add(asin)
            continue
        selected.append(row)
        seen.add(asin)
        if len(selected) >= TARGET_SIZE:
            break
    return selected, excluded


def choose_final_rows(main_rows, bsr_rows, details):
    bsr = bsr_map(bsr_rows)
    if is_hhp():
        final_rows, excluded_rows = choose_hhp_final_rows(main_rows, bsr_rows, bsr, details)
        return final_rows, bsr, excluded_rows

    main_by_asin = {row["asin"]: row for row in main_rows if row.get("asin")}
    bsr_only = [row for asin, row in bsr.items() if asin not in main_by_asin]

    if len(main_rows) >= TARGET_SIZE:
        keep_main_count = max(0, TARGET_SIZE - len(bsr_only))
        final_rows = main_rows[:keep_main_count]
        final_rows.extend(row_from_bsr_only(row) for row in bsr_only[: TARGET_SIZE - len(final_rows)])
    else:
        final_rows = list(main_rows)
        for row in bsr_only:
            if len(final_rows) >= TARGET_SIZE:
                break
            final_rows.append(row_from_bsr_only(row))
    return final_rows, bsr, []


def enrich_rows(rows, bsr, details):
    output = []
    for index, row in enumerate(rows, 1):
        asin = str(row.get("asin") or row.get("sku_id") or "").strip()
        bsr_row = bsr.get(asin) or {}
        out = dict(row)
        out["category_key"] = amazon_product_type().upper()
        out["final_target_rank"] = index
        out["asin"] = asin
        out["sku_id"] = asin
        out["bsr_rank"] = bsr_row.get("bsr_rank", "")
        out = merged_row(out, bsr_row, details.get(asin))
        output.append(out)
    return output


def write_csv(path, rows, preferred=None):
    preferred = preferred or [
        "category_key",
        "final_target_rank",
        "target_source",
        "target_rank",
        "main_rank",
        "bsr_rank",
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
        "page",
        "rank_in_page",
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


def product_list_rows(rows):
    crawl_dt = datetime.now().strftime("%Y-%m-%d %H:%M")
    output = []
    for row in rows:
        output.append(
            {
                "account_name": "Amazon",
                "page_type": "bsr" if row.get("target_source") == "bsr_only_backfill" else "main",
                "retailer_sku_name": row.get("product_name", ""),
                "final_sku_price": row.get("customer_price", ""),
                "sku_status": "Sponsored" if row.get("is_sponsored") in {"1", "true", "True"} else "",
                "main_rank": row.get("main_rank", ""),
                "bsr_rank": row.get("bsr_rank", ""),
                "product_url": row.get("product_url", ""),
                "crawl_strdatetime": crawl_dt,
                "batch_id": f"amazon_{RUN_DATE}",
                "main_page_number": row.get("page", "") if row.get("main_rank") else "",
                "sku_id": row.get("sku_id", ""),
                "asin": row.get("asin", ""),
                "category_key": row.get("category_key", amazon_product_type().upper()),
                "final_target_rank": row.get("final_target_rank", ""),
            }
        )
    return output


def main():
    started_at = datetime.now().isoformat(timespec="seconds")
    raw_main_rows = read_csv(MAIN_INPUT)
    if is_hhp():
        raw_main_rows.extend(read_csv(MAIN_ROOT / "parsed" / "main_occurrences.csv"))
    main_rows = unique_main_rows(raw_main_rows)
    bsr_rows = read_csv(BSR_INPUT)
    details = detail_map(read_csv(DETAIL_INPUT))
    selected_rows, bsr, excluded_rows = choose_final_rows(main_rows, bsr_rows, details)
    final_rows = enrich_rows(selected_rows, bsr, details)
    write_csv(OUTPUT_CSV, final_rows)
    write_csv(EXCLUDED_CSV, excluded_rows)
    listing_rows = product_list_rows(final_rows)
    write_csv(PRODUCT_LIST_CSV, listing_rows)
    manifest = {
        "run_type": "step07_final_targets",
        "run_date": RUN_DATE,
        "run_root": rel_path(RUN_ROOT),
        "main_input": rel_path(MAIN_INPUT),
        "bsr_input": rel_path(BSR_INPUT),
        "detail_input": rel_path(DETAIL_INPUT),
        "output_csv": rel_path(OUTPUT_CSV),
        "product_list_csv": rel_path(PRODUCT_LIST_CSV),
        "excluded_csv": rel_path(EXCLUDED_CSV),
        "target_size": TARGET_SIZE,
        "main_unique_count": len(main_rows),
        "bsr_count": len(bsr),
        "detail_count": len(details),
        "excluded_count": len(excluded_rows),
        "excluded_by_reason": {
            reason: sum(1 for row in excluded_rows if row.get("exclusion_reason") == reason)
            for reason in sorted({row.get("exclusion_reason") for row in excluded_rows})
        },
        "final_row_count": len(final_rows),
        "final_unique_asin_count": len({row.get("asin") for row in final_rows if row.get("asin")}),
        "product_list_row_count": len(listing_rows),
        "needs_more_main_candidates": len(final_rows) < TARGET_SIZE,
        "started_at": started_at,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
    }
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    (OUTPUT_ROOT / "amazon_final_targets.manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
