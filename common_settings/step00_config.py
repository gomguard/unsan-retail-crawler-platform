import ast
import csv
import json
import os
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent
SEED_DIR = PACKAGE_DIR / "seeds"
DEFAULT_SCHEMA = os.getenv("COMMON_DB_SCHEMA", "public")
TARGET_URL_TABLE = os.getenv("COMMON_TARGET_URL_TABLE", "public.common_setting_step01_target_page_url")
OUTPUT_TABLE_REGISTRY = os.getenv("COMMON_OUTPUT_TABLE_REGISTRY", "public.common_setting_step02_output_table")
RUN_PROFILE_TABLE = os.getenv("COMMON_RUN_PROFILE_TABLE", "public.common_setting_step03_run_profile")


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


def connect():
    import psycopg2

    config = db_config()
    if not config:
        raise RuntimeError("DB_CONFIG is missing")
    return psycopg2.connect(
        host=config.get("host"),
        port=int(config.get("port") or 5432),
        user=config.get("user"),
        password=config.get("password"),
        dbname=config.get("database"),
        connect_timeout=10,
    )


def quote_ident(value):
    return '"' + str(value).replace('"', '""') + '"'


def split_table_name(value, default_schema=DEFAULT_SCHEMA):
    parts = [part.strip() for part in str(value).split(".") if part.strip()]
    if len(parts) == 1:
        return default_schema, parts[0]
    return parts[-2], parts[-1]


def qtable(value):
    schema, table = split_table_name(value)
    return f"{quote_ident(schema)}.{quote_ident(table)}"


def read_seed_csv(path):
    with Path(path).open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def truthy(value):
    return str(value if value is not None else "true").strip().lower() in {"1", "true", "yes", "y"}
