import json
import os
from datetime import datetime

from .step00_config import OUTPUT_TABLE_REGISTRY, connect, qtable, quote_ident


INTEGER_COLUMNS = {
    "main_rank",
    "bsr_rank",
    "trend_rank",
    "promotion_position",
    "number_of_ppl_purchased_yesterday",
    "number_of_ppl_added_to_carts",
    "number_of_units_purchased_past_month",
    "main_page_number",
    "bsr_page_number",
    "final_target_rank",
}


BESTBUY_FINAL_FIELDS = {
    "TV": [
        "id",
        "item",
        "account_name",
        "page_type",
        "count_of_reviews",
        "retailer_sku_name",
        "product_url",
        "star_rating",
        "count_of_star_ratings",
        "screen_size",
        "sku_popularity",
        "final_sku_price",
        "original_sku_price",
        "savings",
        "discount_type",
        "offer",
        "pick_up_availability",
        "fastest_delivery",
        "delivery_availability",
        "shipping_info",
        "available_quantity_for_purchase",
        "inventory_status",
        "sku_status",
        "retailer_membership_discounts",
        "detailed_review_content",
        "summarized_review_content",
        "top_mentions",
        "recommendation_intent",
        "main_rank",
        "bsr_rank",
        "rank_1",
        "rank_2",
        "promotion_position",
        "trend_rank",
        "number_of_ppl_purchased_yesterday",
        "number_of_ppl_added_to_carts",
        "retailer_sku_name_similar",
        "estimated_annual_electricity_use",
        "promotion_type",
        "calendar_week",
        "crawl_datetime",
        "number_of_units_purchased_past_month",
        "model_year",
        "batch_id",
        "country",
    ],
    "HHP": [
        "id",
        "country",
        "product",
        "item",
        "account_name",
        "page_type",
        "count_of_reviews",
        "retailer_sku_name",
        "product_url",
        "star_rating",
        "count_of_star_ratings",
        "sku_popularity",
        "final_sku_price",
        "original_sku_price",
        "savings",
        "discount_type",
        "offer",
        "bundle",
        "pick_up_availability",
        "fastest_delivery",
        "delivery_availability",
        "shipping_info",
        "available_quantity_for_purchase",
        "inventory_status",
        "sku_status",
        "retailer_membership_discounts",
        "trade_in",
        "hhp_storage",
        "hhp_color",
        "hhp_carrier",
        "detailed_review_content",
        "summarized_review_content",
        "top_mentions",
        "recommendation_intent",
        "main_rank",
        "bsr_rank",
        "rank_1",
        "rank_2",
        "trend_rank",
        "number_of_ppl_purchased_yesterday",
        "number_of_ppl_added_to_carts",
        "number_of_units_purchased_past_month",
        "retailer_sku_name_similar",
        "promotion_type",
        "calendar_week",
        "crawl_strdatetime",
        "batch_id",
    ],
    "REF": [
        "id",
        "item",
        "account_name",
        "page_type",
        "count_of_reviews",
        "retailer_sku_name",
        "product_url",
        "star_rating",
        "count_of_star_ratings",
        "sku_popularity",
        "final_sku_price",
        "original_sku_price",
        "savings",
        "discount_type",
        "offer",
        "pick_up_availability",
        "fastest_delivery",
        "delivery_availability",
        "available_quantity_for_purchase",
        "inventory_status",
        "sku_status",
        "retailer_membership_discounts",
        "detailed_review_content",
        "recommendation_intent",
        "main_rank",
        "bsr_rank",
        "rank_1",
        "rank_2",
        "trend_rank",
        "number_of_ppl_purchased_yesterday",
        "number_of_ppl_added_to_carts",
        "number_of_units_purchased_past_month",
        "retailer_sku_name_similar",
        "promotion_type",
        "calendar_week",
        "crawl_datetime",
        "batch_id",
        "country",
        "capacity",
        "refrigerator_type",
        "installation_depth",
        "ice_maker",
        "water_dispenser",
        "color",
        "height",
        "width",
        "depth",
        "model_year",
    ],
    "LDY": [
        "id",
        "item",
        "account_name",
        "page_type",
        "count_of_reviews",
        "retailer_sku_name",
        "product_url",
        "star_rating",
        "count_of_star_ratings",
        "sku_popularity",
        "final_sku_price",
        "original_sku_price",
        "savings",
        "discount_type",
        "offer",
        "pick_up_availability",
        "fastest_delivery",
        "delivery_availability",
        "available_quantity_for_purchase",
        "inventory_status",
        "sku_status",
        "retailer_membership_discounts",
        "detailed_review_content",
        "recommendation_intent",
        "main_rank",
        "bsr_rank",
        "rank_1",
        "rank_2",
        "trend_rank",
        "number_of_ppl_purchased_yesterday",
        "number_of_ppl_added_to_carts",
        "number_of_units_purchased_past_month",
        "retailer_sku_name_similar",
        "promotion_type",
        "calendar_week",
        "crawl_datetime",
        "batch_id",
        "country",
        "washer_capacity",
        "dryer_capacity",
        "laundry_type",
        "fuel_type",
        "stackable",
        "high_efficiency",
        "color",
        "height",
        "width",
        "depth",
        "model_year",
    ],
}


