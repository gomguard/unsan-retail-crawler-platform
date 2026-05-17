import json
import os
from datetime import datetime
from pathlib import Path

from .step00_config import DEFAULT_LOWES_RUN_ROOT


RUN_DATE = os.getenv("LOWES_RUN_DATE", datetime.now().strftime("%Y%m%d"))
RUN_ROOT = Path(os.getenv("LOWES_RUN_ROOT", str(DEFAULT_LOWES_RUN_ROOT)))
DETAIL_ROOT = Path(os.getenv("LOWES_DETAIL_RUN_ROOT", str(RUN_ROOT / "detail")))
REVIEW_ROOT = Path(os.getenv("LOWES_REVIEW_RUN_ROOT", str(DETAIL_ROOT / "raw" / "review20")))


def main():
    REVIEW_ROOT.mkdir(parents=True, exist_ok=True)
    manifest = {
        "run_type": "step09_review20",
        "run_date": RUN_DATE,
        "run_root": str(RUN_ROOT),
        "review_root": str(REVIEW_ROOT),
        "success": True,
        "skipped": True,
        "skip_reason": "Lowe's review20 source is not configured yet.",
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "finished_at": datetime.now().isoformat(timespec="seconds"),
    }
    (DETAIL_ROOT / "manifest_review20.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
