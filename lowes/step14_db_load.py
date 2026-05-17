import csv
import json
import os
from datetime import datetime
from pathlib import Path

from .step00_config import (
    DEFAULT_LOWES_RUN_ROOT,
    db_config,
    lowes_output_table,
    lowes_product_type,
    lowes_run_date,
    rel_path,
)


RUN_DATE = lowes_run_date()
RUN_ROOT = Path(os.getenv("LOWES_RUN_ROOT", str(DEFAULT_LOWES_RUN_ROOT)))
OUTPUT_ROOT = Path(os.getenv("LOWES_OUTPUT_ROOT", str(RUN_ROOT / "output")))
FINAL_OUTPUT_CSV = Path(os.getenv("LOWES_FINAL_OUTPUT_CSV", str(OUTPUT_ROOT / "final_output.csv")))
MANIFEST_PATH = OUTPUT_ROOT / "db_load_manifest.json"
TARGET_SCHEMA = os.getenv("LOWES_DB_SCHEMA", "public").strip() or "public"
TARGET_TABLE = lowes_output_table()


def now():
    return datetime.now().isoformat(timespec="seconds")


def quote_ident(value):
    return '"' + str(value).replace('"', '""') + '"'


def read_rows(path):
    with Path(path).open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def as_int(value):
    try:
        if value in ("", None):
            return None
        return int(float(str(value).replace(",", "").strip()))
    except (TypeError, ValueError):
        return None


def pick(row, *names):
    for name in names:
        value = row.get(name)
        if value not in ("", None):
            return value
    return None


def table_exists(cur):
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = %s AND table_name = %s
        )
        """,
        (TARGET_SCHEMA, TARGET_TABLE),
    )
    return bool(cur.fetchone()[0])


def delete_existing_batch(cur, rows):
    batch_ids = sorted({str(row.get("batch_id") or "").strip() for row in rows if row.get("batch_id")})
    if batch_ids:
        cur.execute(
            f"DELETE FROM {quote_ident(TARGET_SCHEMA)}.{quote_ident(TARGET_TABLE)} WHERE batch_id = ANY(%s)",
            (batch_ids,),
        )
        return cur.rowcount
    if os.getenv("LOWES_DB_LOAD_TRUNCATE", "1").strip().lower() in {"1", "true", "yes", "y"}:
        cur.execute(f"TRUNCATE TABLE {quote_ident(TARGET_SCHEMA)}.{quote_ident(TARGET_TABLE)}")
        return cur.rowcount
    return 0


def insert_rows(cur, rows):
    if not rows:
        return 0
    sql = f"""
        INSERT INTO {quote_ident(TARGET_SCHEMA)}.{quote_ident(TARGET_TABLE)} (
          product_type,
          run_date,
          batch_id,
          omni_item_id,
          item_number,
          brand,
          model_id,
          main_rank,
          bsr_rank,
          final_target_rank,
          product_url,
          retailer_sku_name,
          final_selling_price,
          final_price_source,
          row_json
        ) VALUES (
          %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb
        )
    """
    values = []
    product_type = lowes_product_type().upper()
    for row in rows:
        values.append(
            (
                product_type,
                RUN_DATE,
                pick(row, "batch_id"),
                pick(row, "omni_item_id", "product.omniitemid", "missing_price_detail_product_id"),
                pick(row, "item_number", "product.itemnumber", "missing_price_detail_item_number"),
                pick(row, "brand", "product.brand", "missing_price_detail_brand"),
                pick(row, "model_id", "product.modelid", "missing_price_detail_model_id"),
                as_int(pick(row, "main_rank")),
                as_int(pick(row, "bsr_rank")),
                as_int(pick(row, "final_target_rank", "target_rank")),
                pick(row, "product_url", "missing_price_source_product_url"),
                pick(row, "retailer_sku_name", "description", "product.description", "missing_price_detail_title"),
                pick(row, "final_selling_price", "selling_price", "missing_price_resolved_selling_price"),
                pick(row, "final_price_source", "price_source", "missing_price_resolved_price_source"),
                json.dumps(row, ensure_ascii=False),
            )
        )
    cur.executemany(sql, values)
    return len(values)


def main():
    started_at = now()
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    if not FINAL_OUTPUT_CSV.exists():
        raise RuntimeError(f"final output CSV not found: {FINAL_OUTPUT_CSV}")

    rows = read_rows(FINAL_OUTPUT_CSV)
    config = db_config()
    if not config:
        raise RuntimeError("DB_CONFIG is missing")

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
            if not table_exists(cur):
                raise RuntimeError(f"DB table not found: {TARGET_SCHEMA}.{TARGET_TABLE}")
            deleted = delete_existing_batch(cur, rows)
            inserted = insert_rows(cur, rows)
    conn.close()

    manifest = {
        "run_type": "step14_db_load",
        "started_at": started_at,
        "finished_at": now(),
        "run_date": RUN_DATE,
        "product_type": lowes_product_type().upper(),
        "run_root": rel_path(RUN_ROOT),
        "output_root": rel_path(OUTPUT_ROOT),
        "final_output_csv": rel_path(FINAL_OUTPUT_CSV),
        "schema": TARGET_SCHEMA,
        "table": TARGET_TABLE,
        "csv_rows": len(rows),
        "deleted_existing": deleted,
        "inserted": inserted,
        "success": True,
        "skipped": False,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
