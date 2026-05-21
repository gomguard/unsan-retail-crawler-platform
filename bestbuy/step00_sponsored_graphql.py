import json
import os
import time
from urllib.parse import urlencode

from zenrows import ZenRowsClient

BESTBUY_BASE_URL = "https://www.bestbuy.com"
GRAPHQL_ENDPOINT = os.getenv("BESTBUY_GRAPHQL_ENDPOINT", "https://www.bestbuy.com/gateway/graphql")
SEARCH_TERM = os.getenv("BESTBUY_SEARCH_TERM", "tv")
REQUEST_TIMEOUT = int(os.getenv("ZENROWS_TIMEOUT", "120"))


def build_search_url(page=1):
    query = {"id": "pcat17071", "st": SEARCH_TERM, "intl": "nosplash"}
    if page > 1:
        query["cp"] = page
    return f"{BESTBUY_BASE_URL}/site/searchpage.jsp?{urlencode(query)}"


def zenrows_params():
    params = {"custom_headers": "true"}
    if os.getenv("BESTBUY_GRAPHQL_PREMIUM_PROXY", "0").lower() in {"1", "true", "yes"}:
        params["premium_proxy"] = "true"
        params["proxy_country"] = "us"
    if os.getenv("BESTBUY_GRAPHQL_MODE_AUTO", "0").lower() in {"1", "true", "yes"}:
        params["mode"] = "auto"
        params["proxy_country"] = "us"
    if os.getenv("BESTBUY_GRAPHQL_JS_RENDER", "0").lower() in {"1", "true", "yes"}:
        params["js_render"] = "true"
    return params


def post_graphql(payload):
    api_key = os.getenv("ZENROWS_API_KEY")
    if not api_key:
        raise RuntimeError("Set ZENROWS_API_KEY in .env")
    client = ZenRowsClient(api_key)
    headers = {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json",
        "origin": BESTBUY_BASE_URL,
        "referer": build_search_url(),
    }
    start = time.time()
    response = client.post(
        GRAPHQL_ENDPOINT,
        params=zenrows_params(),
        headers=headers,
        data=json.dumps(payload),
        timeout=REQUEST_TIMEOUT,
    )
    return response, round(time.time() - start, 3)


def build_sponsored_payload(skus):
    quoted_skus = " ".join(json.dumps(str(sku)) for sku in skus)
    query = (
        "fragment ReviewStats_Fragment on Product{"
        "skuId reviewInfo{averageRating isReviewable reviewCount "
        "syndicatedReviewSummary{clientDisplayName overallRating totalReviewCount}}"
        "url{relativePdp}}"
        "query AdTech_NinjaCarousel_SkuDataQuery{"
        f"batch0:productsBySkuIds(skuIds:[{quoted_skus}])"
        "{...on Product{skuId name{short}primaryImage{href piscesHref altText}"
        "...ReviewStats_Fragment url{skuSpecificUrl relativePdp pdp}"
        "price(input:{salesChannel:\"LargeView\",usePriceWithCart:true})"
        "{displayableCustomerPrice customerPrice displayableRegularPrice regularPrice "
        "totalSavings totalSavingsPercent giftSkus{skuId quantity}}}}}"
    )
    return {
        "operationName": "AdTech_NinjaCarousel_SkuDataQuery",
        "variables": {},
        "query": query,
    }


def sponsored_product_map(response_json):
    data = response_json.get("data", {}) if isinstance(response_json, dict) else {}
    batch = data.get("batch0") if isinstance(data, dict) else []
    products = {}
    if not isinstance(batch, list):
        return products
    for product in batch:
        if isinstance(product, dict) and product.get("skuId"):
            products[str(product["skuId"])] = product
    return products
