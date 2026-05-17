import ast
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode


AMAZON_BASE_URL = "https://www.amazon.com"
PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent
CONFIG_DIR = PACKAGE_DIR / "config"
INITIAL_URLS_CSV = CONFIG_DIR / "amazon_initial_urls.csv"
DEFAULT_AMAZON_RUNS_BASE = PACKAGE_DIR / "data"
DEFAULT_PRODUCT_TYPE = "TV"
DEFAULT_MARKETPLACE = "US"
DEFAULT_RETAILER = "Amazon"
TARGET_URL_TABLE = os.getenv("AMAZON_TARGET_URL_TABLE", "public.dx_target_page_url")


def load_env(path=None):
    env_path = Path(path or (PROJECT_ROOT / ".env"))
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

AMAZON_URLS = {
    "main_search_tv": f"{AMAZON_BASE_URL}/s?{urlencode({'k': 'tv'})}",
    "bsr_tv": f"{AMAZON_BASE_URL}/Best-Sellers-Electronics-Televisions/zgbs/electronics/172659",
}


def amazon_run_date():
    return os.getenv("AMAZON_RUN_DATE", datetime.now().strftime("%Y%m%d"))


def amazon_product_type():
    return os.getenv("AMAZON_PRODUCT_TYPE", DEFAULT_PRODUCT_TYPE).strip().lower() or DEFAULT_PRODUCT_TYPE.lower()


def amazon_marketplace():
    return os.getenv("AMAZON_MARKETPLACE", DEFAULT_MARKETPLACE).strip().upper() or DEFAULT_MARKETPLACE


def amazon_dated_run_root(run_date=None, product_type=None):
    return DEFAULT_AMAZON_RUNS_BASE / (product_type or amazon_product_type()).lower() / (run_date or amazon_run_date())


DEFAULT_AMAZON_RUN_ROOT = amazon_dated_run_root()


def _read_multiline_env_object(name):
    raw = os.getenv(name)
    if raw and raw.strip() not in {"{", ""}:
        return raw
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return raw or ""
    lines = env_path.read_text(encoding="utf-8", errors="ignore").splitlines()
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


def _value(row, candidates):
    lowered = {str(key).lower(): value for key, value in row.items()}
    for candidate in candidates:
        if candidate.lower() in lowered:
            return lowered[candidate.lower()]
    return ""


def _target_url_key(page_type):
    value = str(page_type or "").strip().lower()
    aliases = {
        "main": "main_search_tv",
        "main_search": "main_search_tv",
        "search": "main_search_tv",
        "bsr": "bsr_tv",
        "best_selling": "bsr_tv",
        "best-selling": "bsr_tv",
        "promotion": "promotion",
        "promo": "promotion",
        "trend": "trending",
        "trending": "trending",
    }
    return aliases.get(value, value)


def _fetch_target_urls_from_db(product_type=None, retailer=DEFAULT_RETAILER):
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
        print(f"[amazon] DB URL load failed, falling back to CSV/default: {type(exc).__name__}", file=sys.stderr)
        return {}

    wanted_product_type = (product_type or amazon_product_type()).strip().upper()
    wanted_retailer = str(retailer or DEFAULT_RETAILER).strip().lower()
    urls = {}
    for row in rows:
        row_product_type = str(
            _value(row, ["product_line", "category", "category_key", "product_group", "division", "sec"]) or ""
        ).strip().upper()
        row_retailer = str(
            _value(row, ["account_name", "retailer", "retailer_name", "mall", "site", "corp"]) or ""
        ).strip().lower()
        page_type = _value(row, ["page_type", "url_type", "type", "target_type", "page"])
        url = str(_value(row, ["url_template", "url", "page_url", "target_url"]) or "").strip()
        if row_product_type != wanted_product_type or row_retailer != wanted_retailer or not url:
            continue
        urls[_target_url_key(page_type)] = url
    return urls


def _load_initial_urls_csv(path=INITIAL_URLS_CSV, product_type=None):
    if not Path(path).exists():
        return {}
    urls = {}
    with Path(path).open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            enabled = str(row.get("enabled", "true")).strip().lower()
            if enabled in {"0", "false", "no", "n"}:
                continue
            row_product_type = str(row.get("product_line") or row.get("category_key") or row.get("category") or "").strip().upper()
            if row_product_type and row_product_type != (product_type or amazon_product_type()).upper():
                continue
            row_marketplace = str(row.get("marketplace") or DEFAULT_MARKETPLACE).strip().upper()
            if row_marketplace and row_marketplace != amazon_marketplace():
                continue
            key = str(row.get("key") or row.get("url_type") or row.get("page_type") or "").strip()
            url = str(row.get("url") or row.get("url_template") or "").strip()
            if key and url:
                urls[_target_url_key(key)] = url
    return urls


def load_initial_urls(path=INITIAL_URLS_CSV, product_type=None, retailer=DEFAULT_RETAILER):
    urls = dict(AMAZON_URLS)
    source = os.getenv("AMAZON_URL_SOURCE", "auto").strip().lower()
    if source in {"auto", "csv"}:
        urls.update(_load_initial_urls_csv(path=path, product_type=product_type))
    if source in {"auto", "db"}:
        urls.update(_fetch_target_urls_from_db(product_type=product_type, retailer=retailer))
    return urls


def available_url_keys(path=INITIAL_URLS_CSV, product_type=None, retailer=DEFAULT_RETAILER):
    keys = set()
    source = os.getenv("AMAZON_URL_SOURCE", "auto").strip().lower()
    if source in {"auto", "db"}:
        keys.update(_fetch_target_urls_from_db(product_type=product_type, retailer=retailer).keys())
    if source in {"auto", "csv"}:
        keys.update(_load_initial_urls_csv(path=path, product_type=product_type).keys())
    return keys


def has_target_url(page_type, product_type=None, retailer=DEFAULT_RETAILER):
    return _target_url_key(page_type) in available_url_keys(product_type=product_type, retailer=retailer)


def target_url(page_type, product_type=None, retailer=DEFAULT_RETAILER):
    return load_initial_urls(product_type=product_type, retailer=retailer).get(_target_url_key(page_type), "")


def url_for_page(url_template, page):
    value = str(url_template or "")
    if "{page}" in value:
        return value.replace("{page}", str(page))
    if page and int(page) > 1:
        joiner = "&" if "?" in value else "?"
        return f"{value}{joiner}{urlencode({'page': int(page)})}"
    return value


def amazon_search_url(search_term="tv", page=1):
    query = {"k": search_term}
    if page and int(page) > 1:
        query["page"] = int(page)
    return f"{AMAZON_BASE_URL}/s?{urlencode(query)}"


def absolute_amazon_url(path):
    if not path:
        return ""
    value = str(path)
    if value.startswith("http"):
        return value
    return f"{AMAZON_BASE_URL}{value}"


def rel_path(path):
    if path in ("", None):
        return ""
    value = Path(path)
    try:
        return os.path.relpath(value.resolve(), PROJECT_ROOT.resolve())
    except (OSError, ValueError):
        return str(path)
