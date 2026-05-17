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
TARGET_SCHEMA = os.getenv("LOWES_DB_SCHEMA", "public").strip() or "public"
TARGET_TABLE = lowes_output_table()


def now():
    return datetime.now().isoformat(timespec="seconds")


def quote_ident(value):
    return '"' + str(value).replace('"', '""') + '"'


def ensure_table(cur):
    cur.execute(f"CREATE SCHEMA IF NOT EXISTS {quote_ident(TARGET_SCHEMA)}")
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {quote_ident(TARGET_SCHEMA)}.{quote_ident(TARGET_TABLE)} (
          id bigserial PRIMARY KEY,
          product_type varchar(20),
          run_date varchar(8),
          batch_id varchar(80),
          omni_item_id text,
          item_number text,
          brand text,
          model_id text,
          main_rank integer,
          bsr_rank integer,
          final_target_rank integer,
          product_url text,
          retailer_sku_name text,
          final_selling_price text,
          final_price_source text,
          row_json jsonb NOT NULL,
          loaded_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    index_prefix = TARGET_TABLE[:45]
    indexes = [
        (f"idx_{index_prefix}_batch", "batch_id"),
        (f"idx_{index_prefix}_omni", "omni_item_id"),
        (f"idx_{index_prefix}_main_rank", "main_rank"),
    ]
    for index_name, column_name in indexes:
        cur.execute(
            f"""
            CREATE INDEX IF NOT EXISTS {quote_ident(index_name)}
            ON {quote_ident(TARGET_SCHEMA)}.{quote_ident(TARGET_TABLE)}
            USING btree ({quote_ident(column_name)})
            """
        )


def main():
    started_at = now()
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
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
            ensure_table(cur)
    conn.close()

    manifest = {
        "run_type": "step13_db_prepare",
        "started_at": started_at,
        "finished_at": now(),
        "run_date": RUN_DATE,
        "product_type": lowes_product_type().upper(),
        "run_root": rel_path(RUN_ROOT),
        "output_root": rel_path(OUTPUT_ROOT),
        "schema": TARGET_SCHEMA,
        "table": TARGET_TABLE,
        "success": True,
        "skipped": False,
    }
    (OUTPUT_ROOT / "manifest_db_prepare.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
