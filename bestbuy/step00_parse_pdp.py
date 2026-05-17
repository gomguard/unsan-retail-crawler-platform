import csv
import io
import json
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


BESTBUY_BASE_URL = "https://www.bestbuy.com"
DEFAULT_HTML_PATH = Path("bestbuy_universal.html")
DEFAULT_CSV_PATH = Path("bestbuy_pdp_parsed.csv")
DEFAULT_JSON_PATH = Path("bestbuy_pdp_raw_apollo.json")


def compact_json(value):
    if value in (None, "", [], {}):
        return ""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def clean_key(value):
    return re.sub(r"[^0-9A-Za-z_]+", "_", str(value).strip()).strip("_").lower()


def nested_get(value, path, default=""):
    current = value
    for key in path:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return default if current is None else current


def absolute_bestbuy_url(path):
    if not path:
        return ""
    if str(path).startswith("http"):
        return path
    return f"{BESTBUY_BASE_URL}{path}"


def extract_apollo_payloads(html):
    soup = BeautifulSoup(html, "html.parser")
    payloads = []
    for script in soup.find_all("script"):
        text = script.string or script.get_text()
        if "ApolloSSRDataTransport" not in text:
            continue
        match = re.search(r"\.push\((.*)\)\s*$", text, re.S)
        if not match:
            continue
        raw_payload = match.group(1)
        # Next/Apollo serializes JavaScript undefined in variables. It is not
        # valid JSON, so normalize it before feeding the structured parser.
        normalized = re.sub(r":\s*undefined(?=[,}])", ":null", raw_payload)
        payloads.append(json.loads(normalized))
    return payloads


def target_sku_from_events(payloads):
    sku_counts = {}
    for payload in payloads:
        for event in payload.get("events", []):
            options = event.get("options", {})
            variables = options.get("variables", {}) if isinstance(options, dict) else {}
            sku = variables.get("skuId") if isinstance(variables, dict) else ""
            if sku:
                sku_counts[str(sku)] = sku_counts.get(str(sku), 0) + 1
    if not sku_counts:
        return ""
    return max(sku_counts.items(), key=lambda item: item[1])[0]


def event_data(event):
    if event.get("type") == "next":
        return event.get("value", {}).get("data", {})
    if event.get("type") == "data":
        return event.get("result", {}).get("data", {})
    return {}


def merge_product_snapshots(payloads, target_sku=""):
    merged = {}
    snapshots = []
    events = []

    for payload in payloads:
        for event in payload.get("events", []):
            events.append(event)
            if event.get("type") not in {"next", "data"}:
                continue
            data = event_data(event)
            product = data.get("productBySkuId")
            if not isinstance(product, dict):
                continue
            if target_sku and str(product.get("skuId", "")) != str(target_sku):
                continue
            snapshots.append(product)
            merged.update({key: value for key, value in product.items() if value is not None})

    return merged, snapshots, events


def spec_map(product):
    result = {}
    groups = product.get("specificationGroups", [])
    if not isinstance(groups, list):
        return result
    for group in groups:
        group_name = clean_key(group.get("name", "")) if isinstance(group, dict) else ""
        specs = group.get("specifications", []) if isinstance(group, dict) else []
        for spec in specs:
            if not isinstance(spec, dict):
                continue
            key = clean_key(spec.get("displayName", "") or spec.get("definition", ""))
            if not key:
                continue
            column = f"spec_{group_name}_{key}" if group_name else f"spec_{key}"
            result[column] = spec.get("value", "")
    return result


def join_badges(product):
    badges = product.get("badgesV2") or product.get("badges") or []
    if not isinstance(badges, list):
        return ""
    labels = []
    for badge in badges:
        if not isinstance(badge, dict):
            continue
        label = badge.get("label") or badge.get("displayName")
        if label:
            labels.append(str(label))
    return "|".join(dict.fromkeys(labels))


def join_highlights(product):
    entries = nested_get(product, ["highlights", "entries"], [])
    if not isinstance(entries, list):
        return ""
    values = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        value = entry.get("value") or entry.get("description") or entry.get("name")
        if value:
            values.append(str(value))
    return "|".join(values)


