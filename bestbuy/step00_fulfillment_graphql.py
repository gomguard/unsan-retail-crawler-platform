import csv
import json
import os
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

from requests import RequestException
from zenrows import ZenRowsClient

from .step00_config import BESTBUY_BASE_URL, bestbuy_store_id, bestbuy_zip_code
from .step00_parse_search import (
    delivery_availability_text,
    fastest_delivery_text,
    first_nested,
    pickup_availability_text,
)

# NOTE:
# This module is intentionally kept as a disabled last-resort probe only.
# Current Best Buy strategy is to parse availability from PDP/detail GraphQL
# `productBySkuId.fulfillmentOptions` when the PDP operation returns it.
# Do not wire this fulfillment endpoint into the normal pipeline unless the
# user explicitly re-enables fallback collection.

FULFILLMENT_ENDPOINT = "https://www.bestbuy.com/gateway/graphql/fulfillment"
REQUEST_TIMEOUT = int(os.getenv("ZENROWS_TIMEOUT", "120"))
FULFILLMENT_FALLBACK_ENABLED = os.getenv("BESTBUY_ENABLE_FULFILLMENT_FALLBACK", "0").lower() in {
    "1",
    "true",
    "yes",
    "y",
}


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def zenrows_params():
    return {
        "custom_headers": "true",
        "premium_proxy": "true",
        "proxy_country": "us",
        "js_render": "true",
    }


def fulfillment_variables(skus, context="PLP", condition="NEW", zip_code=None, store_id=None):
    sku_value = ",".join(str(sku).strip() for sku in skus if str(sku).strip())
    zip_code = str(zip_code or bestbuy_zip_code())
    store_id = str(store_id or bestbuy_store_id())
    payload = {
        "fulfillmentOptionsInput": {
            "sku": sku_value,
            "buttonState": {
                "context": context,
                "destinationZipCode": zip_code,
                "storeId": store_id,
            },
            "condition": condition,
        }
    }
    if context == "PLP":
        payload["fulfillmentOptionsInput"].update(
            {
                "shipping": {
                    "destinationZipCode": zip_code,
                    "effectivePlanPaidMembership": "NULL",
                },
                "delivery": {
                    "destinationZipCode": zip_code,
                    "deliveryDateOption": "EARLIEST_AVAILABLE_DATE",
                    "effectivePlanPaidMembership": "NULL",
                },
                "inStorePickup": {
                    "storeId": store_id,
                    "searchNearby": True,
                    "showNearbyLocations": False,
                },
                "profileCode": None,
            }
        )
    return payload


def fulfillment_url(skus, context="PLP", condition="NEW", zip_code=None, store_id=None):
    variables = fulfillment_variables(
        skus,
        context=context,
        condition=condition,
        zip_code=zip_code,
        store_id=store_id,
    )
    return f"{FULFILLMENT_ENDPOINT}?{urlencode({'variables': json.dumps(variables, separators=(',', ':'))})}"


