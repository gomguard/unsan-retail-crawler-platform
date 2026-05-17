import json
from datetime import datetime

from .step00_config import OUTPUT_TABLE_REGISTRY, RUN_PROFILE_TABLE, TARGET_URL_TABLE, connect, qtable


def now():
    return datetime.now().isoformat(timespec="seconds")


def add_column(cur, table_name, column_sql):
    cur.execute(f"ALTER TABLE {qtable(table_name)} ADD COLUMN IF NOT EXISTS {column_sql}")


def create_target_url_table(cur):
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {qtable(TARGET_URL_TABLE)} (
          id serial PRIMARY KEY,
          corp varchar(50) NOT NULL,
          product_line varchar(50) NOT NULL,
          account_name varchar(100) NOT NULL,
          page_type varchar(50) NOT NULL,
          url_template text NOT NULL,
          is_active boolean NOT NULL DEFAULT true,
          notes text,
          created_at timestamp without time zone NOT NULL DEFAULT now(),
          updated_at timestamp without time zone NOT NULL DEFAULT now()
        )
        """
    )
    for column_sql in [
        "corp varchar(50)",
        "product_line varchar(50)",
        "account_name varchar(100)",
        "page_type varchar(50)",
        "url_template text",
        "is_active boolean NOT NULL DEFAULT true",
        "notes text",
        "created_at timestamp without time zone NOT NULL DEFAULT now()",
        "updated_at timestamp without time zone NOT NULL DEFAULT now()",
    ]:
        add_column(cur, TARGET_URL_TABLE, column_sql)


def create_output_table_registry(cur):
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {qtable(OUTPUT_TABLE_REGISTRY)} (
          id serial PRIMARY KEY,
          corp varchar(50) NOT NULL,
          product_line varchar(50) NOT NULL,
          account_name varchar(100) NOT NULL,
          output_kind varchar(50) NOT NULL,
          schema_name varchar(100) NOT NULL DEFAULT 'public',
          table_name varchar(200) NOT NULL,
          csv_name varchar(200),
          loader_module varchar(200),
          is_active boolean NOT NULL DEFAULT true,
          notes text,
          created_at timestamp without time zone NOT NULL DEFAULT now(),
          updated_at timestamp without time zone NOT NULL DEFAULT now()
        )
        """
    )
    for column_sql in [
        "corp varchar(50)",
        "product_line varchar(50)",
        "account_name varchar(100)",
        "output_kind varchar(50)",
        "schema_name varchar(100) NOT NULL DEFAULT 'public'",
        "table_name varchar(200)",
        "csv_name varchar(200)",
        "loader_module varchar(200)",
        "is_active boolean NOT NULL DEFAULT true",
        "notes text",
        "created_at timestamp without time zone NOT NULL DEFAULT now()",
        "updated_at timestamp without time zone NOT NULL DEFAULT now()",
    ]:
        add_column(cur, OUTPUT_TABLE_REGISTRY, column_sql)
    cur.execute(
        f"""
        CREATE INDEX IF NOT EXISTS idx_dx_crawler_output_table_lookup
        ON {qtable(OUTPUT_TABLE_REGISTRY)}
        USING btree (corp, product_line, account_name, output_kind, is_active)
        """
    )


def create_run_profile_table(cur):
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {qtable(RUN_PROFILE_TABLE)} (
          id serial PRIMARY KEY,
          corp varchar(50) NOT NULL,
          product_line varchar(50) NOT NULL,
          account_name varchar(100) NOT NULL,
          orchestrator_module varchar(200) NOT NULL,
          default_pages integer,
          detail_limit integer,
          page_workers integer,
          detail_workers integer,
          is_active boolean NOT NULL DEFAULT true,
          notes text,
          created_at timestamp without time zone NOT NULL DEFAULT now(),
          updated_at timestamp without time zone NOT NULL DEFAULT now()
        )
        """
    )
    for column_sql in [
        "corp varchar(50)",
        "product_line varchar(50)",
        "account_name varchar(100)",
        "orchestrator_module varchar(200)",
        "default_pages integer",
        "detail_limit integer",
        "page_workers integer",
        "detail_workers integer",
        "is_active boolean NOT NULL DEFAULT true",
        "notes text",
        "created_at timestamp without time zone NOT NULL DEFAULT now()",
        "updated_at timestamp without time zone NOT NULL DEFAULT now()",
    ]:
        add_column(cur, RUN_PROFILE_TABLE, column_sql)


def main():
    started_at = now()
    conn = connect()
    with conn:
        with conn.cursor() as cur:
            create_target_url_table(cur)
            create_output_table_registry(cur)
            create_run_profile_table(cur)
    conn.close()
    manifest = {
        "run_type": "common_setting_step01_core_tables",
        "started_at": started_at,
        "finished_at": now(),
        "success": True,
        "tables": [TARGET_URL_TABLE, OUTPUT_TABLE_REGISTRY, RUN_PROFILE_TABLE],
    }
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
