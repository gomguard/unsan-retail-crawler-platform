import csv
import html
import json
import os
import re
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from threading import Lock
from urllib.parse import urlencode

from bs4 import BeautifulSoup
from lxml import html as lxml_html
from requests import RequestException
from zenrows import ZenRowsClient

from .step00_config import (
    DEFAULT_BESTBUY_RUN_ROOT,
    KRW_PER_USD,
    apply_bestbuy_location,
    bestbuy_category,
    bestbuy_output_table,
    bestbuy_store_id,
    bestbuy_zip_code,
    db_config,
    old_pdp_url,
    rel_path,
)
from .step00_detail_benchmarks import append_detail_benchmark, write_detail_benchmarks
from .step00_parse_pdp import event_data, extract_apollo_payloads

RUN_DATE = os.getenv("BESTBUY_RUN_DATE", datetime.now().strftime("%Y%m%d"))
CATEGORY = bestbuy_category()
DETAIL_ROOT = Path(os.getenv("BESTBUY_DETAIL_RUN_ROOT", DEFAULT_BESTBUY_RUN_ROOT / "detail"))
OUTPUT_ROOT = Path(os.getenv("BESTBUY_OUTPUT_ROOT", DEFAULT_BESTBUY_RUN_ROOT / "output"))
TARGET_CSV = Path(os.getenv("BESTBUY_DETAIL_TARGET_CSV", OUTPUT_ROOT / "bestbuy_final_targets.csv"))
SAMPLE_SCHEMA_CSV = Path(os.getenv("BESTBUY_OUTPUT_SCHEMA_CSV", "references/tv_retail_com_202605170513.csv"))
SELECTOR_TABLE = os.getenv("BESTBUY_SELECTOR_TABLE", "dx_xpath_selectors")
LIMIT = int(os.getenv("BESTBUY_DETAIL_LIMIT", "0"))
MAX_ATTEMPTS = int(os.getenv("BESTBUY_DETAIL_MAX_ATTEMPTS", "3"))
RETRY_ONLY = os.getenv("BESTBUY_DETAIL_RETRY_ONLY", "0").lower() in {"1", "true", "yes", "y"}
REBUILD_ONLY = os.getenv("BESTBUY_DETAIL_REBUILD_ONLY", "0").lower() in {"1", "true", "yes", "y"}
REQUEST_TIMEOUT = int(os.getenv("ZENROWS_TIMEOUT", "240"))
FETCH_MODE = os.getenv("BESTBUY_FETCH_MODE", os.getenv("BESTBUY_DETAIL_FETCH_MODE", "zenrows")).strip().lower()
WORKERS = int(os.getenv("BESTBUY_DETAIL_WORKERS", "1"))
STAGE = os.getenv("BESTBUY_DETAIL_STAGE", "detail").lower()
SAVE_HTML_MODE = os.getenv("BESTBUY_SAVE_HTML_MODE", "slim").lower()

RAW_DETAIL_DIR = DETAIL_ROOT / "raw" / "detail_html"
RAW_REVIEW_DIR = DETAIL_ROOT / "raw" / "review20"
RAW_COMPARE_DIR = DETAIL_ROOT / "raw" / "compare"
PARSED_DIR = DETAIL_ROOT / "parsed"
BENCHMARKS_DIR = DETAIL_ROOT / "benchmarks"
DETAIL_ROWS_CSV = PARSED_DIR / "detail_enriched_rows.csv"
FAILURES_CSV = PARSED_DIR / "detail_failures.csv"
DETAIL_BENCHMARKS_CSV = BENCHMARKS_DIR / "detail_benchmarks.csv"
FINAL_OUTPUT_CSV = Path(os.getenv("BESTBUY_FINAL_OUTPUT_CSV", OUTPUT_ROOT / "final_output.csv"))
MANIFEST_PATH = DETAIL_ROOT / "manifest_detail_enrichment.json"
FETCH_COMPARE = os.getenv("BESTBUY_DETAIL_FETCH_COMPARE", "0").lower() in {"1", "true", "yes", "y"}
RUN_BATCH_ID = os.getenv("BESTBUY_BATCH_ID") or f"b_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
BATCH_FETCH = os.getenv("BESTBUY_DETAIL_BATCH_FETCH", "0").lower() in {"1", "true", "yes", "y"}
BATCH_SIZE = max(1, int(os.getenv("BESTBUY_DETAIL_BATCH_SIZE", "25")))

HHP_FINAL_FIELDS = [
    "item",
    "account_name",
    "page_type",
    "product",
    "count_of_reviews",
    "retailer_sku_name",
    "product_url",
    "star_rating",
    "count_of_star_ratings",
    "final_sku_price",
    "original_sku_price",
    "savings",
    "offer",
    "pick_up_availability",
    "fastest_delivery",
    "sku_status",
    "trade_in",
    "hhp_storage",
    "hhp_color",
    "hhp_carrier",
    "recommendation_intent",
    "main_rank",
    "bsr_rank",
    "trend_rank",
    "retailer_sku_name_similar",
    "promotion_type",
    "calendar_week",
    "crawl_strdatetime",
    "batch_id",
    "country",
    "detailed_review_content",
]

FALLBACK_FINAL_FIELDS = {
    "HHP": HHP_FINAL_FIELDS,
}


def now():
    return datetime.now().isoformat(timespec="seconds")


def batch_id_from_datetime(value):
    return f"b_{value.strftime('%Y%m%d_%H%M%S')}"


def compact_text(value):
    return re.sub(r"\s+", " ", html.unescape(str(value or ""))).strip()


def first_non_empty(*values):
    for value in values:
        if value not in ("", None, [], {}):
            return value
    return ""


def clean_hhp_carrier(value):
    text = compact_text(value)
    if not text:
        return ""
    lowered = text.lower()
    carriers = [
        ("Unlocked", ["unlocked", "fully unlocked"]),
        ("AT&T", ["at&t", "att"]),
        ("Verizon", ["verizon"]),
        ("T-Mobile", ["t-mobile", "tmobile"]),
        ("Boost Mobile", ["boost mobile"]),
        ("Cricket", ["cricket"]),
        ("Tracfone", ["tracfone"]),
        ("Google Fi", ["google fi"]),
        ("Metro by T-Mobile", ["metro by t-mobile", "metro"]),
        ("Consumer Cellular", ["consumer cellular"]),
        ("Straight Talk", ["straight talk"]),
        ("Total Wireless", ["total wireless"]),
    ]
    for canonical, needles in carriers:
        if any(needle in lowered for needle in needles):
            return canonical
    return text


def hhp_attributes_from_name(name):
    text = compact_text(name)
    attrs = {"hhp_storage": "", "hhp_color": "", "hhp_carrier": ""}
    if not text:
        return attrs

    storage_match = re.search(r"(?i)\b(\d+(?:\.\d+)?)\s*(TB|GB)\b", text)
    if storage_match:
        number = storage_match.group(1)
        unit = storage_match.group(2).upper()
        attrs["hhp_storage"] = f"{number}{unit}"

    paren_values = re.findall(r"\(([^()]*)\)", text)
    for value in reversed(paren_values):
        carrier = clean_hhp_carrier(value)
        if carrier:
            attrs["hhp_carrier"] = carrier
            break

    if not attrs["hhp_carrier"]:
        attrs["hhp_carrier"] = clean_hhp_carrier(text)

    # Best Buy HHP titles usually end with "- Color" after carrier/storage.
    parts = [part.strip() for part in re.split(r"\s+-\s+", text) if part.strip()]
    if len(parts) >= 2:
        color = parts[-1]
        if not re.search(r"(?i)\b(class|series|gb|tb|unlocked|verizon|at&t|t-mobile)\b", color):
            attrs["hhp_color"] = color
        elif color and len(color.split()) <= 4:
            attrs["hhp_color"] = color
    return attrs


def hhp_attributes_from_product(product, product_name):
    attrs = hhp_attributes_from_name(product_name)
    color = first_path([product], ["color", "displayName"])
    if color:
        attrs["hhp_color"] = color
    spec_candidates = {
        "hhp_storage": ["Internal Storage", "Storage Capacity", "Built-In Storage", "Total Storage Capacity"],
        "hhp_color": ["Color", "Color Category"],
        "hhp_carrier": ["Carrier", "Wireless Carrier"],
    }
    for field, names in spec_candidates.items():
        if attrs.get(field):
            continue
        for name in names:
            value = spec_value([product], name)
            if value:
                attrs[field] = clean_hhp_carrier(value) if field == "hhp_carrier" else compact_text(value)
                break
    storage = (
        spec_value([product], "Internal Storage")
        or spec_value([product], "Storage Capacity")
        or spec_value([product], "Built-In Storage")
        or spec_value([product], "Total Storage Capacity")
    )
    if storage:
        attrs["hhp_storage"] = compact_text(storage)
    return attrs


def output_product_value(target):
    category = (target.get("category_key") or CATEGORY).strip().upper()
    return "HHP" if category == "HHP" else category.lower()


def output_page_type(target):
    value = str(target.get("page_type") or "").strip().lower()
    if value in {"main", "bsr", "promotion", "trend"}:
        return value
    return "bsr" if target.get("target_source") == "bsr_only_backfill" else "main"


def money(value):
    if value in ("", None):
        return ""
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value)


def money_int(value):
    if value in ("", None):
        return ""
    try:
        return f"${int(round(float(value))):,}"
    except (TypeError, ValueError):
        return str(value)


def int_commas(value):
    if value in ("", None):
        return ""
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value)


def date_to_phrase(prefix, date_value):
    if not date_value:
        return ""
    try:
        dt = datetime.fromisoformat(str(date_value)[:10])
    except ValueError:
        return ""
    return f"{prefix} {dt.strftime('%a, %b')} {dt.day}"


def date_to_relative_or_phrase(prefix, date_value):
    if not date_value:
        return ""
    try:
        dt = datetime.fromisoformat(str(date_value)[:10])
    except ValueError:
        return ""
    today = datetime.now().date()
    target = dt.date()
    if target == today:
        return f"{prefix} today"
    if (target - today).days == 1:
        return f"{prefix} tomorrow"
    return f"{prefix} {dt.strftime('%a, %b')} {dt.day}"


def html_match(pattern, html_text, flags=re.I | re.S):
    match = re.search(pattern, html_text, flags)
    return compact_text(match.group(1)) if match else ""


def recommendation_from_html(html_text):
    match = re.search(
        r"<span[^>]*>\s*(\d+%)\s*</span>\s*&nbsp;\s*would recommend to a friend",
        html_text,
        re.I | re.S,
    )
    if match:
        return f"{match.group(1)} would recommend to a friend"
    return html_match(r"(\d+%\s*would recommend to a friend)", html_text)


def fastest_delivery_from_html(html_text):
    for pattern in (r'aria-label="(Get it[^"]+)"', r">\s*(Get it[^<]+)</"):
        value = html_match(pattern, html_text)
        if value and value.lower().startswith("get"):
            return compact_text(value)
    return ""


