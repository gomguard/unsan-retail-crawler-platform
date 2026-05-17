import os
from pathlib import Path

from .step00_config import DEFAULT_AMAZON_RUN_ROOT
from .step00_stub import write_skip_manifest


def main():
    run_root = Path(os.getenv("AMAZON_RUN_ROOT", str(DEFAULT_AMAZON_RUN_ROOT)))
    write_skip_manifest(
        run_root,
        "detail",
        "manifest_review20.json",
        "step09_review20",
        "Amazon review collection is not configured yet.",
    )


if __name__ == "__main__":
    main()
