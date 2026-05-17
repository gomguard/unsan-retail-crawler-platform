import csv
import json
import re
import sys
from pathlib import Path

from .step00_parse_pdp import (
    absolute_bestbuy_url,
    compact_json,
    event_data,
    extract_apollo_payloads,
    nested_get,
)

DEFAULT_HTML_PATH = Path("references/bestbuy_main_search_page_sample.html")
DEFAULT_CSV_PATH = Path("bestbuy_search_parsed.csv")
DEFAULT_JSON_PATH = Path("bestbuy_search_raw_products.json")


def iter_dicts(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from iter_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_dicts(child)


def merge_dict(existing, incoming):
    for key, value in incoming.items():
        if value in (None, "", [], {}):
            continue
        current = existing.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merge_dict(current, value)
        elif current in (None, "", [], {}) or key == "price":
            existing[key] = value
        elif key not in existing:
            existing[key] = value


def search_documents(data):
    documents = nested_get(data, ["detailedProductSearch", "documents"], [])
    if isinstance(documents, list):
        return documents
    return []


def collect_search_products(payloads):
    products = {}
    occurrences = []
    raw_documents = []
    seen_occurrences = set()
    started_by_id = {}
    organic_rank_by_sku = {}

    for payload in payloads:
        for event in payload.get("events", []):
            if event.get("type") != "started":
                continue
            query = event.get("options", {}).get("query", "")
            query_name = ""
            if isinstance(query, str):
                match = re.search(r"query\s+([A-Za-z0-9_]+)", query)
                query_name = match.group(1) if match else ""
            variables = event.get("options", {}).get("variables", {})
            started_by_id[event.get("id", "")] = {
                "query_name": query_name,
                "variables": variables if isinstance(variables, dict) else {},
            }

    for payload in payloads:
        for event in payload.get("events", []):
            if event.get("type") not in {"next", "data"}:
                continue
            data = event_data(event)
            for rank, document in enumerate(search_documents(data), 1):
                product = document.get("product") if isinstance(document, dict) else None
                if not isinstance(product, dict) or not product.get("skuId"):
                    continue
                sku = str(product["skuId"])
                raw_documents.append(document)
                products.setdefault(sku, {})
                merge_dict(products[sku], product)
                organic_rank_by_sku.setdefault(sku, rank)
                occurrence_key = ("organic_product", sku, rank)
                if occurrence_key not in seen_occurrences:
                    seen_occurrences.add(occurrence_key)
                    occurrences.append(
                        {
                            "sku_id": sku,
                            "container_type": "organic_product",
                            "is_sponsored": False,
                            "organic_rank": rank,
                            "visual_rank": len(occurrences) + 1,
                            "placement": "detailedProductSearch.documents",
                            "source_event_id": event.get("id", ""),
                        }
                    )

            batch = data.get("batch0") if isinstance(data, dict) else None
            if isinstance(batch, list):
                for rank, product in enumerate(batch, 1):
                    if not isinstance(product, dict) or not product.get("skuId"):
                        continue
                    sku = str(product["skuId"])
                    products.setdefault(sku, {})
                    merge_dict(products[sku], product)
                    occurrence_key = ("sponsored_carousel", sku, event.get("id", ""))
                    if occurrence_key not in seen_occurrences:
                        seen_occurrences.add(occurrence_key)
                        occurrences.append(
                            {
                                "sku_id": sku,
                                "container_type": "sponsored_carousel",
                                "is_sponsored": True,
                                "organic_rank": "",
                                "visual_rank": len(occurrences) + 1,
                                "placement": "AdTech_NinjaCarousel_SkuDataQuery.batch0",
                                "source_event_id": event.get("id", ""),
                                "sponsored_rank": rank,
                            }
                        )

            for node in iter_dicts(data):
                if node.get("__typename") != "Product" or not node.get("skuId"):
                    continue
                if not isinstance(node.get("name"), dict) and not isinstance(node.get("price"), dict):
                    continue
                sku = str(node["skuId"])
                products.setdefault(sku, {})
                merge_dict(products[sku], node)
                if not isinstance(node.get("name"), dict):
                    continue

                started = started_by_id.get(event.get("id", ""), {})
                query_name = started.get("query_name", "")
                if query_name == "PlpView_ProductListItem_Init":
                    organic_rank = organic_rank_by_sku.get(sku)
                    if organic_rank is None:
                        organic_rank = 1 + max([0] + [rank for rank in organic_rank_by_sku.values() if isinstance(rank, int)])
                        organic_rank_by_sku[sku] = organic_rank
                    occurrence_key = ("organic_product", sku, organic_rank)
                    if occurrence_key not in seen_occurrences:
                        seen_occurrences.add(occurrence_key)
                        occurrences.append(
                            {
                                "sku_id": sku,
                                "container_type": "organic_product",
                                "is_sponsored": False,
                                "organic_rank": organic_rank,
                                "visual_rank": len(occurrences) + 1,
                                "placement": "PlpView_ProductListItem_Init",
                                "source_event_id": event.get("id", ""),
                            }
                        )
                elif query_name == "getProduct":
                    # These events hydrate cards that are already represented by
                    # sponsored carousel occurrences, so keep their product data
                    # without counting them as additional visible containers.
                    continue

    return products, occurrences, raw_documents


def price_value(price, *keys):
    if not isinstance(price, dict):
        return ""
    for key in keys:
        value = price.get(key)
        if value not in (None, ""):
            return value
    return ""


def parse_product(product, occurrence):
    price = product.get("price", {}) if isinstance(product.get("price"), dict) else {}
    review_info = product.get("reviewInfo", {}) if isinstance(product.get("reviewInfo"), dict) else {}
    primary_image = product.get("primaryImage", {}) if isinstance(product.get("primaryImage"), dict) else {}
    shipping = nested_get(product, ["fulfillmentOptions", "shippingDetails", "shippingAvailability"], {})
    pickup = nested_get(product, ["fulfillmentOptions", "ispuDetails", "ispuAvailability"], {})
    offers = nested_get(product, ["offers", "offers"], [])

    return {
        "page": occurrence.get("page", 1),
        "visual_rank": occurrence.get("visual_rank", ""),
        "organic_rank": occurrence.get("organic_rank", ""),
        "container_type": occurrence.get("container_type", ""),
        "is_sponsored": occurrence.get("is_sponsored", ""),
        "placement": occurrence.get("placement", ""),
        "source_event_id": occurrence.get("source_event_id", ""),
        "sku_id": product.get("skuId", ""),
        "bsin": product.get("bsin", ""),
        "brand": product.get("brand", ""),
        "product_name": nested_get(product, ["name", "short"]),
        "product_url": absolute_bestbuy_url(
            nested_get(product, ["url", "skuSpecificUrl"])
            or nested_get(product, ["url", "pdp"])
            or nested_get(product, ["url", "relativePdp"])
        ),
        "image_url": primary_image.get("piscesHref") or primary_image.get("href", ""),
        "rating": review_info.get("averageRating", ""),
        "review_count": review_info.get("reviewCount", ""),
        "is_reviewable": review_info.get("isReviewable", ""),
        "customer_price": price_value(price, "displayableCustomerPrice", "customerPrice"),
        "regular_price": price_value(price, "displayableRegularPrice"),
        "total_savings": price_value(price, "totalSavings"),
        "total_savings_percent": price_value(price, "totalSavingsPercent"),
        "restricted_price_message": price.get("restrictedPriceDisplayMessage", "") if isinstance(price, dict) else "",
        "deal_expiration": price.get("dealExpirationTimeStamp", "") if isinstance(price, dict) else "",
        "shipping_eligible": shipping.get("shippingEligible", "") if isinstance(shipping, dict) else "",
        "pickup_eligible": pickup.get("pickupEligible", "") if isinstance(pickup, dict) else "",
        "pickup_quantity": pickup.get("quantity", "") if isinstance(pickup, dict) else "",
        "offer_count": len(offers) if isinstance(offers, list) else "",
        "buying_options_json": compact_json(product.get("buyingOptions")),
        "syndicated_review_summary_json": compact_json(review_info.get("syndicatedReviewSummary")),
        "raw_product_json": compact_json(product),
    }


def write_csv(path, rows):
    preferred = [
        "page",
        "visual_rank",
        "organic_rank",
        "container_type",
        "is_sponsored",
        "placement",
        "sku_id",
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
        "restricted_price_message",
        "shipping_eligible",
        "pickup_eligible",
        "offer_count",
    ]
    keys = set()
    for row in rows:
        keys.update(row)
    fieldnames = [key for key in preferred if key in keys]
    fieldnames.extend(sorted(keys - set(fieldnames)))
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main():
    html_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_HTML_PATH
    csv_path = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_CSV_PATH
    json_path = Path(sys.argv[3]) if len(sys.argv) > 3 else DEFAULT_JSON_PATH

    payloads = extract_apollo_payloads(html_path.read_text(encoding="utf-8", errors="replace"))
    products, occurrences, raw_documents = collect_search_products(payloads)
    rows = []
    seen_rows = set()
    for occurrence in occurrences:
        sku = occurrence.get("sku_id", "")
        product = products.get(sku, {})
        if not nested_get(product, ["name", "short"]):
            continue
        row_key = (sku, occurrence.get("container_type"), occurrence.get("placement"))
        if row_key in seen_rows:
            continue
        seen_rows.add(row_key)
        rows.append(parse_product(product, occurrence))
    rows.sort(key=lambda row: (row.get("visual_rank") or 9999, row.get("sku_id", "")))

    write_csv(csv_path, rows)
    json_path.write_text(
        json.dumps(
            {
                "source_html_path": str(html_path),
                "product_count": len(rows),
                "raw_document_count": len(raw_documents),
                "occurrence_count": len(occurrences),
                "products": products,
                "occurrences": occurrences,
                "raw_documents": raw_documents,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"parsed products={len(rows)}")
    print(f"wrote csv -> {csv_path}")
    print(f"wrote raw json -> {json_path}")


if __name__ == "__main__":
    main()
