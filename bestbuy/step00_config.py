import csv
import ast
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse


KRW_PER_USD = 1550
BESTBUY_BASE_URL = "https://www.bestbuy.com"
PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parent
INITIAL_URLS_CSV = PACKAGE_DIR / "config" / "bestbuy_initial_urls.csv"
DEFAULT_RETAILER = "Bestbuy"
DEFAULT_CATEGORY = "TV"
TARGET_URL_TABLE = os.getenv("BESTBUY_TARGET_URL_TABLE", "dx_target_page_url")
OUTPUT_TABLE_REGISTRY = os.getenv("COMMON_OUTPUT_TABLE_REGISTRY", "public.common_setting_step02_output_table")

BESTBUY_OUTPUT_TABLES = {
    "TV": "tv_retail_com",
    "HHP": "hhp_retail_com_bby_v2_test",
    "REF": "ref_retail_com_bby",
    "LDY": "ldy_retail_com_bby",
}

BESTBUY_PRODUCT_LIST_TABLES = {
    "TV": "bby_tv_product_list_v2_test",
    "HHP": "bby_hhp_product_list_v2_test",
    "REF": "bby_ref_product_list",
    "LDY": "bby_ldy_product_list",
}


def load_env(path=None):
    env_path = Path(path or (REPO_ROOT / ".env"))
    if not env_path.exists():
        return
    lines = env_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value == "{":
            collected = ["{"]
            depth = 1
            while i < len(lines) and depth > 0:
                part = lines[i]
                i += 1
                collected.append(part)
                depth += part.count("{") - part.count("}")
            value = "\n".join(collected)
        else:
            value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


load_env()

BESTBUY_URLS = {
    "main_search": "https://www.bestbuy.com/site/searchpage.jsp?id=pcat17071&st=tv",
    "bsr_search": "https://www.bestbuy.com/site/searchpage.jsp?id=pcat17071&sp=Best-Selling&st=tv",
    "promotion_tv_home_theater": (
        "https://www.bestbuy.com/site/all-electronics-on-sale/all-tv-home-theater-on-sale/"
        "pcmcat1690836748285.c?id=pcmcat1690836748285"
    ),
    "trending_tvs_projectors": (
        "https://www.bestbuy.com/discover/trending-deals/"
        "trending-deals-tvs-projectors/pcmcat1752523988655"
    ),
}

PROMOTION_LABELS = {
    "pcmcat1690836748285-1": "DON'T-MISS DEALS ON TVs",
    "pcmcat1690836748285-2": "Featured deals",
    "pcmcat1690836748285-3": "On-sale lifestyle TVs as low as $799.99",
    "pcmcat1690836748285-5": "Save up to $1,500 on select OLED TVs",
}

DEFAULT_BESTBUY_RUNS_BASE = PACKAGE_DIR / "data"


def bestbuy_category():
    return os.getenv("BESTBUY_CATEGORY", DEFAULT_CATEGORY).strip().upper() or DEFAULT_CATEGORY


def bestbuy_output_table(category=None):
    category_key = (category or bestbuy_category()).strip().upper()
    override = os.getenv(f"BESTBUY_OUTPUT_TABLE_{category_key}") or os.getenv("BESTBUY_OUTPUT_TABLE")
    return override or BESTBUY_OUTPUT_TABLES.get(category_key, f"{category_key.lower()}_retail_com_bby")


def bestbuy_product_list_table(category=None):
    category_key = (category or bestbuy_category()).strip().upper()
    override = (
        os.getenv(f"BESTBUY_PRODUCT_LIST_TABLE_{category_key}")
        or os.getenv("BESTBUY_PRODUCT_LIST_TABLE")
    )
    return override or BESTBUY_PRODUCT_LIST_TABLES.get(
        category_key,
        f"bby_{category_key.lower()}_product_list",
    )


def bestbuy_run_date():
    return os.getenv("BESTBUY_RUN_DATE", datetime.now().strftime("%Y%m%d"))


def bestbuy_dated_run_root(run_date=None, category=None):
    return DEFAULT_BESTBUY_RUNS_BASE / (category or bestbuy_category()).lower() / (run_date or bestbuy_run_date())


DEFAULT_BESTBUY_RUN_ROOT = bestbuy_dated_run_root()


def bestbuy_zip_code():
    return os.getenv("BESTBUY_ZIP_CODE", "10010").strip() or "10010"


def bestbuy_store_id():
    return os.getenv("BESTBUY_STORE_ID", "482").strip() or "482"


