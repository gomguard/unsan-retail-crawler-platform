import json
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from .step00_config import DEFAULT_BESTBUY_RUNS_BASE, bestbuy_category, bestbuy_run_date, rel_path


CATEGORY = bestbuy_category().lower()
RUN_DATE = bestbuy_run_date()
CATEGORY_ROOT = DEFAULT_BESTBUY_RUNS_BASE / CATEGORY
RUN_ROOT = Path(os.getenv("BESTBUY_RUN_ROOT", CATEGORY_ROOT / RUN_DATE))

LOCAL_RETENTION_DAYS = max(0, int(os.getenv("LOCAL_RETENTION_DAYS", "7") or 7))
LOCAL_CLEANUP_DRY_RUN = os.getenv("LOCAL_CLEANUP_DRY_RUN", "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "y",
}
LOCAL_CLEANUP_REQUIRE_S3_SUCCESS = os.getenv(
    "LOCAL_CLEANUP_REQUIRE_S3_SUCCESS",
    "1",
).strip().lower() in {"1", "true", "yes", "y"}


def now():
    return datetime.now().isoformat(timespec="seconds")


def parse_run_date(path):
    try:
        return datetime.strptime(path.name, "%Y%m%d").date()
    except ValueError:
        return None


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}


def is_safe_child(path, parent):
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def s3_success(path):
    manifest = read_json(path / "s3_sync_manifest.json")
    return manifest.get("success") is True


def evaluate_candidate(path, cutoff_date):
    run_date = parse_run_date(path)
    if not path.is_dir():
        return False, "not a directory"
    if run_date is None:
        return False, "not a YYYYMMDD run folder"
    if path.resolve() == RUN_ROOT.resolve():
        return False, "current run folder"
    if run_date > cutoff_date:
        return False, f"within {LOCAL_RETENTION_DAYS} day retention"
    if LOCAL_CLEANUP_REQUIRE_S3_SUCCESS and not s3_success(path):
        return False, "missing successful s3_sync_manifest.json"
    if not is_safe_child(path, CATEGORY_ROOT):
        return False, "outside category root"
    return True, "eligible"


def cleanup():
    CATEGORY_ROOT.mkdir(parents=True, exist_ok=True)
    cutoff_date = (datetime.now().date() - timedelta(days=LOCAL_RETENTION_DAYS))
    started_at = now()
    deleted = []
    skipped = []
    candidates = []

    for path in sorted(CATEGORY_ROOT.iterdir()):
        eligible, reason = evaluate_candidate(path, cutoff_date)
        record = {
            "path": rel_path(path),
            "reason": reason,
        }
        if not eligible:
            skipped.append(record)
            continue

        candidates.append(record)
        if LOCAL_CLEANUP_DRY_RUN:
            continue
        shutil.rmtree(path)
        deleted.append(record)

    manifest = {
        "run_type": "step12_local_cleanup",
        "started_at": started_at,
        "finished_at": now(),
        "category": CATEGORY.upper(),
        "current_run_date": RUN_DATE,
        "category_root": rel_path(CATEGORY_ROOT),
        "retention_days": LOCAL_RETENTION_DAYS,
        "cutoff_date": cutoff_date.isoformat(),
        "dry_run": LOCAL_CLEANUP_DRY_RUN,
        "require_s3_success": LOCAL_CLEANUP_REQUIRE_S3_SUCCESS,
        "candidate_count": len(candidates),
        "deleted_count": len(deleted),
        "candidates": candidates,
        "deleted": deleted,
        "skipped": skipped,
    }
    manifest_path = CATEGORY_ROOT / f"cleanup_manifest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest


def main():
    manifest = cleanup()
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
