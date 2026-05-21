import argparse
import csv
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .step00_config import DEFAULT_BESTBUY_RUN_ROOT, bestbuy_dated_run_root, has_target_url


PYTHON = sys.executable
TARGET_SIZE = 300


@dataclass(frozen=True)
class Step:
    number: int
    name: str
    module: str
    env: dict[str, str] = field(default_factory=dict)
    resume_env: dict[str, str] = field(default_factory=dict)
    implemented: bool = True

    @property
    def key(self):
        return f"{self.number:02d}"


STEPS = [
    Step(
        1,
        "main_list",
        "bestbuy.step01_main_list",
        {
            "BESTBUY_MAIN_PAGES": "16",
            "BESTBUY_MAIN_RUN_ID": "main",
            "BESTBUY_MAIN_ORGANIC_OFFSET": "18",
            "BESTBUY_GRAPHQL_PREMIUM_PROXY": "1",
            "BESTBUY_GRAPHQL_JS_RENDER": "1",
            "ZENROWS_TIMEOUT": "180",
        },
    ),
    Step(
        2,
        "main_targets",
        "bestbuy.step02_main_targets",
        {
            "BESTBUY_MAIN_TARGET_RUN_ID": "main",
            "BESTBUY_GRAPHQL_PREMIUM_PROXY": "1",
            "BESTBUY_GRAPHQL_JS_RENDER": "1",
            "ZENROWS_TIMEOUT": "180",
        },
    ),
    Step(
        3,
        "bsr_list",
        "bestbuy.step03_bsr_list",
        {
            "BESTBUY_MAIN_PAGES": "6",
            "BESTBUY_MAIN_RUN_ID": "bsr",
            "BESTBUY_MAIN_ORGANIC_OFFSET": "72",
            "BESTBUY_SEARCH_SORT": "Best-Selling",
            "BESTBUY_GRAPHQL_PREMIUM_PROXY": "1",
            "BESTBUY_GRAPHQL_JS_RENDER": "1",
            "ZENROWS_TIMEOUT": "180",
        },
    ),
    Step(4, "bsr_rank", "bestbuy.step04_bsr_rank"),
    Step(
        5,
        "promotion_deals",
        "bestbuy.step05_promotion_deals",
        {"BESTBUY_PROMOTION_PLACEMENT": "all", "ZENROWS_TIMEOUT": "180"},
    ),
    Step(6, "trending_deals", "bestbuy.step06_trending_deals"),
    Step(
        7,
        "final_targets",
        "bestbuy.step07_final_targets",
        {
            "BESTBUY_FINAL_MAIN_RUN_ID": "main",
            "BESTBUY_FINAL_BSR_RUN_ID": "bsr",
            "BESTBUY_FINAL_TARGET_SIZE": "300",
        },
    ),
    Step(
        8,
        "detail_html",
        "bestbuy.step08_detail_enrichment",
        {
            "BESTBUY_DETAIL_STAGE": "detail",
            "BESTBUY_DETAIL_FETCH_COMPARE": "0",
            "BESTBUY_DETAIL_BATCH_FETCH": "0",
            "BESTBUY_SAVE_HTML_MODE": "slim",
            "ZENROWS_TIMEOUT": "240",
        },
        {
            "BESTBUY_DETAIL_STAGE": "detail",
            "BESTBUY_DETAIL_FETCH_COMPARE": "0",
            "BESTBUY_DETAIL_BATCH_FETCH": "0",
            "BESTBUY_DETAIL_RETRY_ONLY": "1",
            "BESTBUY_SAVE_HTML_MODE": "slim",
            "ZENROWS_TIMEOUT": "240",
        },
    ),
    Step(
        9,
        "review20",
        "bestbuy.step09_review20",
        {"BESTBUY_GRAPHQL_ONLY": "0", "ZENROWS_TIMEOUT": "240"},
        {"BESTBUY_DETAIL_RETRY_ONLY": "1", "BESTBUY_GRAPHQL_ONLY": "0", "ZENROWS_TIMEOUT": "240"},
    ),
    Step(10, "status_check", "bestbuy.step10_status_check"),
    Step(11, "s3_sync", "bestbuy.step11_s3_sync"),
    Step(12, "local_cleanup", "bestbuy.step12_local_cleanup"),
    Step(13, "db_prepare", "bestbuy.step13_db_prepare"),
    Step(14, "db_load", "bestbuy.step14_db_load"),
]


def run_root(env=None):
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return Path(merged.get("BESTBUY_RUN_ROOT", DEFAULT_BESTBUY_RUN_ROOT))


def path_exists(path):
    return Path(path).exists()


def read_json(path):
    path = Path(path)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
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


