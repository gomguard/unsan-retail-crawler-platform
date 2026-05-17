import argparse
import subprocess
import sys
from dataclasses import dataclass


PYTHON = sys.executable


@dataclass(frozen=True)
class Step:
    number: int
    name: str
    module: str

    @property
    def key(self):
        return f"{self.number:02d}"


STEPS = [
    Step(1, "core_tables", "common_settings.common_setting_step01_core_tables"),
    Step(2, "seed_target_urls", "common_settings.common_setting_step02_seed_target_urls"),
    Step(3, "seed_output_tables", "common_settings.common_setting_step03_seed_output_tables"),
    Step(4, "seed_run_profiles", "common_settings.common_setting_step04_seed_run_profiles"),
    Step(5, "prepare_output_tables", "common_settings.common_setting_step05_prepare_output_tables"),
]


def step_by_key(value):
    for step in STEPS:
        if value in {step.key, step.name, str(step.number)}:
            return step
    raise SystemExit(f"Unknown common setting step: {value}")


def selected_steps(args):
    if args.all:
        return STEPS
    if args.from_step:
        start = step_by_key(args.from_step).number
        return [step for step in STEPS if step.number >= start]
    if args.steps:
        return [step_by_key(value) for value in args.steps]
    return []


def print_steps():
    print("Common setting steps:")
    for step in STEPS:
        print(f"  {step.key} {step.name:<20} {step.module}")


def main():
    parser = argparse.ArgumentParser(description="Common crawler DB setting orchestrator")
    parser.add_argument("steps", nargs="*", help="Step numbers or names. Omit to list steps.")
    parser.add_argument("--all", action="store_true", help="Run all common setting steps.")
    parser.add_argument("--from-step", dest="from_step", help="Run from this step onward.")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without running.")
    args = parser.parse_args()

    steps = selected_steps(args)
    if not steps:
        print_steps()
        return
    for step in steps:
        command = [PYTHON, "-m", step.module]
        print(f"[run] common setting {step.key} {step.name}: {' '.join(command)}")
        if not args.dry_run:
            subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
