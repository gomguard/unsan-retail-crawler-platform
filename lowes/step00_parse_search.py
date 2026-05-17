import csv
import io
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

from bs4 import BeautifulSoup
from requests import RequestException
from zenrows import ZenRowsClient

from .step00_config import DEFAULT_LOWES_RUN_ROOT, LOWES_BASE_URL, load_env

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
SCRIPT_DIR = Path(__file__).resolve().parent
LOWES_ROOT = SCRIPT_DIR
PROJECT_ROOT = LOWES_ROOT.parent

load_env(PROJECT_ROOT / ".env")


SEARCH_TERM = os.getenv("LOWES_SEARCH_TERM", "refrigerator")
PAGE_SIZE = int(os.getenv("LOWES_PAGE_SIZE", "24"))
PAGES = int(os.getenv("LOWES_PAGES", "3"))
OUT_DIR = Path(os.getenv("LOWES_OUT_DIR", str(DEFAULT_LOWES_RUN_ROOT / "main" / "raw" / "legacy_parse_pages")))
CSV_PATH = Path(os.getenv("LOWES_CSV_PATH", str(DEFAULT_LOWES_RUN_ROOT / "output" / "lowes_parsed_pages_1_3.csv")))
RAW_JSON_PATH = Path(os.getenv("LOWES_RAW_JSON_PATH", str(DEFAULT_LOWES_RUN_ROOT / "main" / "parsed" / "lowes_parsed_pages_1_3.json")))


def money_to_number(value):
    if value in (None, ""):
        return ""
    if isinstance(value, (int, float)):
        return int(value) if float(value).is_integer() else value
    cleaned = re.sub(r"[^\d.]", "", str(value))
    if not cleaned:
        return ""
    parsed = float(cleaned)
    return int(parsed) if parsed.is_integer() else parsed


def compact_json(value):
    if value in (None, "", [], {}):
        return ""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def clean_key(value):
    return re.sub(r"[^0-9A-Za-z_]+", "_", str(value).strip()).strip("_").lower()


def spec_map(specs):
    result = {}
    if not isinstance(specs, list):
        return result
    for spec in specs:
        if not isinstance(spec, dict):
            continue
        key = clean_key(str(spec.get("key", "")).rstrip(":"))
        if key:
            result[f"spec_{key}"] = spec.get("value", "")
    return result


def flatten(value, prefix=""):
    rows = {}
    if isinstance(value, dict):
        for key, child in value.items():
            child_key = clean_key(key)
            child_prefix = f"{prefix}.{child_key}" if prefix else child_key
            rows.update(flatten(child, child_prefix))
    elif isinstance(value, list):
        rows[prefix] = compact_json(value)
        rows[f"{prefix}.__count"] = len(value)
    else:
        rows[prefix] = "" if value is None else value
    return rows


def absolute_lowes_url(path):
    if not path:
        return ""
    if str(path).startswith("http"):
        return path
    return f"{LOWES_BASE_URL}{path}"


def build_url(offset):
    query = urlencode({"searchTerm": SEARCH_TERM, "offset": offset})
    return f"{LOWES_BASE_URL}/search?{query}"


def extract_preloaded_state(html):
    match = re.search(r"window\['__PRELOADED_STATE__'\] = (.*?)</script>", html, re.S)
    if not match:
        return {}
    return json.loads(match.group(1))


def find_item_list(state):
    if isinstance(state, dict):
        item_list = state.get("itemList")
        if isinstance(item_list, list):
            return item_list
        for child in state.values():
            found = find_item_list(child)
            if found is not None:
                return found
    elif isinstance(state, list):
        for child in state:
            found = find_item_list(child)
            if found is not None:
                return found
    return None


def product_card_prices(html):
    soup = BeautifulSoup(html, "html.parser")
    prices = {}

    for holder in soup.select('[data-selector="prd-price-holder"][data-tile]'):
        tile = holder.get("data-tile")
        candidates = soup.select(f'[data-tile="{tile}"]')
        item_id = ""
        for candidate in candidates:
            button = candidate.select_one('button[id^="add-to-cart-button-"][value]')
            if button:
                item_id = button.get("value", "")
                break
            link = candidate.select_one('a[href*="/pd/"][href]')
            if link:
                match = re.search(r"/(\d{7,})(?:[/?#].*)?$", link["href"])
                if match:
                    item_id = match.group(1)
                    break

        price_el = holder.select_one('[data-selector="splp-prd-act-$"]')
        if item_id and price_el:
            aria = price_el.get("aria-label", "")
            price = money_to_number(aria or price_el.get_text(" ", strip=True))
            if price:
                prices[item_id] = price

    return prices


