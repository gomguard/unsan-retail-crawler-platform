import csv
import html
import json
import os
import re
import time
from urllib.parse import unquote
from datetime import datetime
from pathlib import Path

from zenrows import ZenRowsClient

from .step00_config import DEFAULT_BESTBUY_RUN_ROOT, has_target_url, load_initial_urls, rel_path


RUN_DATE = os.getenv("BESTBUY_RUN_DATE", datetime.now().strftime("%Y%m%d"))
INPUT_HTML = Path(os.getenv("BESTBUY_TRENDING_HTML", "references/bestbuy_tv_trending_page_sample.html"))
RUN_ROOT = Path(os.getenv("BESTBUY_TRENDING_RUN_ROOT", DEFAULT_BESTBUY_RUN_ROOT / "trending"))
OUTPUT_CSV = Path(
    os.getenv(
        "BESTBUY_TRENDING_OUTPUT",
        DEFAULT_BESTBUY_RUN_ROOT / "trending" / "parsed" / "trending_products.csv",
    )
)
LIVE_FETCH = os.getenv("BESTBUY_TRENDING_LIVE", "1").lower() in {"1", "true", "yes", "y"}
REQUEST_TIMEOUT = int(os.getenv("ZENROWS_TIMEOUT", "180"))
TRENDING_URL = os.getenv("BESTBUY_TRENDING_URL", load_initial_urls().get("trending_tvs_projectors", ""))
LIMIT = int(os.getenv("BESTBUY_TRENDING_LIMIT", "10"))
TREND_SECTION = os.getenv("BESTBUY_TRENDING_SECTION", "Trending Deals in TVs & Projectors")
SKU_WINDOW = os.getenv("BESTBUY_TRENDING_SKU_WINDOW", "tail").strip().lower()
BESTBUY_BASE_URL = "https://www.bestbuy.com"


def now():
    return datetime.now().isoformat(timespec="seconds")


def decode_capture_text(text):
    decoded = unquote(str(text or "").replace("^%^", "%"))
    decoded = decoded.replace("^\\^\"", '"').replace("^\"", '"').replace("^", "")
    decoded = decoded.replace('\\"', '"')
    return html.unescape(decoded)


def clean_text(value):
    return " ".join(str(value or "").split())


def absolute_url(path):
    if not path:
        return ""
    if path.startswith("http"):
        return path
    if path.startswith("/"):
        return f"{BESTBUY_BASE_URL}{path}"
    return path


def extract_analytics_sku_sequences(text):
    sequences = []
    seen = set()
    for match in re.finditer(r"\bskus\b[^\n\r]{0,8000}", text, flags=re.IGNORECASE):
        snippet = decode_capture_text(match.group(0))
        skus = re.findall(r"\b\d{7}\b", snippet)
        if len(skus) < 3:
            continue
        key = tuple(skus)
        if key in seen:
            continue
        seen.add(key)
        sequences.append(skus)
    return sequences


def choose_trending_skus(text, limit=10):
    sequences = extract_analytics_sku_sequences(text)
    if not sequences:
        return []
    sequence = max(sequences, key=len)
    if not limit:
        return sequence
    if SKU_WINDOW in {"head", "first"}:
        return sequence[:limit]
    return sequence[-limit:]


