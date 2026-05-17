import os

if __name__ == "__main__":
    os.environ["BESTBUY_DETAIL_STAGE"] = "review"
    from .step08_detail_enrichment import main

    main()
