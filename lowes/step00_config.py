import csv
import ast
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode


LOWES_BASE_URL = "https://www.lowes.com"
PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent
CONFIG_DIR = PACKAGE_DIR / "config"
INITIAL_URLS_CSV = CONFIG_DIR / "lowes_initial_urls.csv"
DEFAULT_LOWES_RUNS_BASE = PACKAGE_DIR / "data"
DEFAULT_PRODUCT_TYPE = "REF"
DEFAULT_RETAILER = "Lowes"
TARGET_URL_TABLE = os.getenv("LOWES_TARGET_URL_TABLE", "public.dx_target_page_url")
OUTPUT_TABLE_REGISTRY = os.getenv("COMMON_OUTPUT_TABLE_REGISTRY", "public.common_setting_step02_output_table")
LOWES_OUTPUT_TABLES = {
    "REF": "ref_retail_com_lowes",
    "LDY": "ldy_retail_com_lowes",
}


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

LOWES_URLS = {
    "main_search_refrigerator": f"{LOWES_BASE_URL}/search?searchTerm=refrigerator",
    "main_search_washing_machine": f"{LOWES_BASE_URL}/search?searchTerm=washing+machine",
    "bsr_refrigerators": f"{LOWES_BASE_URL}/best-sellers/appliances/refrigerators/4294857973",
    "bsr_washing_machines": f"{LOWES_BASE_URL}/best-sellers/appliances/washers-dryers/washing-machines/4294857977",
}


def default_lowes_urls(product_type=None):
    product = (product_type or lowes_product_type()).strip().upper()
    if product == "LDY":
        return {
            "main_search_washing_machine": LOWES_URLS["main_search_washing_machine"],
            "bsr_washing_machines": LOWES_URLS["bsr_washing_machines"],
        }
    return {
        "main_search_refrigerator": LOWES_URLS["main_search_refrigerator"],
        "bsr_refrigerators": LOWES_URLS["bsr_refrigerators"],
    }


def lowes_run_date():
    return os.getenv("LOWES_RUN_DATE", datetime.now().strftime("%Y%m%d"))


def lowes_product_type():
    return os.getenv("LOWES_PRODUCT_TYPE", DEFAULT_PRODUCT_TYPE).strip().lower() or DEFAULT_PRODUCT_TYPE.lower()


def lowes_dated_run_root(run_date=None, product_type=None):
    return DEFAULT_LOWES_RUNS_BASE / (product_type or lowes_product_type()) / (run_date or lowes_run_date())


DEFAULT_LOWES_RUN_ROOT = lowes_dated_run_root()


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


def lowes_output_table(product_type=None):
    product = (product_type or lowes_product_type()).strip().upper()
    return os.getenv("LOWES_DB_FINAL_TABLE") or _fetch_output_table_from_db(product, "final") or LOWES_OUTPUT_TABLES.get(
        product,
        f"{product.lower()}_retail_com_lowes",
    )


def _fetch_output_table_from_db(product_type, output_kind, retailer=DEFAULT_RETAILER):
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
                    ("SEA", product_type, retailer, output_kind),
                )
                row = cur.fetchone()
        conn.close()
        return str(row["table_name"]).strip() if row and row.get("table_name") else ""
    except Exception as exc:
        print(f"[lowes] output table registry lookup failed: {type(exc).__name__}", file=sys.stderr)
        return ""


def _value(row, candidates):
    lowered = {str(key).lower(): value for key, value in row.items()}
    for candidate in candidates:
        if candidate.lower() in lowered:
            return lowered[candidate.lower()]
    return ""


def _target_url_key(page_type, product_type=None):
    value = str(page_type or "").strip().lower()
    product = (product_type or lowes_product_type()).strip().upper()
    if value in {"main", "main_search", "search"}:
        return "main_search_washing_machine" if product == "LDY" else "main_search_refrigerator"
    if value in {"bsr", "best_selling", "best-selling"}:
        return "bsr_washing_machines" if product == "LDY" else "bsr_refrigerators"
    aliases = {
        "main_search_refrigerator": "main_search_refrigerator",
        "main_search_washing_machine": "main_search_washing_machine",
        "bsr_refrigerators": "bsr_refrigerators",
        "bsr_washing_machines": "bsr_washing_machines",
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
        print(f"[lowes] DB URL load failed, falling back to CSV/default: {type(exc).__name__}", file=sys.stderr)
        return {}

    wanted_product_type = (product_type or lowes_product_type()).strip().upper()
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
        urls[_target_url_key(page_type, product_type=wanted_product_type)] = url
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
            if row_product_type and row_product_type != (product_type or lowes_product_type()).upper():
                continue
            key = str(row.get("key") or "").strip()
            url = str(row.get("url") or "").strip()
            if key and url:
                urls[_target_url_key(key, product_type=product_type)] = url
    return urls


def load_initial_urls(path=INITIAL_URLS_CSV, product_type=None, retailer=DEFAULT_RETAILER):
    urls = default_lowes_urls(product_type=product_type)
    source = os.getenv("LOWES_URL_SOURCE", "auto").strip().lower()
    if source in {"auto", "db"}:
        urls.update(_fetch_target_urls_from_db(product_type=product_type, retailer=retailer))
    if source in {"auto", "csv"}:
        urls.update(_load_initial_urls_csv(path=path, product_type=product_type))
    return urls


def available_url_keys(path=INITIAL_URLS_CSV, product_type=None, retailer=DEFAULT_RETAILER):
    keys = set()
    source = os.getenv("LOWES_URL_SOURCE", "auto").strip().lower()
    if source in {"auto", "db"}:
        keys.update(_fetch_target_urls_from_db(product_type=product_type, retailer=retailer).keys())
    if source in {"auto", "csv"}:
        keys.update(_load_initial_urls_csv(path=path, product_type=product_type).keys())
    return keys


def has_target_url(page_type, product_type=None, retailer=DEFAULT_RETAILER):
    return _target_url_key(page_type) in available_url_keys(product_type=product_type, retailer=retailer)


def absolute_lowes_url(path):
    if not path:
        return ""
    value = str(path)
    if value.startswith("http"):
        return value
    return f"{LOWES_BASE_URL}{value}"


def lowes_search_url(search_term="refrigerator", offset=0):
    query = {"searchTerm": search_term}
    if offset:
        query["offset"] = offset
    return f"{LOWES_BASE_URL}/search?{urlencode(query)}"


def rel_path(path):
    if path in ("", None):
        return ""
    value = Path(path)
    try:
        return os.path.relpath(value.resolve(), PROJECT_ROOT.resolve())
    except (OSError, ValueError):
        return str(path)
