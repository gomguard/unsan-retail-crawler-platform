import csv
import json
import os
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, urlencode

from requests import RequestException, Session
from zenrows import ZenRowsClient

from .step00_config import DEFAULT_LOWES_RUN_ROOT, LOWES_BASE_URL, load_env
from .step00_parse_search import (
    extract_preloaded_state,
    find_item_list,
    parse_item,
    product_card_prices,
)

SCRIPT_DIR = Path(__file__).resolve().parent
LOWES_ROOT = SCRIPT_DIR
PROJECT_ROOT = LOWES_ROOT.parent

load_env(PROJECT_ROOT / ".env")


SEARCH_TERM = os.getenv("LOWES_SEARCH_TERM", "refrigerator")
PAGE_SIZE = int(os.getenv("LOWES_PAGE_SIZE", "24"))
PAGES = int(os.getenv("LOWES_PAGES", "13"))
PAGE_LIST = os.getenv("LOWES_PAGE_LIST", "").strip()
MAX_WORKERS = int(os.getenv("LOWES_PAGE_WORKERS", "1"))
REQUEST_TIMEOUT = int(os.getenv("ZENROWS_TIMEOUT", "600"))
MAX_ATTEMPTS = int(os.getenv("LOWES_MAX_ATTEMPTS", "2"))
RETRY_SLEEP_SECONDS = int(os.getenv("LOWES_RETRY_SLEEP_SECONDS", "10"))
MAIN_SOURCE = os.getenv("LOWES_MAIN_SOURCE", "html").strip().lower()
LOCAL_HTML_PATH = os.getenv("LOWES_MAIN_LOCAL_HTML", "").strip()
LOCAL_STATE_JSON_PATH = os.getenv("LOWES_MAIN_LOCAL_STATE_JSON", "").strip()
REQUEST_VARIANT = os.getenv("LOWES_REQUEST_VARIANT", "auto").strip().lower()
BLOCK_RESOURCES = os.getenv("LOWES_BLOCK_RESOURCES", "image,media,font,stylesheet").strip()
ANTIBOT = os.getenv("LOWES_ZENROWS_ANTIBOT", "true").strip().lower()
HTML_CUSTOM_HEADERS = os.getenv("LOWES_HTML_CUSTOM_HEADERS", "true").strip().lower() in {"1", "true", "yes", "y"}
WAIT_FOR_SELECTOR = os.getenv("LOWES_WAIT_FOR_SELECTOR", ".content").strip()
WAIT_MS = os.getenv("LOWES_WAIT_MS", "2500").strip()
API_CURL_FILE = os.getenv("LOWES_API_CURL_FILE", "").strip()
API_TRANSPORT = os.getenv("LOWES_API_TRANSPORT", "curl" if API_CURL_FILE else "zenrows").strip().lower()
API_INITIAL_ADJUSTED_OFFSET = os.getenv("LOWES_API_INITIAL_ADJUSTED_OFFSET", "").strip()
API_NEARBY_STORES = os.getenv("LOWES_API_NEARBY_STORES", "1633,2955,2512").strip()
API_STORE_ID = os.getenv("LOWES_API_STORE_ID", "0289").strip()
API_STORE_NUMBER = os.getenv("LOWES_API_STORE_NUMBER", str(int(API_STORE_ID))).strip()
API_STORE_NAME = os.getenv("LOWES_API_STORE_NAME", "Anchorage Lowe's").strip()
API_STORE_CITY = os.getenv("LOWES_API_STORE_CITY", "Anchorage").strip()
API_STORE_STATE = os.getenv("LOWES_API_STORE_STATE", "AK").strip()
API_STORE_ZIP = os.getenv("LOWES_API_STORE_ZIP", "99503").strip()
API_STORE_REGION = os.getenv("LOWES_API_STORE_REGION", "14").strip()
API_COOKIE = os.getenv("LOWES_API_COOKIE", "").strip()
RETRY_STATUS_CODES = {
    int(value.strip())
    for value in os.getenv("LOWES_RETRY_STATUS_CODES", "413,499,500,502,503,504").split(",")
    if value.strip()
}

