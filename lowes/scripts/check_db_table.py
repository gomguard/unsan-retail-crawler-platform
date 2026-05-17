import os
import sys
from pathlib import Path

import psycopg2

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from lowes.step00_config import db_config


def main():
    schema = os.getenv("LOWES_DB_SCHEMA", "public")
    table = os.getenv("LOWES_DB_FINAL_TABLE", "ldy_retail_com_lowes")
    config = db_config()
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
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_schema = %s AND table_name = %s
                )
                """,
                (schema, table),
            )
            exists = bool(cur.fetchone()[0])
            rows = None
            if exists:
                cur.execute(f'SELECT count(*) FROM "{schema}"."{table}"')
                rows = cur.fetchone()[0]
    conn.close()
    print({"schema": schema, "table": table, "exists": exists, "rows": rows})


if __name__ == "__main__":
    main()
