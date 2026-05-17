import json
import os
from datetime import datetime

from .step00_config import OUTPUT_TABLE_REGISTRY, SEED_DIR, connect, qtable, read_seed_csv, truthy


SEED_CSV = os.getenv("COMMON_OUTPUT_TABLE_SEED_CSV", str(SEED_DIR / "dx_crawler_output_table_seed.csv"))


def now():
    return datetime.now().isoformat(timespec="seconds")


def upsert_row(cur, row):
    key = (
        row.get("corp", "").strip(),
        row.get("product_line", "").strip().upper(),
        row.get("account_name", "").strip(),
        row.get("output_kind", "").strip().lower(),
    )
    values = {
        "schema_name": row.get("schema_name", "public").strip() or "public",
        "table_name": row.get("table_name", "").strip(),
        "csv_name": row.get("csv_name", "").strip(),
        "loader_module": row.get("loader_module", "").strip(),
        "is_active": truthy(row.get("is_active", "true")),
        "notes": row.get("notes", "").strip(),
    }
    if not all(key) or not values["table_name"]:
        return "skipped"

    cur.execute(
        f"""
        UPDATE {qtable(OUTPUT_TABLE_REGISTRY)}
        SET schema_name = %s,
            table_name = %s,
            csv_name = %s,
            loader_module = %s,
            is_active = %s,
            notes = %s,
            updated_at = now()
        WHERE lower(corp) = lower(%s)
          AND upper(product_line) = upper(%s)
          AND lower(account_name) = lower(%s)
          AND lower(output_kind) = lower(%s)
        """,
        (
            values["schema_name"],
            values["table_name"],
            values["csv_name"],
            values["loader_module"],
            values["is_active"],
            values["notes"],
            *key,
        ),
    )
    if cur.rowcount:
        return "updated"
    cur.execute(
        f"""
        INSERT INTO {qtable(OUTPUT_TABLE_REGISTRY)}
          (corp, product_line, account_name, output_kind, schema_name, table_name,
           csv_name, loader_module, is_active, notes)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            *key,
            values["schema_name"],
            values["table_name"],
            values["csv_name"],
            values["loader_module"],
            values["is_active"],
            values["notes"],
        ),
    )
    return "inserted"


def main():
    started_at = now()
    rows = read_seed_csv(SEED_CSV)
    counts = {"inserted": 0, "updated": 0, "skipped": 0}
    conn = connect()
    with conn:
        with conn.cursor() as cur:
            for row in rows:
                counts[upsert_row(cur, row)] += 1
    conn.close()
    manifest = {
        "run_type": "common_setting_step03_seed_output_tables",
        "started_at": started_at,
        "finished_at": now(),
        "seed_csv": SEED_CSV,
        "table": OUTPUT_TABLE_REGISTRY,
        "success": True,
        **counts,
    }
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