def delivery_from_html(html_text):
    value = html_match(r'aria-label="(Delivery\s+As soon as[^"]+)"', html_text) or html_match(
        r">\s*(Delivery\s+as soon as[^<]+)</",
        html_text,
    )
    return compact_text(value).replace("Delivery As soon as", "Delivery as soon as")


def clean_energy(value):
    match = re.search(r"\d+(?:\.\d+)?", str(value or ""))
    return match.group(0) if match else ""


def quote_ident(value):
    return '"' + str(value).replace('"', '""') + '"'


@lru_cache(maxsize=32)
def detail_selectors(category):
    config = db_config()
    if not config:
        return {}
    try:
        import psycopg2

        conn = psycopg2.connect(
            host=config.get("host"),
            port=int(config.get("port") or 5432),
            user=config.get("user"),
            password=config.get("password"),
            dbname=config.get("database"),
            connect_timeout=10,
        )
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT data_field, xpath
                    FROM public.{quote_ident(SELECTOR_TABLE)}
                    WHERE product_line = %s
                      AND account_name ILIKE %s
                      AND page_type = %s
                      AND is_active IS TRUE
                    ORDER BY id
                    """,
                    (str(category or "").upper(), "Bestbuy", "detail"),
                )
                rows = cur.fetchall()
        conn.close()
    except Exception:
        return {}

    selectors = {}
    for field, xpath in rows:
        field = str(field or "").strip()
        xpath = str(xpath or "").strip()
        if field and xpath:
            selectors.setdefault(field, []).append(xpath)
    return selectors


def xpath_text(node):
    if isinstance(node, str):
        return compact_text(node)
    if isinstance(node, bytes):
        return compact_text(node.decode("utf-8", errors="ignore"))
    if hasattr(node, "text_content"):
        return compact_text(node.text_content())
    return compact_text(node)


def eval_selector(document, xpath_expr):
    values = []
    for part in str(xpath_expr or "").split("|||"):
        expr = part.strip()
        if not expr:
            continue
        try:
            matches = document.xpath(expr)
        except Exception:
            continue
        if not isinstance(matches, list):
            matches = [matches]
        for match in matches:
            text = xpath_text(match)
            if text:
                values.append(text)
    return " ".join(dict.fromkeys(values))


def detail_selector_values(html_text):
    if not html_text:
        return {}
    selectors = detail_selectors(bestbuy_category())
    if not selectors:
        return {}
    try:
        document = lxml_html.fromstring(html_text)
    except Exception:
        return {}
    values = {}
    for field, xpaths in selectors.items():
        for xpath_expr in xpaths:
            value = eval_selector(document, xpath_expr)
            if value:
                values[field] = value
                break
    return values


def recommendation_phrase(value):
    value = compact_text(value)
    if not value:
        return ""
    if "would recommend" in value:
        return value
    match = re.search(r"\d+%", value)
    if match:
        return f"{match.group(0)} would recommend to a friend"
    if re.fullmatch(r"\d+(?:\.\d+)?", value):
        return f"{value}% would recommend to a friend"
    return value


def request_cost(headers):
    raw = headers.get("X-Request-Cost") or headers.get("x-request-cost") or "0"
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def detail_params():
    return {
        "js_render": "true",
        "premium_proxy": "true",
        "proxy_country": "us",
        "js_instructions": json.dumps(
            [
                {"wait": 2000},
                {"scroll_y": 1800},
                {"wait": 800},
                {"scroll_y": 1800},
                {"wait": 800},
                {"scroll_y": 1800},
                {"wait": 800},
                {"scroll_y": 2200},
                {"wait": 900},
                {"scroll_y": 2200},
                {"wait": 900},
                {"scroll_y": 2200},
                {"wait": 900},
                {"wait": 1500},
            ]
        ),
    }


def graphql_params():
    return {
        "custom_headers": "true",
        "premium_proxy": "true",
        "proxy_country": "us",
        "js_render": "true",
    }


def fetch_transports():
    if FETCH_MODE in {"zenrows", "zr"}:
        return ["zenrows"]
    raise RuntimeError("Best Buy detail collection is ZenRows GraphQL only. Set BESTBUY_FETCH_MODE=zenrows.")


def load_csv(path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, preferred=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = set()
    for row in rows:
        keys.update(row)
    fieldnames = [key for key in (preferred or []) if key in keys]
    fieldnames.extend(sorted(keys - set(fieldnames)))
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def read_json(path):
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except ValueError:
        return {}


def safe_part(value, default="na"):
    value = re.sub(r"[^0-9A-Za-z_-]+", "_", str(value or "").strip()).strip("_")
    return value or default


def detail_rank(target):
    if isinstance(target, dict):
        return safe_part(target.get("main_rank") or target.get("final_target_rank") or target.get("bsr_rank") or target.get("rank") or "na")
    return "na"


def existing_detail_dirs(sku):
    pattern = f"*_{safe_part(sku)}_*"
    dirs = []
    for path in RAW_DETAIL_DIR.glob(pattern):
        if path.is_dir() and (path / f"{sku}_meta.json").exists():
            dirs.append(path)
    return sorted(
        dirs,
        key=lambda path: (
            0 if path.name.endswith("_success") else 1 if path.name.endswith("_fail") else 2,
            path.name,
        ),
    )


def remove_stale_fail_dirs(existing, desired, raw_root):
    if not desired or not str(desired.name).endswith("_success"):
        return
    raw_root = raw_root.resolve()
    for old_dir in existing:
        if old_dir == desired or not old_dir.name.endswith("_fail"):
            continue
        resolved = old_dir.resolve()
        if raw_root == resolved or raw_root not in resolved.parents:
            continue
        shutil.rmtree(resolved, ignore_errors=True)


def legacy_detail_paths(sku):
    return {
        "html": RAW_DETAIL_DIR / f"{sku}.html",
        "headers": RAW_DETAIL_DIR / f"{sku}_headers.json",
        "apollo": RAW_DETAIL_DIR / f"{sku}_apollo.json",
        "meta": RAW_DETAIL_DIR / f"{sku}_meta.json",
    }


def detail_folder(sku, target=None, status=None):
    sku_part = safe_part(sku)
    desired = None
    if status:
        desired = RAW_DETAIL_DIR / f"{detail_rank(target)}_{sku_part}_{safe_part(status)}"

    existing = existing_detail_dirs(sku)
    if desired:
        if existing and desired not in existing:
            if not desired.exists():
                existing[0].rename(desired)
            else:
                for old_dir in existing:
                    if old_dir == desired:
                        continue
                    for old_file in old_dir.iterdir():
                        new_file = desired / old_file.name
                        if not new_file.exists():
                            old_file.rename(new_file)
                    try:
                        old_dir.rmdir()
                    except OSError:
                        pass
        desired.mkdir(parents=True, exist_ok=True)
        remove_stale_fail_dirs(existing_detail_dirs(sku), desired, RAW_DETAIL_DIR)
        return desired
    if existing:
        return existing[0]
    return None


def existing_review_dirs(sku):
    pattern = f"*_{safe_part(sku)}_*"
    dirs = []
    for path in RAW_REVIEW_DIR.glob(pattern):
        if path.is_dir() and (path / f"{sku}_meta.json").exists():
            dirs.append(path)
    return sorted(
        dirs,
        key=lambda path: (
            0 if path.name.endswith("_success") else 1 if path.name.endswith("_fail") else 2,
            path.name,
        ),
    )


def review_folder(sku, target=None, status=None):
    sku_part = safe_part(sku)
    desired = None
    if status:
        desired = RAW_REVIEW_DIR / f"{detail_rank(target)}_{sku_part}_{safe_part(status)}"

    existing = existing_review_dirs(sku)
    if desired:
        if existing and desired not in existing:
            if not desired.exists():
                existing[0].rename(desired)
            else:
                for old_dir in existing:
                    if old_dir == desired:
                        continue
                    for old_file in old_dir.iterdir():
                        new_file = desired / old_file.name
                        if not new_file.exists():
                            old_file.rename(new_file)
                    try:
                        old_dir.rmdir()
                    except OSError:
                        pass
        desired.mkdir(parents=True, exist_ok=True)
        remove_stale_fail_dirs(existing_review_dirs(sku), desired, RAW_REVIEW_DIR)
        return desired
    if existing:
        return existing[0]
    return None


def existing_compare_dirs(sku):
    pattern = f"*_{safe_part(sku)}_*"
    dirs = []
    for path in RAW_COMPARE_DIR.glob(pattern):
        if path.is_dir() and (path / f"{sku}_meta.json").exists():
            dirs.append(path)
    return sorted(
        dirs,
        key=lambda path: (
            0 if path.name.endswith("_success") else 1 if path.name.endswith("_fail") else 2,
            path.name,
        ),
    )


def compare_folder(sku, target=None, status=None):
    sku_part = safe_part(sku)
    desired = None
    if status:
        desired = RAW_COMPARE_DIR / f"{detail_rank(target)}_{sku_part}_{safe_part(status)}"

    existing = existing_compare_dirs(sku)
    if desired:
        if existing and desired not in existing:
            if not desired.exists():
                existing[0].rename(desired)
            else:
                for old_dir in existing:
                    if old_dir == desired:
                        continue
                    for old_file in old_dir.iterdir():
                        new_file = desired / old_file.name
                        if not new_file.exists():
                            old_file.rename(new_file)
                    try:
                        old_dir.rmdir()
                    except OSError:
                        pass
        desired.mkdir(parents=True, exist_ok=True)
        remove_stale_fail_dirs(existing_compare_dirs(sku), desired, RAW_COMPARE_DIR)
        return desired
    if existing:
        return existing[0]
    return None


def detail_paths(sku):
    folder = detail_folder(sku)
    if folder:
        return {
            "html": folder / f"{sku}.html",
            "headers": folder / f"{sku}_headers.json",
            "apollo": folder / f"{sku}_apollo.json",
            "meta": folder / f"{sku}_meta.json",
        }
    legacy = legacy_detail_paths(sku)
    if any(path.exists() for path in legacy.values()):
        return legacy
    folder = RAW_DETAIL_DIR / f"na_{safe_part(sku)}_pending"
    return {
        "html": folder / f"{sku}.html",
        "headers": folder / f"{sku}_headers.json",
        "apollo": folder / f"{sku}_apollo.json",
        "meta": folder / f"{sku}_meta.json",
    }


def detail_paths_for_status(sku, target, success):
    folder = detail_folder(sku, target, "success" if success else "fail")
    return {
        "html": folder / f"{sku}.html",
        "headers": folder / f"{sku}_headers.json",
        "apollo": folder / f"{sku}_apollo.json",
        "meta": folder / f"{sku}_meta.json",
    }


def review_paths(sku):
    folder = review_folder(sku)
    if folder:
        return {
            "request": folder / f"{sku}_request.json",
            "response_txt": folder / f"{sku}_response.txt",
            "response_json": folder / f"{sku}_response.json",
            "headers": folder / f"{sku}_headers.json",
            "meta": folder / f"{sku}_meta.json",
        }
    legacy = {
        "request": RAW_REVIEW_DIR / f"{sku}_request.json",
        "response_txt": RAW_REVIEW_DIR / f"{sku}_response.txt",
        "response_json": RAW_REVIEW_DIR / f"{sku}_response.json",
        "headers": RAW_REVIEW_DIR / f"{sku}_headers.json",
        "meta": RAW_REVIEW_DIR / f"{sku}_meta.json",
    }
    if any(path.exists() for path in legacy.values()):
        return legacy
    folder = RAW_REVIEW_DIR / f"na_{safe_part(sku)}_pending"
    return {
        "request": folder / f"{sku}_request.json",
        "response_txt": folder / f"{sku}_response.txt",
        "response_json": folder / f"{sku}_response.json",
        "headers": folder / f"{sku}_headers.json",
        "meta": folder / f"{sku}_meta.json",
    }


def review_paths_for_status(sku, target, success):
    folder = review_folder(sku, target, "success" if success else "fail")
    return {
        "request": folder / f"{sku}_request.json",
        "response_txt": folder / f"{sku}_response.txt",
        "response_json": folder / f"{sku}_response.json",
        "headers": folder / f"{sku}_headers.json",
        "meta": folder / f"{sku}_meta.json",
    }


def compare_paths(sku):
    folder = compare_folder(sku)
    if folder:
        return {
            "request": folder / f"{sku}_request.json",
            "response_txt": folder / f"{sku}_response.txt",
            "response_json": folder / f"{sku}_response.json",
            "headers": folder / f"{sku}_headers.json",
            "meta": folder / f"{sku}_meta.json",
        }
    folder = RAW_COMPARE_DIR / f"na_{safe_part(sku)}_pending"
    return {
        "request": folder / f"{sku}_request.json",
        "response_txt": folder / f"{sku}_response.txt",
        "response_json": folder / f"{sku}_response.json",
        "headers": folder / f"{sku}_headers.json",
        "meta": folder / f"{sku}_meta.json",
    }


def compare_paths_for_status(sku, target, success):
    folder = compare_folder(sku, target, "success" if success else "fail")
    return {
        "request": folder / f"{sku}_request.json",
        "response_txt": folder / f"{sku}_response.txt",
        "response_json": folder / f"{sku}_response.json",
        "headers": folder / f"{sku}_headers.json",
        "meta": folder / f"{sku}_meta.json",
    }


def target_url(target, sku):
    url = str(target.get("product_url") or "").strip()
    # PDP URL fallback is intentionally disabled for sponsored enrichment.
    # Sponsored rows should be resolved first via productsBySkuIds in step02.
    # Keep this only as a last-resort detail/review fallback for explicit PDP runs.
    return url or old_pdp_url(sku)


def has_product_schema(html_text):
    return "ProductSchema_init" in html_text and "productBySkuId" in html_text


def apollo_payloads_json(html_text):
    try:
        return extract_apollo_payloads(html_text)
    except Exception:
        return []


def slim_html(html_text):
    soup = BeautifulSoup(html_text or "", "html.parser")
    for tag in soup.find_all(["style", "link", "svg", "noscript", "iframe"]):
        tag.decompose()
    for script in list(soup.find_all("script")):
        script_type = (script.get("type") or "").lower()
        text = script.string or script.get_text() or ""
        keep = "ApolloSSRDataTransport" not in text and script_type == "application/ld+json"
        if not keep:
            script.decompose()
            continue
        for attr in list(script.attrs):
            if attr not in {"type", "id"}:
                del script.attrs[attr]
    return str(soup)


def stored_html(html_text):
    if SAVE_HTML_MODE == "none":
        return ""
    if SAVE_HTML_MODE == "full":
        return html_text
    return slim_html(html_text)


def write_detail_artifacts(paths, html_text, headers):
    payloads = apollo_payloads_json(html_text)
    paths["apollo"].write_text(json.dumps(payloads, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    stored = stored_html(html_text)
    if SAVE_HTML_MODE == "none":
        if paths["html"].exists():
            paths["html"].unlink()
    else:
        paths["html"].write_text(stored, encoding="utf-8", errors="replace")
    paths["headers"].write_text(json.dumps(headers, indent=2, ensure_ascii=False), encoding="utf-8")
    return {
        "html_mode": SAVE_HTML_MODE,
        "full_bytes": len(html_text or ""),
        "stored_bytes": len(stored or ""),
        "apollo_payload_count": len(payloads),
    }


def detail_success(sku):
    paths = detail_paths(sku)
    meta = read_json(paths["meta"])
    if meta.get("success") is True and (paths["apollo"].exists() or paths["html"].exists()):
        return True
    return False


def review_success(sku):
    paths = review_paths(sku)
    meta = read_json(paths["meta"])
    if meta.get("success") is True and paths["response_json"].exists():
        return True
    if review_result_count(paths["response_json"]) is not None:
        return True
    return False


def review_result_count(path):
    data = read_json(path)
    return review_result_count_from_json(data)


def review_result_count_from_json(data):
    product = ((data.get("data") or {}).get("productBySkuId") or {})
    reviews = (product.get("reviews") or {}).get("results")
    if isinstance(reviews, list):
        return len(reviews)
    return None


def attempts(meta_path):
    return int(read_json(meta_path).get("attempt", 0) or 0)


def next_attempt(meta_path, url):
    meta = read_json(meta_path)
    previous_url = str(meta.get("url") or "").strip()
    if previous_url and previous_url != str(url or "").strip():
        return 1
    return int(meta.get("attempt", 0) or 0) + 1


def target_rows(apply_filters=True):
    rows = load_csv(TARGET_CSV)
    unique = []
    seen = set()
    for row in rows:
        sku = str(row.get("sku_id") or "").strip()
        if not sku or sku in seen:
            continue
        seen.add(sku)
        unique.append(row)
    if apply_filters and RETRY_ONLY:
        if STAGE == "detail":
            unique = [row for row in unique if not detail_success(row["sku_id"])]
        elif STAGE == "review":
            unique = [
                row
                for row in unique
                if detail_success(row["sku_id"])
                and review20_required_for_target(row, row["sku_id"])
                and not review_success(row["sku_id"])
            ]
        else:
            unique = [
                row
                for row in unique
                if not detail_success(row["sku_id"])
                or (review20_required_for_target(row, row["sku_id"]) and not review_success(row["sku_id"]))
            ]
    if apply_filters and LIMIT:
        unique = unique[:LIMIT]
    return unique


def find_started_operation(html_text, operation_name):
    for payload in extract_apollo_payloads(html_text):
        for event in payload.get("events", []):
            if event.get("type") != "started":
                continue
            options = event.get("options", {})
            query = options.get("query") or ""
            if query.startswith(f"query {operation_name}") or f"query {operation_name}(" in query:
                return {
                    "operationName": operation_name,
                    "variables": options.get("variables", {}),
                    "query": query,
                }
    return None


def find_started_operation_from_payloads(payloads, operation_name):
    for payload in payloads:
        for event in payload.get("events", []):
            if event.get("type") != "started":
                continue
            options = event.get("options", {})
            query = options.get("query") or ""
            if query.startswith(f"query {operation_name}") or f"query {operation_name}(" in query:
                return {
                    "operationName": operation_name,
                    "variables": options.get("variables", {}),
                    "query": query,
                }
    return None


def operation_name(event):
    options = event.get("options", {}) if isinstance(event, dict) else {}
    query = options.get("query") or ""
    if not isinstance(query, str):
        return ""
    match = re.search(r"\bquery\s+([A-Za-z0-9_]+)", query)
    return match.group(1) if match else ""


def event_variables(event):
    options = event.get("options", {}) if isinstance(event, dict) else {}
    variables = options.get("variables") or {}
    return variables if isinstance(variables, dict) else {}


def product_short_name(product):
    return ((product or {}).get("name") or {}).get("short") or ""


def review20_payload(html_text):
    payload = find_started_operation(html_text, "ProductSchema_init")
    if not payload:
        return None
    apply_bestbuy_location(payload.get("variables", {}))
    payload["query"] = payload["query"].replace("reviews(filter:{pageSize:5})", "reviews(filter:{pageSize:20})")
    return payload


DETAIL_PRODUCT_QUERY = """
query BestBuyDetailGraphqlOnly(
  $skuId: String!
  $fulfillmentInput: ProductFulfillmentInput!
  $productPriceInput: ProductItemPriceInput!
  $placement: String!
  $site: String!
  $limit: Int!
) {
  productBySkuId(skuId: $skuId) {
    skuId
    bsin
    brand
    name { short }
    url { pdp relativePdp skuSpecificUrl }
    color { displayName }
    reviewInfo {
      averageRating
      reviewCount
      recommendedPercent
      reviewSummary
      conFeatures { name }
      proFeatures { name }
      syndicatedReviewSummary { clientDisplayName overallRating totalReviewCount }
    }
    price(input: $productPriceInput) {
      displayableCustomerPrice
      displayableRegularPrice
      customerPrice
      currentPrice
      regularPrice
      totalSavings
      totalSavingsPercent
      preferredBadging
      puckDisplayMessage
    }
    specificationGroups { name specifications { definition displayName value } }
    productVariationDetailDisplay {
      productVariations {
        shortName
        color
        colorCategory
        sku
        variations { rawName value }
      }
    }
    fulfillmentOptions(input: $fulfillmentInput) {
      buttonStates { buttonState displayText secondaryButtonState secondaryDisplayText }
      ispuDetails {
        ispuAvailability {
          pickupEligible
          maxDate
          fulfillDate
          promiseByStreetDate
        }
      }
      deliveryDetails {
        deliveryAvailability {
          deliveryEligible
          deliverySlots { date }
        }
      }
      shippingDetails {
        shippingAvailability {
          shippingEligible
          promiseByStreetDate
          defaultCustomerLosGroupId
          customerLOSGroup {
            customerLosGroupId
            minLineItemMaxDate
            maxLineItemMaxDate
            price
          }
        }
      }
    }
    operationalAttributes { values }
    badgesV2 { badgeId label type description }
    badges { displayName typeCode }
    offers { offers { offerId offerType hotOffer complexMemberOffer } }
    buyingOptions { type description pdpUrl skuId }
    isConstrainedHighVelocity
    isPurchaseWithTradeInEligible
    connectionType { code }
    openBoxCondition
  }
  versionedJsonByKey(key: "trade-in-call-to-action") { json }
  recommendations(filter: {placement: $placement, site: $site, limit: $limit, skus: [$skuId]}) {
    subPlacements {
      recommendations {
        item {
          ... on Product {
            skuId
            name { short }
            url { relativePdp }
            reviewInfo { averageRating reviewCount }
            specificationGroups { name specifications { definition displayName value } }
          }
        }
      }
    }
  }
}
""".strip()


def detail_product_payload(sku):
    zip_code = str(bestbuy_zip_code())
    store_id = str(bestbuy_store_id())
    return {
        "operationName": "BestBuyDetailGraphqlOnly",
        "variables": {
            "skuId": str(sku),
            "fulfillmentInput": {
                "shipping": {"destinationZipCode": zip_code, "effectivePlanPaidMembership": "NULL"},
                "delivery": {
                    "destinationZipCode": zip_code,
                    "deliveryDateOption": "EARLIEST_AVAILABLE_DATE",
                    "effectivePlanPaidMembership": "NULL",
                },
                "inStorePickup": {"storeId": store_id, "searchNearby": True, "showNearbyLocations": False},
                "profileCode": None,
                "buttonState": {
                    "fulfillmentOption": None,
                    "context": "PDP",
                    "destinationZipCode": zip_code,
                    "storeId": store_id,
                    "effectivePlanPaidMembership": "NULL",
                },
            },
            "productPriceInput": {
                "customerAttributes": "",
                "salesChannel": "LargeView",
                "customerId": None,
                "planPaidMemberType": "NULL",
                "ct": "",
                "isStoreAgent": False,
                "locationId": "",
            },
            "placement": "single-compare",
            "site": "dotcom-l",
            "limit": 3,
        },
        "extensions": {"clientLibrary": {"name": "@apollo/client", "version": "4.1.6"}},
        "query": DETAIL_PRODUCT_QUERY,
    }


def batch_graphql_inputs():
    zip_code = str(bestbuy_zip_code())
    store_id = str(bestbuy_store_id())
    fulfillment_input = (
        f'{{shipping:{{destinationZipCode:"{zip_code}",effectivePlanPaidMembership:"NULL"}},'
        f'delivery:{{destinationZipCode:"{zip_code}",deliveryDateOption:EARLIEST_AVAILABLE_DATE,effectivePlanPaidMembership:"NULL"}},'
        f'inStorePickup:{{storeId:"{store_id}",searchNearby:true,showNearbyLocations:false}},'
        f'profileCode:null,'
        f'buttonState:{{fulfillmentOption:null,context:PDP,destinationZipCode:"{zip_code}",storeId:"{store_id}",effectivePlanPaidMembership:"NULL"}}}}'
    )
    price_input = (
        '{customerAttributes:"",salesChannel:"LargeView",customerId:null,'
        'planPaidMemberType:"NULL",ct:"",isStoreAgent:false,locationId:""}'
    )
    return fulfillment_input, price_input


def batch_product_block(alias, sku, fulfillment_input, price_input):
    return f'''
  {alias}: productBySkuId(skuId: "{sku}") {{
    skuId
    bsin
    brand
    name {{ short }}
    url {{ pdp relativePdp skuSpecificUrl }}
    color {{ displayName }}
    reviewInfo {{
      averageRating
      reviewCount
      recommendedPercent
      reviewSummary
      conFeatures {{ name }}
      proFeatures {{ name }}
      syndicatedReviewSummary {{ clientDisplayName overallRating totalReviewCount }}
    }}
    reviews(filter: {{page: 1, pageSize: 20, sortBy: BEST_MATCH}}) {{
      results {{ rating title text userNickname submissionTime }}
    }}
    price(input: {price_input}) {{
      displayableCustomerPrice
      displayableRegularPrice
      customerPrice
      currentPrice
      regularPrice
      totalSavings
      totalSavingsPercent
      preferredBadging
      puckDisplayMessage
    }}
    specificationGroups {{ name specifications {{ definition displayName value }} }}
    productVariationDetailDisplay {{
      productVariations {{
        shortName
        color
        colorCategory
        sku
        variations {{ rawName value }}
      }}
    }}
    fulfillmentOptions(input: {fulfillment_input}) {{
      buttonStates {{ buttonState displayText secondaryButtonState secondaryDisplayText }}
      ispuDetails {{
        ispuAvailability {{
          pickupEligible
          maxDate
          fulfillDate
          promiseByStreetDate
        }}
      }}
      deliveryDetails {{
        deliveryAvailability {{
          deliveryEligible
          deliverySlots {{ date }}
        }}
      }}
      shippingDetails {{
        shippingAvailability {{
          shippingEligible
          promiseByStreetDate
          defaultCustomerLosGroupId
          customerLOSGroup {{
            customerLosGroupId
            minLineItemMaxDate
            maxLineItemMaxDate
            price
          }}
        }}
      }}
    }}
    operationalAttributes {{ values }}
    badgesV2 {{ badgeId label type description }}
    badges {{ displayName typeCode }}
    offers {{ offers {{ offerId offerType hotOffer complexMemberOffer }} }}
    buyingOptions {{ type description pdpUrl skuId }}
    isConstrainedHighVelocity
    isPurchaseWithTradeInEligible
    connectionType {{ code }}
    openBoxCondition
  }}'''


def batch_recommendations_block(alias, sku):
    return f'''
  {alias}: recommendations(filter: {{placement: "single-compare", site: "dotcom-l", limit: 3, skus: ["{sku}"]}}) {{
    subPlacements {{
      recommendations {{
        item {{
          ... on Product {{
            description {{ long }}
            name {{ short }}
            primaryImage {{ piscesHref }}
            reviewInfo {{ averageRating reviewCount conFeatures {{ name }} proFeatures {{ name }} }}
            specificationGroups {{ name specifications {{ definition displayName value }} }}
            url {{ relativePdp }}
            skuId
            openBoxCondition
          }}
        }}
      }}
    }}
  }}'''


def detail_review_compare_batch_payload(skus):
    fulfillment_input, price_input = batch_graphql_inputs()
    chunks = ['  tradeInContent: versionedJsonByKey(key: "trade-in-call-to-action") { json }']
    for index, sku in enumerate(skus):
        chunks.append(batch_product_block(f"p{index}", sku, fulfillment_input, price_input))
        if FETCH_COMPARE:
            chunks.append(batch_recommendations_block(f"r{index}", sku))
    return {
        "operationName": "BestBuyDetailReviewCompareBatch",
        "variables": {},
        "extensions": {"clientLibrary": {"name": "@apollo/client", "version": "4.1.6"}},
        "query": "query BestBuyDetailReviewCompareBatch {\n" + "\n".join(chunks) + "\n}",
    }


def apollo_events_from_graphql_response(response_json):
    return [
        {
            "events": [
                {
                    "type": "next",
                    "value": {"data": response_json.get("data", {}) if isinstance(response_json, dict) else {}},
                }
            ]
        }
    ]


REVIEW20_QUERY = """
query BestBuyReview20GraphqlOnly($skuId: String!) {
  productBySkuId(skuId: $skuId) {
    skuId
    reviews(filter: {page: 1, pageSize: 20, sortBy: BEST_MATCH}) {
      results { rating title text userNickname submissionTime }
    }
  }
}
""".strip()


def review20_direct_payload(sku):
    return {
        "operationName": "BestBuyReview20GraphqlOnly",
        "variables": {"skuId": str(sku)},
        "extensions": {"clientLibrary": {"name": "@apollo/client", "version": "4.1.6"}},
        "query": REVIEW20_QUERY,
    }


COMPARE_PRODUCT_QUERY = """
query GetCompareProduct($placement: String!, $site: String!, $limit: Int!, $skuId: String!) {
  productBySkuId(skuId: $skuId) {
    description { long }
    name { short }
    primaryImage { piscesHref }
    reviewInfo { averageRating reviewCount conFeatures { name } proFeatures { name } }
    specificationGroups { name specifications { definition displayName value } }
    url { relativePdp }
    skuId
    openBoxCondition
  }
  recommendations(filter: {placement: $placement, site: $site, limit: $limit, skus: [$skuId]}) {
    subPlacements {
      recommendations {
        ep
        id
        item {
          ... on Product {
            description { long }
            name { short }
            primaryImage { piscesHref }
            reviewInfo { averageRating reviewCount conFeatures { name } proFeatures { name } }
            specificationGroups { name specifications { definition displayName value } }
            url { relativePdp }
            skuId
            openBoxCondition
          }
        }
      }
      ep
      id
      name
    }
  }
}
""".strip()


def compare_product_payload(sku):
    return {
        "operationName": "GetCompareProduct",
        "variables": {
            "placement": "single-compare",
            "site": "dotcom-l",
            "limit": 3,
            "skuId": str(sku),
        },
        "extensions": {"clientLibrary": {"name": "@apollo/client", "version": "4.1.6"}},
        "query": COMPARE_PRODUCT_QUERY,
    }


def chunked(items, size):
    for index in range(0, len(items), size):
        yield items[index : index + size]


def batch_response_for_product(response_json, alias):
    data = response_json.get("data") if isinstance(response_json, dict) else {}
    product = data.get(alias) if isinstance(data, dict) else None
    return {"data": {"productBySkuId": product}} if isinstance(product, dict) else {}


def batch_response_for_compare(response_json, product_alias, recommendation_alias):
    data = response_json.get("data") if isinstance(response_json, dict) else {}
    if not isinstance(data, dict):
        return {}
    product = data.get(product_alias)
    recommendations = data.get(recommendation_alias)
    out = {"data": {}}
    if isinstance(product, dict):
        out["data"]["productBySkuId"] = product
    if isinstance(recommendations, dict):
        out["data"]["recommendations"] = recommendations
    return out


def write_batch_detail_result(target, sku, response_json, headers, request_payload, base_meta):
    product_alias = base_meta["product_alias"]
    single_json = batch_response_for_product(response_json, product_alias)
    product = ((single_json.get("data") or {}).get("productBySkuId") or {})
    success = isinstance(product, dict) and str(product.get("skuId") or "") == str(sku)
    paths = detail_paths_for_status(sku, target, success)
    paths["apollo"].write_text(
        json.dumps(apollo_events_from_graphql_response(single_json), ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    paths["headers"].write_text(json.dumps(headers, indent=2, ensure_ascii=False), encoding="utf-8")
    if paths["html"].exists():
        paths["html"].unlink()
    meta = {
        "sku_id": sku,
        "stage": "detail",
        "url": target_url(target, sku),
        "attempt": base_meta["attempt"],
        "started_at": base_meta["started_at"],
        "success": success,
        "status_code": base_meta["status_code"],
        "transport": base_meta["transport"],
        "fetch_mode": FETCH_MODE,
        "batch_fetch": True,
        "batch_size": base_meta["batch_size"],
        "elapsed_seconds": base_meta["elapsed_seconds"],
        "x_request_cost": base_meta["x_request_cost"],
        "bytes": base_meta["bytes"],
        "stored_bytes": 0,
        "html_mode": "graphql_only",
        "apollo_payload_count": 1 if single_json else 0,
        "finished_at": base_meta["finished_at"],
        "error": "" if success else (base_meta.get("error") or "detail_graphql_missing_product"),
    }
    paths["meta"].write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return meta


def write_batch_review_result(target, sku, response_json, headers, request_payload, base_meta):
    product_alias = base_meta["product_alias"]
    single_json = batch_response_for_product(response_json, product_alias)
    review_count = review_result_count_from_json(single_json)
    success = review_count is not None
    paths = review_paths_for_status(sku, target, success)
    paths["response_json"].write_text(json.dumps(single_json, indent=2, ensure_ascii=False), encoding="utf-8")
    paths["response_txt"].write_text(json.dumps(single_json, ensure_ascii=False), encoding="utf-8", errors="replace")
    paths["headers"].write_text(json.dumps(headers, indent=2, ensure_ascii=False), encoding="utf-8")
    paths["request"].write_text(json.dumps(request_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    meta = {
        "sku_id": sku,
        "stage": "review20",
        "url": target_url(target, sku),
        "attempt": base_meta["attempt"],
        "started_at": base_meta["started_at"],
        "success": success,
        "status_code": base_meta["status_code"],
        "transport": base_meta["transport"],
        "fetch_mode": FETCH_MODE,
        "batch_fetch": True,
        "batch_size": base_meta["batch_size"],
        "elapsed_seconds": base_meta["elapsed_seconds"],
        "x_request_cost": 0,
        "bytes": len(json.dumps(single_json, ensure_ascii=False)),
        "review_count_returned": review_count if review_count is not None else 0,
        "finished_at": base_meta["finished_at"],
        "error": "" if success else (base_meta.get("error") or "review20_missing_results"),
    }
    paths["meta"].write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return meta


def write_batch_compare_result(target, sku, response_json, headers, request_payload, base_meta):
    product_alias = base_meta["product_alias"]
    recommendation_alias = base_meta["recommendation_alias"]
    single_json = batch_response_for_compare(response_json, product_alias, recommendation_alias)
    data = single_json.get("data") if isinstance(single_json, dict) else {}
    recommendations = first_path([data], ["recommendations", "subPlacements", 0, "recommendations"]) or []
    success = isinstance(data, dict) and isinstance(recommendations, list)
    paths = compare_paths_for_status(sku, target, success)
    paths["response_json"].write_text(json.dumps(single_json, indent=2, ensure_ascii=False), encoding="utf-8")
    paths["response_txt"].write_text(json.dumps(single_json, ensure_ascii=False), encoding="utf-8", errors="replace")
    paths["headers"].write_text(json.dumps(headers, indent=2, ensure_ascii=False), encoding="utf-8")
    paths["request"].write_text(json.dumps(request_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    meta = {
        "sku_id": sku,
        "stage": "compare",
        "url": target_url(target, sku),
        "attempt": base_meta["attempt"],
        "started_at": base_meta["started_at"],
        "success": success,
        "status_code": base_meta["status_code"],
        "transport": base_meta["transport"],
        "fetch_mode": FETCH_MODE,
        "batch_fetch": True,
        "batch_size": base_meta["batch_size"],
        "elapsed_seconds": base_meta["elapsed_seconds"],
        "x_request_cost": 0,
        "bytes": len(json.dumps(single_json, ensure_ascii=False)),
        "recommendation_count": len(recommendations) if isinstance(recommendations, list) else 0,
        "finished_at": base_meta["finished_at"],
        "error": "" if success else (base_meta.get("error") or "compare_recommendations_missing"),
    }
    paths["meta"].write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return meta


def fetch_detail_review_compare_batch(client, batch_targets):
    skus = [str(target.get("sku_id") or "").strip() for target in batch_targets]
    payload = detail_review_compare_batch_payload(skus)
    started = now()
    for transport in fetch_transports():
        if transport == "zenrows" and not client:
            continue
        start = time.perf_counter()
        try:
            response = client.post(
                "https://www.bestbuy.com/gateway/graphql",
                params=graphql_params(),
                headers={
                    "accept": "application/json, text/plain, */*",
                    "content-type": "application/json",
                    "origin": "https://www.bestbuy.com",
                    "referer": target_url(batch_targets[0], skus[0]) if batch_targets else "https://www.bestbuy.com/",
                },
                data=json.dumps(payload),
                timeout=REQUEST_TIMEOUT,
            )
            elapsed = round(time.perf_counter() - start, 3)
            response_json = {}
            error = ""
            try:
                response_json = response.json()
                if response_json.get("errors"):
                    error = json.dumps(response_json.get("errors"), ensure_ascii=False, separators=(",", ":"))
            except ValueError as exc:
                error = str(exc)
            if response.status_code != 200 or not isinstance(response_json.get("data"), dict):
                return [], request_cost(response.headers), error or "batch_graphql_missing_data"
            cost = request_cost(response.headers)
            per_sku_cost = round(cost / max(len(skus), 1), 7)
            results = []
            finished = now()
            headers = dict(response.headers)
            for index, target in enumerate(batch_targets):
                sku = skus[index]
                base_meta = {
                    "attempt": next_attempt(detail_paths(sku)["meta"], target_url(target, sku)),
                    "started_at": started,
                    "finished_at": finished,
                    "status_code": response.status_code,
                    "transport": transport,
                    "batch_size": len(batch_targets),
                    "elapsed_seconds": elapsed,
                    "x_request_cost": per_sku_cost,
                    "bytes": len(response.text or ""),
                    "error": error,
                    "product_alias": f"p{index}",
                    "recommendation_alias": f"r{index}",
                }
                dmeta = write_batch_detail_result(target, sku, response_json, headers, payload, base_meta)
                rmeta = read_json(review_paths(sku)["meta"])
                cmeta = compare_meta(sku)
                if review20_required_for_target(target, sku) and not review_success(sku):
                    rmeta = write_batch_review_result(target, sku, response_json, headers, payload, base_meta)
                if FETCH_COMPARE and dmeta.get("success") and not compare_success(sku):
                    cmeta = write_batch_compare_result(target, sku, response_json, headers, payload, base_meta)
                results.append((sku, dmeta, rmeta, cmeta))
            return results, cost, ""
        except RequestException as exc:
            return [], 0.0, str(exc)
    return [], 0.0, "no_available_transport"


def detail_payloads(sku):
    paths = detail_paths(sku)
    if paths.get("apollo") and paths["apollo"].exists():
        try:
            data = json.loads(paths["apollo"].read_text(encoding="utf-8-sig"))
            if isinstance(data, list):
                return data
        except ValueError:
            pass
    html_path = paths["html"]
    html_text = html_path.read_text(encoding="utf-8", errors="replace") if html_path.exists() else ""
    return apollo_payloads_json(html_text)


def review20_payload_for_sku(sku):
    if os.getenv("BESTBUY_GRAPHQL_ONLY", "0").lower() in {"1", "true", "yes", "y"}:
        return review20_direct_payload(sku)
    payload = find_started_operation_from_payloads(detail_payloads(sku), "ProductSchema_init")
    if not payload:
        return None
    apply_bestbuy_location(payload.get("variables", {}))
    payload["query"] = payload["query"].replace("reviews(filter:{pageSize:5})", "reviews(filter:{pageSize:20})")
    return payload


def fetch_detail(client, target):
    sku = str(target.get("sku_id") or "").strip()
    pdp_url = target_url(target, sku)
    current_paths = detail_paths(sku)
    if detail_success(sku):
        return read_json(current_paths["meta"])
    attempt = next_attempt(current_paths["meta"], pdp_url)
    meta = {"sku_id": sku, "stage": "detail", "url": pdp_url, "attempt": attempt, "started_at": now()}
    if attempt > MAX_ATTEMPTS:
        paths = detail_paths_for_status(sku, target, False)
        meta.update({"success": False, "error": "max_attempts_exceeded"})
        paths["meta"].write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        return meta

    paths = detail_paths_for_status(sku, target, False)
    for transport in fetch_transports():
        if transport == "zenrows" and not client:
            continue
        start = time.perf_counter()
        try:
            response = client.get(pdp_url, params=detail_params(), timeout=REQUEST_TIMEOUT)
            html_text = response.text
            status = response.status_code
            success = status == 200 and has_product_schema(html_text)
            paths = detail_paths_for_status(sku, target, success)
            artifact_meta = write_detail_artifacts(paths, html_text, dict(response.headers))
            meta.update(
                {
                    "success": success,
                    "status_code": status,
                    "transport": transport,
                    "fetch_mode": FETCH_MODE,
                    "elapsed_seconds": round(time.perf_counter() - start, 3),
                    "x_request_cost": request_cost(response.headers),
                    "bytes": artifact_meta["full_bytes"],
                    "stored_bytes": artifact_meta["stored_bytes"],
                    "html_mode": artifact_meta["html_mode"],
                    "apollo_payload_count": artifact_meta["apollo_payload_count"],
                    "finished_at": now(),
                    "error": "" if success else "detail_html_missing_product_schema",
                }
            )
        except RequestException as exc:
            paths = detail_paths_for_status(sku, target, False)
            meta.update(
                {
                    "success": False,
                    "status_code": "ERR",
                    "transport": transport,
                    "fetch_mode": FETCH_MODE,
                    "elapsed_seconds": round(time.perf_counter() - start, 3),
                    "x_request_cost": 0,
                    "finished_at": now(),
                    "error": str(exc),
                }
            )
        if meta.get("success"):
            break
    paths["meta"].write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return meta


def fetch_review20(client, target):
    sku = str(target.get("sku_id") or "").strip()
    pdp_url = target_url(target, sku)
    current_paths = review_paths(sku)
    if review_success(sku):
        return read_json(current_paths["meta"])
    attempt = next_attempt(current_paths["meta"], pdp_url)
    meta = {"sku_id": sku, "stage": "review20", "url": pdp_url, "attempt": attempt, "started_at": now()}
    if attempt > MAX_ATTEMPTS:
        paths = review_paths_for_status(sku, target, False)
        meta.update({"success": False, "error": "max_attempts_exceeded"})
        paths["meta"].write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        return meta

    payload = review20_payload_for_sku(sku)
    if not payload:
        paths = review_paths_for_status(sku, target, False)
        meta.update({"success": False, "error": "ProductSchema_init not found", "finished_at": now()})
        paths["meta"].write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        return meta
    paths = current_paths

    for transport in fetch_transports():
        if transport == "zenrows" and not client:
            continue
        start = time.perf_counter()
        try:
            response = client.post(
                "https://www.bestbuy.com/gateway/graphql",
                params=graphql_params(),
                headers={
                    "accept": "application/json, text/plain, */*",
                    "content-type": "application/json",
                    "origin": "https://www.bestbuy.com",
                    "referer": pdp_url,
                },
                data=json.dumps(payload),
                timeout=REQUEST_TIMEOUT,
            )
        except RequestException as exc:
            paths = review_paths_for_status(sku, target, False)
            meta.update(
                {
                    "success": False,
                    "status_code": "ERR",
                    "transport": transport,
                    "fetch_mode": FETCH_MODE,
                    "elapsed_seconds": round(time.perf_counter() - start, 3),
                    "x_request_cost": 0,
                    "finished_at": now(),
                    "error": str(exc),
                }
            )
            paths["meta"].write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
            continue
        text = response.text
        review_count = 0
        error = ""
        response_json = {}
        try:
            response_json = response.json()
            count = review_result_count_from_json(response_json)
            review_count = count if count is not None else 0
            if response_json.get("errors"):
                error = json.dumps(response_json.get("errors"), ensure_ascii=False, separators=(",", ":"))
        except ValueError as exc:
            error = str(exc)
        success = response.status_code == 200 and review_result_count_from_json(response_json) is not None
        paths = review_paths_for_status(sku, target, success)
        if response_json:
            paths["response_json"].write_text(
                json.dumps(response_json, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        paths["response_txt"].write_text(text, encoding="utf-8", errors="replace")
        paths["headers"].write_text(
            json.dumps(dict(response.headers), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        paths["request"].write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        meta.update(
            {
                "success": success,
                "status_code": response.status_code,
                "transport": transport,
                "fetch_mode": FETCH_MODE,
                "elapsed_seconds": round(time.perf_counter() - start, 3),
                "x_request_cost": request_cost(response.headers),
                "bytes": len(text or ""),
                "review_count_returned": review_count,
                "finished_at": now(),
                "error": error if not success else "",
            }
        )
        if meta.get("success"):
            break
    paths["meta"].write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return meta


def compare_success(sku):
    meta = read_json(compare_paths(sku)["meta"])
    return bool(meta.get("success")) or bool(compare_data_from_detail_payloads(sku))


def compare_meta(sku):
    meta = read_json(compare_paths(sku)["meta"])
    if meta.get("success"):
        return meta
    if compare_data_from_detail_payloads(sku):
        return {
            "sku_id": sku,
            "stage": "compare",
            "success": True,
            "attempt": 0,
            "status_code": "HTML",
            "transport": "detail_html",
            "fetch_mode": FETCH_MODE,
            "x_request_cost": 0,
            "error": "",
            "source": "detail_apollo",
        }
    return meta


def fetch_compare(client, target):
    sku = str(target.get("sku_id") or "").strip()
    pdp_url = target_url(target, sku)
    current_paths = compare_paths(sku)
    if compare_success(sku):
        return read_json(current_paths["meta"])
    attempt = next_attempt(current_paths["meta"], pdp_url)
    meta = {"sku_id": sku, "stage": "compare", "url": pdp_url, "attempt": attempt, "started_at": now()}
    if attempt > MAX_ATTEMPTS:
        paths = compare_paths_for_status(sku, target, False)
        meta.update({"success": False, "error": "max_attempts_exceeded"})
        paths["meta"].write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        return meta

    payload = compare_product_payload(sku)
    paths = current_paths

    for transport in fetch_transports():
        if transport == "zenrows" and not client:
            continue
        start = time.perf_counter()
        try:
            response = client.post(
                "https://www.bestbuy.com/gateway/graphql",
                params=graphql_params(),
                headers={
                    "accept": "application/json, text/plain, */*",
                    "content-type": "application/json",
                    "origin": "https://www.bestbuy.com",
                    "referer": pdp_url,
                },
                data=json.dumps(payload),
                timeout=REQUEST_TIMEOUT,
            )
            text = response.text
            response_json = {}
            error = ""
            try:
                response_json = response.json()
            except ValueError:
                error = "invalid_json"
            data = response_json.get("data") if isinstance(response_json, dict) else {}
            recommendations = first_path([data], ["recommendations", "subPlacements", 0, "recommendations"]) or []
            success = response.status_code == 200 and isinstance(data, dict) and isinstance(recommendations, list)
            paths = compare_paths_for_status(sku, target, success)
            paths["response_txt"].write_text(text, encoding="utf-8", errors="replace")
            if response_json:
                paths["response_json"].write_text(json.dumps(response_json, indent=2, ensure_ascii=False), encoding="utf-8")
            paths["headers"].write_text(json.dumps(dict(response.headers), indent=2, ensure_ascii=False), encoding="utf-8")
            paths["request"].write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            meta.update(
                {
                    "success": success,
                    "status_code": response.status_code,
                    "transport": transport,
                    "fetch_mode": FETCH_MODE,
                    "elapsed_seconds": round(time.perf_counter() - start, 3),
                    "x_request_cost": request_cost(response.headers),
                    "bytes": len(text or ""),
                    "recommendation_count": len(recommendations) if isinstance(recommendations, list) else 0,
                    "finished_at": now(),
                    "error": "" if success else (error or "compare_recommendations_missing"),
                }
            )
        except RequestException as exc:
            paths = compare_paths_for_status(sku, target, False)
            meta.update(
                {
                    "success": False,
                    "status_code": "ERR",
                    "transport": transport,
                    "fetch_mode": FETCH_MODE,
                    "elapsed_seconds": round(time.perf_counter() - start, 3),
                    "x_request_cost": 0,
                    "finished_at": now(),
                    "error": str(exc),
                }
            )
        if meta.get("success"):
            break
    paths["meta"].write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return meta


def products_from_detail(sku):
    products = []
    for payload in detail_payloads(sku):
        for event in payload.get("events", []):
            data = event_data(event)
            product = data.get("productBySkuId") if isinstance(data, dict) else None
            if isinstance(product, dict) and str(product.get("skuId")) == str(sku):
                products.append(product)
    return products


def compare_similar_names_from_detail(sku):
    paths = compare_paths(sku)
    response_json = read_json(paths["response_json"])
    data = response_json.get("data") if isinstance(response_json, dict) else {}
    if not isinstance(data, dict) or not data:
        data = compare_data_from_detail_payloads(sku)
    if not isinstance(data, dict):
        return []

    names = []
    current = data.get("productBySkuId")
    current_name = product_short_name(current) if isinstance(current, dict) else ""
    if current_name:
        names.append(current_name)

    subplacements = first_path([data], ["recommendations", "subPlacements"]) or []
    for subplacement in subplacements:
        for recommendation in subplacement.get("recommendations") or []:
            item = recommendation.get("item") or {}
            name = product_short_name(item)
            if name and name not in names:
                names.append(name)
    return names


def compare_data_from_detail_payloads(sku):
    for payload in detail_payloads(sku):
        for event in payload.get("events", []):
            data = event_data(event)
            if not isinstance(data, dict):
                continue
            current = data.get("productBySkuId")
            recommendations = data.get("recommendations")
            if not isinstance(current, dict) or not isinstance(recommendations, dict):
                continue
            if str(current.get("skuId") or "") != str(sku):
                continue
            subplacements = recommendations.get("subPlacements")
            if isinstance(subplacements, list):
                return data
    return {}


def first_value(products, key):
    for product in reversed(products):
        value = product.get(key)
        if value not in (None, "", [], {}):
            return value
    return ""


def first_path(products, path):
    for product in reversed(products):
        current = product
        ok = True
        for part in path:
            if isinstance(part, int):
                if isinstance(current, list) and len(current) > part:
                    current = current[part]
                else:
                    ok = False
                    break
            elif isinstance(current, dict) and part in current:
                current = current[part]
            else:
                ok = False
                break
        if ok and current not in (None, "", [], {}):
            return current
    return ""


def best_path(products, path, required_keys=()):
    values = []
    for product in products:
        current = product
        ok = True
        for part in path:
            if isinstance(part, int):
                if isinstance(current, list) and len(current) > part:
                    current = current[part]
                else:
                    ok = False
                    break
            elif isinstance(current, dict) and part in current:
                current = current[part]
            else:
                ok = False
                break
        if ok and isinstance(current, dict):
            score = sum(1 for key in required_keys if current.get(key) not in (None, "", [], {}))
            values.append((score, current))
    return sorted(values, key=lambda item: item[0], reverse=True)[0][1] if values else {}


def best_shipping_availability(products):
    values = []
    for product in products:
        details = first_path([product], ["fulfillmentOptions", "shippingDetails"]) or []
        for detail in details:
            for shipping in detail.get("shippingAvailability") or []:
                if not isinstance(shipping, dict) or not shipping.get("shippingEligible"):
                    continue
                groups = shipping.get("customerLOSGroup") or []
                default_group_id = shipping.get("defaultCustomerLosGroupId")
                score = 1
                if groups:
                    score += 1
                if default_group_id not in (None, ""):
                    score += 3
                if any(isinstance(group, dict) and group.get("price") in (0, 0.0, "0", "0.0") for group in groups):
                    score += 1
                values.append((score, shipping))
    return sorted(values, key=lambda item: item[0], reverse=True)[0][1] if values else {}


def best_price(products):
    best = {}
    best_score = -1
    for product in products:
        price = product.get("price")
        if not isinstance(price, dict):
            continue
        score = sum(
            1
            for key in ("displayableCustomerPrice", "customerPrice", "displayableRegularPrice", "regularPrice", "totalSavings")
            if price.get(key) not in (None, "", [], {})
        )
        if score > best_score:
            best = price
            best_score = score
    return best


def visible_regular_price(price, target):
    regular = price.get("displayableRegularPrice") or price.get("regularPrice") or target.get("regular_price")
    customer = price.get("displayableCustomerPrice") or price.get("customerPrice") or target.get("customer_price")
    savings = price.get("totalSavings") or target.get("total_savings")
    try:
        savings_number = float(str(savings).replace("$", "").replace(",", ""))
    except (TypeError, ValueError):
        savings_number = None
    if savings_number is not None and savings_number <= 0:
        return ""
    if regular not in (None, "") and customer not in (None, ""):
        if money(regular) == money(customer):
            return ""
    return regular


def visible_savings(price, target):
    savings = price.get("totalSavings") or target.get("total_savings")
    try:
        savings_number = float(str(savings).replace("$", "").replace(",", ""))
    except (TypeError, ValueError):
        savings_number = None
    if savings_number is not None and savings_number <= 0:
        return ""
    return savings


def spec_value(products, display_name):
    for product in reversed(products):
        for group in product.get("specificationGroups") or []:
            for spec in group.get("specifications") or []:
                if (spec.get("displayName") or "").lower() == display_name.lower():
                    return spec.get("value", "")
    return ""


def offer_count(products):
    offers = first_path(products, ["offers", "offers"]) or []
    if offers:
        return str(len(offers))
    buying = first_value(products, "buyingOptions") or []
    return str(len(buying)) if buying else ""


def badge_labels(products):
    labels = []
    for product in products:
        for badge in product.get("badgesV2") or []:
            label = compact_text((badge or {}).get("label") or (badge or {}).get("description"))
            if label and label not in labels:
                labels.append(label)
        for badge in product.get("badges") or []:
            label = compact_text((badge or {}).get("displayName"))
            if label and label not in labels:
                labels.append(label)
        price = product.get("price") or {}
        for key in ("preferredBadging", "puckDisplayMessage"):
            label = compact_text(price.get(key))
            if label and label not in labels:
                labels.append(label)
    return labels


def trade_in_text_from_detail_payloads(sku, products):
    eligible = any(product.get("isPurchaseWithTradeInEligible") for product in products if isinstance(product, dict))
    content = {}
    for payload in detail_payloads(sku):
        for event in payload.get("events", []):
            data = event_data(event)
            if not isinstance(data, dict):
                continue
            versioned = data.get("versionedJsonByKey") or {}
            json_value = versioned.get("json") if isinstance(versioned, dict) else {}
            if isinstance(json_value, dict):
                content = json_value
                break
        if content:
            break
    if not eligible and not content:
        return ""

    text = json.dumps(content, ensure_ascii=False) if content else ""
    amount_match = re.search(r"\$\s?[\d,]+(?:\.\d{2})?", text)
    if amount_match:
        return f"Check your trade-in value.Save up to {amount_match.group(0).replace(' ', '')} when you trade in a similar device."
    return "Check your trade-in value.Save when you trade in a similar device." if eligible or content else ""


def promotion_type_from_products(products, trade_in=""):
    values = []
    if trade_in:
        values.append("Trade-in offer")
    for label in badge_labels(products):
        if label and label not in values:
            values.append(label)
    return " ||| ".join(values)


def recommendation(products):
    value = first_path(products, ["reviewInfo", "recommendedPercent"])
    return f"{value}% would recommend to a friend" if value not in ("", None) else ""


def review_count_number(*values):
    for value in values:
        if value in ("", None):
            continue
        text = re.sub(r"[^0-9]", "", str(value))
        if text:
            return int(text)
    return None


def has_external_review_text(*values):
    for value in values:
        text = str(value or "")
        if re.search(r"\breviews?\s+from\b", text, flags=re.IGNORECASE):
            return True
    return False


def syndicated_review_summary(review_info):
    if not isinstance(review_info, dict):
        return {}
    summary = review_info.get("syndicatedReviewSummary")
    return summary if isinstance(summary, dict) else {}


def is_external_review_source(target=None, review_info=None):
    target = target or {}
    summary = syndicated_review_summary(review_info)
    if summary:
        return True
    return has_external_review_text(
        target.get("count_of_reviews"),
        target.get("review_count"),
        target.get("count_of_star_ratings"),
        target.get("rating"),
    )


def review20_required_for_target(target, sku=None):
    if is_external_review_source(target):
        return False
    count = review_count_number(
        target.get("count_of_reviews"),
        target.get("review_count"),
        target.get("count_of_star_ratings"),
    )
    if count is None and sku and detail_success(sku):
        review_info = (first_value(products_from_detail(sku), "reviewInfo") or {})
        if isinstance(review_info, dict):
            if is_external_review_source(target, review_info):
                return False
            count = review_count_number(review_info.get("reviewCount"))
    return count is None or count > 5


def recommendation_intent_value(review_count, *values):
    if review_count == 0:
        return ""
    return first_non_empty(*(recommendation_phrase(value) for value in values))


def pickup_text(pickup):
    if not isinstance(pickup, dict) or not pickup.get("pickupEligible"):
        return ""
    return date_to_relative_or_phrase("Pick up", pickup.get("maxDate") or pickup.get("fulfillDate") or pickup.get("promiseByStreetDate"))


def delivery_text(delivery):
    if not isinstance(delivery, dict) or not delivery.get("deliveryEligible"):
        return ""
    slots = delivery.get("deliverySlots") or delivery.get("installationSlots") or []
    if isinstance(slots, list) and slots:
        slot = slots[0] if isinstance(slots[0], dict) else {}
        return date_to_relative_or_phrase("Delivery as soon as", slot.get("date"))
    return ""


def fastest_delivery_text(shipping):
    if not isinstance(shipping, dict) or not shipping.get("shippingEligible"):
        return ""
    groups = shipping.get("customerLOSGroup") or []
    if isinstance(groups, list) and groups:
        group = groups[0] if isinstance(groups[0], dict) else {}
        default_group_id = shipping.get("defaultCustomerLosGroupId")
        for candidate in groups:
            if not isinstance(candidate, dict):
                continue
            if default_group_id not in (None, "") and str(candidate.get("customerLosGroupId")) == str(default_group_id):
                group = candidate
                break
        date_value = group.get("minLineItemMaxDate") or group.get("maxLineItemMaxDate")
        phrase = date_to_relative_or_phrase("Get it", date_value)
        if phrase:
            if group.get("price") in (0, 0.0, "0", "0.0"):
                phrase = f"{phrase} \u2022 FREE"
            return phrase
    return date_to_relative_or_phrase("Get it", shipping.get("promiseByStreetDate"))


def review20_content(sku):
    path = review_paths(sku)["response_json"]
    reviews = []
    if path.exists():
        data = read_json(path)
        reviews = (((data.get("data") or {}).get("productBySkuId") or {}).get("reviews") or {}).get("results") or []
    if not reviews:
        for payload in detail_payloads(sku):
            for event in payload.get("events", []):
                data = event_data(event)
                product = data.get("productBySkuId") if isinstance(data, dict) else None
                if not isinstance(product, dict) or str(product.get("skuId") or "") != str(sku):
                    continue
                fallback_reviews = ((product.get("reviews") or {}).get("results") or [])
                if fallback_reviews:
                    reviews = fallback_reviews
                    break
            if reviews:
                break
    chunks = []
    for index, review in enumerate(reviews[:20], 1):
        text = compact_text(review.get("text"))
        if text:
            chunks.append(f"review{index} - {text}")
    return " ||| ".join(chunks)


def recommended_percent_from_detail(sku):
    for payload in detail_payloads(sku):
        stack = [payload]
        while stack:
            current = stack.pop()
            if isinstance(current, dict):
                if str(current.get("skuId") or "") == str(sku):
                    review_info = current.get("reviewInfo") or {}
                    value = review_info.get("recommendedPercent")
                    if value not in ("", None):
                        return value
                stack.extend(current.values())
            elif isinstance(current, list):
                stack.extend(current)
    return ""


def sample_fields():
    config = db_config()
    table_name = bestbuy_output_table()
    if config and table_name:
        try:
            import psycopg2

            conn = psycopg2.connect(
                host=config.get("host"),
                port=int(config.get("port") or 5432),
                user=config.get("user"),
                password=config.get("password"),
                dbname=config.get("database"),
                connect_timeout=10,
            )
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_schema = 'public' AND table_name = %s
                        ORDER BY ordinal_position
                        """,
                        (table_name,),
                    )
                    fields = [row[0] for row in cur.fetchall()]
                    if fields:
                        return fields
        except Exception:
            pass
    if CATEGORY in FALLBACK_FINAL_FIELDS:
        return FALLBACK_FINAL_FIELDS[CATEGORY]
    with SAMPLE_SCHEMA_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        return next(csv.reader(f))


