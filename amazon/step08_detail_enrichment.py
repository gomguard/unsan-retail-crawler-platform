import csv
import html
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

from requests import RequestException, Session
from zenrows import ZenRowsClient

from .step00_config import AMAZON_BASE_URL, DEFAULT_AMAZON_RUN_ROOT, load_env, rel_path
from .step00_direct import get_with_interstitial_retry
from .step00_parse_search import clean_text


load_env()

RUN_DATE = os.getenv("AMAZON_RUN_DATE", datetime.now().strftime("%Y%m%d"))
RUN_ROOT = Path(os.getenv("AMAZON_RUN_ROOT", str(DEFAULT_AMAZON_RUN_ROOT)))
DETAIL_ROOT = Path(os.getenv("AMAZON_DETAIL_RUN_ROOT", RUN_ROOT / "detail"))
FINAL_TARGETS_CSV = Path(os.getenv("AMAZON_FINAL_TARGET_OUTPUT", RUN_ROOT / "output" / "amazon_final_targets.csv"))
EXCLUDED_CSV = Path(os.getenv("AMAZON_FINAL_EXCLUDED_OUTPUT", RUN_ROOT / "output" / "amazon_final_targets_excluded.csv"))
DETAIL_MAP_CSV = Path(os.getenv("AMAZON_DETAIL_MAP_OUTPUT", DETAIL_ROOT / "parsed" / "detail_map.csv"))
DETAIL_FAILURES_CSV = Path(os.getenv("AMAZON_DETAIL_FAILURES_OUTPUT", DETAIL_ROOT / "parsed" / "detail_failures.csv"))
FINAL_OUTPUT_CSV = Path(os.getenv("AMAZON_FINAL_OUTPUT", RUN_ROOT / "output" / "final_output.csv"))
REQUEST_TIMEOUT = int(os.getenv("ZENROWS_TIMEOUT", "180"))
MAX_ATTEMPTS = int(os.getenv("AMAZON_DETAIL_MAX_ATTEMPTS", "2"))
RETRY_SLEEP_SECONDS = int(os.getenv("AMAZON_RETRY_SLEEP_SECONDS", "10"))
FETCH_MODE = os.getenv("AMAZON_FETCH_MODE", os.getenv("AMAZON_DETAIL_FETCH_MODE", "direct")).strip().lower()
DETAIL_LIMIT = int(os.getenv("AMAZON_DETAIL_LIMIT", "0"))
FORCE_ALL_DETAILS = os.getenv("AMAZON_DETAIL_FORCE_ALL", "0").strip().lower() in {"1", "true", "yes", "y"}
USE_RAW_CACHE = os.getenv("AMAZON_DETAIL_USE_RAW_CACHE", "1").strip().lower() in {"1", "true", "yes", "y"}
REFRESH_EMPTY_CACHE = os.getenv("AMAZON_DETAIL_REFRESH_EMPTY_CACHE", "0").strip().lower() in {"1", "true", "yes", "y"}
RERUN_FINAL_TARGETS = os.getenv("AMAZON_DETAIL_RERUN_FINAL_TARGETS", "1").strip().lower() in {"1", "true", "yes", "y"}
CLEAR_DETAIL_BENCHMARKS = os.getenv("AMAZON_DETAIL_CLEAR_BENCHMARKS", "0").strip().lower() in {"1", "true", "yes", "y"}

REQUEST_PARAMS = {
    "premium_proxy": os.getenv("AMAZON_DETAIL_PREMIUM_PROXY", os.getenv("AMAZON_PREMIUM_PROXY", "true")),
    "proxy_country": os.getenv("AMAZON_PROXY_COUNTRY", "us"),
    "js_render": os.getenv("AMAZON_DETAIL_JS_RENDER", "false"),
    "wait": os.getenv("AMAZON_DETAIL_WAIT", "2000"),
}


def now():
    return datetime.now().isoformat(timespec="seconds")


def make_dirs():
    for subdir in ("raw/detail_html", "raw/detail_meta", "parsed", "logs"):
        (DETAIL_ROOT / subdir).mkdir(parents=True, exist_ok=True)


def zenrows_client():
    api_key = os.getenv("ZENROWS_API_KEY")
    if not api_key:
        raise RuntimeError("Set ZENROWS_API_KEY in .env")
    return ZenRowsClient(api_key)


def direct_headers():
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "accept-language": os.getenv("AMAZON_ACCEPT_LANGUAGE", "en-US,en;q=0.9"),
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "upgrade-insecure-requests": "1",
        "user-agent": os.getenv(
            "AMAZON_USER_AGENT",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        ),
    }
    cookie = os.getenv("AMAZON_COOKIE", "").strip()
    if cookie:
        headers["cookie"] = cookie
    return headers


