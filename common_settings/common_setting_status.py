import json

from .step00_config import OUTPUT_TABLE_REGISTRY, RUN_PROFILE_TABLE, TARGET_URL_TABLE, connect, qtable


def count_table(cur, table_name):
    cur.execute(f"SELECT count(*) FROM {qtable(table_name)}")
    return cur.fetchone()[0]


def sample_output_tables(cur):
    cur.execute(
        f"""
        SELECT corp, product_line, account_name, output_kind, schema_name, table_name, is_active
        FROM {qtable(OUTPUT_TABLE_REGISTRY)}
        ORDER BY account_name, product_line, output_kind
        """
    )
    return [
        {
            "corp": row[0],
            "product_line": row[1],
            "account_name": row[2],
            "output_kind": row[3],
            "schema_name": row[4],
            "table_name": row[5],
            "is_active": row[6],
            "exists": output_table_exists(cur, row[4], row[5]),
        }
        for row in cur.fetchall()
    ]


def output_table_exists(cur, schema_name, table_name):
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = %s AND table_name = %s
        )
        """,
        (schema_name, table_name),
    )
    return bool(cur.fetchone()[0])


def main():
    conn = connect()
    with conn:
        with conn.cursor() as cur:
            payload = {
                "target_url_table": TARGET_URL_TABLE,
                "target_url_rows": count_table(cur, TARGET_URL_TABLE),
                "output_table_registry": OUTPUT_TABLE_REGISTRY,
                "output_table_rows": count_table(cur, OUTPUT_TABLE_REGISTRY),
                "run_profile_table": RUN_PROFILE_TABLE,
                "run_profile_rows": count_table(cur, RUN_PROFILE_TABLE),
                "output_tables": sample_output_tables(cur),
            }
    conn.close()
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
