import json
import os
from datetime import datetime
from pathlib import Path

from .step00_config import DEFAULT_AMAZON_RUN_ROOT, amazon_marketplace, amazon_product_type, amazon_run_date, rel_path


RUN_DATE = amazon_run_date()
RUN_ROOT = Path(os.getenv("AMAZON_RUN_ROOT", str(DEFAULT_AMAZON_RUN_ROOT)))
OUTPUT_ROOT = Path(os.getenv("AMAZON_OUTPUT_ROOT", str(RUN_ROOT / "output")))


def now():
    return datetime.now().isoformat(timespec="seconds")


def main():
    started_at = now()
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    manifest = {
        "run_type": "step13_db_prepare",
        "started_at": started_at,
        "finished_at": now(),
        "run_date": RUN_DATE,
        "marketplace": amazon_marketplace(),
        "product_type": amazon_product_type().upper(),
        "run_root": rel_path(RUN_ROOT),
        "output_root": rel_path(OUTPUT_ROOT),
        "success": True,
        "skipped": True,
        "skip_reason": "Amazon target DB schema is not configured yet.",
    }
    (OUTPUT_ROOT / "manifest_db_prepare.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
