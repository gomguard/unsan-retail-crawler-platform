import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SAMPLE_DIR = ROOT / "sample_csv"


def default_unsan_root():
    candidates = [
        ROOT,
        ROOT.parent,
        ROOT.parent / "unsan-retail-crawler-platform",
        ROOT.parent.parent / "unsan-retail-crawler-platform",
    ]
    for path in candidates:
        if (path / "bestbuy").is_dir() and (path / "common_settings").is_dir():
            return path
    return ROOT.parent / "unsan-retail-crawler-platform"


UNSAN_ROOT = default_unsan_root()

BSIN_RE = re.compile(r"/product/[^/]+/([^/?#]+)(?:/sku/\d+)?(?:[?#].*)?$")
SKU_RE = re.compile(r"/sku/(\d+)")


def latest_file(pattern):
    files = sorted(SAMPLE_DIR.glob(pattern), key=lambda path: path.stat().st_mtime, reverse=True)
    if not files:
        raise FileNotFoundError(f"No sample file found: {SAMPLE_DIR / pattern}")
    return files[0]


def read_csv(path):
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader), list(reader.fieldnames or [])


def write_csv(path, rows, fields):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def bsin_from_url(url):
    match = BSIN_RE.search(str(url or "").strip())
    return match.group(1).strip() if match else ""


def sku_from_url(url):
    match = SKU_RE.search(str(url or "").strip())
    return match.group(1).strip() if match else ""


def is_bestbuy(row):
    return str(row.get("account_name") or "").strip().lower() == "bestbuy"


def select_rows(rows, mode, category):
    detail_fields = {
        "TV": ["count_of_reviews", "star_rating", "detailed_review_content", "screen_size", "final_sku_price"],
        "HHP": ["count_of_reviews", "star_rating", "detailed_review_content", "hhp_storage", "hhp_color"],
    }[category]
    selected = []
    for row in rows:
        if not is_bestbuy(row):
            continue
        if mode == "all-bestbuy":
            selected.append(row)
        elif mode == "missing-detail":
            if any(not str(row.get(field) or "").strip() for field in detail_fields):
                selected.append(row)
        else:
            if not str(row.get("item") or "").strip():
                selected.append(row)
    return selected


def target_row(row, category):
    url = str(row.get("product_url") or "").strip()
    bsin = str(row.get("item") or "").strip() or bsin_from_url(url)
    sku = sku_from_url(url) or bsin
    return {
        "sku_id": sku,
        "bsin": bsin,
        "category_key": category,
        "product_url": url,
        "product_name": row.get("retailer_sku_name", ""),
        "retailer_sku_name": row.get("retailer_sku_name", ""),
        "target_source": row.get("page_type", ""),
        "page_type": row.get("page_type", ""),
        "main_rank": row.get("main_rank", ""),
        "bsr_rank": row.get("bsr_rank", ""),
        "trend_rank": row.get("trend_rank", ""),
        "promotion_position": row.get("promotion_position", ""),
        "promotion_type": row.get("promotion_type", ""),
        "review_count": row.get("count_of_reviews", ""),
        "rating": row.get("star_rating", ""),
        "customer_price": row.get("final_sku_price", ""),
        "regular_price": row.get("original_sku_price", ""),
        "total_savings": row.get("savings", ""),
        "offer_count": row.get("offer", ""),
        "is_sponsored": "1" if str(row.get("sku_status") or "").strip().lower() == "sponsored" else "",
    }


def write_schema(path, fields):
    write_csv(path, [], fields)


def patch_unsan_detail(enrich):
    original_event_data = enrich.event_data

    def products_from_detail_allow_bsin(sku):
        products = []
        variations = []
        sku_text = str(sku or "").strip()
        for payload in enrich.detail_payloads(sku):
            for event in payload.get("events", []):
                data = original_event_data(event)
                product = data.get("productBySkuId") if isinstance(data, dict) else None
                if isinstance(product, dict):
                    product_sku = str(product.get("skuId") or "").strip()
                    product_bsin = str(product.get("bsin") or "").strip()
                    if product_sku == sku_text or product_bsin == sku_text or not sku_text.isdigit():
                        products.append(product)
                bsin_product = data.get("bsinProduct") if isinstance(data, dict) else None
                if isinstance(bsin_product, dict):
                    variation_display = bsin_product.get("productVariationDetailDisplay") or {}
                    items = variation_display.get("productBsinVariations", []) or []
                    for item in items:
                        name = (
                            (((item.get("bsinProduct") or {}).get("featuredSKU") or {}).get("product") or {})
                            .get("name", {})
                            .get("short")
                        )
                        if name and name not in variations:
                            variations.append(name)
        return products, variations

    enrich.products_from_detail = products_from_detail_allow_bsin