def fetch_page(client, page_number, offset):
    url = build_url(offset)
    params = {"mode": "auto", "proxy_country": "us"}
    print(f"[Lowes] page={page_number} offset={offset} GET {url}")
    start = time.time()
    response = client.get(url, params=params, timeout=int(os.getenv("ZENROWS_TIMEOUT", "180")))
    elapsed = time.time() - start
    print(f"  status={response.status_code} size={len(response.text)} elapsed={elapsed:.1f}s")
    for header in ["x-request-cost", "x-request-id", "zr-final-url"]:
        if header in response.headers:
            print(f"  {header}: {response.headers[header]}")
    return response


def save_response(page_number, response):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    suffix = "html" if response.status_code == 200 else "txt"
    body_path = OUT_DIR / f"lowes_page_{page_number}.{suffix}"
    headers_path = OUT_DIR / f"lowes_page_{page_number}_headers.json"
    body_path.write_text(response.text, encoding="utf-8", errors="replace")
    headers_path.write_text(
        json.dumps(dict(response.headers), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"  saved body -> {body_path}")
    print(f"  saved headers -> {headers_path}")


def parse_item(item, page_number, rank_in_page, main_rank, html_prices):
    product = item.get("product", {}) if isinstance(item, dict) else {}
    location = item.get("location", {}) if isinstance(item, dict) else {}
    tag = item.get("tag", {}) if isinstance(item, dict) else {}
    price = location.get("price", {}) if isinstance(location, dict) else {}
    inventory = location.get("itemInventory", {}) if isinstance(location, dict) else {}
    promotion = location.get("promotion", {}) if isinstance(location, dict) else {}

    omni_id = str(product.get("omniItemId", ""))
    pd_url = absolute_lowes_url(product.get("pdURL", ""))
    selling_price = money_to_number(price.get("sellingPrice", ""))
    html_card_price = html_prices.get(omni_id, "")

    row = {
        "page": page_number,
        "rank_in_page": rank_in_page,
        "main_rank": main_rank,
        "omni_item_id": omni_id,
        "item_number": product.get("itemNumber", ""),
        "lin": product.get("lin", ""),
        "brand": product.get("brand", ""),
        "model_id": product.get("modelId", ""),
        "description": product.get("description", ""),
        "product_url": pd_url,
        "image_url": product.get("imageUrl", ""),
        "alternate_image_url": product.get("alternateImageUrl", ""),
        "rating": product.get("rating", ""),
        "review_count": product.get("reviewCount", ""),
        "is_buyable": product.get("isBuyable", ""),
        "is_published": product.get("isPublished", ""),
        "is_live_goods": product.get("isLiveGoods", ""),
        "energy_star": product.get("energyStar", ""),
        "sponsored": product.get("sponsored", ""),
        "marketplace": product.get("marketplace", ""),
        "vendor_direct": product.get("vendorDirect", ""),
        "vendor_number": product.get("vendorNumber", ""),
        "program_type": product.get("programType", ""),
        "product_type": product.get("type", ""),
        "selling_price": selling_price,
        "was_price": money_to_number(price.get("wasPrice", "")),
        "total_saving": money_to_number(price.get("totalSaving", "")),
        "total_percentage": price.get("totalPercentage", ""),
        "display_type": price.get("displayType", ""),
        "display_price_type": price.get("displayPriceType", ""),
        "price_end_date": price.get("endDate", ""),
        "price_end_date_iso": price.get("endDateISO", ""),
        "html_card_price": html_card_price,
        "price_source": "preloaded_state" if selling_price != "" else ("html_card" if html_card_price != "" else ""),
        "inventory_omni_id": inventory.get("omniID", "") if isinstance(inventory, dict) else "",
        "inventory_methods": "|".join(
            str(method.get("fullMtdMsg", ""))
            for method in inventory.get("itemAvailList", [])
            if isinstance(method, dict) and method.get("fullMtdMsg")
        )
        if isinstance(inventory, dict)
        else "",
        "available_methods": "|".join(
            str(method.get("fullMtdMsg", ""))
            for method in inventory.get("itemAvailList", [])
            if isinstance(method, dict) and method.get("isAvlSts") and method.get("fullMtdMsg")
        )
        if isinstance(inventory, dict)
        else "",
        "promotion_labels": "|".join(
            promo.get("listingPageMessage", {}).get("label", "")
            for promo in promotion.get("productLevelPromotions", [])
            if isinstance(promo, dict) and promo.get("listingPageMessage", {}).get("label")
        )
        if isinstance(promotion, dict)
        else "",
        "categories_json": compact_json(product.get("categories")),
        "groups_json": compact_json(product.get("groups")),
        "tag_json": compact_json(tag),
    }

    row.update(spec_map(product.get("productSpecsData") or product.get("productSpecs")))

    flattened = {}
    flattened.update(flatten(product, "product"))
    flattened.update(flatten(location, "location"))
    if tag:
        flattened.update(flatten(tag, "tag"))

    for key, value in flattened.items():
        row.setdefault(key, value)

    row["raw_item_json"] = compact_json(item)
    return row


def write_csv(rows):
    preferred = [
        "page",
        "rank_in_page",
        "main_rank",
        "omni_item_id",
        "item_number",
        "lin",
        "brand",
        "model_id",
        "description",
        "product_url",
        "image_url",
        "alternate_image_url",
        "rating",
        "review_count",
        "selling_price",
        "was_price",
        "total_saving",
        "total_percentage",
        "display_type",
        "price_end_date",
        "html_card_price",
        "price_source",
        "energy_star",
        "sponsored",
        "marketplace",
        "vendor_direct",
        "is_buyable",
        "promotion_labels",
        "inventory_methods",
        "available_methods",
        "categories_json",
        "groups_json",
    ]
    all_keys = set()
    for row in rows:
        all_keys.update(row.keys())
    fieldnames = [key for key in preferred if key in all_keys]
    fieldnames.extend(sorted(all_keys - set(fieldnames)))

    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main():
    api_key = os.getenv("ZENROWS_API_KEY")
    if not api_key:
        raise RuntimeError("Set ZENROWS_API_KEY first. Example: $env:ZENROWS_API_KEY='your_key'")

    client = ZenRowsClient(api_key)
    rows = []
    raw_pages = []
    seen_ids = set()

    for page_number in range(1, PAGES + 1):
        offset = (page_number - 1) * PAGE_SIZE
        try:
            response = fetch_page(client, page_number, offset)
        except RequestException as exc:
            print(f"  request exception: {exc}")
            continue

        save_response(page_number, response)
        if response.status_code != 200:
            print(f"  skipped parse due to status={response.status_code}")
            continue

        state = extract_preloaded_state(response.text)
        items = find_item_list(state) or []
        html_prices = product_card_prices(response.text)
        raw_pages.append(
            {
                "page": page_number,
                "offset": offset,
                "url": build_url(offset),
                "status_code": response.status_code,
                "item_count": len(items),
                "product_count": state.get("productCount", ""),
                "pagination": state.get("pagination", {}),
                "items": items,
            }
        )
        print(f"  parsed itemList={len(items)} html_card_prices={len(html_prices)}")

        for rank_in_page, item in enumerate(items, 1):
            main_rank = offset + rank_in_page
            row = parse_item(item, page_number, rank_in_page, main_rank, html_prices)
            dedupe_key = row.get("omni_item_id") or f"page{page_number}-rank{rank_in_page}"
            if dedupe_key in seen_ids:
                row["duplicate_omni_item_id"] = True
            else:
                row["duplicate_omni_item_id"] = False
                seen_ids.add(dedupe_key)
            rows.append(row)

    write_csv(rows)
    RAW_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    RAW_JSON_PATH.write_text(json.dumps(raw_pages, indent=2, ensure_ascii=False), encoding="utf-8")

    print("=" * 80)
    print(f"Saved CSV -> {CSV_PATH} ({len(rows)} rows)")
    print(f"Saved raw JSON -> {RAW_JSON_PATH}")
    print(f"Saved page bodies/headers -> {OUT_DIR}")
    print(f"Unique omni_item_id -> {len(seen_ids)}")


if __name__ == "__main__":
    main()