def fetch_transports():
    if FETCH_MODE in {"zenrows", "zr"}:
        return ["zenrows"]
    if FETCH_MODE in {"auto", "direct_first", "fallback"}:
        return ["direct", "zenrows"]
    return ["direct"]


def read_csv(path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, preferred=None):
    preferred = preferred or []
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


def append_csv(path, row, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists() and path.stat().st_size > 0
    with path.open("a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        writer.writerow(row)


DETAIL_BENCHMARKS_CSV = DETAIL_ROOT / "benchmarks" / "detail_benchmarks.csv"
DETAIL_BENCHMARK_FIELDS = [
    "asin",
    "status_code",
    "detail_status",
    "transport",
    "direct_challenge_solved",
    "cache_hit",
    "elapsed_seconds",
    "x_request_cost",
    "bytes",
    "interstitial_challenge",
    "body_path",
    "error",
]


def compact_json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def first_match(patterns, text, flags=re.I | re.S):
    for pattern in patterns:
        match = re.search(pattern, text or "", flags)
        if match:
            return match.group(1)
    return ""


def meta_content(text, name):
    escaped = re.escape(name)
    return html.unescape(
        first_match(
            [
                rf"<meta[^>]+(?:property|name)=['\"]{escaped}['\"][^>]+content=['\"]([^'\"]+)['\"]",
                rf"<meta[^>]+content=['\"]([^'\"]+)['\"][^>]+(?:property|name)=['\"]{escaped}['\"]",
            ],
            text,
        )
    )


def normalize_title(value):
    title = clean_text(value)
    title = re.sub(r"\s*:\s*Amazon\.com.*$", "", title, flags=re.I)
    title = re.sub(r"\s*-\s*Amazon\.com.*$", "", title, flags=re.I)
    return title.strip()


def parse_price(text):
    candidates = [
        r'"displayPrice"\s*:\s*"\$?([0-9][0-9,]*(?:\.[0-9]{2})?)"',
        r"<span[^>]+class=['\"][^'\"]*a-price-whole[^'\"]*['\"][^>]*>(.*?)</span>\s*<span[^>]+class=['\"][^'\"]*a-price-fraction[^'\"]*['\"][^>]*>(.*?)</span>",
        r"\$([0-9][0-9,]*(?:\.[0-9]{2})?)",
    ]
    pair = re.search(candidates[1], text or "", re.I | re.S)
    if pair:
        whole = re.sub(r"[^0-9]", "", clean_text(pair.group(1)))
        fraction = re.sub(r"[^0-9]", "", clean_text(pair.group(2)))[:2]
        if whole:
            return f"{whole}.{fraction or '00'}"
    for pattern in (candidates[0], candidates[2]):
        raw = first_match([pattern], text)
        if raw:
            return raw.replace(",", "")
    return ""


def parse_detail_html(text, asin):
    product_name = normalize_title(
        first_match(
            [
                r"<span[^>]+id=['\"]productTitle['\"][^>]*>(.*?)</span>",
                r"<h1[^>]+id=['\"]title['\"][^>]*>(.*?)</h1>",
            ],
            text,
        )
        or meta_content(text, "og:title")
        or first_match([r"<title[^>]*>(.*?)</title>"], text)
    )
    brand = clean_text(
        first_match(
            [
                r"<a[^>]+id=['\"]bylineInfo['\"][^>]*>(.*?)</a>",
                r"<span[^>]+class=['\"][^'\"]*po-brand[^'\"]*['\"][^>]*>.*?<span[^>]*>(.*?)</span>",
                r"<th[^>]*>\s*Brand\s*</th>\s*<td[^>]*>(.*?)</td>",
            ],
            text,
        )
    )
    brand = re.sub(r"^(visit the|brand:|by)\s+", "", brand, flags=re.I).strip()
    image_url = html.unescape(
        first_match(
            [
                r'"hiRes"\s*:\s*"([^"]+)"',
                r'"large"\s*:\s*"([^"]+)"',
                r"<img[^>]+id=['\"]landingImage['\"][^>]+src=['\"]([^'\"]+)['\"]",
            ],
            text,
        )
        or meta_content(text, "og:image")
    )
    rating = first_match([r"([0-5](?:\.[0-9])?)\s+out of\s+5\s+stars"], clean_text(text), flags=re.I)
    review_count = first_match([r"([0-9][0-9,]*)\s+ratings", r"([0-9][0-9,]*)\s+global ratings"], clean_text(text), flags=re.I)
    if review_count:
        review_count = review_count.replace(",", "")
    return {
        "asin": asin,
        "sku_id": asin,
        "brand": brand or (product_name.split(" ", 1)[0] if product_name else ""),
        "product_name": product_name,
        "product_url": f"{AMAZON_BASE_URL}/dp/{asin}",
        "detail_url": f"{AMAZON_BASE_URL}/dp/{asin}",
        "image_url": image_url,
        "rating": rating,
        "review_count": review_count,
        "customer_price": parse_price(text),
        "detail_status": "parsed" if product_name else "missing_product_name",
        "raw_card_json": compact_json({"asin": asin, "detail_enriched": True}),
    }


def is_interstitial(text):
    value = str(text or "")
    return "bm-verify" in value or "/_sec/verify" in value or "Enter the characters you see below" in value


def cached_detail(asin):
    if not USE_RAW_CACHE:
        return None
    body_path = DETAIL_ROOT / "raw" / "detail_html" / f"{asin}.html"
    meta_path = DETAIL_ROOT / "raw" / "detail_meta" / f"{asin}.json"
    if not body_path.exists():
        return None
    text = body_path.read_text(encoding="utf-8", errors="replace")
    parsed = parse_detail_html(text, asin)
    if REFRESH_EMPTY_CACHE and (is_interstitial(text) or not parsed.get("product_name")):
        return None
    meta = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except ValueError:
            meta = {}
    return {
        "asin": asin,
        "status_code": meta.get("status_code", 200),
        "headers": meta.get("headers", {}),
        "text": text,
        "error": "",
        "cache_hit": True,
        "elapsed_seconds": 0,
        "transport": "raw_cache",
    }


def save_detail_result(result):
    asin = result["asin"]
    body_path = DETAIL_ROOT / "raw" / "detail_html" / f"{asin}.html"
    meta_path = DETAIL_ROOT / "raw" / "detail_meta" / f"{asin}.json"
    body_path.write_text(result.get("text") or result.get("error") or "", encoding="utf-8", errors="replace")
    meta = {key: value for key, value in result.items() if key not in {"text"}}
    meta["body_path"] = rel_path(body_path)
    meta["x_request_cost"] = (result.get("headers") or {}).get("X-Request-Cost", "")
    meta["interstitial_challenge"] = is_interstitial(result.get("text", ""))
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")


def fetch_detail(asin):
    cached = cached_detail(asin)
    if cached:
        return cached
    url = f"{AMAZON_BASE_URL}/dp/{asin}"
    last_result = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        for transport in fetch_transports():
            if transport == "zenrows" and not os.getenv("ZENROWS_API_KEY"):
                continue
            start = time.time()
            try:
                if transport == "zenrows":
                    response = zenrows_client().get(url, params=REQUEST_PARAMS, timeout=REQUEST_TIMEOUT)
                    challenge_solved = False
                    challenge_error = ""
                else:
                    response, challenge_solved, challenge_error = get_with_interstitial_retry(
                        Session(), url, direct_headers(), REQUEST_TIMEOUT
                    )
                result = {
                    "asin": asin,
                    "attempt": attempt,
                    "url": url,
                    "started_at": now(),
                    "finished_at": now(),
                    "elapsed_seconds": round(time.time() - start, 3),
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                    "text": response.text,
                    "transport": transport,
                    "direct_challenge_solved": challenge_solved,
                    "direct_challenge_error": challenge_error,
                    "error": "",
                }
            except RequestException as exc:
                result = {
                    "asin": asin,
                    "attempt": attempt,
                    "url": url,
                    "started_at": now(),
                    "finished_at": now(),
                    "elapsed_seconds": round(time.time() - start, 3),
                    "status_code": "",
                    "headers": {},
                    "text": "",
                    "transport": transport,
                    "direct_challenge_solved": False,
                    "direct_challenge_error": "",
                    "error": str(exc),
                }
            save_detail_result(result)
            last_result = result
            parsed = parse_detail_html(result.get("text", ""), asin)
            if result.get("status_code") == 200 and parsed.get("product_name") and not is_interstitial(result.get("text", "")):
                return result
        if attempt < MAX_ATTEMPTS:
            time.sleep(RETRY_SLEEP_SECONDS)
    return last_result


def candidate_asins():
    rows = []
    rows.extend(read_csv(FINAL_TARGETS_CSV))
    rows.extend(row for row in read_csv(EXCLUDED_CSV) if row.get("exclusion_reason") == "missing_product_name_needs_enrichment")
    seen = set()
    output = []
    for row in rows:
        asin = str(row.get("asin") or row.get("sku_id") or "").strip()
        if not asin or asin in seen:
            continue
        if not FORCE_ALL_DETAILS and row.get("product_name") and row.get("image_url") and row.get("customer_price"):
            continue
        seen.add(asin)
        output.append(asin)
    if DETAIL_LIMIT > 0:
        return output[:DETAIL_LIMIT]
    return output


def merge_existing_details(rows):
    result = {}
    for row in rows:
        asin = str(row.get("asin") or row.get("sku_id") or "").strip()
        if asin:
            result[asin] = dict(row)
    return result


def write_final_output_copy():
    rows = read_csv(FINAL_TARGETS_CSV)
    write_csv(
        FINAL_OUTPUT_CSV,
        rows,
        preferred=[
            "category_key",
            "final_target_rank",
            "target_source",
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
        ],
    )


def main():
    make_dirs()
    started_at = now()
    if CLEAR_DETAIL_BENCHMARKS and DETAIL_BENCHMARKS_CSV.exists():
        DETAIL_BENCHMARKS_CSV.unlink()
    existing = merge_existing_details(read_csv(DETAIL_MAP_CSV))
    failures = []
    parsed_by_asin = dict(existing)
    asins = candidate_asins()
    for index, asin in enumerate(asins, 1):
        result = fetch_detail(asin)
        parsed = parse_detail_html(result.get("text", ""), asin)
        parsed["detail_cache_hit"] = "1" if result.get("cache_hit") else ""
        parsed["detail_status_code"] = result.get("status_code", "")
        parsed["detail_elapsed_seconds"] = result.get("elapsed_seconds", "")
        parsed["detail_x_request_cost"] = (result.get("headers") or {}).get("X-Request-Cost", "")
        parsed["detail_transport"] = result.get("transport", "")
        parsed_by_asin[asin] = parsed
        append_csv(
            DETAIL_BENCHMARKS_CSV,
            {
                "asin": asin,
                "status_code": result.get("status_code", ""),
                "detail_status": parsed.get("detail_status", ""),
                "transport": result.get("transport", ""),
                "direct_challenge_solved": result.get("direct_challenge_solved", ""),
                "cache_hit": "1" if result.get("cache_hit") else "",
                "elapsed_seconds": result.get("elapsed_seconds", ""),
                "x_request_cost": (result.get("headers") or {}).get("X-Request-Cost", ""),
                "bytes": len(result.get("text", "")),
                "interstitial_challenge": str(int(is_interstitial(result.get("text", "")))),
                "body_path": rel_path(DETAIL_ROOT / "raw" / "detail_html" / f"{asin}.html"),
                "error": result.get("error", ""),
            },
            DETAIL_BENCHMARK_FIELDS,
        )
        if not parsed.get("product_name"):
            failures.append({"asin": asin, "status_code": result.get("status_code", ""), "error": result.get("error", ""), "detail_status": parsed.get("detail_status", "")})
        print(f"detail {index}/{len(asins)} asin={asin} status={result.get('status_code') or 'ERR'} name={'yes' if parsed.get('product_name') else 'no'}")

    detail_rows = list(parsed_by_asin.values())
    write_csv(
        DETAIL_MAP_CSV,
        detail_rows,
        preferred=[
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
            "detail_status",
            "detail_status_code",
            "detail_cache_hit",
            "detail_elapsed_seconds",
            "detail_x_request_cost",
            "detail_transport",
        ],
    )
    write_csv(DETAIL_FAILURES_CSV, failures, preferred=["asin", "status_code", "detail_status", "error"])

    if RERUN_FINAL_TARGETS:
        from . import step07_final_targets

        step07_final_targets.main()

    write_final_output_copy()
    manifest = {
        "run_type": "step08_detail_enrichment",
        "run_date": RUN_DATE,
        "run_root": rel_path(RUN_ROOT),
        "detail_root": rel_path(DETAIL_ROOT),
        "candidate_count": len(asins),
        "force_all_details": FORCE_ALL_DETAILS,
        "fetch_mode": FETCH_MODE,
        "fetch_transports": fetch_transports(),
        "detail_count": len(detail_rows),
        "failure_count": len(failures),
        "detail_map_csv": rel_path(DETAIL_MAP_CSV),
        "detail_failures_csv": rel_path(DETAIL_FAILURES_CSV),
        "detail_benchmarks_csv": rel_path(DETAIL_BENCHMARKS_CSV),
        "final_output_csv": rel_path(FINAL_OUTPUT_CSV),
        "reran_final_targets": RERUN_FINAL_TARGETS,
        "started_at": started_at,
        "finished_at": now(),
        "success": True,
    }
    (DETAIL_ROOT / "manifest_detail_enrichment.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
