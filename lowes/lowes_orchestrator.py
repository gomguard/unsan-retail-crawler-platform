import argparse
import csv
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .step00_config import DEFAULT_LOWES_RUN_ROOT, lowes_dated_run_root


PYTHON = sys.executable


@dataclass(frozen=True)
class Step:
    number: int
    name: str
    module: str
    implemented: bool = True
    env: dict = field(default_factory=dict)

    @property
    def key(self):
        return f"{self.number:02d}"


STEPS = [
    Step(
        1,
        "main_list",
        os.getenv("LOWES_MAIN_LIST_MODULE", "lowes.step01_main_list"),
        env={"LOWES_MAIN_RUN_ID": "main"},
    ),
    Step(2, "main_targets", "lowes.step02_main_targets", env={"LOWES_MAIN_RUN_ID": "main"}),
    Step(3, "bsr_list", "lowes.step03_bsr_list", env={"LOWES_BSR_RUN_ID": "bsr"}),
    Step(4, "bsr_rank", "lowes.step04_bsr_rank", env={"LOWES_BSR_RUN_ID": "bsr"}),
    Step(5, "promotion_deals", "lowes.step05_promotion_deals"),
    Step(6, "trending_deals", "lowes.step06_trending_deals"),
    Step(7, "final_targets", "lowes.step07_final_targets"),
    Step(8, "detail_enrichment", "lowes.step08_detail_enrichment"),
    Step(9, "review20", "lowes.step09_review20"),
    Step(10, "status_check", "lowes.step10_status_check"),
    Step(11, "s3_sync", "lowes.step11_s3_sync"),
    Step(12, "local_cleanup", "lowes.step12_local_cleanup"),
    Step(13, "db_prepare", "lowes.step13_db_prepare"),
    Step(14, "db_load", "lowes.step14_db_load"),
]


def run_root(env=None):
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return Path(merged.get("LOWES_RUN_ROOT", str(DEFAULT_LOWES_RUN_ROOT)))


def read_json(path):
    path = Path(path)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except ValueError:
        return {}


def csv_count(path):
    path = Path(path)
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        next(reader, None)
        return sum(1 for _ in reader)


def step_complete(step):
    root = run_root(step.env)
    if step.name == "main_list":
        subject = root / step.env.get("LOWES_MAIN_RUN_ID", "main")
        manifest = read_json(subject / "manifest.json")
        return csv_count(subject / "parsed" / "main_occurrences.csv") > 0, manifest.get("run_type", "main list")
    if step.name == "main_targets":
        subject = root / step.env.get("LOWES_MAIN_RUN_ID", "main")
        return csv_count(subject / "parsed" / "main_target_occurrences.csv") > 0, "main targets"
    if step.name == "bsr_list":
        subject = root / step.env.get("LOWES_BSR_RUN_ID", "bsr")
        return csv_count(subject / "parsed" / "main_occurrences.csv") > 0, "bsr list"
    if step.name == "bsr_rank":
        return csv_count(root / "bsr" / "parsed" / "bsr_rank_map.csv") > 0, "bsr rank"
    if step.name == "final_targets":
        return csv_count(root / "output" / "lowes_final_targets.csv") > 0, "final targets"
    if step.name == "detail_enrichment":
        return csv_count(root / "output" / "final_output.csv") > 0, "detail output"
    if step.name in {"promotion_deals", "trending_deals", "review20"}:
        manifest_name = {
            "promotion_deals": "promotion/manifest_promotion_deals.json",
            "trending_deals": "trending/manifest_trending_deals.json",
            "review20": "detail/manifest_review20.json",
        }[step.name]
        manifest = read_json(root / manifest_name)
        return manifest.get("success") is True, manifest.get("skip_reason", step.name)
    if step.name == "status_check":
        return False, "always refresh status"
    if step.name == "s3_sync":
        return False, "always sync to S3 when selected"
    if step.name == "local_cleanup":
        return False, "always evaluate local retention when selected"
    if step.name == "db_prepare":
        return False, "always ensure DB tables when selected"
    if step.name == "db_load":
        return False, "always load final outputs to DB when selected"
    return False, "no completion rule"


