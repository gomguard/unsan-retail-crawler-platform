import csv
import json
import os
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
INCLUDE_SPONSORED_CAROUSEL = os.getenv("BESTBUY_INCLUDE_SPONSORED_CAROUSEL", "0").lower() in {
    "1",
    "true",
    "yes",
    "y",
}


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
            if isinstance(batch, list) and INCLUDE_SPONSORED_CAROUSEL:
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


def money_text(value, drop_cents_for_whole=False):
    if value in (None, ""):
        return ""
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return ""
        if text.startswith("$"):
            return text
        try:
            value = float(text.replace(",", ""))
        except ValueError:
            return text
    if isinstance(value, (int, float)):
        if drop_cents_for_whole and float(value).is_integer():
            return f"${int(value):,}"
        return f"${float(value):,.2f}"
    return str(value)


def _date_to_listing_text(prefix, value):
    if not value:
        return ""
    return f"{prefix} {value}"


def _first_text(value, keys):
    if not isinstance(value, dict):
        return ""
    for key in keys:
        text = value.get(key)
        if text not in (None, "", [], {}):
            return str(text).strip()
    return ""


def _prefixed_text(text, prefixes):
    if not text:
        return ""
    normalized = str(text).strip()
    for prefix in prefixes:
        if normalized.lower().startswith(prefix.lower()):
            return normalized
    return ""


def first_nested(value, path, default=""):
    current = value
    for key in path:
        if isinstance(current, list):
            current = current[0] if current else default
        if not isinstance(current, dict):
            return default
        current = current.get(key, default)
    if isinstance(current, list):
        current = current[0] if current else default
    return default if current is None else current


def pickup_availability_text(pickup):
    if not isinstance(pickup, dict) or not pickup.get("pickupEligible"):
        return ""
    text = _first_text(
        pickup,
        [
            "displayText",
            "displayMessage",
            "availabilityMessage",
            "fulfillmentMessage",
            "message",
            "text",
            "displayDate",
        ],
    )
    text = _prefixed_text(text, ["Pick up"])
    if text:
        return text
    date_value = pickup.get("maxDate") or pickup.get("fulfillDate") or pickup.get("promiseByStreetDate")
    if date_value:
        return _date_to_listing_text("Pick up", date_value)
    hours = pickup.get("minPickupInHours")
    if hours not in (None, ""):
        suffix = "hour" if str(hours) == "1" else "hours"
        return f"Pick up in {hours} {suffix}"
    return "Pick up available"


def delivery_availability_text(delivery):
    if not isinstance(delivery, dict) or not delivery.get("deliveryEligible"):
        return ""
    text = _first_text(
        delivery,
        [
            "displayText",
            "displayMessage",
            "availabilityMessage",
            "fulfillmentMessage",
            "message",
            "text",
            "displayDate",
        ],
    )
    text = _prefixed_text(text, ["Delivery"])
    if text:
        return text
    slots = delivery.get("deliverySlots")
    if isinstance(slots, list) and slots:
        first = slots[0] if isinstance(slots[0], dict) else {}
        slot_text = _prefixed_text(
            _first_text(first, ["displayText", "displayMessage", "message", "text", "displayDate"]),
            ["Delivery"],
        )
        if slot_text:
            return slot_text
        if first.get("date"):
            return _date_to_listing_text("Delivery as soon as", first.get("date"))
    installation_slots = delivery.get("installationSlots")
    if isinstance(installation_slots, list) and installation_slots:
        first = installation_slots[0] if isinstance(installation_slots[0], dict) else {}
        slot_text = _prefixed_text(
            _first_text(first, ["displayText", "displayMessage", "message", "text", "displayDate"]),
            ["Delivery"],
        )
        if slot_text:
            return slot_text
        if first.get("date"):
            return _date_to_listing_text("Delivery as soon as", first.get("date"))
    return "Delivery available"


def fastest_delivery_text(shipping, delivery):
    if isinstance(shipping, dict) and shipping.get("shippingEligible"):
        groups = shipping.get("customerLOSGroup")
        if isinstance(groups, list) and groups:
            group = groups[0] if isinstance(groups[0], dict) else {}
            date_value = group.get("minLineItemMaxDate") or group.get("maxLineItemMaxDate")
            price = group.get("price")
            suffix = " FREE" if price in (0, 0.0, "0", "0.0", None, "") else ""
            if date_value:
                return f"Get it by {date_value}{suffix}"
            group_text = _prefixed_text(
                _first_text(group, ["displayText", "displayMessage", "message", "text"]),
                ["Get"],
            )
            if group_text:
                return f"{group_text}{suffix}"
        if shipping.get("promiseByStreetDate"):
            return _date_to_listing_text("Get it by", shipping.get("promiseByStreetDate"))
        text = _first_text(
            shipping,
            [
                "displayText",
                "displayMessage",
                "availabilityMessage",
                "fulfillmentMessage",
                "message",
                "text",
                "displayDate",
            ],
        )
        text = _prefixed_text(text, ["Get"])
        if text:
            return text
    return ""


