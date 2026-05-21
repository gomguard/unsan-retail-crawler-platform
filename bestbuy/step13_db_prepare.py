from .step00_config import BESTBUY_OUTPUT_TABLES, BESTBUY_PRODUCT_LIST_TABLES, db_config


TARGET_SCHEMA = "public"


COMMON_COLUMNS = [
    ("id", "serial PRIMARY KEY"),
    ("product", "varchar"),
    ("item", "varchar"),
    ("account_name", "varchar"),
    ("page_type", "varchar"),
    ("count_of_reviews", "text"),
    ("retailer_sku_name", "text"),
    ("product_url", "text"),
    ("star_rating", "varchar"),
    ("count_of_star_ratings", "text"),
    ("sku_popularity", "varchar"),
    ("final_sku_price", "varchar"),
    ("original_sku_price", "varchar"),
    ("savings", "varchar"),
    ("discount_type", "varchar"),
    ("offer", "text"),
    ("pick_up_availability", "text"),
    ("fastest_delivery", "text"),
    ("delivery_availability", "text"),
    ("available_quantity_for_purchase", "varchar"),
    ("inventory_status", "varchar"),
    ("sku_status", "varchar"),
    ("retailer_membership_discounts", "varchar"),
    ("detailed_review_content", "text"),
    ("recommendation_intent", "varchar"),
    ("main_rank", "integer"),
    ("bsr_rank", "integer"),
    ("rank_1", "varchar"),
    ("rank_2", "varchar"),
    ("trend_rank", "integer"),
    ("number_of_ppl_purchased_yesterday", "integer"),
    ("number_of_ppl_added_to_carts", "integer"),
    ("number_of_units_purchased_past_month", "integer"),
    ("retailer_sku_name_similar", "text"),
    ("promotion_type", "varchar"),
    ("calendar_week", "varchar"),
    ("crawl_datetime", "varchar"),
    ("batch_id", "varchar"),
    ("country", "varchar"),
]


REF_COLUMNS = COMMON_COLUMNS + [
    ("capacity", "varchar"),
    ("refrigerator_type", "varchar"),
    ("installation_depth", "varchar"),
    ("ice_maker", "varchar"),
    ("water_dispenser", "varchar"),
    ("color", "varchar"),
    ("height", "varchar"),
    ("width", "varchar"),
    ("depth", "varchar"),
    ("model_year", "varchar"),
]


LDY_COLUMNS = COMMON_COLUMNS + [
    ("washer_capacity", "varchar"),
    ("dryer_capacity", "varchar"),
    ("laundry_type", "varchar"),
    ("fuel_type", "varchar"),
    ("stackable", "varchar"),
    ("high_efficiency", "varchar"),
    ("color", "varchar"),
    ("height", "varchar"),
    ("width", "varchar"),
    ("depth", "varchar"),
    ("model_year", "varchar"),
]


SCHEMAS = {
    "REF": REF_COLUMNS,
    "LDY": LDY_COLUMNS,
}


TV_PRODUCT_LIST_COLUMNS = [
    ("id", "serial4 NOT NULL PRIMARY KEY"),
    ("account_name", "varchar(50) NOT NULL"),
    ("page_type", "varchar(50) NOT NULL"),
    ("retailer_sku_name", "text NULL"),
    ("offer", "varchar(100) NULL"),
    ("pick_up_availability", "varchar(100) NULL"),
    ("fastest_delivery", "varchar(100) NULL"),
    ("delivery_availability", "varchar(100) NULL"),
    ("sku_status", "varchar(100) NULL"),
    ("promotion_type", "varchar(100) NULL"),
    ("trend_rank", "int4 NULL"),
    ("main_rank", "int4 NULL"),
    ("bsr_rank", "int4 NULL"),
    ("product_url", "text NULL"),
    ("calendar_week", "varchar(10) NULL"),
    ("crawl_datetime", "varchar(50) NULL"),
    ("batch_id", "varchar(50) NULL"),
    ("main_page_number", "int4 NULL"),
    ("bsr_page_number", "int4 NULL"),
    ("promotion_position", "int4 NULL"),
]