def run_unsan_detail(category, run_root, target_csv, schema_csv, enriched_csv, unsan_root, workers):
    env = os.environ
    env["BESTBUY_CATEGORY"] = category
    env["BESTBUY_RUN_DATE"] = datetime.now().strftime("%Y%m%d")
    env["BESTBUY_RUN_ROOT"] = str(run_root)
    env["BESTBUY_DETAIL_TARGET_CSV"] = str(target_csv)
    env["BESTBUY_OUTPUT_SCHEMA_CSV"] = str(schema_csv)
    env["BESTBUY_FINAL_OUTPUT_CSV"] = str(enriched_csv)
    env.setdefault("BESTBUY_DETAIL_STAGE", "all")
    env.setdefault("BESTBUY_DETAIL_WORKERS", str(workers))
    env.setdefault("BESTBUY_SAVE_HTML_MODE", "slim")

    sys.path.insert(0, str(unsan_root))
    import bestbuy.step08_detail_enrichment as enrich

    patch_unsan_detail(enrich)
    enrich.main()


def merge_enriched(source_rows, selected_rows, enriched_rows, fields, overwrite):
    protected = {"id", "account_name", "page_type", "batch_id", "calendar_week"}
    for row in source_rows:
        if is_bestbuy(row) and not str(row.get("item") or "").strip():
            row["item"] = bsin_from_url(row.get("product_url"))

    for source, enriched in zip(selected_rows, enriched_rows):
        if not str(source.get("item") or "").strip():
            source["item"] = bsin_from_url(source.get("product_url")) or enriched.get("item", "")
        for field in fields:
            if field in protected:
                continue
            value = enriched.get(field, "")
            if value in ("", None):
                continue
            if overwrite or not str(source.get(field) or "").strip():
                source[field] = value


def run_category(
    category,
    final_pattern,
    product_pattern,
    output_dir,
    final_table,
    product_table,
    load_db_func,
):
    parser = argparse.ArgumentParser(description=f"Collect missing BestBuy {category} detail rows via Unsan.")
    parser.add_argument("--source-final-csv", default=str(latest_file(final_pattern)))
    parser.add_argument("--source-product-list-csv", default=str(latest_file(product_pattern)))
    parser.add_argument("--unsan-root", default=str(UNSAN_ROOT))
    parser.add_argument("--mode", choices=["item-null", "missing-detail", "all-bestbuy"], default="item-null")
    parser.add_argument("--include-all-retailers", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--load-db", action="store_true")
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()

    output_dir = Path(output_dir)
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    run_root = output_dir / "runs" / stamp
    run_output = run_root / "output"
    run_output.mkdir(parents=True, exist_ok=True)

    rows, fields = read_csv(args.source_final_csv)
    product_rows, product_fields = read_csv(args.source_product_list_csv)
    selected = select_rows(rows, args.mode, category)
    targets = [target_row(row, category) for row in selected if row.get("product_url")]

    target_csv = run_output / f"{category.lower()}_targets.csv"
    schema_csv = run_output / f"{category.lower()}_schema.csv"
    enriched_csv = run_output / f"{category.lower()}_enriched_missing.csv"
    final_out = output_dir / f"{category.lower()}_retail_com_bestbuy_collected_{stamp}.csv"
    product_out = output_dir / f"bby_{category.lower()}_product_list_{stamp}.csv"
    manifest_path = output_dir / f"{category.lower()}_collect_manifest_{stamp}.json"

    target_fields = [
        "sku_id", "bsin", "category_key", "product_url", "product_name", "retailer_sku_name",
        "target_source", "page_type", "main_rank", "bsr_rank", "trend_rank",
        "promotion_position", "promotion_type", "review_count", "rating", "customer_price",
        "regular_price", "total_savings", "offer_count", "is_sponsored",
    ]
    write_csv(target_csv, targets, target_fields)
    write_schema(schema_csv, fields)

    if not args.prepare_only and targets:
        run_unsan_detail(
            category=category,
            run_root=run_root,
            target_csv=target_csv,
            schema_csv=schema_csv,
            enriched_csv=enriched_csv,
            unsan_root=Path(args.unsan_root),
            workers=args.workers,
        )
    elif not enriched_csv.exists():
        write_csv(enriched_csv, [], fields)

    enriched_rows, _ = read_csv(enriched_csv)
    merge_enriched(rows, selected, enriched_rows, fields, args.overwrite)

    output_rows = rows if args.include_all_retailers else [row for row in rows if is_bestbuy(row)]
    write_csv(final_out, output_rows, fields)
    write_csv(product_out, product_rows, product_fields)

    load_result = None
    if args.load_db:
        load_result = load_db_func(final_out, product_out)

    manifest = {
        "category": category,
        "source_final_csv": str(Path(args.source_final_csv).resolve()),
        "source_product_list_csv": str(Path(args.source_product_list_csv).resolve()),
        "mode": args.mode,
        "include_all_retailers": args.include_all_retailers,
        "selected_bestbuy_rows": len(selected),
        "target_rows": len(targets),
        "enriched_rows": len(enriched_rows),
        "output_final_csv": str(final_out.resolve()),
        "output_product_list_csv": str(product_out.resolve()),
        "target_csv": str(target_csv.resolve()),
        "schema_csv": str(schema_csv.resolve()),
        "enriched_csv": str(enriched_csv.resolve()),
        "final_table": final_table,
        "product_list_table": product_table,
        "load_db": load_result,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
