import json
import os
from datetime import datetime

from .step00_config import SEED_DIR, TARGET_URL_TABLE, connect, qtable, read_seed_csv, truthy


SEED_CSV = os.getenv("COMMON_TARGET_URL_SEED_CSV", str(SEED_DIR / "dx_target_page_url_seed.csv"))


def now():
    return datetime.now().isoformat(timespec="seconds")


def upsert_row(cur, row):
    key = (
        row.get("corp", "").strip(),
        row.get("product_line", "").strip().upper(),
        row.get("account_name", "").strip(),
        row.get("page_type", "").strip().lower(),
    )
    values = {
        "url_template": row.get("url_template", "").strip(),
        "is_active": truthy(row.get("is_active", "true")),
        "notes": row.get("notes", "").strip(),
    }
    if not all(key) or not values["url_template"]:
        return "skipped"

    cur.execute(
        f"""
        UPDATE {qtable(TARGET_URL_TABLE)}
        SET url_template = %s,
            is_active = %s,
            notes = %s,
            updated_at = now()
        WHERE lower(corp) = lower(%s)
          AND upper(product_line) = upper(%s)
          AND lower(account_name) = lower(%s)
          AND lower(page_type) = lower(%s)
        """,
        (values["url_template"], values["is_active"], values["notes"], *key),
    )
    if cur.rowcount:
        return "updated"
    cur.execute(
        f"""
        INSERT INTO {qtable(TARGET_URL_TABLE)}
          (corp, product_line, account_name, page_type, url_template, is_active, notes)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (*key, values["url_template"], values["is_active"], values["notes"]),
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
        "run_type": "common_setting_step02_seed_target_urls",
        "started_at": started_at,
        "finished_at": now(),
        "seed_csv": SEED_CSV,
        "table": TARGET_URL_TABLE,
        "success": True,
        **counts,
    }
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