_CURL_FILE_CACHE = None
RUN_DATE = os.getenv("LOWES_RUN_DATE", datetime.now().strftime("%Y%m%d"))
RUN_ID = os.getenv("LOWES_MAIN_RUN_ID", os.getenv("LOWES_RUN_ID", "main"))
RUN_ROOT = Path(os.getenv("LOWES_RUN_ROOT", str(DEFAULT_LOWES_RUN_ROOT))) / RUN_ID


REQUEST_VARIANTS = {
    "auto": {"mode": "auto", "proxy_country": "us"},
    "basic_us": {},
    "premium_us": {"premium_proxy": "true", "proxy_country": "us"},
    "js_premium_wait": {
        "js_render": "true",
        "premium_proxy": "true",
        "proxy_country": "us",
        "wait": "8000",
    },
    "js_premium_block_visual": {
        "js_render": "true",
        "antibot": ANTIBOT,
        "premium_proxy": "true",
        "proxy_country": "us",
        "wait": "8000",
        "block_resources": BLOCK_RESOURCES,
    },
    "js_premium_content_fast": {
        "js_render": "true",
        "premium_proxy": "true",
        "wait_for": WAIT_FOR_SELECTOR,
        "wait": WAIT_MS,
    },
}


class RunLogger:
    def __init__(self, path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, message=""):
        stamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{stamp}] {message}" if message else ""
        print(line, flush=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


def parse_page_list():
    if PAGE_LIST:
        return [int(value.strip()) for value in PAGE_LIST.split(",") if value.strip()]
    start_page = int(os.getenv("LOWES_START_PAGE", "1"))
    end_page = int(os.getenv("LOWES_END_PAGE", str(PAGES)))
    return list(range(start_page, end_page + 1))


def build_url(offset):
    query = urlencode({"searchTerm": SEARCH_TERM, "offset": offset})
    return f"{LOWES_BASE_URL}/search?{query}"


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


def build_store_cookie():
    if API_COOKIE:
        return API_COOKIE

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
    return "; ".join(
        [
            f"sn={API_STORE_ID}",
            f"sd={quote(json.dumps(store_data, separators=(',', ':')), safe='')}",
            f"zipcode={API_STORE_ZIP}",
            f"nearbyid={API_STORE_ID}",
            f"zipstate={API_STORE_STATE}",
            f"regionNumber={API_STORE_REGION}",
            f"p13n={quote(json.dumps(personalization, separators=(',', ':')), safe='')}",
        ]
    )


def parse_cmd_curl_file(path):
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    text = text.replace("^\r\n", " ").replace("^\n", " ")
    text = text.replace("^", "")

    data = {"url": "", "headers": {}, "cookie": ""}
    url_match = re.search(r'curl\s+"((?:[^"\\]|\\.)*)"', text, re.S)
    if url_match:
        data["url"] = url_match.group(1).replace(r"\"", '"')

    header_pattern = re.compile(r'-H\s+"((?:[^"\\]|\\.)*)"', re.S)
    for header_match in header_pattern.finditer(text):
        header = header_match.group(1).replace(r"\"", '"')
        if ":" not in header:
            continue
        key, value = header.split(":", 1)
        data["headers"][key.strip().lower()] = value.strip()

    cookie_match = re.search(r'-b\s+"((?:[^"\\]|\\.)*)"', text, re.S)
    if cookie_match:
        data["cookie"] = cookie_match.group(1).replace(r"\"", '"')
    return data


def curl_file_data():
    global _CURL_FILE_CACHE
    if not API_CURL_FILE:
        return {"url": "", "headers": {}, "cookie": ""}
    if _CURL_FILE_CACHE is None:
        _CURL_FILE_CACHE = parse_cmd_curl_file(API_CURL_FILE)
    return _CURL_FILE_CACHE


def api_headers():
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "ko,en-US;q=0.9,en;q=0.8",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "referer": f"{LOWES_BASE_URL}/search?searchTerm={SEARCH_TERM}",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
        ),
        "cookie": build_store_cookie(),
    }
    curl_data = curl_file_data()
    headers.update(curl_data.get("headers", {}))
    if curl_data.get("cookie"):
        headers["cookie"] = curl_data["cookie"]
    return headers


