import json
from datetime import datetime
from pathlib import Path

from .step00_config import (
    DEFAULT_AMAZON_RUN_ROOT,
    amazon_marketplace,
    amazon_product_type,
    amazon_run_date,
    rel_path,
)


def now():
    return datetime.now().isoformat(timespec="seconds")


def write_skip_manifest(run_root, subject, manifest_name, run_type, skip_reason):
    run_root = Path(run_root or DEFAULT_AMAZON_RUN_ROOT)
    subject_root = run_root / subject
    for child in ("raw", "parsed", "benchmarks"):
        (subject_root / child).mkdir(parents=True, exist_ok=True)

    started_at = now()
    manifest = {
        "run_type": run_type,
        "started_at": started_at,
        "finished_at": now(),
        "run_date": amazon_run_date(),
        "marketplace": amazon_marketplace(),
        "product_type": amazon_product_type().upper(),
        "run_root": rel_path(run_root),
        "subject_root": rel_path(subject_root),
        "success": True,
        "skipped": True,
        "skip_reason": skip_reason,
    }
    manifest_path = subject_root / manifest_name
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return manifest
