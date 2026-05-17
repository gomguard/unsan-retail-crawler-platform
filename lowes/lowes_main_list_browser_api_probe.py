import json
import os
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync

from .step00_config import DEFAULT_LOWES_RUN_ROOT, LOWES_BASE_URL, load_env
from .step01_main_list import (
    API_NEARBY_STORES,
    PAGE_SIZE,
    RUN_DATE,
    RunLogger,
    parse_page_list,
    parse_pages,
    write_csv,
    write_manifest,
    write_page_summary,
)

SCRIPT_DIR = Path(__file__).resolve().parent
LOWES_ROOT = SCRIPT_DIR
PROJECT_ROOT = LOWES_ROOT.parent

load_env(PROJECT_ROOT / ".env")

SEARCH_TERM = os.getenv("LOWES_SEARCH_TERM", "refrigerator")
RUN_ID = os.getenv("LOWES_MAIN_RUN_ID", os.getenv("LOWES_RUN_ID", "main_browser_api"))
RUN_ROOT = Path(os.getenv("LOWES_RUN_ROOT", str(DEFAULT_LOWES_RUN_ROOT))) / RUN_ID
HEADLESS = os.getenv("LOWES_BROWSER_HEADLESS", "1").strip().lower() not in {"0", "false", "no"}
SLOW_MO = int(os.getenv("LOWES_BROWSER_SLOW_MO", "0"))
BOOT_WAIT_MS = int(os.getenv("LOWES_BROWSER_BOOT_WAIT_MS", "12000"))
API_WAIT_MS = int(os.getenv("LOWES_BROWSER_API_WAIT_MS", "45000"))
USER_AGENT = os.getenv(
    "LOWES_BROWSER_USER_AGENT",
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
    ),
)
BROWSER_CHANNEL = os.getenv("LOWES_BROWSER_CHANNEL", "").strip()
BROWSER_EXECUTABLE = os.getenv("LOWES_BROWSER_EXECUTABLE", "").strip()


def make_dirs():
    for subdir in ["raw/main_pages", "parsed", "logs"]:
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
    return f"{LOWES_BASE_URL}/search/products?{urlencode(query, safe=',')}"


def save_attempt(result):
    page = result["page"]
    attempt = result["attempt"]
    suffix = "json" if result["status_code"] == 200 else "txt"
    body_path = RUN_ROOT / "raw/main_pages" / f"page_{page:03d}_attempt_{attempt:02d}.{suffix}"
    headers_path = RUN_ROOT / "raw/main_pages" / f"page_{page:03d}_attempt_{attempt:02d}_headers.json"
    meta_path = RUN_ROOT / "raw/main_pages" / f"page_{page:03d}_attempt_{attempt:02d}_meta.json"

    body_path.write_text(result.get("text", "") or result.get("error", ""), encoding="utf-8", errors="replace")
    headers_path.write_text(
        json.dumps(result.get("headers", {}), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    meta = {key: value for key, value in result.items() if key not in {"text", "headers"}}
    meta["bytes"] = len(result.get("text", ""))
    meta["body_path"] = str(body_path)
    meta["headers_path"] = str(headers_path)
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return meta


def fetch_api_from_page(page, url):
    return page.evaluate(
        """async ({ url, timeoutMs }) => {
            const controller = new AbortController();
            const timer = setTimeout(() => controller.abort(), timeoutMs);
            try {
                const response = await fetch(url, {
                    credentials: "include",
                    headers: {
                        "accept": "application/json, text/plain, */*",
                        "cache-control": "no-cache",
                        "pragma": "no-cache"
                    },
                    signal: controller.signal
                });
                const headers = {};
                response.headers.forEach((value, key) => { headers[key] = value; });
                return {
                    status: response.status,
                    statusText: response.statusText,
                    headers,
                    text: await response.text(),
                    error: ""
                };
            } catch (error) {
                return {
                    status: "",
                    statusText: "",
                    headers: {},
                    text: "",
                    error: String(error && error.message ? error.message : error)
                };
            } finally {
                clearTimeout(timer);
            }
        }""",
        {"url": url, "timeoutMs": API_WAIT_MS},
    )


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
    return payload


def collect_pages(page, tasks, logger):
    results = []
    adjusted_next_offset = None
    for page_number, offset in tasks:
        url = build_api_url(offset, adjusted_next_offset)
        logger.write(
            f"START browser-api page={page_number:03d} offset={offset} "
            f"adjusted={adjusted_next_offset if adjusted_next_offset not in (None, '') else '-'}"
        )
        started = datetime.now().isoformat(timespec="seconds")
        start = time.time()
        response = fetch_api_from_page(page, url)
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
        meta = save_attempt(result)
        result["attempts"] = [meta]
        results.append(result)
        logger.write(
            f"DONE  browser-api page={page_number:03d} status={result['status_code'] or 'ERR'} "
            f"elapsed={elapsed}s bytes={len(result.get('text', ''))} "
            f"itemList={result.get('item_count', 0)} adjustedNext={result.get('adjusted_next_offset', '')}"
        )

        if result.get("adjusted_next_offset") not in (None, ""):
            adjusted_next_offset = result["adjusted_next_offset"]
        else:
            adjusted_next_offset = offset + PAGE_SIZE
    return results


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
        f"headless={HEADLESS} boot_wait_ms={BOOT_WAIT_MS} api_wait_ms={API_WAIT_MS}"
    )

    fetch_results = []
    with sync_playwright() as playwright:
        launch_options = {
            "headless": HEADLESS,
            "slow_mo": SLOW_MO,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-first-run",
            ],
        }
        if BROWSER_CHANNEL:
            launch_options["channel"] = BROWSER_CHANNEL
        if BROWSER_EXECUTABLE:
            launch_options["executable_path"] = BROWSER_EXECUTABLE
        browser = playwright.chromium.launch(**launch_options)
        context = browser.new_context(
            user_agent=USER_AGENT,
            locale="en-US",
            viewport={"width": 1440, "height": 1000},
        )
        page = context.new_page()
        stealth_sync(page)
        search_url = build_search_url()
        logger.write(f"OPEN  {search_url}")
        try:
            page.goto(search_url, wait_until="domcontentloaded", timeout=90000)
        except PlaywrightTimeoutError as exc:
            logger.write(f"WARN  initial page timeout: {exc}")
        page.wait_for_timeout(BOOT_WAIT_MS)
        logger.write(f"READY title={page.title()!r} url={page.url}")
        fetch_results = collect_pages(page, tasks, logger)
        context.close()
        browser.close()

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
        "run_type": "step01_main_list_browser_api",
        "run_root": str(RUN_ROOT),
        "run_started_at": run_started_at,
        "run_finished_at": datetime.now().isoformat(timespec="seconds"),
        "elapsed_seconds": round(elapsed, 3),
        "search_term": SEARCH_TERM,
        "pages_requested": len(tasks),
        "page_numbers": pages,
        "page_size": PAGE_SIZE,
        "headless": HEADLESS,
        "boot_wait_ms": BOOT_WAIT_MS,
        "api_wait_ms": API_WAIT_MS,
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

    logger.write("-" * 80)
    logger.write(
        f"FINISH elapsed={elapsed:.1f}s rows={len(rows)} unique={len(seen_ids)} "
        f"http_ok={manifest['successful_http_pages']} valid_pages={manifest['valid_item_pages']}"
    )
    logger.write(f"CSV={csv_path}")
    logger.write(f"PAGE_SUMMARY={page_summary_path}")
    logger.write(f"MANIFEST={manifest_path}")


if __name__ == "__main__":
    main()