def parse_product(product, source_html_path):
    price = product.get("price", {}) if isinstance(product.get("price"), dict) else {}
    review_info = product.get("reviewInfo", {}) if isinstance(product.get("reviewInfo"), dict) else {}
    manufacturer = product.get("manufacturer", {}) if isinstance(product.get("manufacturer"), dict) else {}
    primary_image = product.get("primaryImage", {}) if isinstance(product.get("primaryImage"), dict) else {}
    dimension = product.get("dimension", {}) if isinstance(product.get("dimension"), dict) else {}
    seller = product.get("seller", {}) if isinstance(product.get("seller"), dict) else {}
    shipping = nested_get(product, ["fulfillmentOptions", "shippingDetails", "shippingAvailability"], {})
    pickup = nested_get(product, ["fulfillmentOptions", "ispuDetails", "ispuAvailability"], {})

    row = {
        "source_html_path": str(source_html_path),
        "sku_id": product.get("skuId", ""),
        "bsin": product.get("bsin", ""),
        "brand": product.get("brand", ""),
        "brand_id": product.get("brandId", ""),
        "product_name": nested_get(product, ["name", "short"]),
        "model_number": manufacturer.get("modelNumber", ""),
        "upc": product.get("upc", ""),
        "what_it_is": product.get("whatItIs", ""),
        "product_url": absolute_bestbuy_url(nested_get(product, ["url", "pdp"])),
        "primary_image_url": primary_image.get("piscesHref", ""),
        "rating": review_info.get("averageRating", ""),
        "review_count": review_info.get("reviewCount", ""),
        "customer_price": price.get("customerPrice", ""),
        "total_savings": price.get("totalSavings", ""),
        "total_savings_percent": price.get("totalSavingsPercent", ""),
        "price_connection_type": price.get("connectionType", ""),
        "dotcom_display_status": product.get("dotComDisplayStatus", ""),
        "release_date": product.get("releaseDateDisplayValue", ""),
        "street_date": product.get("dotComStreetDate", ""),
        "color": nested_get(product, ["color", "displayName"]),
        "height": dimension.get("height", ""),
        "width": dimension.get("width", ""),
        "depth": dimension.get("depth", ""),
        "weight": dimension.get("weight", ""),
        "seller_id": seller.get("id", ""),
        "seller_classification": nested_get(product, ["seller", "marketplaceSeller", "classification"])
        or seller.get("classification", ""),
        "badges": join_badges(product),
        "highlights": join_highlights(product),
        "shipping_eligible": shipping.get("shippingEligible", "") if isinstance(shipping, dict) else "",
        "pickup_eligible": pickup.get("pickupEligible", "") if isinstance(pickup, dict) else "",
        "pickup_quantity": pickup.get("quantity", "") if isinstance(pickup, dict) else "",
        "images_json": compact_json(product.get("images")),
        "documents_json": compact_json(product.get("documents") or product.get("productManuals")),
        "buying_options_json": compact_json(product.get("buyingOptions")),
        "raw_product_json": compact_json(product),
    }
    row.update(spec_map(product))
    return row


def write_csv(path, rows):
    preferred = [
        "source_html_path",
        "sku_id",
        "bsin",
        "brand",
        "brand_id",
        "product_name",
        "model_number",
        "upc",
        "what_it_is",
        "product_url",
        "primary_image_url",
        "rating",
        "review_count",
        "customer_price",
        "total_savings",
        "total_savings_percent",
        "dotcom_display_status",
        "shipping_eligible",
        "pickup_eligible",
        "badges",
        "highlights",
    ]
    all_keys = set()
    for row in rows:
        all_keys.update(row.keys())
    fieldnames = [key for key in preferred if key in all_keys]
    fieldnames.extend(sorted(all_keys - set(fieldnames)))
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main():
    html_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_HTML_PATH
    csv_path = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_CSV_PATH
    json_path = Path(sys.argv[3]) if len(sys.argv) > 3 else DEFAULT_JSON_PATH

    html = html_path.read_text(encoding="utf-8", errors="replace")
    payloads = extract_apollo_payloads(html)
    target_sku = target_sku_from_events(payloads)
    product, snapshots, events = merge_product_snapshots(payloads, target_sku)
    if not product:
        raise RuntimeError(f"No productBySkuId data found in {html_path}")

    row = parse_product(product, html_path)
    write_csv(csv_path, [row])
    json_path.write_text(
        json.dumps(
            {
                "source_html_path": str(html_path),
                "payload_count": len(payloads),
                "target_sku": target_sku,
                "event_count": len(events),
                "product_snapshot_count": len(snapshots),
                "merged_product": product,
                "product_snapshots": snapshots,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(f"parsed sku={row.get('sku_id')} name={row.get('product_name')}")
    print(f"wrote csv -> {csv_path}")
    print(f"wrote raw json -> {json_path}")


if __name__ == "__main__":
    main()