def output_row(target):
    sku = str(target.get("sku_id") or "").strip()
    html_text = ""
    selector_values = {}
    products = products_from_detail(sku)
    compare_similar_names = compare_similar_names_from_detail(sku)
    price = best_price(products)
    review_info = first_value(products, "reviewInfo") or {}
    review_count = review_count_number(review_info.get("reviewCount"), target.get("review_count"))
    external_reviews = is_external_review_source(target, review_info)
    pickup = best_path(products, ["fulfillmentOptions", "ispuDetails", 0, "ispuAvailability", 0], ("maxDate",))
    delivery = best_path(
        products,
        ["fulfillmentOptions", "deliveryDetails", 0, "deliveryAvailability", 0],
        ("deliverySlots",),
    )
    delivery_slot = (delivery.get("deliverySlots") or [{}])[0].get("date") if isinstance(delivery, dict) else ""
    screen = spec_value(products, "Screen Size Class") or spec_value(products, "Screen Size")
    energy = spec_value(products, "Estimated Annual Electricity Use")
    model_year = spec_value(products, "Model Year")
    product_name = first_path(products, ["name", "short"]) or target.get("product_name", "")
    product_url = first_path(products, ["url", "pdp"]) or target.get("product_url", "")
    bsin = first_value(products, "bsin") or target.get("bsin", "")
    primary_product = products[-1] if products else {}
    hhp_attrs = hhp_attributes_from_product(primary_product, product_name) if CATEGORY == "HHP" else {}
    trade_in = trade_in_text_from_detail_payloads(sku, products) if CATEGORY == "HHP" else ""
    promotion_type = first_non_empty(target.get("promotion_type", ""), promotion_type_from_products(products, trade_in))

    crawl_dt = datetime.now()
    row = {
        "id": "",
        "product": output_product_value(target),
        "item": bsin,
        "account_name": "Bestbuy",
        "page_type": output_page_type(target),
        "count_of_reviews": "0" if external_reviews else int_commas(review_info.get("reviewCount") or target.get("review_count")),
        "retailer_sku_name": first_non_empty(product_name, selector_values.get("retailer_sku_name")),
        "product_url": product_url,
        "star_rating": "Not yet reviewed"
        if external_reviews
        else first_non_empty(
            review_info.get("averageRating"),
            target.get("rating"),
            selector_values.get("top_star_rating"),
            selector_values.get("star_rating"),
            "Not yet reviewed",
        ),
        "count_of_star_ratings": "0"
        if external_reviews
        else int_commas(review_info.get("reviewCount") or target.get("review_count")),
        "screen_size": first_non_empty(screen, selector_values.get("screen_size")),
        "final_sku_price": first_non_empty(
            money(price.get("displayableCustomerPrice") or price.get("customerPrice") or target.get("customer_price")),
            selector_values.get("final_sku_price"),
            selector_values.get("final_sku_price_see_price_in_cart"),
            selector_values.get("final_sku_price_no_longer_available"),
        ),
        "original_sku_price": first_non_empty(
            money(visible_regular_price(price, target)),
            selector_values.get("original_sku_price"),
        ),
        "savings": first_non_empty(
            money_int(visible_savings(price, target)),
            selector_values.get("savings"),
        ),
        "offer": first_non_empty(target.get("offer"), target.get("offer_count")),
        "pick_up_availability": first_non_empty(
            target.get("pick_up_availability"),
            pickup_text(pickup),
        ),
        "fastest_delivery": first_non_empty(
            target.get("fastest_delivery"),
            fastest_delivery_text(best_shipping_availability(products)),
        ),
        "delivery_availability": first_non_empty(
            target.get("delivery_availability"),
            delivery_text(delivery),
            date_to_relative_or_phrase("Delivery as soon as", delivery_slot),
        ),
        "shipping_info": "",
        "sku_status": "Sponsored" if target.get("is_sponsored") in {"1", "true", "True"} else "",
        "trade_in": trade_in,
        "hhp_storage": hhp_attrs.get("hhp_storage", ""),
        "hhp_color": hhp_attrs.get("hhp_color", ""),
        "hhp_carrier": hhp_attrs.get("hhp_carrier", ""),
        "detailed_review_content": "" if external_reviews else review20_content(sku),
        "recommendation_intent": ""
        if external_reviews
        else recommendation_intent_value(
            review_count,
            recommended_percent_from_detail(sku),
            recommendation(products),
        ),
        "main_rank": target.get("main_rank", ""),
        "bsr_rank": target.get("bsr_rank", ""),
        "promotion_position": target.get("promotion_position", ""),
        "trend_rank": target.get("trend_rank", ""),
        "retailer_sku_name_similar": " ||| ".join(compare_similar_names[:4]),
        "estimated_annual_electricity_use": clean_energy(energy),
        "promotion_type": promotion_type,
        "calendar_week": f"w{crawl_dt.isocalendar().week}",
        "crawl_datetime": crawl_dt.strftime("%Y-%m-%d %H:%M"),
        "crawl_strdatetime": crawl_dt.strftime("%Y-%m-%d %H:%M"),
        "model_year": model_year,
        "batch_id": RUN_BATCH_ID,
        "country": "SEA",
    }
    return row