def apply_bestbuy_location(value, zip_code=None, store_id=None):
    zip_code = str(zip_code or bestbuy_zip_code())
    store_id = str(store_id or bestbuy_store_id())
    if isinstance(value, dict):
        for key, item in list(value.items()):
            if key in {
                "destinationZipCode",
                "preferredStoreZipCode",
                "zipCode",
                "postalCode",
            }:
                value[key] = zip_code
            elif key in {"storeId", "locationId"}:
                value[key] = store_id
            else:
                apply_bestbuy_location(item, zip_code=zip_code, store_id=store_id)
    elif isinstance(value, list):
        for item in value:
            apply_bestbuy_location(item, zip_code=zip_code, store_id=store_id)
    return value


def _read_multiline_env_object(name):
    raw = os.getenv(name)
    if raw and raw.strip() not in {"{", ""}:
        return raw
    if not (REPO_ROOT / ".env").exists():
        return raw or ""
    lines = (REPO_ROOT / ".env").read_text(encoding="utf-8", errors="ignore").splitlines()
    collecting = False
    collected = []
    depth = 0
    for line in lines:
        stripped = line.strip()
        if not collecting and stripped.startswith(f"{name}") and "=" in stripped:
            value = line.split("=", 1)[1].strip()
            collecting = True
            collected.append(value)
            depth += value.count("{") - value.count("}")
            if depth <= 0 and value:
                break
            continue
        if collecting:
            collected.append(line)
            depth += line.count("{") - line.count("}")
            if depth <= 0:
                break
    return "\n".join(collected).strip()


def db_config():
    raw = _read_multiline_env_object("DB_CONFIG")
    if not raw:
        return {}
    for parser in (json.loads, ast.literal_eval):
        try:
            value = parser(raw)
            return value if isinstance(value, dict) else {}
        except Exception:
            continue
    return {}


def _fetch_output_table_from_db(category, output_kind, retailer=DEFAULT_RETAILER):
    config = db_config()
    if not config:
        return ""
    try:
        import psycopg2
        import psycopg2.extras

        conn = psycopg2.connect(
            host=config.get("host"),
            port=int(config.get("port") or 5432),
            user=config.get("user"),
            password=config.get("password"),
            dbname=config.get("database"),
            connect_timeout=5,
        )
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    f"""
                    SELECT table_name
                    FROM {OUTPUT_TABLE_REGISTRY}
                    WHERE lower(corp) = lower(%s)
                      AND upper(product_line) = upper(%s)
                      AND lower(account_name) = lower(%s)
                      AND lower(output_kind) = lower(%s)
                      AND is_active = true
                    ORDER BY updated_at DESC NULLS LAST, id DESC
                    LIMIT 1
                    """,
                    ("SEA", category, retailer, output_kind),
                )
                row = cur.fetchone()
        conn.close()
        return str(row["table_name"]).strip() if row and row.get("table_name") else ""
    except Exception as exc:
        print(f"[bestbuy] output table registry lookup failed: {type(exc).__name__}", file=sys.stderr)
        return ""


def _value(row, candidates):
    lowered = {str(key).lower(): value for key, value in row.items()}
    for candidate in candidates:
        if candidate.lower() in lowered:
            return lowered[candidate.lower()]
    return ""


def _target_url_key(page_type):
    value = str(page_type or "").strip().lower()
    aliases = {
        "main": "main_search",
        "main_search": "main_search",
        "bsr": "bsr_search",
        "best_selling": "bsr_search",
        "best-selling": "bsr_search",
        "promotion": "promotion_tv_home_theater",
        "promo": "promotion_tv_home_theater",
        "trend": "trending_tvs_projectors",
        "trending": "trending_tvs_projectors",
    }
    return aliases.get(value, value)