HHP_PRODUCT_LIST_COLUMNS = [
    ("id", "serial4 NOT NULL PRIMARY KEY"),
    ("account_name", "varchar(50) NOT NULL"),
    ("page_type", "varchar(50) NOT NULL"),
    ("retailer_sku_name", "text NULL"),
    ("final_sku_price", "varchar(50) NULL"),
    ("savings", "varchar(50) NULL"),
    ("comparable_pricing", "varchar(100) NULL"),
    ("offer", "varchar(100) NULL"),
    ("pick_up_availability", "varchar(100) NULL"),
    ("fastest_delivery", "varchar(100) NULL"),
    ("delivery_availability", "varchar(100) NULL"),
    ("sku_status", "varchar(100) NULL"),
    ("promotion_type", "varchar(100) NULL"),
    ("trend_rank", "int4 NULL"),
    ("main_rank", "int4 NULL"),
    ("bsr_rank", "int4 NULL"),
    ("product_url", "text NULL"),
    ("calendar_week", "varchar(10) NULL"),
    ("crawl_strdatetime", "varchar(50) NULL"),
    ("batch_id", "varchar(50) NULL"),
    ("main_page_number", "int4 NULL"),
    ("bsr_page_number", "int4 NULL"),
]

PRODUCT_LIST_SCHEMAS = {
    "TV": TV_PRODUCT_LIST_COLUMNS,
    "HHP": HHP_PRODUCT_LIST_COLUMNS,
    "REF": HHP_PRODUCT_LIST_COLUMNS,
    "LDY": HHP_PRODUCT_LIST_COLUMNS,
}


def quote_ident(value):
    return '"' + str(value).replace('"', '""') + '"'


def table_exists(cur, table_name, schema=TARGET_SCHEMA):
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = %s AND table_name = %s
        )
        """,
        (schema, table_name),
    )
    return bool(cur.fetchone()[0])


def create_table(cur, table_name, columns):
    column_sql = ",\n  ".join(f"{quote_ident(name)} {data_type}" for name, data_type in columns)
    cur.execute(f"CREATE TABLE {quote_ident(TARGET_SCHEMA)}.{quote_ident(table_name)} (\n  {column_sql}\n)")


def create_product_list_indexes(cur, table_name, crawl_column):
    prefix = table_name[:45]
    cur.execute(
        f"CREATE INDEX {quote_ident(f'idx_{prefix}_crawl')} "
        f"ON {quote_ident(TARGET_SCHEMA)}.{quote_ident(table_name)} USING btree ({quote_ident(crawl_column)})"
    )
    cur.execute(
        f"CREATE INDEX {quote_ident(f'idx_{prefix}_page_type')} "
        f"ON {quote_ident(TARGET_SCHEMA)}.{quote_ident(table_name)} USING btree (page_type)"
    )
    cur.execute(
        f"CREATE INDEX {quote_ident(f'idx_{prefix}_product_url')} "
        f"ON {quote_ident(TARGET_SCHEMA)}.{quote_ident(table_name)} USING btree (product_url)"
    )


def main():
    import psycopg2

    config = db_config()
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
    created = []
    skipped = []
    with conn:
        with conn.cursor() as cur:
            for category, columns in SCHEMAS.items():
                table_name = BESTBUY_OUTPUT_TABLES[category]
                if table_exists(cur, table_name):
                    skipped.append(table_name)
                    continue
                create_table(cur, table_name, columns)
                created.append(table_name)
            for category, table_name in BESTBUY_PRODUCT_LIST_TABLES.items():
                if table_exists(cur, table_name):
                    skipped.append(table_name)
                    continue
                columns = PRODUCT_LIST_SCHEMAS.get(category, HHP_PRODUCT_LIST_COLUMNS)
                create_table(cur, table_name, columns)
                crawl_column = "crawl_datetime" if category == "TV" else "crawl_strdatetime"
                create_product_list_indexes(cur, table_name, crawl_column)
                created.append(table_name)
    conn.close()
    print({"created": created, "skipped_existing": skipped})


if __name__ == "__main__":
    main()
