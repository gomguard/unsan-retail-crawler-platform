import argparse
import csv
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .step00_config import DEFAULT_AMAZON_RUN_ROOT, amazon_dated_run_root, has_target_url


PYTHON = sys.executable


@dataclass(frozen=True)
class Step:
    number: int
    name: str
    module: str
    implemented: bool = True
    env: dict[str, str] = field(default_factory=dict)

    @property
    def key(self):
        return f"{self.number:02d}"


STEPS = [
    Step(1, "main_list", "amazon.step01_main_list", env={"AMAZON_MAIN_RUN_ID": "main"}),
    Step(2, "main_targets", "amazon.step02_main_targets", env={"AMAZON_MAIN_RUN_ID": "main"}),
    Step(3, "bsr_list", "amazon.step03_bsr_list", env={"AMAZON_BSR_RUN_ID": "bsr"}),
    Step(4, "bsr_rank", "amazon.step04_bsr_rank", env={"AMAZON_BSR_RUN_ID": "bsr"}),
    Step(5, "promotion_deals", "amazon.step05_promotion_deals"),
    Step(6, "trending_deals", "amazon.step06_trending_deals"),
    Step(7, "final_targets", "amazon.step07_final_targets"),
    Step(8, "detail_enrichment", "amazon.step08_detail_enrichment"),
    Step(9, "review20", "amazon.step09_review20"),
    Step(10, "status_check", "amazon.step10_status_check"),
    Step(11, "s3_sync", "amazon.step11_s3_sync"),
    Step(12, "local_cleanup", "amazon.step12_local_cleanup"),
    Step(13, "db_prepare", "amazon.step13_db_prepare"),
    Step(14, "db_load", "amazon.step14_db_load"),
]


def run_root(env=None):
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return Path(merged.get("AMAZON_RUN_ROOT", str(DEFAULT_AMAZON_RUN_ROOT)))


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
        subject = root / step.env.get("AMAZON_MAIN_RUN_ID", "main")
        manifest = read_json(subject / "manifest.json")
        return csv_count(subject / "parsed" / "main_occurrences.csv") > 0, manifest.get("skip_reason", "main list")
    if step.name == "main_targets":
        subject = root / step.env.get("AMAZON_MAIN_RUN_ID", "main")
        manifest = read_json(subject / "manifest_main_targets.json")
        return csv_count(subject / "parsed" / "main_target_occurrences.csv") > 0, manifest.get("skip_reason", "main targets")
    if step.name == "bsr_list":
        subject = root / step.env.get("AMAZON_BSR_RUN_ID", "bsr")
        manifest = read_json(subject / "manifest.json")
        return csv_count(subject / "parsed" / "main_occurrences.csv") > 0, manifest.get("skip_reason", "bsr list")
    if step.name == "bsr_rank":
        manifest = read_json(root / "bsr" / "manifest_bsr_rank.json")
        return csv_count(root / "bsr" / "parsed" / "bsr_rank_map.csv") > 0, manifest.get("skip_reason", "bsr rank")
    if step.name == "final_targets":
        manifest = read_json(root / "output" / "amazon_final_targets.manifest.json")
        return csv_count(root / "output" / "amazon_final_targets.csv") > 0, manifest.get("skip_reason", "final targets")
    if step.name == "detail_enrichment":
        manifest = read_json(root / "detail" / "manifest_detail_enrichment.json")
        return csv_count(root / "output" / "final_output.csv") > 0, manifest.get("skip_reason", "detail output")
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
        print(f"[skip] step {step.key} {step.name}: not implemented for Amazon")
        return 0
    if step.name == "promotion_deals" and not has_target_url("promotion"):
        print(f"[skip] step {step.key} {step.name}: no promotion URL for product type")
        return 0
    if step.name == "trending_deals" and not has_target_url("trend"):
        print(f"[skip] step {step.key} {step.name}: no trend URL for product type")
        return 0

    env = os.environ.copy()
    env.setdefault("AMAZON_RUN_ROOT", str(DEFAULT_AMAZON_RUN_ROOT))
    env.update(step.env)
    command = [PYTHON, "-m", step.module]
    print(f"[run] step {step.key} {step.name}: {' '.join(command)}")
    print(f"      AMAZON_RUN_ROOT={env.get('AMAZON_RUN_ROOT')}")
    if dry_run:
        return 0
    return subprocess.call(command, env=env, cwd=Path(__file__).resolve().parent.parent)


def print_steps():
    print("Amazon US pipeline steps:")
    for step in STEPS:
        status = "ready" if step.implemented else "planned"
        print(f"  {step.key} {step.name:<18} {status:<7} {step.module}")


def main():
    parser = argparse.ArgumentParser(description="Amazon US crawler orchestrator")
    parser.add_argument("steps", nargs="*", help="Step numbers or names to run. Omit to list steps.")
    parser.add_argument("--from-step", dest="from_step", help="Run from this step through the last implemented step.")
    parser.add_argument("--all", action="store_true", help="Run all implemented steps.")
    parser.add_argument("--resume", action="store_true", help="Run incomplete steps and always refresh status.")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without running them.")
    parser.add_argument(
        "--product-type",
        "--category",
        dest="product_type",
        default=os.getenv("AMAZON_PRODUCT_TYPE", "TV"),
        help="Product type for the operational data folder, e.g. TV, HHP, REF, LDY.",
    )
    parser.add_argument(
        "--marketplace",
        default=os.getenv("AMAZON_MARKETPLACE", "US"),
        help="Amazon marketplace code. Initial implementation targets US.",
    )
    args = parser.parse_args()

    os.environ["AMAZON_PRODUCT_TYPE"] = str(args.product_type).strip().upper()
    os.environ["AMAZON_MARKETPLACE"] = str(args.marketplace).strip().upper()
    os.environ.setdefault(
        "AMAZON_RUN_ROOT",
        str(amazon_dated_run_root(product_type=os.environ["AMAZON_PRODUCT_TYPE"].lower())),
    )
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