def build_outputs(targets):
    rows = []
    failures = []
    for target in targets:
        sku = str(target.get("sku_id") or "").strip()
        dmeta = read_json(detail_paths(sku)["meta"])
        rmeta = read_json(review_paths(sku)["meta"])
        cmeta = compare_meta(sku)
        rows.append(output_row(target))
        if not dmeta.get("success"):
            failures.append(
                {
                    "sku_id": sku,
                    "stage": "detail",
                    "attempt": dmeta.get("attempt", 0),
                    "status_code": dmeta.get("status_code", ""),
                    "error": dmeta.get("error", "missing_detail"),
                    "retryable": str(int(int(dmeta.get("attempt", 0) or 0) < MAX_ATTEMPTS)),
                }
            )
        review_required = review20_required_for_target(target, sku)
        if review_required and not rmeta.get("success"):
            failures.append(
                {
                    "sku_id": sku,
                    "stage": "review20",
                    "attempt": rmeta.get("attempt", 0),
                    "status_code": rmeta.get("status_code", ""),
                    "error": rmeta.get("error", "missing_review20"),
                    "retryable": str(int(int(rmeta.get("attempt", 0) or 0) < MAX_ATTEMPTS)),
                }
            )
        if FETCH_COMPARE and not cmeta.get("success"):
            failures.append(
                {
                    "sku_id": sku,
                    "stage": "compare",
                    "attempt": cmeta.get("attempt", 0),
                    "status_code": cmeta.get("status_code", ""),
                    "error": cmeta.get("error", "missing_compare"),
                    "retryable": str(int(int(cmeta.get("attempt", 0) or 0) < MAX_ATTEMPTS)),
                }
            )
    return rows, failures