def extract_structured_product_metadata(text):
    decoded = decode_capture_text(text)
    metadata = {}

    patterns = [
        re.compile(
            r'"skuId"\s*:\s*"(?P<sku>\d{7})".{0,2500?}'
            r'"name"\s*:\s*\{[^{}]*"short"\s*:\s*"(?P<name>[^"]+)"[^{}]*\}.{0,2500?}'
            r'"url"\s*:\s*\{[^{}]*(?:"pdp"|"relativePdp"|"skuSpecificUrl")\s*:\s*"(?P<url>[^"]+)"',
            re.DOTALL,
        ),
        re.compile(
            r'"skuId"\s*:\s*"(?P<sku>\d{7})".{0,2500?}'
            r'"url"\s*:\s*\{[^{}]*(?:"pdp"|"relativePdp"|"skuSpecificUrl")\s*:\s*"(?P<url>[^"]+)"[^{}]*\}.{0,2500?}'
            r'"name"\s*:\s*\{[^{}]*"short"\s*:\s*"(?P<name>[^"]+)"',
            re.DOTALL,
        ),
    ]
    for pattern in patterns:
        for match in pattern.finditer(decoded):
            sku = match.group("sku")
            metadata.setdefault(sku, {})
            metadata[sku].update(
                {
                    "retailer_sku_name": clean_text(match.group("name")),
                    "product_url": absolute_url(match.group("url")),
                }
            )

    return metadata


def parse_trending_products(html_text, limit=10):
    trend_skus = choose_trending_skus(html_text, limit=limit)
    metadata = extract_structured_product_metadata(html_text)
    rows = []
    for rank, sku in enumerate(trend_skus, 1):
        product = metadata.get(sku, {})
        rows.append(
            {
                "trend_section": TREND_SECTION,
                "trend_rank": rank,
                "sku_id": sku,
                "retailer_sku_name": product.get("retailer_sku_name", ""),
                "product_url": product.get("product_url", ""),
                "source_card_id": "",
                "source": "analytics_skus_with_structured_product_metadata" if product else "analytics_skus",
            }
        )
    return rows


def write_rows(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "trend_section",
                "trend_rank",
                "sku_id",
                "retailer_sku_name",
                "product_url",
                "source_card_id",
                "source",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def live_html():
    api_key = os.getenv("ZENROWS_API_KEY")
    if not api_key:
        raise RuntimeError("Set ZENROWS_API_KEY in .env")
    if not TRENDING_URL:
        raise RuntimeError("Set BESTBUY_TRENDING_URL or target_urls.trend before live trending collection")

    raw_dir = RUN_ROOT / "raw" / "live_page"
    raw_dir.mkdir(parents=True, exist_ok=True)
    client = ZenRowsClient(api_key)
    start = time.perf_counter()
    response = client.get(
        TRENDING_URL,
        params={
            "js_render": "true",
            "premium_proxy": "true",
            "proxy_country": "us",
        },
        timeout=REQUEST_TIMEOUT,
    )
    elapsed = round(time.perf_counter() - start, 3)
    text = response.text
    html_path = raw_dir / "trending_page.html"
    headers_path = raw_dir / "trending_page_headers.json"
    html_path.write_text(text, encoding="utf-8", errors="replace")
    headers_path.write_text(json.dumps(dict(response.headers), indent=2, ensure_ascii=False), encoding="utf-8")
    summary = {
        "started_at": now(),
        "live": True,
        "url": TRENDING_URL,
        "status_code": response.status_code,
        "elapsed_seconds": elapsed,
        "x_request_cost": response.headers.get("x-request-cost", ""),
        "bytes": len(text or ""),
        "html": rel_path(html_path),
        "headers": rel_path(headers_path),
        "success": response.status_code == 200,
    }
    (RUN_ROOT / "summary_live_fetch.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    if response.status_code != 200:
        raise RuntimeError(f"Trending live fetch failed: status={response.status_code}")
    return text


def main():
    if not has_target_url("trend"):
        write_rows(OUTPUT_CSV, [])
        print(f"skipped trending: no trend URL for category -> {OUTPUT_CSV}")
        return
    html_text = live_html() if LIVE_FETCH else INPUT_HTML.read_text(encoding="utf-8", errors="ignore")
    rows = parse_trending_products(html_text, LIMIT)
    write_rows(OUTPUT_CSV, rows)
    print(f"wrote {len(rows)} rows -> {OUTPUT_CSV}")
    for row in rows:
        print(f"{row['trend_rank']}. {row['sku_id']} {row['retailer_sku_name']}")


if __name__ == "__main__":
    main()