def html_headers():
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "referer": LOWES_BASE_URL + "/",
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "same-origin",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
        ),
        "cookie": build_store_cookie(),
    }
    curl_data = curl_file_data()
    if curl_data.get("cookie"):
        headers["cookie"] = curl_data["cookie"]
    return headers


def make_dirs():
    for subdir in ["raw/main_pages", "parsed", "benchmarks", "logs"]:
        (RUN_ROOT / subdir).mkdir(parents=True, exist_ok=True)


def compact_headers(headers):
    wanted = [
        "X-Request-Cost",
        "X-Request-Id",
        "Zr-Final-Url",
        "Concurrency-Limit",
        "Concurrency-Remaining",
        "Content-Type",
    ]
    return {key: headers.get(key, "") for key in wanted if headers.get(key, "")}


def should_retry(status_code):
    return status_code in RETRY_STATUS_CODES


def zenrows_client():
    api_key = os.getenv("ZENROWS_API_KEY")
    if not api_key:
        raise RuntimeError("Set ZENROWS_API_KEY in .env")
    return ZenRowsClient(api_key)


def fetch_once(task, attempt):
    page_number, offset = task
    url = build_url(offset)
    client = zenrows_client()
    variant_params = REQUEST_VARIANTS.get(REQUEST_VARIANT)
    if variant_params is None:
        raise ValueError(f"Unknown LOWES_REQUEST_VARIANT={REQUEST_VARIANT}")
    params = dict(variant_params)
    headers = html_headers() if HTML_CUSTOM_HEADERS else {}
    if headers:
        params["custom_headers"] = "true"
    started = datetime.now().isoformat(timespec="seconds")
    start = time.time()
    try:
        response = client.get(url, params=params, headers=headers or None, timeout=REQUEST_TIMEOUT)
        elapsed = time.time() - start
        return {
            "page": page_number,
            "offset": offset,
            "url": url,
            "attempt": attempt,
            "started_at": started,
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "elapsed_seconds": round(elapsed, 3),
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "request_params": params,
            "request_custom_headers": bool(headers),
            "text": response.text,
            "content_kind": "html",
            "error": "",
        }
    except RequestException as exc:
        elapsed = time.time() - start
        return {
            "page": page_number,
            "offset": offset,
            "url": url,
            "attempt": attempt,
            "started_at": started,
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "elapsed_seconds": round(elapsed, 3),
            "status_code": "",
            "headers": {},
            "request_params": params,
            "request_custom_headers": bool(headers),
            "text": "",
            "content_kind": "html",
            "error": str(exc),
        }


def fetch_api_once(task, attempt):
    page_number, offset, adjusted_next_offset = task
    url = build_api_url(offset, adjusted_next_offset)
    headers = api_headers()
    started = datetime.now().isoformat(timespec="seconds")
    start = time.time()
    try:
        if API_TRANSPORT == "direct":
            with Session() as session:
                response = session.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            response_status = response.status_code
            response_headers = dict(response.headers)
            response_text = response.text
            response_error = ""
        elif API_TRANSPORT == "zenrows":
            params = dict(REQUEST_VARIANTS.get(REQUEST_VARIANT, {}))
            if not params and REQUEST_VARIANT not in REQUEST_VARIANTS:
                raise ValueError(f"Unknown LOWES_REQUEST_VARIANT={REQUEST_VARIANT}")
            params["custom_headers"] = "true"
            response = zenrows_client().get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
            response_status = response.status_code
            response_headers = dict(response.headers)
            response_text = response.text
            response_error = ""
        elif API_TRANSPORT == "curl":
            response_status, response_headers, response_text, response_error = fetch_api_with_curl(
                url, headers, page_number, attempt
            )
        else:
            raise ValueError("LOWES_API_TRANSPORT must be 'zenrows', 'direct', or 'curl'")

        elapsed = time.time() - start
        return {
            "page": page_number,
            "offset": offset,
            "request_adjusted_next_offset": adjusted_next_offset,
            "url": url,
            "attempt": attempt,
            "started_at": started,
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "elapsed_seconds": round(elapsed, 3),
            "status_code": response_status,
            "headers": response_headers,
            "text": response_text,
            "content_kind": "json",
            "error": response_error,
        }
    except RequestException as exc:
        elapsed = time.time() - start
        return {
            "page": page_number,
            "offset": offset,
            "request_adjusted_next_offset": adjusted_next_offset,
            "url": url,
            "attempt": attempt,
            "started_at": started,
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "elapsed_seconds": round(elapsed, 3),
            "status_code": "",
            "headers": {},
            "text": "",
            "content_kind": "json",
            "error": str(exc),
        }