BESTBUY_PRODUCT_LIST_FIELDS = {
    "TV": [
        "id",
        "account_name",
        "page_type",
        "retailer_sku_name",
        "offer",
        "pick_up_availability",
        "fastest_delivery",
        "delivery_availability",
        "sku_status",
        "promotion_type",
        "trend_rank",
        "main_rank",
        "bsr_rank",
        "product_url",
        "calendar_week",
        "crawl_datetime",
        "batch_id",
        "main_page_number",
        "bsr_page_number",
        "promotion_position",
        "sku_id",
        "category_key",
        "final_target_rank",
    ],
    "DEFAULT": [
        "id",
        "account_name",
        "page_type",
        "retailer_sku_name",
        "final_sku_price",
        "savings",
        "comparable_pricing",
        "offer",
        "pick_up_availability",
        "fastest_delivery",
        "delivery_availability",
        "sku_status",
        "promotion_type",
        "trend_rank",
        "main_rank",
        "bsr_rank",
        "product_url",
        "calendar_week",
        "crawl_strdatetime",
        "batch_id",
        "main_page_number",
        "bsr_page_number",
        "sku_id",
        "category_key",
        "final_target_rank",
    ],
}


LOWES_FINAL_COLUMNS = [
    ("id", "bigserial PRIMARY KEY"),
    ("product_type", "varchar(20)"),
    ("run_date", "varchar(8)"),
    ("batch_id", "varchar(80)"),
    ("omni_item_id", "text"),
    ("item_number", "text"),
    ("brand", "text"),
    ("model_id", "text"),
    ("main_rank", "integer"),
    ("bsr_rank", "integer"),
    ("final_target_rank", "integer"),
    ("product_url", "text"),
    ("retailer_sku_name", "text"),
    ("final_selling_price", "text"),
    ("final_price_source", "text"),
    ("row_json", "jsonb NOT NULL"),
    ("loaded_at", "timestamptz NOT NULL DEFAULT now()"),
]


GENERIC_JSON_COLUMNS = [
    ("id", "bigserial PRIMARY KEY"),
    ("corp", "varchar(50)"),
    ("product_line", "varchar(50)"),
    ("account_name", "varchar(100)"),
    ("output_kind", "varchar(50)"),
    ("page_type", "varchar(50)"),
    ("batch_id", "varchar(80)"),
    ("product_url", "text"),
    ("retailer_sku_name", "text"),
    ("final_sku_price", "text"),
    ("main_rank", "integer"),
    ("bsr_rank", "integer"),
    ("row_json", "jsonb"),
    ("loaded_at", "timestamptz NOT NULL DEFAULT now()"),
]


def now():
    return datetime.now().isoformat(timespec="seconds")


def column_type(name):
    if name == "id":
        return "serial PRIMARY KEY"
    if name in INTEGER_COLUMNS:
        return "integer"
    if name in {"row_json"}:
        return "jsonb"
    if name in {"loaded_at"}:
        return "timestamptz NOT NULL DEFAULT now()"
    if name in {"detailed_review_content", "summarized_review_content", "top_mentions", "product_url"}:
        return "text"
    return "varchar"


def fields_to_columns(fields):
    return [(field, column_type(field)) for field in fields]


