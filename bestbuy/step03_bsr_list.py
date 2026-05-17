import os

from . import step01_main_list


def main():
    os.environ.setdefault("BESTBUY_MAIN_PAGES", "2")
    os.environ.setdefault("BESTBUY_MAIN_RUN_ID", "bsr")
    os.environ.setdefault("BESTBUY_MAIN_ORGANIC_OFFSET", "72")
    os.environ.setdefault("BESTBUY_SEARCH_SORT", "Best-Selling")
    step01_main_list.main()


if __name__ == "__main__":
    main()