def main():
    started_at = now()
    targets = target_rows(apply_filters=True)
    output_targets = target_rows(apply_filters=False)
    api_key = "" if REBUILD_ONLY else os.getenv("ZENROWS_API_KEY")
    client = ZenRowsClient(api_key) if api_key else None
    transports = [] if REBUILD_ONLY else fetch_transports()
    can_fetch_network = not REBUILD_ONLY and ("zenrows" in transports and client is not None)

    RAW_DETAIL_DIR.mkdir(parents=True, exist_ok=True)
    RAW_REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    RAW_COMPARE_DIR.mkdir(parents=True, exist_ok=True)
    PARSED_DIR.mkdir(parents=True, exist_ok=True)
    BENCHMARKS_DIR.mkdir(parents=True, exist_ok=True)
    if not REBUILD_ONLY and DETAIL_BENCHMARKS_CSV.exists():
        DETAIL_BENCHMARKS_CSV.unlink()

    if STAGE not in {"all", "detail", "review"}:
        raise RuntimeError("BESTBUY_DETAIL_STAGE must be one of: all, detail, review")

    if not can_fetch_network and not REBUILD_ONLY:
        # Cached parse-only mode is useful during local development.
        if STAGE == "detail":
            missing = [row.get("sku_id") for row in targets if not detail_success(row.get("sku_id"))]
        elif STAGE == "review":
            missing = [row.get("sku_id") for row in targets if not review_success(row.get("sku_id"))]
        else:
            missing = [
                row.get("sku_id")
                for row in targets
                if not detail_success(row.get("sku_id"))
                or (review20_required_for_target(row, row.get("sku_id")) and not review_success(row.get("sku_id")))
            ]
        if missing:
            raise RuntimeError("Set ZENROWS_API_KEY or provide cached detail/review files for all selected SKUs")

    benchmark_lock = Lock()

    def process_target(index, target):
        sku = str(target.get("sku_id") or "").strip()
        fetched_detail = False
        fetched_review = False
        fetched_compare = False
        if STAGE in {"all", "detail"}:
            should_fetch_detail = can_fetch_network and not detail_success(sku)
            dmeta = fetch_detail(client, target) if should_fetch_detail else read_json(detail_paths(sku)["meta"])
            fetched_detail = bool(should_fetch_detail)
        else:
            dmeta = read_json(detail_paths(sku)["meta"])
        if STAGE in {"all", "review"}:
            should_fetch_review = (
                can_fetch_network
                and dmeta.get("success")
                and review20_required_for_target(target, sku)
                and not review_success(sku)
            )
            rmeta = fetch_review20(client, target) if should_fetch_review else read_json(review_paths(sku)["meta"])
            fetched_review = bool(should_fetch_review)
        else:
            rmeta = read_json(review_paths(sku)["meta"])
        if FETCH_COMPARE and STAGE in {"all", "detail"}:
            should_fetch_compare = can_fetch_network and dmeta.get("success") and not compare_success(sku)
            cmeta = fetch_compare(client, target) if should_fetch_compare else compare_meta(sku)
            fetched_compare = bool(should_fetch_compare)
        else:
            cmeta = compare_meta(sku)
        with benchmark_lock:
            append_detail_benchmark(target, DETAIL_ROOT, DETAIL_BENCHMARKS_CSV)
        return index, sku, dmeta, rmeta, cmeta, fetched_detail, fetched_review, fetched_compare

    detail_cost = 0.0
    review_cost = 0.0
    compare_cost = 0.0
    batch_processed = set()
    if REBUILD_ONLY:
        print(f"rebuild_only=1 output_targets={len(output_targets)}")
    elif BATCH_FETCH and can_fetch_network and targets:
        for batch_targets in chunked(targets, BATCH_SIZE):
            results, batch_cost, batch_error = fetch_detail_review_compare_batch(client, batch_targets)
            if batch_cost:
                detail_cost += batch_cost
            result_map = {sku: (dmeta, rmeta, cmeta) for sku, dmeta, rmeta, cmeta in results}
            for target in batch_targets:
                sku = str(target.get("sku_id") or "").strip()
                dmeta, rmeta, cmeta = result_map.get(
                    sku,
                    (
                        read_json(detail_paths(sku)["meta"]),
                        read_json(review_paths(sku)["meta"]),
                        compare_meta(sku),
                    ),
                )
                if dmeta.get("success"):
                    batch_processed.add(sku)
                with benchmark_lock:
                    append_detail_benchmark(target, DETAIL_ROOT, DETAIL_BENCHMARKS_CSV)
                print(
                    f"[batch {len(batch_processed)}/{len(targets)}] sku={sku} "
                    f"detail={dmeta.get('success')} attempt={dmeta.get('attempt')} "
                    f"compare={cmeta.get('success')} attempt={cmeta.get('attempt')} "
                    f"review={rmeta.get('success')} attempt={rmeta.get('attempt')} "
                    f"reviews={rmeta.get('review_count_returned', '')}"
                    + (f" batch_error={batch_error}" if batch_error and sku not in result_map else "")
                )
        targets = [target for target in targets if str(target.get("sku_id") or "").strip() not in batch_processed]
        if targets:
            print(f"batch fallback sku_count={len(targets)}")

    if not REBUILD_ONLY and WORKERS > 1 and len(targets) > 1:
        with ThreadPoolExecutor(max_workers=WORKERS) as executor:
            futures = [executor.submit(process_target, index, target) for index, target in enumerate(targets, 1)]
            for future in as_completed(futures):
                index, sku, dmeta, rmeta, cmeta, fetched_detail, fetched_review, fetched_compare = future.result()
                if fetched_detail:
                    detail_cost += float(dmeta.get("x_request_cost") or 0)
                if fetched_review:
                    review_cost += float(rmeta.get("x_request_cost") or 0)
                if fetched_compare:
                    compare_cost += float(cmeta.get("x_request_cost") or 0)
                print(
                    f"[{index}/{len(targets)}] sku={sku} "
                    f"detail={dmeta.get('success')} attempt={dmeta.get('attempt')} "
                    f"compare={cmeta.get('success')} attempt={cmeta.get('attempt')} "
                    f"review={rmeta.get('success')} attempt={rmeta.get('attempt')} "
                    f"reviews={rmeta.get('review_count_returned', '')}"
                )
    elif not REBUILD_ONLY:
        for index, target in enumerate(targets, 1):
            index, sku, dmeta, rmeta, cmeta, fetched_detail, fetched_review, fetched_compare = process_target(index, target)
            if fetched_detail:
                detail_cost += float(dmeta.get("x_request_cost") or 0)
            if fetched_review:
                review_cost += float(rmeta.get("x_request_cost") or 0)
            if fetched_compare:
                compare_cost += float(cmeta.get("x_request_cost") or 0)
            print(
                f"[{index}/{len(targets)}] sku={sku} "
                f"detail={dmeta.get('success')} attempt={dmeta.get('attempt')} "
                f"compare={cmeta.get('success')} attempt={cmeta.get('attempt')} "
                f"review={rmeta.get('success')} attempt={rmeta.get('attempt')} "
                f"reviews={rmeta.get('review_count_returned', '')}"
            )

    enriched_rows, failures = build_outputs(output_targets)
    write_csv(DETAIL_ROWS_CSV, enriched_rows)
    write_csv(FAILURES_CSV, failures, ["sku_id", "stage", "attempt", "status_code", "error", "retryable"])
    fields = sample_fields()
    for row in enriched_rows:
        for field in fields:
            row.setdefault(field, "")
    final_rows = [{field: row.get(field, "") for field in fields} for row in enriched_rows]
    write_csv(FINAL_OUTPUT_CSV, final_rows, fields)
    benchmark_rows = write_detail_benchmarks(TARGET_CSV, DETAIL_ROOT, DETAIL_BENCHMARKS_CSV)

    manifest = {
        "run_type": "step08_detail_enrichment",
        "started_at": started_at,
        "finished_at": now(),
        "target_csv": rel_path(TARGET_CSV),
        "limit": LIMIT,
        "retry_only": RETRY_ONLY,
        "rebuild_only": REBUILD_ONLY,
        "stage": STAGE,
        "workers": WORKERS,
        "max_attempts": MAX_ATTEMPTS,
        "fetch_mode": FETCH_MODE,
        "fetch_transports": fetch_transports(),
        "target_count": len(output_targets),
        "processed_count": len(targets),
        "success_count": len(enriched_rows),
        "failure_count": len(failures),
        "detail_cost_usd_this_run": detail_cost,
        "review_cost_usd_this_run": review_cost,
        "compare_cost_usd_this_run": compare_cost,
        "total_cost_usd_this_run": detail_cost + review_cost + compare_cost,
        "total_cost_krw_1550_this_run": round((detail_cost + review_cost + compare_cost) * KRW_PER_USD, 2),
        "detail_rows_csv": rel_path(DETAIL_ROWS_CSV),
        "failures_csv": rel_path(FAILURES_CSV),
        "detail_benchmarks_csv": rel_path(DETAIL_BENCHMARKS_CSV),
        "detail_benchmark_rows": len(benchmark_rows),
        "final_output_csv": rel_path(FINAL_OUTPUT_CSV),
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