def request_cost(headers):
    raw = headers.get("x-request-cost") or headers.get("X-Request-Cost") or "0"
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def iter_dicts(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from iter_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_dicts(child)


def node_sku(node):
    for key in ("skuId", "sku", "sku_id"):
        value = node.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def direct_fulfillment_fields(product):
    shipping = first_nested(product, ["fulfillmentOptions", "shippingDetails", "shippingAvailability"], {})
    delivery = first_nested(product, ["fulfillmentOptions", "deliveryDetails", "deliveryAvailability"], {})
    pickup = first_nested(product, ["fulfillmentOptions", "ispuDetails", "ispuAvailability"], {})
    return {
        "pick_up_availability": pickup_availability_text(pickup),
        "fastest_delivery": fastest_delivery_text(shipping, delivery),
        "delivery_availability": delivery_availability_text(delivery),
    }


def fulfillment_fields_from_node(node):
    values = direct_fulfillment_fields(node)
    if any(values.values()):
        return values

    shipping = first_nested(node, ["shippingDetails", "shippingAvailability"], {})
    delivery = first_nested(node, ["deliveryDetails", "deliveryAvailability"], {})
    pickup = first_nested(node, ["ispuDetails", "ispuAvailability"], {})
    values = {
        "pick_up_availability": pickup_availability_text(pickup),
        "fastest_delivery": fastest_delivery_text(shipping, delivery),
        "delivery_availability": delivery_availability_text(delivery),
    }
    if any(values.values()):
        return values

    shipping = first_nested(node, ["shippingAvailability"], {})
    delivery = first_nested(node, ["deliveryAvailability"], {})
    pickup = first_nested(node, ["ispuAvailability"], {})
    return {
        "pick_up_availability": pickup_availability_text(pickup),
        "fastest_delivery": fastest_delivery_text(shipping, delivery),
        "delivery_availability": delivery_availability_text(delivery),
    }


def parse_fulfillment_response(response_json):
    rows = {}
    for node in iter_dicts(response_json):
        if not isinstance(node, dict):
            continue
        sku = node_sku(node)
        if not sku:
            continue
        values = fulfillment_fields_from_node(node)
        if any(values.values()):
            current = rows.setdefault(sku, {"sku_id": sku})
            for key, value in values.items():
                if value and not current.get(key):
                    current[key] = value
    return rows


def write_csv(path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def fetch_fulfillment_batch(skus, output_dir, context="PLP", chunk_size=20):
    if not FULFILLMENT_FALLBACK_ENABLED:
        raise RuntimeError(
            "Best Buy fulfillment fallback is disabled. "
            "Set BESTBUY_ENABLE_FULFILLMENT_FALLBACK=1 only for an explicit fallback test."
        )

    api_key = os.getenv("ZENROWS_API_KEY")
    if not api_key:
        raise RuntimeError("Set ZENROWS_API_KEY in .env")

    output_dir = Path(output_dir)
    raw_dir = output_dir / "raw_fulfillment"
    parsed_dir = output_dir / "parsed"
    raw_dir.mkdir(parents=True, exist_ok=True)
    parsed_dir.mkdir(parents=True, exist_ok=True)

    unique_skus = []
    seen = set()
    for sku in skus:
        sku = str(sku).strip()
        if sku and sku not in seen:
            seen.add(sku)
            unique_skus.append(sku)

    client = ZenRowsClient(api_key)
    all_rows = {}
    calls = []
    for index in range(0, len(unique_skus), chunk_size):
        chunk = unique_skus[index : index + chunk_size]
        chunk_no = index // chunk_size + 1
        url = fulfillment_url(chunk, context=context)
        chunk_dir = raw_dir / f"chunk_{chunk_no:03d}"
        chunk_dir.mkdir(parents=True, exist_ok=True)
        (chunk_dir / "request.json").write_text(
            json.dumps(
                {
                    "endpoint": FULFILLMENT_ENDPOINT,
                    "variables": fulfillment_variables(chunk, context=context),
                    "sku_count": len(chunk),
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        started_at = now()
        start = time.perf_counter()
        status_code = "ERR"
        cost = 0.0
        error = ""
        returned = {}
        try:
            response = client.get(
                url,
                params=zenrows_params(),
                headers={
                    "accept": "*/*",
                    "referer": f"{BESTBUY_BASE_URL}/",
                    "x-client-id": "pdp-web",
                    "x-requested-for-operation-name": "AIV_FulfillmentBatchCall",
                },
                timeout=REQUEST_TIMEOUT,
            )
            status_code = response.status_code
            cost = request_cost(response.headers)
            (chunk_dir / "response.txt").write_text(response.text, encoding="utf-8", errors="replace")
            (chunk_dir / "headers.json").write_text(
                json.dumps(dict(response.headers), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            try:
                response_json = response.json()
                (chunk_dir / "response.json").write_text(
                    json.dumps(response_json, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                returned = parse_fulfillment_response(response_json)
                for sku, row in returned.items():
                    all_rows[sku] = row
                if response_json.get("errors"):
                    error = json.dumps(response_json.get("errors"), ensure_ascii=False)[:500]
            except ValueError as exc:
                error = str(exc)
        except RequestException as exc:
            error = str(exc)
        elapsed = round(time.perf_counter() - start, 3)
        call = {
            "chunk": chunk_no,
            "sku_count": len(chunk),
            "returned_sku_count": len(returned),
            "status_code": status_code,
            "elapsed_seconds": elapsed,
            "x_request_cost": cost,
            "started_at": started_at,
            "finished_at": now(),
            "error": error,
            "request_path": str(chunk_dir / "request.json"),
            "response_path": str(chunk_dir / "response.json"),
        }
        calls.append(call)
        print(
            f"fulfillment_chunk={chunk_no:03d} status={status_code} "
            f"skus={len(chunk)} returned={len(returned)} cost={cost}"
        )

    rows = [all_rows[sku] for sku in unique_skus if sku in all_rows]
    write_csv(
        parsed_dir / "fulfillment_rows.csv",
        rows,
        ["sku_id", "pick_up_availability", "fastest_delivery", "delivery_availability"],
    )
    write_csv(
        output_dir / "fulfillment_calls.csv",
        calls,
        [
            "chunk",
            "sku_count",
            "returned_sku_count",
            "status_code",
            "elapsed_seconds",
            "x_request_cost",
            "started_at",
            "finished_at",
            "error",
            "request_path",
            "response_path",
        ],
    )
    (output_dir / "manifest.json").write_text(
        json.dumps(
            {
                "sku_count": len(unique_skus),
                "returned_sku_count": len(rows),
                "call_count": len(calls),
                "total_x_request_cost": round(sum(float(call["x_request_cost"] or 0) for call in calls), 7),
                "context": context,
                "created_at": now(),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return rows, calls
