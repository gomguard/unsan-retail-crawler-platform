import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from .step00_config import DEFAULT_BESTBUY_RUN_ROOT, bestbuy_category, bestbuy_run_date, rel_path


RUN_ROOT = Path(os.getenv("BESTBUY_RUN_ROOT", DEFAULT_BESTBUY_RUN_ROOT))
CATEGORY = bestbuy_category().lower()
RUN_DATE = bestbuy_run_date()

S3_BUCKET = os.getenv("S3_BUCKET", "").strip()
S3_PREFIX = os.getenv("S3_PREFIX", "retail_backup").strip().strip("/")
AWS_REGION = os.getenv("AWS_REGION", "").strip()
S3_UPLOAD_RAW = os.getenv("S3_UPLOAD_RAW", "1").strip().lower() in {"1", "true", "yes", "y"}
S3_DELETE_EXTRA = os.getenv("S3_DELETE_EXTRA", "0").strip().lower() in {"1", "true", "yes", "y"}
S3_STORAGE_CLASS = os.getenv("S3_STORAGE_CLASS", "STANDARD").strip() or "STANDARD"
S3_DRY_RUN = os.getenv("S3_DRY_RUN", "0").strip().lower() in {"1", "true", "yes", "y"}
S3_INCLUDE_OUTPUT_ONLY = os.getenv("S3_INCLUDE_OUTPUT_ONLY", "0").strip().lower() in {"1", "true", "yes", "y"}
S3_SYNC_MAX_ATTEMPTS = max(1, int(os.getenv("S3_SYNC_MAX_ATTEMPTS", "3") or 3))
S3_SYNC_RETRY_SECONDS = max(0, int(os.getenv("S3_SYNC_RETRY_SECONDS", "10") or 10))
S3_VERIFY_AFTER_SYNC = os.getenv("S3_VERIFY_AFTER_SYNC", "1").strip().lower() in {"1", "true", "yes", "y"}

MANIFEST_PATH = RUN_ROOT / "s3_sync_manifest.json"
DEFAULT_AWS_EXE = Path(r"C:\Program Files\Amazon\AWSCLIV2\aws.exe")


def now():
    return datetime.now().isoformat(timespec="seconds")


def s3_uri():
    parts = [part for part in [S3_PREFIX, "bestbuy", CATEGORY, RUN_DATE] if part]
    return f"s3://{S3_BUCKET}/{'/'.join(parts)}"


def require_config():
    if not S3_BUCKET:
        raise RuntimeError("S3_BUCKET is missing")
    if not RUN_ROOT.exists():
        raise RuntimeError(f"RUN_ROOT does not exist: {RUN_ROOT}")


def aws_executable():
    configured = os.getenv("AWS_CLI_PATH", "").strip()
    if configured:
        return configured
    if DEFAULT_AWS_EXE.exists():
        return str(DEFAULT_AWS_EXE)
    return "aws"


def sync_command():
    command = [
        aws_executable(),
        "s3",
        "sync",
        str(RUN_ROOT),
        s3_uri(),
        "--storage-class",
        S3_STORAGE_CLASS,
        "--only-show-errors",
    ]
    if AWS_REGION:
        command.extend(["--region", AWS_REGION])
    if S3_DELETE_EXTRA:
        command.append("--delete")
    if S3_DRY_RUN:
        command.append("--dryrun")
    if not S3_UPLOAD_RAW:
        command.extend(["--exclude", "*/raw/*"])
    if S3_INCLUDE_OUTPUT_ONLY:
        command.extend(["--exclude", "*", "--include", "output/*", "--include", "status/*", "--include", "*.json"])
    return command


def verify_command():
    command = [aws_executable(), "s3", "ls", f"{s3_uri()}/", "--recursive", "--summarize"]
    if AWS_REGION:
        command.extend(["--region", AWS_REGION])
    return command


def run_command(command):
    return subprocess.run(command, text=True, capture_output=True)


def summarize_attempt(index, command, result):
    return {
        "attempt": index,
        "command": command,
        "returncode": result.returncode,
        "success": result.returncode == 0,
        "stdout": (result.stdout or "")[-4000:],
        "stderr": (result.stderr or "")[-4000:],
        "finished_at": now(),
    }


def write_manifest(started_at, sync_cmd, attempts, verify_cmd=None, verify_result=None):
    sync_success = bool(attempts and attempts[-1].get("returncode") == 0)
    verify_success = True
    verify_payload = None
    if verify_result is not None:
        verify_success = verify_result.returncode == 0
        verify_payload = {
            "command": verify_cmd,
            "returncode": verify_result.returncode,
            "success": verify_success,
            "stdout": (verify_result.stdout or "")[-4000:],
            "stderr": (verify_result.stderr or "")[-4000:],
        }

    manifest = {
        "run_type": "step11_s3_sync",
        "started_at": started_at,
        "finished_at": now(),
        "run_root": rel_path(RUN_ROOT),
        "category": CATEGORY.upper(),
        "run_date": RUN_DATE,
        "s3_bucket": S3_BUCKET,
        "s3_prefix": S3_PREFIX,
        "s3_uri": s3_uri(),
        "upload_raw": S3_UPLOAD_RAW,
        "delete_extra": S3_DELETE_EXTRA,
        "storage_class": S3_STORAGE_CLASS,
        "dry_run": S3_DRY_RUN,
        "max_attempts": S3_SYNC_MAX_ATTEMPTS,
        "retry_seconds": S3_SYNC_RETRY_SECONDS,
        "verify_after_sync": S3_VERIFY_AFTER_SYNC,
        "command": sync_cmd,
        "attempts": attempts,
        "verify": verify_payload,
        "success": sync_success and verify_success,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest


def main():
    require_config()
    started_at = now()
    command = sync_command()
    attempts = []
    print(" ".join(command))

    for attempt_index in range(1, S3_SYNC_MAX_ATTEMPTS + 1):
        result = run_command(command)
        attempts.append(summarize_attempt(attempt_index, command, result))
        if result.returncode == 0:
            break
        if attempt_index < S3_SYNC_MAX_ATTEMPTS and S3_SYNC_RETRY_SECONDS:
            time.sleep(S3_SYNC_RETRY_SECONDS)

    verify_cmd = None
    verify_result = None
    if attempts and attempts[-1].get("returncode") == 0 and S3_VERIFY_AFTER_SYNC and not S3_DRY_RUN:
        verify_cmd = verify_command()
        verify_result = run_command(verify_cmd)

    manifest = write_manifest(started_at, command, attempts, verify_cmd=verify_cmd, verify_result=verify_result)
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    if not manifest["success"]:
        last_returncode = attempts[-1].get("returncode") if attempts else 1
        if verify_result is not None and verify_result.returncode != 0:
            last_returncode = verify_result.returncode
        sys.exit(last_returncode or 1)


if __name__ == "__main__":
    main()
