import json
import os
import time
import csv
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode

import undetected_chromedriver as uc
from selenium.common.exceptions import TimeoutException, WebDriverException

from .step00_config import DEFAULT_LOWES_RUN_ROOT, LOWES_BASE_URL, load_env
from .step01_main_list import (
    API_NEARBY_STORES,
    API_STORE_CITY,
    API_STORE_ID,
    API_STORE_NAME,
    API_STORE_REGION,
    API_STORE_STATE,
    API_STORE_ZIP,
    PAGE_SIZE,
    RunLogger,
    parse_page_list,
    parse_pages,
    write_csv,
    write_manifest,
    write_page_summary,
)

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

load_env(PROJECT_ROOT / ".env")

SEARCH_TERM = os.getenv("LOWES_SEARCH_TERM", "refrigerator")
RUN_ID = os.getenv("LOWES_MAIN_RUN_ID", os.getenv("LOWES_RUN_ID", "main_uc_api"))
RUN_ROOT = Path(os.getenv("LOWES_RUN_ROOT", str(DEFAULT_LOWES_RUN_ROOT))) / RUN_ID
HEADLESS = os.getenv("LOWES_UC_HEADLESS", "0").strip().lower() in {"1", "true", "yes"}
BOOT_WAIT_SECONDS = float(os.getenv("LOWES_UC_BOOT_WAIT_SECONDS", "25"))
API_WAIT_SECONDS = int(os.getenv("LOWES_UC_API_WAIT_SECONDS", "45"))
USER_DATA_DIR = os.getenv("LOWES_UC_USER_DATA_DIR", "").strip()
PROFILE_DIR = os.getenv("LOWES_UC_PROFILE_DIR", "").strip()
SET_STORE_COOKIES = os.getenv("LOWES_SET_STORE_COOKIES", "1").strip().lower() not in {"0", "false", "no"}
API_EXTRA_QUERY = os.getenv("LOWES_API_EXTRA_QUERY", "").strip()
STOP_AT_PAGE_COUNT = os.getenv("LOWES_UC_STOP_AT_PAGE_COUNT", "1").strip().lower() not in {"0", "false", "no"}
BENCHMARK_ROOT = Path(os.getenv("LOWES_MAIN_BENCHMARK_ROOT", str(RUN_ROOT / "benchmarks")))
MAIN_PROGRESS_CSV = Path(os.getenv("LOWES_MAIN_PROGRESS_CSV", str(BENCHMARK_ROOT / "main_fetch_progress.csv")))
MAIN_PROGRESS_JSON = Path(os.getenv("LOWES_MAIN_PROGRESS_JSON", str(BENCHMARK_ROOT / "main_fetch_progress.json")))
MAIN_BENCHMARK_SUMMARY_JSON = Path(
    os.getenv("LOWES_MAIN_BENCHMARK_SUMMARY_JSON", str(BENCHMARK_ROOT / "main_fetch_summary.json"))
)


def make_dirs():
    for subdir in ["raw/main_pages", "parsed", "logs", "benchmarks"]:
        (RUN_ROOT / subdir).mkdir(parents=True, exist_ok=True)


def build_search_url():
    return f"{LOWES_BASE_URL}/search?{urlencode({'searchTerm': SEARCH_TERM})}"


def build_api_url(offset, adjusted_next_offset=None):
    query = [
        ("searchTerm", SEARCH_TERM),
        ("offset", offset),
    ]
    if adjusted_next_offset not in (None, ""):
        query.append(("adjustedNextOffset", adjusted_next_offset))
    query.extend(
        [
            ("nearByStores", API_NEARBY_STORES),
            ("ac", "false"),
            ("algoRulesAppliedInPageLoad", "false"),
        ]
    )
    if API_EXTRA_QUERY:
        query.extend(parse_qsl(API_EXTRA_QUERY, keep_blank_values=True))
    return f"{LOWES_BASE_URL}/search/products?{urlencode(query, safe=',')}"