def step_by_key(value):
    for step in STEPS:
        if value in {step.key, step.name, str(step.number)}:
            return step
    raise SystemExit(f"Unknown step: {value}")


def resume_steps():
    selected = []
    force_downstream = False
    for step in STEPS:
        if not step.implemented:
            continue
        complete, reason = step_complete(step)
        if complete and not force_downstream and step.name != "status_check":
            print(f"[ok] step {step.key} {step.name}: {reason}")
            continue
        print(f"[todo] step {step.key} {step.name}: {reason}")
        selected.append(step)
        if step.name not in {"status_check", "s3_sync", "local_cleanup", "db_prepare", "db_load"}:
            force_downstream = True
    return selected


def selected_steps(args):
    if args.resume:
        return resume_steps()
    if args.all:
        return [step for step in STEPS if step.implemented]
    if args.from_step:
        start = step_by_key(args.from_step).number
        return [step for step in STEPS if step.number >= start and step.implemented]
    if args.steps:
        return [step_by_key(value) for value in args.steps]
    return []


def run_step(step, dry_run=False):
    if not step.implemented:
        print(f"[skip] step {step.key} {step.name}: not implemented for Lowe's")
        return 0
    env = os.environ.copy()
    env.setdefault("LOWES_RUN_ROOT", str(DEFAULT_LOWES_RUN_ROOT))
    env.update(step.env)
    command = [PYTHON, "-m", step.module]
    print(f"[run] step {step.key} {step.name}: {' '.join(command)}")
    print(f"      LOWES_RUN_ROOT={env.get('LOWES_RUN_ROOT')}")
    if dry_run:
        return 0
    return subprocess.call(command, env=env, cwd=Path(__file__).resolve().parent.parent)


def print_steps():
    print("Lowe's pipeline steps:")
    for step in STEPS:
        status = "ready" if step.implemented else "planned"
        print(f"  {step.key} {step.name:<18} {status:<7} {step.module}")


def main():
    parser = argparse.ArgumentParser(description="Lowe's crawler orchestrator")
    parser.add_argument("steps", nargs="*", help="Step numbers or names to run. Omit to list steps.")
    parser.add_argument("--from-step", dest="from_step", help="Run from this step through the last implemented step.")
    parser.add_argument("--all", action="store_true", help="Run all implemented steps.")
    parser.add_argument("--resume", action="store_true", help="Run incomplete steps and always refresh status.")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without running them.")
    parser.add_argument(
        "--product-type",
        "--category",
        dest="product_type",
        default=os.getenv("LOWES_PRODUCT_TYPE", "REF"),
        help="Product type for the operational data folder, e.g. REF or LDY.",
    )
    args = parser.parse_args()

    os.environ["LOWES_PRODUCT_TYPE"] = str(args.product_type).strip().upper()
    if os.environ["LOWES_PRODUCT_TYPE"] == "LDY":
        os.environ.setdefault("LOWES_SEARCH_TERM", "washing machine")
        os.environ.setdefault("LOWES_BSR_PRODUCT_GROUP", "LDY")
        os.environ.setdefault("LOWES_REQUEST_VARIANT", "js_premium_block_visual")
    else:
        os.environ.setdefault("LOWES_SEARCH_TERM", "refrigerator")
        os.environ.setdefault("LOWES_BSR_PRODUCT_GROUP", "REF")
    os.environ.setdefault("LOWES_RUN_ROOT", str(lowes_dated_run_root(product_type=os.environ["LOWES_PRODUCT_TYPE"].lower())))
    steps = selected_steps(args)
    if not steps:
        print_steps()
        return
    for step in steps:
        code = run_step(step, dry_run=args.dry_run)
        if code:
            raise SystemExit(code)


if __name__ == "__main__":
    main()
