import os
from pathlib import Path

from .step00_config import DEFAULT_AMAZON_RUN_ROOT
from .step00_stub import write_skip_manifest


def main():
    run_root = Path(os.getenv("AMAZON_RUN_ROOT", str(DEFAULT_AMAZON_RUN_ROOT)))
    write_skip_manifest(
        run_root,
        "trending",
        "manifest_trending_deals.json",
        "step06_trending_deals",
        "Amazon trending source is not configured yet.",
    )


if __name__ == "__main__":
    main()