def save_attempt(result):
    page = result["page"]
    attempt = result["attempt"]
    body_suffix = "json" if result.get("content_kind") == "json" and result["status_code"] == 200 else (
        "html" if result["status_code"] == 200 else "txt"
    )
    status_name = "success" if result["status_code"] == 200 else "fail"
    unit_dir = RUN_ROOT / "raw/main_pages" / f"page_{page:03d}_{status_name}"
    unit_dir.mkdir(parents=True, exist_ok=True)
    request_path = unit_dir / f"page_{page:03d}_request.json"
    body_path = unit_dir / f"page_{page:03d}_response.{body_suffix}"
    headers_path = unit_dir / f"page_{page:03d}_headers.json"
    meta_path = unit_dir / f"page_{page:03d}_meta.json"

    request_path.write_text(
        json.dumps(
            {
                "page": page,
                "attempt": attempt,
                "url": result.get("url", ""),
                "source": result.get("source", ""),
                "transport": result.get("transport", ""),
                "request_variant": REQUEST_VARIANT,
                "request_params": result.get("request_params", {}),
                "custom_headers": result.get("request_custom_headers", False),
                "store_id": API_STORE_ID if result.get("request_custom_headers") else "",
                "store_zip": API_STORE_ZIP if result.get("request_custom_headers") else "",
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    body_path.write_text(result["text"] or result["error"], encoding="utf-8", errors="replace")
    headers_path.write_text(
        json.dumps(result["headers"], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    meta = {key: value for key, value in result.items() if key not in {"text", "headers"}}
    meta["bytes"] = len(result["text"])
    meta["headers_brief"] = compact_headers(result["headers"])
    meta["request_path"] = str(request_path)
    meta["body_path"] = str(body_path)
    meta["headers_path"] = str(headers_path)
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return meta


def fetch_page_with_retries(task, logger):
    page_number, offset = task
    attempts = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        logger.write(f"START page={page_number:03d} offset={offset} attempt={attempt}/{MAX_ATTEMPTS}")
        result = fetch_once(task, attempt)
        meta = save_attempt(result)
        attempts.append(meta)

        status = result["status_code"] or "ERR"
        logger.write(
            f"DONE  page={page_number:03d} attempt={attempt} "
            f"status={status} elapsed={result['elapsed_seconds']}s bytes={len(result['text'])}"
        )

        if result["status_code"] == 200:
            result["attempts"] = attempts
            return result

        if attempt < MAX_ATTEMPTS and should_retry(result["status_code"]):
            logger.write(f"WAIT  page={page_number:03d} retry_after={RETRY_SLEEP_SECONDS}s")
            time.sleep(RETRY_SLEEP_SECONDS)
            continue

        result["attempts"] = attempts
        return result

    result["attempts"] = attempts
    return result


def parse_json_payload(text):
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def curl_config_value(value):
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def write_curl_cookie_jar(path, cookie_header):
    lines = ["# Netscape HTTP Cookie File"]
    for cookie in str(cookie_header).split("; "):
        if "=" not in cookie:
            continue
        name, value = cookie.split("=", 1)
        name = name.strip()
        if not name:
            continue
        value = value.replace("\t", "%09").replace("\r", "").replace("\n", "")
        lines.append(f".lowes.com\tTRUE\t/\tFALSE\t0\t{name}\t{value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_curl_config(path, url, headers, cookie_jar_path=None):
    lines = [
        f'url = "{curl_config_value(url)}"',
        'request = "GET"',
        "compressed",
        "silent",
        "show-error",
        f"max-time = {max(1, REQUEST_TIMEOUT)}",
    ]
    cookie = headers.get("cookie", "")
    for key, value in headers.items():
        if key.lower() == "cookie":
            continue
        lines.append(f'header = "{curl_config_value(f"{key}: {value}")}"')
    if cookie and cookie_jar_path:
        write_curl_cookie_jar(cookie_jar_path, cookie)
        lines.append(f'cookie = "{curl_config_value(cookie_jar_path)}"')
    elif cookie:
        lines.append(f'cookie = "{curl_config_value(cookie)}"')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_curl_headers(path):
    headers = {}
    if not path.exists():
        return headers
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        headers[key.strip()] = value.strip()
    return headers


def fetch_api_with_curl(url, headers, page_number, attempt):
    tmp_dir = RUN_ROOT / "raw/main_pages"
    cfg_path = tmp_dir / f"page_{page_number:03d}_attempt_{attempt:02d}_curl.cfg"
    header_path = tmp_dir / f"page_{page_number:03d}_attempt_{attempt:02d}_curl_headers.txt"
    cookie_jar_path = tmp_dir / f"page_{page_number:03d}_attempt_{attempt:02d}_cookies.txt"
    write_curl_config(cfg_path, url, headers, cookie_jar_path)

    marker = "\n__LOWES_HTTP_STATUS__:"
    command = [
        "curl",
        "--config",
        str(cfg_path),
        "--dump-header",
        str(header_path),
        "--write-out",
        marker + "%{http_code}",
    ]
    completed = subprocess.run(
        command,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=REQUEST_TIMEOUT + 10,
        check=False,
    )
    stdout = completed.stdout or ""
    marker_index = stdout.rfind(marker)
    if marker_index >= 0:
        body = stdout[:marker_index]
        status_text = stdout[marker_index + len(marker) :].strip()
        status_code = int(status_text) if status_text.isdigit() else ""
    else:
        body = stdout
        status_code = ""

    error = completed.stderr.strip()
    if completed.returncode and not error:
        error = f"curl exited with code {completed.returncode}"
    return status_code, read_curl_headers(header_path), body, error


def annotate_api_result(result):
    payload = parse_json_payload(result.get("text", ""))
    items = payload.get("itemList", []) if isinstance(payload.get("itemList"), list) else []
    pagination = payload.get("pagination", {}) if isinstance(payload.get("pagination"), dict) else {}
    result["item_count"] = len(items)
    result["product_count"] = payload.get("productCount", payload.get("itemCount", ""))
    result["adjusted_next_offset"] = payload.get("adjustedNextOffset", "")
    result["pagination_page"] = pagination.get("page", "")
    result["pagination_page_count"] = pagination.get("pageCount", "")
    return payload


def fetch_api_page_with_retries(task, logger):
    page_number, offset, adjusted_next_offset = task
    attempts = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        logger.write(
            f"START api page={page_number:03d} offset={offset} "
            f"adjusted={adjusted_next_offset if adjusted_next_offset not in (None, '') else '-'} "
            f"attempt={attempt}/{MAX_ATTEMPTS}"
        )
        result = fetch_api_once(task, attempt)
        if result["status_code"] == 200:
            annotate_api_result(result)
        meta = save_attempt(result)
        attempts.append(meta)

        status = result["status_code"] or "ERR"
        logger.write(
            f"DONE  api page={page_number:03d} attempt={attempt} "
            f"status={status} elapsed={result['elapsed_seconds']}s bytes={len(result['text'])} "
            f"itemList={result.get('item_count', 0)} adjustedNext={result.get('adjusted_next_offset', '')}"
        )

        if result["status_code"] == 200 and result.get("item_count", 0) > 0:
            result["attempts"] = attempts
            return result

        if attempt < MAX_ATTEMPTS and should_retry(result["status_code"]):
            logger.write(f"WAIT  api page={page_number:03d} retry_after={RETRY_SLEEP_SECONDS}s")
            time.sleep(RETRY_SLEEP_SECONDS)
            continue

        result["attempts"] = attempts
        return result

    result["attempts"] = attempts
    return result


def fetch_api_pages(tasks, logger):
    results = []
    adjusted_next_offset = int(API_INITIAL_ADJUSTED_OFFSET) if API_INITIAL_ADJUSTED_OFFSET else None
    for page_number, offset in tasks:
        result = fetch_api_page_with_retries((page_number, offset, adjusted_next_offset), logger)
        results.append(result)
        if result.get("adjusted_next_offset") not in (None, ""):
            adjusted_next_offset = result["adjusted_next_offset"]
        else:
            adjusted_next_offset = offset + PAGE_SIZE
    return results


def fetch_local_html_pages(tasks, logger):
    if not LOCAL_HTML_PATH:
        raise ValueError("LOWES_MAIN_LOCAL_HTML is required when LOWES_MAIN_SOURCE='local_html'")
    html_path = Path(LOCAL_HTML_PATH)
    html = html_path.read_text(encoding="utf-8", errors="replace")
    results = []
    for page_number, offset in tasks:
        logger.write(f"LOCAL page={page_number:03d} offset={offset} html={html_path}")
        results.append(
            {
                "page": page_number,
                "offset": offset,
                "url": build_url(offset),
                "attempt": 1,
                "started_at": datetime.now().isoformat(timespec="seconds"),
                "finished_at": datetime.now().isoformat(timespec="seconds"),
                "elapsed_seconds": 0,
                "status_code": 200,
                "headers": {},
                "text": html,
                "content_kind": "html",
                "error": "",
                "source_path": str(html_path),
                "attempts": [
                    {
                        "page": page_number,
                        "offset": offset,
                        "url": build_url(offset),
                        "attempt": 1,
                        "status_code": 200,
                        "elapsed_seconds": 0,
                        "bytes": len(html),
                        "body_path": str(html_path),
                        "headers_brief": {},
                    }
                ],
            }
        )
    return results


def fetch_local_state_json_pages(tasks, logger):
    if not LOCAL_STATE_JSON_PATH:
        raise ValueError("LOWES_MAIN_LOCAL_STATE_JSON is required when LOWES_MAIN_SOURCE='local_state_json'")
    state_path = Path(LOCAL_STATE_JSON_PATH)
    text = state_path.read_text(encoding="utf-8", errors="replace")
    results = []
    for page_number, offset in tasks:
        logger.write(f"LOCAL_STATE page={page_number:03d} offset={offset} json={state_path}")
        results.append(
            {
                "page": page_number,
                "offset": offset,
                "url": build_url(offset),
                "attempt": 1,
                "started_at": datetime.now().isoformat(timespec="seconds"),
                "finished_at": datetime.now().isoformat(timespec="seconds"),
                "elapsed_seconds": 0,
                "status_code": 200,
                "headers": {},
                "text": text,
                "content_kind": "json",
                "error": "",
                "source_path": str(state_path),
                "attempts": [
                    {
                        "page": page_number,
                        "offset": offset,
                        "url": build_url(offset),
                        "attempt": 1,
                        "status_code": 200,
                        "elapsed_seconds": 0,
                        "bytes": len(text),
                        "body_path": str(state_path),
                        "headers_brief": {},
                    }
                ],
            }
        )
    return results


def write_csv(path, rows):
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
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_page_summary(path, fetch_results):
    fieldnames = [
        "page",
        "offset",
        "source",
        "status_code",
        "attempts",
        "elapsed_seconds",
        "bytes",
        "item_count",
        "product_count",
        "request_adjusted_next_offset",
        "adjusted_next_offset",
        "pagination_page",
        "pagination_page_count",
        "body_path",
        "content_type",
        "x_request_cost",
        "x_request_id",
        "concurrency_limit",
        "concurrency_remaining",
        "zr_final_url",
        "error",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for result in sorted(fetch_results, key=lambda item: item["page"]):
            headers = result.get("headers", {})
            latest_attempt = result.get("attempts", [{}])[-1]
            writer.writerow(
                {
                    "page": result["page"],
                    "offset": result["offset"],
                    "source": result.get("content_kind", MAIN_SOURCE),
                    "status_code": result["status_code"],
                    "attempts": len(result.get("attempts", [])),
                    "elapsed_seconds": result["elapsed_seconds"],
                    "bytes": len(result.get("text", "")),
                    "item_count": result.get("item_count", 0),
                    "product_count": result.get("product_count", ""),
                    "request_adjusted_next_offset": result.get("request_adjusted_next_offset", ""),
                    "adjusted_next_offset": result.get("adjusted_next_offset", ""),
                    "pagination_page": result.get("pagination_page", ""),
                    "pagination_page_count": result.get("pagination_page_count", ""),
                    "body_path": latest_attempt.get("body_path", ""),
                    "content_type": headers.get("Content-Type", ""),
                    "x_request_cost": headers.get("X-Request-Cost", ""),
                    "x_request_id": headers.get("X-Request-Id", ""),
                    "concurrency_limit": headers.get("Concurrency-Limit", ""),
                    "concurrency_remaining": headers.get("Concurrency-Remaining", ""),
                    "zr_final_url": headers.get("Zr-Final-Url", ""),
                    "error": result.get("error", ""),
                }
            )


def parse_pages(fetch_results, logger):
    rows = []
    raw_pages = []
    seen_ids = set()
    for result in sorted(fetch_results, key=lambda item: item["page"]):
        result["item_count"] = 0
        result["product_count"] = ""
        if result["status_code"] != 200:
            continue

        page_number = result["page"]
        offset = result["offset"]
        if result.get("content_kind") == "json":
            state = parse_json_payload(result["text"])
            items = state.get("itemList", []) if isinstance(state.get("itemList"), list) else []
            html_prices = {}
            pagination = state.get("pagination", {}) if isinstance(state, dict) else {}
            result["adjusted_next_offset"] = state.get("adjustedNextOffset", "")
            result["pagination_page"] = pagination.get("page", "")
            result["pagination_page_count"] = pagination.get("pageCount", "")
        else:
            html = result["text"]
            state = extract_preloaded_state(html)
            items = find_item_list(state) or []
            html_prices = product_card_prices(html)
        result["item_count"] = len(items)
        result["product_count"] = (
            state.get("productCount", state.get("itemCount", "")) if isinstance(state, dict) else ""
        )
        logger.write(
            f"PARSE page={page_number:03d} itemList={len(items)} "
            f"html_prices={len(html_prices)} productCount={result['product_count']}"
        )

        raw_pages.append(
            {
                "page": page_number,
                "offset": offset,
                "url": result["url"],
                "status_code": result["status_code"],
                "source": result.get("content_kind", "html"),
                "item_count": len(items),
                "product_count": result["product_count"],
                "pagination": state.get("pagination", {}) if isinstance(state, dict) else {},
                "adjusted_next_offset": result.get("adjusted_next_offset", ""),
                "items": items,
            }
        )
        for rank_in_page, item in enumerate(items, 1):
            main_rank = offset + rank_in_page
            row = parse_item(item, page_number, rank_in_page, main_rank, html_prices)
            dedupe_key = row.get("omni_item_id") or f"page{page_number}-rank{rank_in_page}"
            row["duplicate_omni_item_id"] = dedupe_key in seen_ids
            seen_ids.add(dedupe_key)
            rows.append(row)
    return rows, raw_pages, seen_ids


def write_manifest(path, manifest):
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def main():
    make_dirs()
    logger = RunLogger(RUN_ROOT / "logs/run.log")
    run_started_at = datetime.now().isoformat(timespec="seconds")
    start = time.time()
    pages = parse_page_list()
    tasks = [(page, (page - 1) * PAGE_SIZE) for page in pages]
    fetch_results = []

    logger.write("=" * 80)
    logger.write(f"RUN_ROOT={RUN_ROOT}")
    logger.write(
        f"SEARCH_TERM={SEARCH_TERM} pages={pages} page_size={PAGE_SIZE} "
        f"workers={MAX_WORKERS} timeout={REQUEST_TIMEOUT}s attempts={MAX_ATTEMPTS} "
        f"source={MAIN_SOURCE} variant={REQUEST_VARIANT} api_transport={API_TRANSPORT}"
    )

    if MAIN_SOURCE == "api":
        fetch_results = fetch_api_pages(tasks, logger)
    elif MAIN_SOURCE == "html":
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_map = {executor.submit(fetch_page_with_retries, task, logger): task for task in tasks}
            for future in as_completed(future_map):
                result = future.result()
                fetch_results.append(result)
    elif MAIN_SOURCE == "local_html":
        fetch_results = fetch_local_html_pages(tasks, logger)
    elif MAIN_SOURCE == "local_state_json":
        fetch_results = fetch_local_state_json_pages(tasks, logger)
    else:
        raise ValueError("LOWES_MAIN_SOURCE must be 'html', 'api', 'local_html', or 'local_state_json'")

    rows, raw_pages, seen_ids = parse_pages(fetch_results, logger)
    parsed_dir = RUN_ROOT / "parsed"
    csv_path = parsed_dir / "main_occurrences.csv"
    raw_json_path = RUN_ROOT / "raw_search_summary.json"
    page_summary_path = parsed_dir / "main_page_summary.csv"
    write_csv(csv_path, rows)
    raw_json_path.write_text(json.dumps(raw_pages, indent=2, ensure_ascii=False), encoding="utf-8")
    write_page_summary(page_summary_path, fetch_results)

    elapsed = time.time() - start
    valid_pages = sum(1 for item in fetch_results if item.get("item_count", 0) > 0)
    manifest = {
        "run_type": "step01_main_list",
        "run_root": str(RUN_ROOT),
        "run_started_at": run_started_at,
        "run_finished_at": datetime.now().isoformat(timespec="seconds"),
        "elapsed_seconds": round(elapsed, 3),
        "search_term": SEARCH_TERM,
        "main_source": MAIN_SOURCE,
        "local_html_path": LOCAL_HTML_PATH if MAIN_SOURCE == "local_html" else "",
        "local_state_json_path": LOCAL_STATE_JSON_PATH if MAIN_SOURCE == "local_state_json" else "",
        "api_transport": API_TRANSPORT if MAIN_SOURCE == "api" else "",
        "api_store": {
            "store_id": API_STORE_ID,
            "store_number": API_STORE_NUMBER,
            "zip": API_STORE_ZIP,
            "state": API_STORE_STATE,
            "nearby_stores": API_NEARBY_STORES,
        }
        if MAIN_SOURCE == "api"
        else {},
        "pages_requested": len(tasks),
        "page_numbers": pages,
        "page_size": PAGE_SIZE,
        "workers": MAX_WORKERS,
        "request_timeout": REQUEST_TIMEOUT,
        "request_variant": REQUEST_VARIANT,
        "request_params": REQUEST_VARIANTS.get(REQUEST_VARIANT, {}),
        "max_attempts": MAX_ATTEMPTS,
        "retry_status_codes": sorted(RETRY_STATUS_CODES),
        "rows": len(rows),
        "unique_omni_item_id": len(seen_ids),
        "successful_http_pages": sum(1 for item in fetch_results if item["status_code"] == 200),
        "valid_item_pages": valid_pages,
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
        f"http_ok={manifest['successful_http_pages']} valid_pages={valid_pages}"
    )
    logger.write(f"CSV={csv_path}")
    logger.write(f"PAGE_SUMMARY={page_summary_path}")
    logger.write(f"MANIFEST={manifest_path}")


if __name__ == "__main__":
    main()
