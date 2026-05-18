from pathlib import Path

from bby_new_common import run_category
from .run import load_db


OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def main():
    run_category(
        category="TV",
        final_pattern="tv_retail_com_*.csv",
        product_pattern="bby_tv_product_list_*.csv",
        output_dir=OUTPUT_DIR,
        final_table="tv_retail_com_bby_v2_test",
        product_table="bby_tv_product_list_v2_test",
        load_db_func=load_db,
    )


if __name__ == "__main__":
    main()