def _fetch_target_urls_from_db(category=None, retailer=DEFAULT_RETAILER):
    config = db_config()
    if not config:
        return {}

    rows = []
    port = str(config.get("port") or "")
    try:
        if port == "3306" or str(config.get("driver") or "").lower().startswith("mysql"):
            import pymysql

            conn = pymysql.connect(
                host=config.get("host"),
                port=int(config.get("port") or 3306),
                user=config.get("user"),
                password=config.get("password"),
                database=config.get("database"),
                charset="utf8mb4",
                cursorclass=pymysql.cursors.DictCursor,
                connect_timeout=10,
            )
            with conn:
                with conn.cursor() as cur:
                    cur.execute(f"SELECT * FROM {TARGET_URL_TABLE}")
                    rows = list(cur.fetchall())
        else:
            import psycopg2
            import psycopg2.extras

            conn = psycopg2.connect(
                host=config.get("host"),
                port=int(config.get("port") or 5432),
                user=config.get("user"),
                password=config.get("password"),
                dbname=config.get("database"),
                connect_timeout=10,
            )
            with conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(f"SELECT * FROM {TARGET_URL_TABLE}")
                    rows = [dict(row) for row in cur.fetchall()]
    except Exception as exc:
        print(f"[bestbuy] DB URL load failed, falling back to CSV/default: {type(exc).__name__}", file=sys.stderr)
        return {}

    wanted_category = (category or bestbuy_category()).strip().upper()
    wanted_retailer = str(retailer or DEFAULT_RETAILER).strip().lower()
    urls = {}
    for row in rows:
        row_category = str(
            _value(row, ["category", "category_key", "product_line", "product_group", "division", "sec"]) or ""
        ).strip().upper()
        row_retailer = str(
            _value(row, ["retailer", "retailer_name", "account_name", "mall", "site"]) or ""
        ).strip().lower()
        page_type = _value(row, ["page_type", "url_type", "type", "target_type", "page"])
        url = str(_value(row, ["url", "page_url", "target_url", "url_template"]) or "").strip()
        if row_category != wanted_category or row_retailer != wanted_retailer or not url:
            continue
        urls[_target_url_key(page_type)] = url
    return urls


def _load_initial_urls_csv(path=INITIAL_URLS_CSV, category=None):
    if not Path(path).exists():
        return {}
    urls = {}
    with Path(path).open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            enabled = str(row.get("enabled", "true")).strip().lower()
            if enabled in {"0", "false", "no", "n"}:
                continue
            row_category = str(row.get("category_key") or row.get("category") or "").strip().upper()
            if row_category and row_category != (category or bestbuy_category()).upper():
                continue
            key = str(row.get("key") or row.get("url_type") or row.get("page_type") or "").strip()
            url = str(row.get("url") or "").strip()
            if key and url:
                urls[_target_url_key(key)] = url
    return urls


def load_initial_urls(path=INITIAL_URLS_CSV, category=None, retailer=DEFAULT_RETAILER):
    urls = dict(BESTBUY_URLS)
    source = os.getenv("BESTBUY_URL_SOURCE", "auto").strip().lower()
    if source in {"auto", "db"}:
        urls.update(_fetch_target_urls_from_db(category=category, retailer=retailer))
    if source in {"auto", "csv"}:
        urls.update(_load_initial_urls_csv(path=path, category=category))
    return urls


def available_url_keys(path=INITIAL_URLS_CSV, category=None, retailer=DEFAULT_RETAILER):
    keys = set()
    source = os.getenv("BESTBUY_URL_SOURCE", "auto").strip().lower()
    if source in {"auto", "db"}:
        keys.update(_fetch_target_urls_from_db(category=category, retailer=retailer).keys())
    if source in {"auto", "csv"}:
        keys.update(_load_initial_urls_csv(path=path, category=category).keys())
    return keys


def has_target_url(page_type, category=None, retailer=DEFAULT_RETAILER):
    return _target_url_key(page_type) in available_url_keys(category=category, retailer=retailer)


def target_url(page_type, category=None, retailer=DEFAULT_RETAILER):
    return load_initial_urls(category=category, retailer=retailer).get(_target_url_key(page_type), "")


def url_for_page(url_template, page):
    value = str(url_template or "")
    if "{page}" in value:
        return value.replace("{page}", str(page))
    return value


def search_term_from_url(url):
    try:
        values = parse_qs(urlparse(str(url)).query)
    except Exception:
        return ""
    return (values.get("st") or [""])[0].replace("+", " ").strip()


def old_pdp_url(sku_id):
    return f"{BESTBUY_BASE_URL}/site/-/{sku_id}.p?skuId={sku_id}&intl=nosplash"


def absolute_bestbuy_url(path):
    if not path:
        return ""
    value = str(path)
    if value.startswith("http"):
        return value
    return f"{BESTBUY_BASE_URL}{value}"


def rel_path(path):
    if path in ("", None):
        return ""
    value = Path(path)
    try:
        return os.path.relpath(value.resolve(), REPO_ROOT.resolve())
    except (OSError, ValueError):
        return str(path)
