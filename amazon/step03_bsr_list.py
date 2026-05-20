import csv
import json
import os
import time
from datetime import datetime
from pathlib import Path

from requests import RequestException, Session
from zenrows import ZenRowsClient

from .step00_config import DEFAULT_AMAZON_RUN_ROOT, load_env, rel_path, target_url, url_for_page
from .step00_direct import get_with_interstitial_retry
from .step00_parse_search import parse_cards


load_env()

RUN_DATE = os.getenv("AMAZON_RUN_DATE", datetime.now().strftime("%Y%m%d"))
RUN_ID = os.getenv("AMAZON_BSR_RUN_ID", "bsr")
RUN_ROOT = Path(os.getenv("AMAZON_RUN_ROOT", str(DEFAULT_AMAZON_RUN_ROOT))) / RUN_ID
PAGES = int(os.getenv("AMAZON_BSR_PAGES", "2"))
REQUEST_TIMEOUT = int(os.getenv("ZENROWS_TIMEOUT", "180"))
MAX_ATTEMPTS = int(os.getenv("AMAZON_MAX_ATTEMPTS", "2"))
RETRY_SLEEP_SECONDS = int(os.getenv("AMAZON_RETRY_SLEEP_SECONDS", "10"))
FETCH_MODE = os.getenv("AMAZON_FETCH_MODE", os.getenv("AMAZON_BSR_FETCH_MODE", "direct")).strip().lower()
REQUEST_PARAMS = {
    "premium_proxy": os.getenv("AMAZON_PREMIUM_PROXY", "true"),
    "proxy_country": os.getenv("AMAZON_PROXY_COUNTRY", "us"),
    "js_render": os.getenv("AMAZON_JS_RENDER", "false"),
    "wait": os.getenv("AMAZON_WAIT", "3000"),
}
USE_RAW_CACHE = os.getenv("AMAZON_USE_RAW_CACHE", "0").strip().lower() in {"1", "true", "yes", "y"}
REFRESH_EMPTY_CACHE = os.getenv("AMAZON_REFRESH_EMPTY_CACHE", "0").strip().lower() in {"1", "true", "yes", "y"}


def now():
    return datetime.now().isoformat(timespec="seconds")


def make_dirs():
    for subdir in ("raw/main_pages", "parsed", "benchmarks", "logs"):
        (RUN_ROOT / subdir).mkdir(parents=True, exist_ok=True)


def bsr_url_template():
    return os.getenv("AMAZON_BSR_URL_TEMPLATE", "").strip() or target_url("bsr")


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


def fetch_page(page):
    cached = fetch_cached_page(page)
    if cached:
        return cached
    url = url_for_page(bsr_url_template(), page)
    last_result = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        for transport in fetch_transports():
            if transport == "zenrows" and not os.getenv("ZENROWS_API_KEY"):
                continue
            started_at = now()
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
                    "page": page,
                    "attempt": attempt,
                    "url": url,
                    "started_at": started_at,
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
                    "page": page,
                    "attempt": attempt,
                    "url": url,
                    "started_at": started_at,
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
            result["item_count_precheck"] = len(parse_cards(result.get("text", ""), page, source="bsr")) if result["status_code"] == 200 else 0
            save_attempt(result)
            last_result = result
            if result["status_code"] == 200 and result["text"] and result["item_count_precheck"] > 0:
                return result
        if attempt < MAX_ATTEMPTS:
            time.sleep(RETRY_SLEEP_SECONDS)
    return last_result


def fetch_cached_page(page):
    if not USE_RAW_CACHE:
        return None
    unit_dir = RUN_ROOT / "raw" / "main_pages" / f"page_{page:03d}_direct_success"
    if not unit_dir.exists():
        unit_dir = RUN_ROOT / "raw" / "main_pages" / f"page_{page:03d}_success"
    body_path = unit_dir / f"page_{page:03d}_response.html"
    meta_path = unit_dir / f"page_{page:03d}_meta.json"
    if not body_path.exists():
        return None
    meta = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except ValueError:
            meta = {}
    text = body_path.read_text(encoding="utf-8", errors="replace")
    item_count = len(parse_cards(text, page, source="bsr"))
    if REFRESH_EMPTY_CACHE and (item_count <= 0 or is_interstitial(text)):
        return None
    return {
        "page": page,
        "attempt": meta.get("attempt", 1),
        "url": meta.get("url", url_for_page(bsr_url_template(), page)),
        "started_at": meta.get("started_at", now()),
        "finished_at": now(),
        "elapsed_seconds": 0,
        "status_code": 200,
        "headers": {},
        "text": text,
        "error": "",
        "item_count_precheck": item_count,
        "cache_hit": True,
        "transport": "raw_cache",
    }


