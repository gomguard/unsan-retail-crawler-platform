# BestBuy TV/HHP Recovery Runner

Run from this directory on the RDP machine.

```powershell
cd nemonomu
python -m tv_bby_new.collect_remaining
python -m hhp_bby_new.collect_remaining
```

Load to the Unsan default DB tables:

```powershell
python -m tv_bby_new.collect_remaining --load-db
python -m hhp_bby_new.collect_remaining --load-db
```

Required RDP environment:

- `.env` with `DB_CONFIG`
- `ZENROWS_API_KEY` if Unsan detail collection needs it
- Unsan crawler repo files available in the parent repository

Default target tables:

- `tv_retail_com_bby_v2_test`
- `bby_tv_product_list_v2_test`
- `hhp_retail_com_bby_v2_test`
- `bby_hhp_product_list_v2_test`

Default behavior:

- Uses BestBuy rows from `sample_csv`.
- Collects missing detail rows where `item` was empty by default.
- Writes a complete BestBuy CSV per category.
- Extracts BestBuy `item` from the product URL BSIN, including non-`J` BSIN values.
