import json
import os
from datetime import datetime

from .step00_config import RUN_PROFILE_TABLE, SEED_DIR, connect, qtable, read_seed_csv, truthy


SEED_CSV = os.getenv("COMMON_RUN_PROFILE_SEED_CSV", str(SEED_DIR / "dx_crawler_run_profile_seed.csv"))


def now():
    return datetime.now().isoformat(timespec="seconds")


def as_int(value):
    try:
        if value in ("", None):
            return None
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def upsert_row(cur, row):
    key = (
        row.get("corp", "").strip(),
        row.get("product_line", "").strip().upper(),
        row.get("account_name", "").strip(),
    )
    values = {
        "orchestrator_module": row.get("orchestrator_module", "").strip(),
        "default_pages": as_int(row.get("default_pages")),
        "detail_limit": as_int(row.get("detail_limit")),
        "page_workers": as_int(row.get("page_workers")),
        "detail_workers": as_int(row.get("detail_workers")),
        "is_active": truthy(row.get("is_active", "true")),
        "notes": row.get("notes", "").strip(),
    }
    if not all(key) or not values["orchestrator_module"]:
        return "skipped"

    cur.execute(
        f"""
        UPDATE {qtable(RUN_PROFILE_TABLE)}
        SET orchestrator_module = %s,
            default_pages = %s,
            detail_limit = %s,
            page_workers = %s,
            detail_workers = %s,
            is_active = %s,
            notes = %s,
            updated_at = now()
        WHERE lower(corp) = lower(%s)
          AND upper(product_line) = upper(%s)
          AND lower(account_name) = lower(%s)
        """,
        (
            values["orchestrator_module"],
            values["default_pages"],
            values["detail_limit"],
            values["page_workers"],
            values["detail_workers"],
            values["is_active"],
            values["notes"],
            *key,
        ),
    )
    if cur.rowcount:
        return "updated"
    cur.execute(
        f"""
        INSERT INTO {qtable(RUN_PROFILE_TABLE)}
          (corp, product_line, account_name, orchestrator_module, default_pages,
           detail_limit, page_workers, detail_workers, is_active, notes)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            *key,
            values["orchestrator_module"],
            values["default_pages"],
            values["detail_limit"],
            values["page_workers"],
            values["detail_workers"],
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
        "run_type": "common_setting_step04_seed_run_profiles",
        "started_at": started_at,
        "finished_at": now(),
        "seed_csv": SEED_CSV,
        "table": RUN_PROFILE_TABLE,
        "success": True,
        **counts,
    }
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