def csv_unique_count(path, key):
    path = Path(path)
    if not path.exists():
        return 0
    seen = set()
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            value = str(row.get(key) or "").strip()
            if value:
                seen.add(value)
    return len(seen)


def csv_stage_count(path, stage):
    path = Path(path)
    if not path.exists():
        return 0
    count = 0
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if str(row.get("stage") or "").strip() == stage:
                count += 1
    return count


def csv_skus(path):
    path = Path(path)
    if not path.exists():
        return []
    skus = []
    seen = set()
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            sku = str(row.get("sku_id") or "").strip()
            if sku and sku not in seen:
                seen.add(sku)
                skus.append(sku)
    return skus


def meta_success_for_sku(raw_dir, sku):
    sku = str(sku or "").strip()
    if not sku:
        return False
    raw_dir = Path(raw_dir)
    for path in raw_dir.glob(f"*_{sku}_*/{sku}_meta.json"):
        if read_json(path).get("success") is True:
            return True
    return read_json(raw_dir / f"{sku}_meta.json").get("success") is True


def expected_pages(step):
    value = os.getenv("BESTBUY_MAIN_PAGES") or step.env.get("BESTBUY_MAIN_PAGES", "0")
    return int(value or 0)


def main_list_complete(step):
    root = run_root(step.env) / step.env.get("BESTBUY_MAIN_RUN_ID", "main")
    manifest = read_json(root / "manifest.json")
    expected = expected_pages(step)
    if not manifest or int(manifest.get("actual_post_calls") or 0) < expected:
        return False, f"calls {manifest.get('actual_post_calls', 0)}/{expected}"
    csv_path = root / "parsed" / "main_occurrences.csv"
    if csv_count(csv_path) <= 0:
        return False, "missing main_occurrences.csv"
    return True, f"calls {manifest.get('actual_post_calls')}/{expected}"


def main_targets_complete(step):
    root = run_root(step.env) / step.env.get("BESTBUY_MAIN_TARGET_RUN_ID", "main")
    manifest = read_json(root / "manifest_main_targets.json")
    csv_path = root / "parsed" / "main_target_occurrences.csv"
    if csv_count(csv_path) <= 0:
        return False, "missing main_target_occurrences.csv"
    if not manifest:
        return False, "missing manifest_main_targets.json"
    return True, f"unique {manifest.get('target_unique_sku_count', csv_unique_count(csv_path, 'sku_id'))}"


def bsr_rank_complete():
    root = run_root() / "bsr"
    csv_path = root / "parsed" / "bsr_rank_map.csv"
    count = csv_count(csv_path)
    if count < 100:
        return False, f"bsr rows {count}/100"
    return True, f"bsr rows {count}"


def promotion_complete():
    if not has_target_url("promotion"):
        return True, "no promotion URL for category"
    path = run_root() / "promotion" / "parsed" / "all_promotion_products.csv"
    count = csv_unique_count(path, "sku_id")
    if count <= 0:
        return False, "missing promotion products"
    return True, f"unique {count}"


def trending_complete():
    if not has_target_url("trend"):
        return True, "no trend URL for category"
    path = run_root() / "trending" / "parsed" / "trending_products.csv"
    count = csv_unique_count(path, "sku_id")
    if count <= 0:
        return False, "missing trending products"
    return True, f"unique {count}"


def final_targets_complete():
    root = run_root() / "output"
    manifest = read_json(root / "bestbuy_final_targets.manifest.json")
    csv_path = root / "bestbuy_final_targets.csv"
    count = csv_unique_count(csv_path, "sku_id")
    if count < TARGET_SIZE:
        return False, f"target unique {count}/{TARGET_SIZE}"
    if manifest.get("needs_more_main_candidates") is True:
        return False, "needs more main candidates"
    return True, f"target unique {count}"


def detail_complete():
    root = run_root()
    target_csv = root / "output" / "bestbuy_final_targets.csv"
    target_skus = csv_skus(target_csv)
    detail_dir = root / "detail" / "raw" / "detail_html"
    if not target_skus:
        return False, "missing final targets"
    detail_success = sum(1 for sku in target_skus if meta_success_for_sku(detail_dir, sku))
    if detail_success < len(target_skus):
        return False, f"detail {detail_success}/{len(target_skus)}"
    return True, f"detail {detail_success}/{len(target_skus)}"


def review20_complete():
    root = run_root()
    target_csv = root / "output" / "bestbuy_final_targets.csv"
    target_count = csv_unique_count(target_csv, "sku_id")
    output_count = csv_count(root / "output" / "final_output.csv")
    review_failures = csv_stage_count(root / "detail" / "parsed" / "detail_failures.csv", "review20")
    if target_count <= 0:
        return False, "missing final targets"
    if output_count < target_count or review_failures:
        return False, f"output {output_count}/{target_count}, review_failures {review_failures}"
    return True, f"output {output_count}/{target_count}, review_failures {review_failures}"