def save_attempt(result):
    page = result["page"]
    attempt = result["attempt"]
    suffix = "json" if result["status_code"] == 200 else "txt"
    status_name = "success" if result["status_code"] == 200 else "fail"
    unit_dir = RUN_ROOT / "raw/main_pages" / f"page_{page:03d}_{status_name}"
    unit_dir.mkdir(parents=True, exist_ok=True)
    request_path = unit_dir / f"page_{page:03d}_request.json"
    body_path = unit_dir / f"page_{page:03d}_response.{suffix}"
    headers_path = unit_dir / f"page_{page:03d}_headers.json"
    meta_path = unit_dir / f"page_{page:03d}_meta.json"
    request_path.write_text(
        json.dumps(
            {
                "page": page,
                "attempt": attempt,
                "url": result.get("url", ""),
                "source": result.get("source", ""),
                "transport": "browser_fetch",
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    body_path.write_text(result.get("text", "") or result.get("error", ""), encoding="utf-8", errors="replace")
    headers_path.write_text(json.dumps(result.get("headers", {}), indent=2, ensure_ascii=False), encoding="utf-8")
    meta = {key: value for key, value in result.items() if key not in {"text", "headers"}}
    meta["bytes"] = len(result.get("text", ""))
    meta["request_path"] = str(request_path)
    meta["body_path"] = str(body_path)
    meta["headers_path"] = str(headers_path)
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return meta


MAIN_BENCHMARK_FIELDS = [
    "completed",
    "total_requested",
    "remaining_requested",
    "page",
    "offset",
    "status_code",
    "elapsed_seconds",
    "bytes",
    "item_count",
    "product_count",
    "pagination_page_count",
    "adjusted_next_offset",
    "rate_per_minute",
    "eta_seconds",
    "started_at",
    "finished_at",
    "url",
    "error",
]


def reset_main_benchmark_csv(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        csv.DictWriter(f, fieldnames=MAIN_BENCHMARK_FIELDS, extrasaction="ignore").writeheader()


def append_main_benchmark(path, row):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8-sig", newline="") as f:
        csv.DictWriter(f, fieldnames=MAIN_BENCHMARK_FIELDS, extrasaction="ignore").writerow(row)


def write_benchmark_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def summarize_json(result):
    try:
        payload = json.loads(result.get("text", ""))
    except json.JSONDecodeError:
        payload = {}
    items = payload.get("itemList", []) if isinstance(payload.get("itemList"), list) else []
    pagination = payload.get("pagination", {}) if isinstance(payload.get("pagination"), dict) else {}
    result["item_count"] = len(items)
    result["product_count"] = payload.get("productCount", payload.get("itemCount", "")) if payload else ""
    result["adjusted_next_offset"] = payload.get("adjustedNextOffset", "") if payload else ""
    result["pagination_page"] = pagination.get("page", "")
    result["pagination_page_count"] = pagination.get("pageCount", "")


def fetch_api(driver, url):
    script = """
        const url = arguments[0];
        const timeoutMs = arguments[1];
        const done = arguments[2];
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), timeoutMs);
        fetch(url, {
            credentials: "include",
            headers: {
                "accept": "application/json, text/plain, */*",
                "cache-control": "no-cache",
                "pragma": "no-cache"
            },
            signal: controller.signal
        })
            .then(async response => {
                const headers = {};
                response.headers.forEach((value, key) => { headers[key] = value; });
                done({
                    status: response.status,
                    statusText: response.statusText,
                    headers,
                    text: await response.text(),
                    error: ""
                });
            })
            .catch(error => done({
                status: "",
                statusText: "",
                headers: {},
                text: "",
                error: String(error && error.message ? error.message : error)
            }))
            .finally(() => clearTimeout(timer));
    """
    driver.set_script_timeout(API_WAIT_SECONDS + 5)
    return driver.execute_async_script(script, url, API_WAIT_SECONDS * 1000)


def collect_pages(driver, tasks, logger):
    results = []
    adjusted_next_offset = None
    last_page_count = None
    reset_main_benchmark_csv(MAIN_PROGRESS_CSV)
    run_started = time.time()
    run_started_at = datetime.now().isoformat(timespec="seconds")
    completed = 0
    success_count = 0
    failure_count = 0
    for page_number, offset in tasks:
        if STOP_AT_PAGE_COUNT and last_page_count and page_number > last_page_count:
            logger.write(f"STOP  uc-api page={page_number:03d}: page_count={last_page_count}")
            break
        url = build_api_url(offset, adjusted_next_offset)
        logger.write(
            f"START uc-api page={page_number:03d} offset={offset} "
            f"adjusted={adjusted_next_offset if adjusted_next_offset not in (None, '') else '-'}"
        )
        started = datetime.now().isoformat(timespec="seconds")
        start = time.time()
        try:
            response = fetch_api(driver, url)
        except (TimeoutException, WebDriverException) as exc:
            response = {"status": "", "statusText": "", "headers": {}, "text": "", "error": str(exc)}
        elapsed = round(time.time() - start, 3)
        result = {
            "page": page_number,
            "offset": offset,
            "request_adjusted_next_offset": adjusted_next_offset,
            "url": url,
            "attempt": 1,
            "started_at": started,
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "elapsed_seconds": elapsed,
            "status_code": response.get("status", ""),
            "status_text": response.get("statusText", ""),
            "headers": response.get("headers", {}),
            "text": response.get("text", ""),
            "content_kind": "json",
            "error": response.get("error", ""),
        }
        if result["status_code"] == 200:
            summarize_json(result)
            page_count = result.get("pagination_page_count")
            if page_count not in (None, ""):
                try:
                    last_page_count = int(page_count)
                except (TypeError, ValueError):
                    pass
        meta = save_attempt(result)
        result["attempts"] = [meta]
        results.append(result)
        completed += 1
        success_count += 1 if result["status_code"] == 200 else 0
        failure_count += 0 if result["status_code"] == 200 else 1
        wall_elapsed = max(time.time() - run_started, 0.001)
        rate_per_minute = round(completed / wall_elapsed * 60, 3)
        remaining = max(len(tasks) - completed, 0)
        eta_seconds = round(remaining / (completed / wall_elapsed), 1) if completed else ""
        benchmark_row = {
            "completed": completed,
            "total_requested": len(tasks),
            "remaining_requested": remaining,
            "page": page_number,
            "offset": offset,
            "status_code": result["status_code"],
            "elapsed_seconds": elapsed,
            "bytes": len(result.get("text", "")),
            "item_count": result.get("item_count", 0),
            "product_count": result.get("product_count", ""),
            "pagination_page_count": result.get("pagination_page_count", ""),
            "adjusted_next_offset": result.get("adjusted_next_offset", ""),
            "rate_per_minute": rate_per_minute,
            "eta_seconds": eta_seconds,
            "started_at": result.get("started_at", ""),
            "finished_at": result.get("finished_at", ""),
            "url": url,
            "error": result.get("error", ""),
        }
        append_main_benchmark(MAIN_PROGRESS_CSV, benchmark_row)
        write_benchmark_json(
            MAIN_PROGRESS_JSON,
            {
                "run_started_at": run_started_at,
                "last_updated_at": datetime.now().isoformat(timespec="seconds"),
                "search_term": SEARCH_TERM,
                "total_requested": len(tasks),
                "completed": completed,
                "remaining_requested": remaining,
                "success_count": success_count,
                "failure_count": failure_count,
                "rate_per_minute": rate_per_minute,
                "eta_seconds": eta_seconds,
                "last_page_count": last_page_count,
                "last_item": benchmark_row,
            },
        )
        logger.write(
            f"DONE  uc-api page={page_number:03d} status={result['status_code'] or 'ERR'} "
            f"elapsed={elapsed}s bytes={len(result.get('text', ''))} "
            f"itemList={result.get('item_count', 0)} adjustedNext={result.get('adjusted_next_offset', '')}"
        )
        if result.get("adjusted_next_offset") not in (None, ""):
            adjusted_next_offset = result["adjusted_next_offset"]
        else:
            adjusted_next_offset = offset + PAGE_SIZE
    return results


def launch_driver(logger):
    options = uc.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--start-maximized")
    options.add_argument("--lang=en-US")
    if USER_DATA_DIR:
        options.add_argument(f"--user-data-dir={USER_DATA_DIR}")
    if PROFILE_DIR:
        options.add_argument(f"--profile-directory={PROFILE_DIR}")
    logger.write(
        f"LAUNCH uc headless={HEADLESS} "
        f"user_data_dir={USER_DATA_DIR or '-'} profile={PROFILE_DIR or '-'}"
    )
    return uc.Chrome(options=options, headless=HEADLESS, use_subprocess=True)


def add_cookie(driver, name, value):
    driver.add_cookie(
        {
            "name": name,
            "value": str(value),
            "domain": ".lowes.com",
            "path": "/",
            "secure": True,
        }
    )


def seed_store_cookies(driver, logger):
    if not SET_STORE_COOKIES:
        return
    logger.write(
        f"SEED  store cookies store={API_STORE_ID} zip={API_STORE_ZIP} "
        f"state={API_STORE_STATE} nearby={API_NEARBY_STORES}"
    )
    driver.get(LOWES_BASE_URL)
    time.sleep(2)
    store_data = {
        "id": API_STORE_ID,
        "zip": API_STORE_ZIP,
        "city": API_STORE_CITY,
        "state": API_STORE_STATE,
        "name": API_STORE_NAME,
        "region": API_STORE_REGION,
    }
    personalization = {
        "zipCode": API_STORE_ZIP,
        "storeId": API_STORE_ID,
        "state": API_STORE_STATE,
        "audienceList": [],
    }
    add_cookie(driver, "sn", API_STORE_ID)
    add_cookie(driver, "sd", json.dumps(store_data, separators=(",", ":")))
    add_cookie(driver, "zipcode", API_STORE_ZIP)
    add_cookie(driver, "nearbyid", API_STORE_ID)
    add_cookie(driver, "zipstate", API_STORE_STATE)
    add_cookie(driver, "regionNumber", API_STORE_REGION)
    add_cookie(driver, "p13n", json.dumps(personalization, separators=(",", ":")))


def main():
    make_dirs()
    logger = RunLogger(RUN_ROOT / "logs/run.log")
    run_started_at = datetime.now().isoformat(timespec="seconds")
    started = time.time()
    pages = parse_page_list()
    tasks = [(page_number, (page_number - 1) * PAGE_SIZE) for page_number in pages]

    logger.write("=" * 80)
    logger.write(f"RUN_ROOT={RUN_ROOT}")
    logger.write(
        f"SEARCH_TERM={SEARCH_TERM} pages={pages} page_size={PAGE_SIZE} "
        f"boot_wait_seconds={BOOT_WAIT_SECONDS} api_wait_seconds={API_WAIT_SECONDS}"
    )

    driver = launch_driver(logger)
    try:
        seed_store_cookies(driver, logger)
        search_url = build_search_url()
        logger.write(f"OPEN  {search_url}")
        driver.get(search_url)
        time.sleep(BOOT_WAIT_SECONDS)
        logger.write(f"READY title={driver.title!r} url={driver.current_url}")
        fetch_results = collect_pages(driver, tasks, logger)
    finally:
        driver.quit()

    rows, raw_pages, seen_ids = parse_pages(fetch_results, logger)
    parsed_dir = RUN_ROOT / "parsed"
    csv_path = parsed_dir / "main_occurrences.csv"
    raw_json_path = RUN_ROOT / "raw_search_summary.json"
    page_summary_path = parsed_dir / "main_page_summary.csv"
    write_csv(csv_path, rows)
    raw_json_path.write_text(json.dumps(raw_pages, indent=2, ensure_ascii=False), encoding="utf-8")
    write_page_summary(page_summary_path, fetch_results)

    elapsed = time.time() - started
    manifest = {
        "run_type": "step01_main_list_uc_api",
        "run_root": str(RUN_ROOT),
        "run_started_at": run_started_at,
        "run_finished_at": datetime.now().isoformat(timespec="seconds"),
        "elapsed_seconds": round(elapsed, 3),
        "search_term": SEARCH_TERM,
        "pages_requested": len(tasks),
        "page_numbers": pages,
        "page_size": PAGE_SIZE,
        "headless": HEADLESS,
        "boot_wait_seconds": BOOT_WAIT_SECONDS,
        "api_wait_seconds": API_WAIT_SECONDS,
        "rows": len(rows),
        "unique_omni_item_id": len(seen_ids),
        "successful_http_pages": sum(1 for item in fetch_results if item["status_code"] == 200),
        "valid_item_pages": sum(1 for item in fetch_results if item.get("item_count", 0) > 0),
        "failed_pages": sum(1 for item in fetch_results if item["status_code"] != 200),
        "outputs": {
            "main_occurrences": str(csv_path),
            "raw_search_summary": str(raw_json_path),
            "main_page_summary": str(page_summary_path),
            "log": str(RUN_ROOT / "logs/run.log"),
        },
        "page_results": [
            {key: value for key, value in item.items() if key not in {"text", "headers"}}
            for item in sorted(fetch_results, key=lambda row: row["page"])
        ],
    }
    manifest_path = RUN_ROOT / "manifest.json"
    write_manifest(manifest_path, manifest)
    write_benchmark_json(
        MAIN_BENCHMARK_SUMMARY_JSON,
        {
            "success": True,
            "run_type": "step01_main_list_uc_api",
            "run_root": str(RUN_ROOT),
            "run_started_at": run_started_at,
            "run_finished_at": manifest["run_finished_at"],
            "elapsed_seconds": manifest["elapsed_seconds"],
            "search_term": SEARCH_TERM,
            "pages_requested": len(tasks),
            "pages_fetched": len(fetch_results),
            "rows": len(rows),
            "unique_omni_item_id": len(seen_ids),
            "successful_http_pages": manifest["successful_http_pages"],
            "valid_item_pages": manifest["valid_item_pages"],
            "failed_pages": manifest["failed_pages"],
            "progress_csv": str(MAIN_PROGRESS_CSV),
            "progress_json": str(MAIN_PROGRESS_JSON),
            "main_occurrences": str(csv_path),
            "main_page_summary": str(page_summary_path),
            "manifest": str(manifest_path),
        },
    )

    logger.write("-" * 80)
    logger.write(
        f"FINISH elapsed={elapsed:.1f}s rows={len(rows)} unique={len(seen_ids)} "
        f"http_ok={manifest['successful_http_pages']} valid_pages={manifest['valid_item_pages']}"
    )
    logger.write(f"CSV={csv_path}")
    logger.write(f"PAGE_SUMMARY={page_summary_path}")
    logger.write(f"MANIFEST={manifest_path}")
    logger.write(f"BENCHMARK={MAIN_BENCHMARK_SUMMARY_JSON}")


if __name__ == "__main__":
    main()