def qname(schema, table):
    return f"{quote_ident(schema)}.{quote_ident(table)}"


def index_name(table, suffix):
    raw = f"idx_{table}_{suffix}"
    return raw[:63]


def table_exists(cur, schema, table):
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
    return bool(cur.fetchone()[0])


def ensure_schema(cur, schema):
    cur.execute(f"CREATE SCHEMA IF NOT EXISTS {quote_ident(schema)}")


def create_table(cur, schema, table, columns):
    column_sql = ",\n  ".join(f"{quote_ident(name)} {data_type}" for name, data_type in columns)
    cur.execute(f"CREATE TABLE IF NOT EXISTS {qname(schema, table)} (\n  {column_sql}\n)")


def add_missing_columns(cur, schema, table, columns):
    for name, data_type in columns:
        if name == "id":
            continue
        cur.execute(f"ALTER TABLE {qname(schema, table)} ADD COLUMN IF NOT EXISTS {quote_ident(name)} {data_type}")


def create_indexes(cur, schema, table, columns):
    names = {name for name, _ in columns}
    for column in ["batch_id", "page_type", "product_url", "main_rank", "omni_item_id"]:
        if column not in names:
            continue
        cur.execute(
            f"""
            CREATE INDEX IF NOT EXISTS {quote_ident(index_name(table, column))}
            ON {qname(schema, table)}
            USING btree ({quote_ident(column)})
            """
        )


def registry_rows(cur):
    include_inactive = os.getenv("COMMON_PREPARE_INACTIVE_OUTPUT_TABLES", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
    }
    where_sql = "" if include_inactive else "WHERE is_active = true"
    cur.execute(
        f"""
        SELECT corp, product_line, account_name, output_kind, schema_name, table_name, is_active
        FROM {qtable(OUTPUT_TABLE_REGISTRY)}
        {where_sql}
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
        }
        for row in cur.fetchall()
    ]


def columns_for(row):
    retailer = str(row["account_name"] or "").strip().lower()
    product_line = str(row["product_line"] or "").strip().upper()
    output_kind = str(row["output_kind"] or "").strip().lower()
    if retailer == "bestbuy" and output_kind == "final":
        return fields_to_columns(BESTBUY_FINAL_FIELDS.get(product_line, BESTBUY_FINAL_FIELDS["HHP"]))
    if retailer == "bestbuy" and output_kind == "product_list":
        fields = BESTBUY_PRODUCT_LIST_FIELDS["TV"] if product_line == "TV" else BESTBUY_PRODUCT_LIST_FIELDS["DEFAULT"]
        return fields_to_columns(fields)
    if retailer == "lowes" and output_kind == "final":
        return LOWES_FINAL_COLUMNS
    return GENERIC_JSON_COLUMNS


def prepare_one(cur, row):
    schema = str(row["schema_name"] or "public").strip() or "public"
    table = str(row["table_name"] or "").strip()
    if not table:
        return {**row, "success": False, "reason": "missing table_name"}
    columns = columns_for(row)
    ensure_schema(cur, schema)
    existed = table_exists(cur, schema, table)
    create_table(cur, schema, table, columns)
    add_missing_columns(cur, schema, table, columns)
    create_indexes(cur, schema, table, columns)
    return {
        **row,
        "schema_name": schema,
        "table_name": table,
        "created": not existed,
        "success": True,
        "column_count": len(columns),
    }


def main():
    started_at = now()
    results = []
    conn = connect()
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("SET lock_timeout TO '5s'")
        cur.execute("SET statement_timeout TO '60s'")
        rows = registry_rows(cur)
        for row in rows:
            print(
                f"[prepare] {row['account_name']} {row['product_line']} {row['output_kind']} "
                f"-> {row['schema_name']}.{row['table_name']}",
                flush=True,
            )
            results.append(prepare_one(cur, row))
    conn.close()
    payload = {
        "run_type": "common_setting_step05_prepare_output_tables",
        "started_at": started_at,
        "finished_at": now(),
        "registry": OUTPUT_TABLE_REGISTRY,
        "prepared_count": sum(1 for result in results if result.get("success")),
        "created_count": sum(1 for result in results if result.get("created")),
        "results": results,
        "success": all(result.get("success") for result in results),
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
