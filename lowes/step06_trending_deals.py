import json
import os
from datetime import datetime
from pathlib import Path

from .step00_config import DEFAULT_LOWES_RUN_ROOT


RUN_DATE = os.getenv("LOWES_RUN_DATE", datetime.now().strftime("%Y%m%d"))
RUN_ROOT = Path(os.getenv("LOWES_RUN_ROOT", str(DEFAULT_LOWES_RUN_ROOT)))
TRENDING_ROOT = Path(os.getenv("LOWES_TRENDING_RUN_ROOT", str(RUN_ROOT / "trending")))


def main():
    TRENDING_ROOT.mkdir(parents=True, exist_ok=True)
    for subdir in ("raw", "parsed", "benchmarks"):
        (TRENDING_ROOT / subdir).mkdir(parents=True, exist_ok=True)

    manifest = {
        "run_type": "step06_trending_deals",
        "run_date": RUN_DATE,
        "run_root": str(RUN_ROOT),
        "trending_root": str(TRENDING_ROOT),
        "success": True,
        "skipped": True,
        "skip_reason": "Lowe's trending source is not configured yet.",
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "finished_at": datetime.now().isoformat(timespec="seconds"),
    }
    (TRENDING_ROOT / "manifest_trending_deals.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