def step_complete(step):
    if step.name in {"main_list", "bsr_list"}:
        return main_list_complete(step)
    if step.name == "main_targets":
        return main_targets_complete(step)
    if step.name == "bsr_rank":
        return bsr_rank_complete()
    if step.name == "promotion_deals":
        return promotion_complete()
    if step.name == "trending_deals":
        return trending_complete()
    if step.name == "final_targets":
        return final_targets_complete()
    if step.name == "detail_html":
        return detail_complete()
    if step.name == "review20":
        return review20_complete()
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


def run_step(step, dry_run=False, resume=False):
    if not step.implemented:
        print(f"[skip] step {step.key} {step.name}: not implemented yet")
        return
    if step.name == "promotion_deals" and not has_target_url("promotion"):
        print(f"[skip] step {step.key} {step.name}: no promotion URL for category")
        return
    if step.name == "trending_deals" and not has_target_url("trend"):
        print(f"[skip] step {step.key} {step.name}: no trend URL for category")
        return

    env = os.environ.copy()
    for key, value in step.env.items():
        env[key] = value
    if resume:
        for key, value in step.resume_env.items():
            env[key] = value
    command = [PYTHON, "-m", step.module]
    print(f"[run] step {step.key} {step.name}: {' '.join(command)}")
    effective_env = {key: env.get(key, value) for key, value in step.env.items()}
    if resume:
        effective_env.update({key: env.get(key, value) for key, value in step.resume_env.items()})
    if effective_env:
        print("[env] " + " ".join(f"{key}={value}" for key, value in effective_env.items()))
    if dry_run:
        return
    subprocess.run(command, check=True, env=env)


def parse_args():
    parser = argparse.ArgumentParser(description="Best Buy crawler orchestrator")
    parser.add_argument(
        "steps",
        nargs="*",
        help="Step numbers or names to run. Omit to list steps.",
    )
    parser.add_argument(
        "--from-step",
        dest="from_step",
        help="Run from this step through the last implemented step.",
    )
    parser.add_argument("--all", action="store_true", help="Run all implemented steps.")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Run only incomplete steps for today's operational folder, plus dependent downstream steps.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print commands without running.")
    parser.add_argument(
        "--category",
        default=os.getenv("BESTBUY_CATEGORY", "TV"),
        help="Category key from dx_target_page_url, e.g. TV, HHP, REF, LDY.",
    )
    return parser.parse_args()


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


def resume_steps():
    selected = []
    dirty_main = False
    dirty_bsr = False
    dirty_join_sources = False

    for step in STEPS:
        if not step.implemented:
            continue
        complete, reason = step_complete(step)
        force = False
        if step.name == "main_targets" and dirty_main:
            force = True
            reason = "main_list rerun"
        elif step.name == "bsr_rank" and dirty_bsr:
            force = True
            reason = "bsr_list rerun"
        elif step.name == "final_targets" and (dirty_main or dirty_bsr or dirty_join_sources):
            force = True
            reason = "upstream source changed"
        elif step.name == "detail_html" and any(item.name == "final_targets" for item in selected):
            force = True
            reason = "final targets refreshed"
        elif step.name == "review20" and any(item.name in {"final_targets", "detail_html"} for item in selected):
            force = True
            reason = "detail source refreshed"

        if complete and not force and step.name != "status_check":
            print(f"[ok] step {step.key} {step.name}: {reason}")
            continue

        print(f"[todo] step {step.key} {step.name}: {reason}")
        selected.append(step)
        if step.name == "main_list":
            dirty_main = True
        elif step.name == "bsr_list":
            dirty_bsr = True
        elif step.name in {"promotion_deals", "trending_deals"}:
            dirty_join_sources = True

    return selected


def print_steps():
    print("Best Buy pipeline steps:")
    for step in STEPS:
        status = "ready" if step.implemented else "planned"
        print(f"  {step.key} {step.name:<18} {status:<7} {step.module}")


def main():
    args = parse_args()
    os.environ["BESTBUY_CATEGORY"] = str(args.category).strip().upper()
    os.environ.setdefault("BESTBUY_RUN_ROOT", str(bestbuy_dated_run_root(category=os.environ["BESTBUY_CATEGORY"])))
    steps = selected_steps(args)
    if not steps:
        print_steps()
        return
    for step in steps:
        run_step(step, dry_run=args.dry_run, resume=args.resume)


if __name__ == "__main__":
    main()
