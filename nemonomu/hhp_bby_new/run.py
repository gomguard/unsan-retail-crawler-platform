import argparse
import ast
import csv
import json
import os
import re
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DIR = ROOT / "sample_csv"
OUTPUT_DIR = Path(__file__).resolve().parent / "output"

FINAL_TABLE = "hhp_retail_com_bby_v2_test"
PRODUCT_LIST_TABLE = "bby_hhp_product_list_v2_test"
FINAL_PATTERN = "hhp_retail_com_*.csv"
PRODUCT_LIST_PATTERN = "bby_hhp_product_list_*.csv"


BSIN_RE = re.compile(r"/product/[^/]+/([^/?#]+)(?:/sku/\d+)?(?:[?#].*)?$")


def latest_file(pattern):
    files = sorted(SAMPLE_DIR.glob(pattern), key=lambda path: path.stat().st_mtime, reverse=True)
    if not files:
        raise FileNotFoundError(f"No sample file found: {SAMPLE_DIR / pattern}")
    return files[0]


def read_csv(path):
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader), list(reader.fieldnames or [])


def write_csv(path, rows, fields):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def bsin_from_url(url):
    match = BSIN_RE.search(str(url or "").strip())
    return match.group(1).strip() if match else ""


def repair_item(rows):
    changed = 0
    unresolved = []
    for row in rows:
        if str(row.get("account_name") or "").strip().lower() != "bestbuy":
            continue
        if str(row.get("item") or "").strip():
            continue
        bsin = bsin_from_url(row.get("product_url"))
        if bsin:
            row["item"] = bsin
            changed += 1
        else:
            unresolved.append(row.get("product_url", ""))
    return changed, unresolved


def load_env(path=None):
    env_path = Path(path or (ROOT / ".env"))
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


def db_config():
    raw = os.getenv("DB_CONFIG", "")
    if not raw:
        return {}
    for parser in (json.loads, ast.literal_eval):
        try:
            value = parser(raw)
            return value if isinstance(value, dict) else {}
        except Exception:
            pass
    return {}


def quote_ident(value):
    return '"' + str(value).replace('"', '""') + '"'


def table_columns(cur, table_name):
    cur.execute(
        """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s
        ORDER BY ordinal_position
        """,
        ("public", table_name),
    )
    return [(row[0], row[1]) for row in cur.fetchall()]


def normalize_value(value, data_type):
    if value in ("", None):
        return None
    if str(data_type).lower() in {"integer", "bigint", "smallint"}:
        try:
            return int(str(value).replace(",", "").strip())
        except ValueError:
            return None
    return value


def load_table(cur, csv_path, table_name):
    rows, _ = read_csv(csv_path)
    columns = table_columns(cur, table_name)
    if not columns:
        raise RuntimeError(f"Target table not found: public.{table_name}")
    batch_ids = sorted({row.get("batch_id", "").strip() for row in rows if row.get("batch_id")})
    if batch_ids and any(name == "batch_id" for name, _ in columns):
        cur.execute(
            f"DELETE FROM public.{quote_ident(table_name)} WHERE batch_id = ANY(%s)",
            (batch_ids,),
        )
    csv_fields = set(rows[0].keys()) if rows else set()
    insert_columns = [(name, dtype) for name, dtype in columns if name != "id" and name in csv_fields]
    if not rows or not insert_columns:
        return {"table": table_name, "inserted": 0}
    sql = (
        f"INSERT INTO public.{quote_ident(table_name)} "
        f"({', '.join(quote_ident(name) for name, _ in insert_columns)}) "
        f"VALUES ({', '.join(['%s'] * len(insert_columns))})"
    )
    values = [
        tuple(normalize_value(row.get(name), dtype) for name, dtype in insert_columns)
        for row in rows
    ]
    cur.executemany(sql, values)
    return {"table": table_name, "inserted": len(values), "columns": [name for name, _ in insert_columns]}


def load_db(final_csv, product_list_csv):
    import psycopg2

    load_env()
    config = db_config()
    if not config:
        raise RuntimeError("DB_CONFIG is missing. Put it in .env on the RDP machine.")
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
            final_result = load_table(cur, final_csv, FINAL_TABLE)
            product_result = load_table(cur, product_list_csv, PRODUCT_LIST_TABLE)
    conn.close()
    return {"final": final_result, "product_list": product_result}


def main():
    parser = argparse.ArgumentParser(description="Repair BestBuy HHP sample CSV and optionally load Unsan default tables.")
    parser.add_argument("--final-csv", default=str(latest_file(FINAL_PATTERN)))
    parser.add_argument("--product-list-csv", default=str(latest_file(PRODUCT_LIST_PATTERN)))
    parser.add_argument("--load-db", action="store_true")
    args = parser.parse_args()

    rows, fields = read_csv(args.final_csv)
    changed, unresolved = repair_item(rows)
    product_rows, product_fields = read_csv(args.product_list_csv)

    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    final_out = OUTPUT_DIR / f"hhp_retail_com_bestbuy_complete_{stamp}.csv"
    product_out = OUTPUT_DIR / f"bby_hhp_product_list_{stamp}.csv"
    write_csv(final_out, rows, fields)
    write_csv(product_out, product_rows, product_fields)

    result = {
        "category": "HHP",
        "source_final_csv": str(Path(args.final_csv).resolve()),
        "source_product_list_csv": str(Path(args.product_list_csv).resolve()),
        "output_final_csv": str(final_out.resolve()),
        "output_product_list_csv": str(product_out.resolve()),
        "bestbuy_item_backfilled": changed,
        "unresolved_item_urls": unresolved,
        "load_db": None,
    }
    if args.load_db:
        result["load_db"] = load_db(final_out, product_out)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