def listing_offer_count(product):
    price = product.get("price", {}) if isinstance(product.get("price"), dict) else {}
    gift_skus = price.get("giftSkus")
    if isinstance(gift_skus, list) and gift_skus:
        return len(gift_skus) + 1
    return ""


def parse_product(product, occurrence):
    price = product.get("price", {}) if isinstance(product.get("price"), dict) else {}
    review_info = product.get("reviewInfo", {}) if isinstance(product.get("reviewInfo"), dict) else {}
    primary_image = product.get("primaryImage", {}) if isinstance(product.get("primaryImage"), dict) else {}
    shipping = first_nested(product, ["fulfillmentOptions", "shippingDetails", "shippingAvailability"], {})
    delivery = first_nested(product, ["fulfillmentOptions", "deliveryDetails", "deliveryAvailability"], {})
    pickup = first_nested(product, ["fulfillmentOptions", "ispuDetails", "ispuAvailability"], {})
    offer_count = listing_offer_count(product)
    customer_price = price_value(price, "displayableCustomerPrice", "customerPrice")
    regular_price = price_value(price, "displayableRegularPrice", "regularPrice")
    total_savings = price_value(price, "totalSavings")
    product_name = nested_get(product, ["name", "short"])
    rating = review_info.get("averageRating", "")
    review_count = review_info.get("reviewCount", "")
    is_sponsored = occurrence.get("is_sponsored", "")
    sku_status = "Sponsored" if is_sponsored in (True, "True", "true", "1", 1) else ""

    return {
        "page": occurrence.get("page", 1),
        "visual_rank": occurrence.get("visual_rank", ""),
        "organic_rank": occurrence.get("organic_rank", ""),
        "container_type": occurrence.get("container_type", ""),
        "is_sponsored": is_sponsored,
        "placement": occurrence.get("placement", ""),
        "source_event_id": occurrence.get("source_event_id", ""),
        "sku_id": product.get("skuId", ""),
        "bsin": product.get("bsin", ""),
        "item": product.get("bsin", ""),
        "brand": product.get("brand", ""),
        "product_name": product_name,
        "retailer_sku_name": product_name,
        "product_url": absolute_bestbuy_url(
            nested_get(product, ["url", "skuSpecificUrl"])
            or nested_get(product, ["url", "pdp"])
            or nested_get(product, ["url", "relativePdp"])
        ),
        "image_url": primary_image.get("piscesHref") or primary_image.get("href", ""),
        "rating": rating,
        "review_count": review_count,
        "star_rating": rating,
        "count_of_star_ratings": review_count,
        "sku_status": sku_status,
        "is_reviewable": review_info.get("isReviewable", ""),
        "customer_price": customer_price,
        "regular_price": regular_price,
        "total_savings": total_savings,
        "final_sku_price": money_text(customer_price),
        "original_sku_price": money_text(regular_price),
        "savings": money_text(total_savings, drop_cents_for_whole=True),
        "total_savings_percent": price_value(price, "totalSavingsPercent"),
        "restricted_price_message": price.get("restrictedPriceDisplayMessage", "") if isinstance(price, dict) else "",
        "deal_expiration": price.get("dealExpirationTimeStamp", "") if isinstance(price, dict) else "",
        "shipping_eligible": shipping.get("shippingEligible", "") if isinstance(shipping, dict) else "",
        "pickup_eligible": pickup.get("pickupEligible", "") if isinstance(pickup, dict) else "",
        "pickup_quantity": pickup.get("quantity", "") if isinstance(pickup, dict) else "",
        "fastest_delivery": fastest_delivery_text(shipping, delivery),
        "delivery_availability": delivery_availability_text(delivery),
        "pick_up_availability": pickup_availability_text(pickup),
        "offer": offer_count,
        "offer_count": offer_count,
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
        "item",
        "brand",
        "product_name",
        "retailer_sku_name",
        "product_url",
        "image_url",
        "rating",
        "review_count",
        "star_rating",
        "count_of_star_ratings",
        "sku_status",
        "customer_price",
        "regular_price",
        "total_savings",
        "final_sku_price",
        "original_sku_price",
        "savings",
        "total_savings_percent",
        "restricted_price_message",
        "fastest_delivery",
        "delivery_availability",
        "pick_up_availability",
        "offer",
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
