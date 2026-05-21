import csv
import json
import os
import re
from datetime import datetime
from pathlib import Path

from .step00_config import (
    DEFAULT_BESTBUY_RUN_ROOT,
    bestbuy_category,
    bestbuy_output_table,
    bestbuy_product_list_table,
    db_config,
    rel_path,
)


TARGET_SCHEMA = "public"
CATEGORY = bestbuy_category()
RUN_ROOT = Path(os.getenv("BESTBUY_RUN_ROOT", DEFAULT_BESTBUY_RUN_ROOT))
OUTPUT_ROOT = RUN_ROOT / "output"
FINAL_OUTPUT_CSV = OUTPUT_ROOT / "final_output.csv"
PRODUCT_LIST_CSV = OUTPUT_ROOT / "bestbuy_product_list.csv"
MANIFEST_PATH = OUTPUT_ROOT / "db_load_manifest.json"
DB_LOAD_DRY_RUN = os.getenv("DB_LOAD_DRY_RUN", "0").strip().lower() in {"1", "true", "yes", "y"}


def now():
    return datetime.now().isoformat(timespec="seconds")


def quote_ident(value):
    return '"' + str(value).replace('"', '""') + '"'


def read_csv(path):
    path = Path(path)
    if not path.exists():
        raise RuntimeError(f"CSV not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def table_columns(cur, table_name):
    cur.execute(
        """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s
        ORDER BY ordinal_position
        """,
        (TARGET_SCHEMA, table_name),
    )
    return [(row[0], row[1]) for row in cur.fetchall()]


def normalize_value(value, data_type):
    if value in ("", None):
        return None
    data_type = str(data_type or "").lower()
    if data_type in {"integer", "bigint", "smallint"}:
        text = str(value).replace(",", "").strip()
        match = re.search(r"-?\d+", text)
        if not match:
            return None
        try:
            return int(match.group(0))
        except ValueError:
            return None
    return value


def delete_existing_batch(cur, table_name, columns, rows):
    column_names = {name for name, _ in columns}
    if "batch_id" not in column_names:
        return 0
    batch_ids = sorted({str(row.get("batch_id") or "").strip() for row in rows if row.get("batch_id")})
    if not batch_ids:
        return 0
    cur.execute(
        f"DELETE FROM {quote_ident(TARGET_SCHEMA)}.{quote_ident(table_name)} WHERE batch_id = ANY(%s)",
        (batch_ids,),
    )
    return cur.rowcount


def insert_rows(cur, table_name, columns, rows):
    if not rows:
        return {"inserted": 0, "deleted_existing": 0, "columns": []}
    insert_columns = [(name, data_type) for name, data_type in columns if name != "id"]
    csv_fields = set(rows[0].keys())
    insert_columns = [(name, data_type) for name, data_type in insert_columns if name in csv_fields]
    if not insert_columns:
        return {"inserted": 0, "deleted_existing": 0, "columns": []}

    deleted = delete_existing_batch(cur, table_name, columns, rows)
    column_sql = ", ".join(quote_ident(name) for name, _ in insert_columns)
    placeholders = ", ".join(["%s"] * len(insert_columns))
    sql = f"INSERT INTO {quote_ident(TARGET_SCHEMA)}.{quote_ident(table_name)} ({column_sql}) VALUES ({placeholders})"
    values = [
        tuple(normalize_value(row.get(name), data_type) for name, data_type in insert_columns)
        for row in rows
    ]
    cur.executemany(sql, values)
    return {
        "inserted": len(values),
        "deleted_existing": deleted,
        "columns": [name for name, _ in insert_columns],
    }


def load_one(cur, csv_path, table_name):
    rows = read_csv(csv_path)
    if not rows:
        raise RuntimeError(f"CSV has no data rows: {csv_path}")
    columns = table_columns(cur, table_name)
    if not columns:
        raise RuntimeError(f"DB table not found or has no columns: {TARGET_SCHEMA}.{table_name}")
    result = insert_rows(cur, table_name, columns, rows)
    result.update(
        {
            "csv": rel_path(csv_path),
            "table": f"{TARGET_SCHEMA}.{table_name}",
            "csv_rows": len(rows),
        }
    )
    return result


def planned_load(csv_path, table_name):
    rows = read_csv(csv_path)
    if not rows:
        raise RuntimeError(f"CSV has no data rows: {csv_path}")
    return {
        "csv": rel_path(csv_path),
        "table": f"{TARGET_SCHEMA}.{table_name}",
        "csv_rows": len(rows),
        "columns_in_csv": list(rows[0].keys()),
    }


def main():
    import psycopg2

    started_at = now()
    config = db_config()
    final_table = bestbuy_output_table(CATEGORY)
    product_list_table = bestbuy_product_list_table(CATEGORY)

    if DB_LOAD_DRY_RUN:
        manifest = {
            "run_type": "step14_db_load",
            "dry_run": True,
            "started_at": started_at,
            "finished_at": now(),
            "category": CATEGORY,
            "run_root": rel_path(RUN_ROOT),
            "final_output": planned_load(FINAL_OUTPUT_CSV, final_table),
            "product_list": planned_load(PRODUCT_LIST_CSV, product_list_table),
        }
        print(json.dumps(manifest, indent=2, ensure_ascii=False))
        return

    if not config:
        raise RuntimeError("DB_CONFIG is missing")

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
            final_result = load_one(cur, FINAL_OUTPUT_CSV, final_table)
            product_list_result = load_one(cur, PRODUCT_LIST_CSV, product_list_table)
    conn.close()

    manifest = {
        "run_type": "step14_db_load",
        "started_at": started_at,
        "finished_at": now(),
        "category": CATEGORY,
        "run_root": rel_path(RUN_ROOT),
        "final_output": final_result,
        "product_list": product_list_result,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