def save_attempt(result):
    page = result["page"]
    success = (
        result["status_code"] == 200
        and int(result.get("item_count_precheck") or 0) > 0
        and not is_interstitial(result.get("text", ""))
    )
    status_name = "success" if success else "fail"
    transport = result.get("transport") or "unknown"
    unit_dir = RUN_ROOT / "raw" / "main_pages" / f"page_{page:03d}_{transport}_{status_name}"
    unit_dir.mkdir(parents=True, exist_ok=True)
    request_path = unit_dir / f"page_{page:03d}_request.json"
    body_path = unit_dir / f"page_{page:03d}_response.html"
    headers_path = unit_dir / f"page_{page:03d}_headers.json"
    meta_path = unit_dir / f"page_{page:03d}_meta.json"
    request_path.write_text(
        json.dumps(
            {
                "page": page,
                "attempt": result["attempt"],
                "url": result["url"],
                "transport": result.get("transport", ""),
                "params": REQUEST_PARAMS if result.get("transport") == "zenrows" else {},
                "direct_headers": sorted(direct_headers()) if result.get("transport") == "direct" else [],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    body_path.write_text(result["text"] or result["error"], encoding="utf-8", errors="replace")
    headers_path.write_text(json.dumps(result["headers"], indent=2, ensure_ascii=False), encoding="utf-8")
    meta = {key: value for key, value in result.items() if key not in {"text", "headers"}}
    meta["success"] = success
    meta["item_count_precheck"] = result.get("item_count_precheck", "")
    meta["interstitial_challenge"] = is_interstitial(result.get("text", ""))
    meta["bytes"] = len(result["text"])
    meta["x_request_cost"] = result["headers"].get("X-Request-Cost", "")
    meta["request_path"] = rel_path(request_path)
    meta["body_path"] = rel_path(body_path)
    meta["headers_path"] = rel_path(headers_path)
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")


def is_interstitial(text):
    value = str(text or "")
    return "bm-verify" in value or "/_sec/verify" in value


def write_csv(path, rows):
    preferred = [
        "page",
        "rank_in_page",
        "bsr_rank",
        "source_page",
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
        "source",
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


def append_csv(path, row, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists() and path.stat().st_size > 0
    with path.open("a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def latest_body_path(result):
    transport = result.get("transport") or "direct"
    unit_dir = RUN_ROOT / "raw" / "main_pages" / f"page_{result['page']:03d}_{transport}_success"
    if not unit_dir.exists():
        unit_dir = RUN_ROOT / "raw" / "main_pages" / f"page_{result['page']:03d}_success"
    path = unit_dir / f"page_{result['page']:03d}_response.html"
    return rel_path(path) if path.exists() else ""


def write_page_benchmarks(path, results, rows_by_page):
    fieldnames = [
        "page",
        "bytes",
        "elapsed_seconds",
        "finished_at",
        "item_count",
        "response_path",
        "source",
        "started_at",
        "status_code",
        "transport",
        "direct_challenge_solved",
        "total_occurrence_count",
        "unique_asin_count",
        "x_request_cost",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for result in sorted(results, key=lambda item: item["page"]):
            page_rows = rows_by_page.get(result["page"], [])
            writer.writerow(
                {
                    "page": result["page"],
                    "bytes": len(result.get("text", "")),
                    "elapsed_seconds": result.get("elapsed_seconds", ""),
                    "finished_at": result.get("finished_at", ""),
                    "item_count": len(page_rows),
                    "response_path": latest_body_path(result),
                    "source": "raw_cache" if result.get("cache_hit") else "network",
                    "started_at": result.get("started_at", ""),
                    "status_code": result.get("status_code", ""),
                    "transport": result.get("transport", ""),
                    "direct_challenge_solved": result.get("direct_challenge_solved", ""),
                    "total_occurrence_count": len(page_rows),
                    "unique_asin_count": len({row.get("asin") for row in page_rows if row.get("asin")}),
                    "x_request_cost": result.get("headers", {}).get("X-Request-Cost", ""),
                }
            )


def page_benchmark_row(result, page_rows):
    return {
        "page": result["page"],
        "bytes": len(result.get("text", "")),
        "elapsed_seconds": result.get("elapsed_seconds", ""),
        "finished_at": result.get("finished_at", ""),
        "item_count": len(page_rows),
        "response_path": latest_body_path(result),
        "source": "raw_cache" if result.get("cache_hit") else "network",
        "started_at": result.get("started_at", ""),
        "status_code": result.get("status_code", ""),
        "transport": result.get("transport", ""),
        "direct_challenge_solved": result.get("direct_challenge_solved", ""),
        "total_occurrence_count": len(page_rows),
        "unique_asin_count": len({row.get("asin") for row in page_rows if row.get("asin")}),
        "x_request_cost": result.get("headers", {}).get("X-Request-Cost", ""),
    }


def main():
    make_dirs()
    started_at = now()
    rows = []
    results = []
    rows_by_page = {}
    page_benchmarks_path = RUN_ROOT / "benchmarks" / "page_benchmarks.csv"
    if page_benchmarks_path.exists():
        page_benchmarks_path.unlink()
    for page in range(1, PAGES + 1):
        result = fetch_page(page)
        results.append(result)
        page_rows = parse_cards(result.get("text", ""), page, rank_offset=len(rows), source="bsr")
        rows.extend(page_rows)
        rows_by_page[page] = page_rows
        append_csv(page_benchmarks_path, page_benchmark_row(result, page_rows), [
            "page", "bytes", "elapsed_seconds", "finished_at", "item_count", "response_path",
            "source", "started_at", "status_code", "transport", "direct_challenge_solved", "total_occurrence_count",
            "unique_asin_count", "x_request_cost"
        ])
        print(f"bsr page={page:03d} status={result['status_code'] or 'ERR'} rows={len(page_rows)}")

    csv_path = RUN_ROOT / "parsed" / "main_occurrences.csv"
    write_csv(csv_path, rows)
    write_page_benchmarks(page_benchmarks_path, results, rows_by_page)
    manifest = {
        "run_type": "step03_bsr_list",
        "run_date": RUN_DATE,
        "run_root": rel_path(RUN_ROOT),
        "started_at": started_at,
        "finished_at": now(),
        "target_url": target_url("bsr"),
        "effective_target_url": bsr_url_template(),
        "pages_requested": PAGES,
        "fetch_mode": FETCH_MODE,
        "fetch_transports": fetch_transports(),
        "rows": len(rows),
        "unique_asins": len({row["asin"] for row in rows if row.get("asin")}),
        "successful_http_pages": sum(1 for result in results if result["status_code"] == 200),
        "output_csv": rel_path(csv_path),
        "page_benchmarks": rel_path(page_benchmarks_path),
    }
    (RUN_ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
