import csv
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin
from datetime import datetime

from bs4 import BeautifulSoup
from requests import RequestException
from zenrows import ZenRowsClient

from .step00_config import DEFAULT_LOWES_RUN_ROOT, load_env
from .step00_parse_search import (
    extract_preloaded_state,
    find_item_list,
    parse_item,
    product_card_prices,
)

SCRIPT_DIR = Path(__file__).resolve().parent
LOWES_ROOT = SCRIPT_DIR
PROJECT_ROOT = LOWES_ROOT.parent

load_env(PROJECT_ROOT / ".env")

REF_BSR_URL = "https://www.lowes.com/best-sellers/appliances/refrigerators/4294857973"
LDY_BSR_URL = "https://www.lowes.com/best-sellers/appliances/washers-dryers/washing-machines/4294857977"

PRODUCT_GROUP = os.getenv("LOWES_BSR_PRODUCT_GROUP", "REF").upper()
BSR_URL = os.getenv("LOWES_BSR_URL", REF_BSR_URL if PRODUCT_GROUP == "REF" else LDY_BSR_URL)
BSR_OFFSET = int(os.getenv("LOWES_BSR_OFFSET", "0"))
RUN_ID = os.getenv("LOWES_BSR_RUN_ID", "bsr")
RUN_ROOT = Path(os.getenv("LOWES_RUN_ROOT", str(DEFAULT_LOWES_RUN_ROOT))) / RUN_ID
OUT_DIR = Path(os.getenv("LOWES_BSR_OUT_DIR", str(RUN_ROOT / "raw" / "main_pages")))
CSV_PATH = Path(os.getenv("LOWES_BSR_CSV", str(RUN_ROOT / "parsed" / "main_occurrences.csv")))
TIMEOUT = int(os.getenv("ZENROWS_TIMEOUT", "180"))


def now():
    return datetime.now().isoformat(timespec="seconds")


def compact_text(value):
    return " ".join((value or "").split())


def html_product_cards(page_html):
    soup = BeautifulSoup(page_html, "html.parser")
    cards = []
    seen = set()
    for link in soup.select('a[href*="/pd/"]'):
        href = urljoin("https://www.lowes.com", link.get("href", ""))
        match = re.search(r"/(\d{7,})(?:[/?#].*)?$", href)
        product_id = match.group(1) if match else ""
        card = link.find_parent(attrs={"data-webvision-id": True}) or link.find_parent(class_=re.compile("product|card", re.I))
        if card and not product_id:
            product_id = card.get("data-webvision-id", "")
        title = ""
        if card:
            title_node = card.select_one(".product-desc, [data-testid*='product-title'], [data-title]")
            if title_node:
                title = compact_text(title_node.get_text(" ", strip=True) or title_node.get("data-title", ""))
        if not title:
            title = compact_text(link.get_text(" ", strip=True))
        key = product_id or href
        if not key or key in seen or not title:
            continue
        seen.add(key)
        cards.append({"product_id": product_id, "title": title, "url": href})
    return cards


def fetch_bsr():
    api_key = os.getenv("ZENROWS_API_KEY")
    if not api_key:
        raise RuntimeError("Set ZENROWS_API_KEY in .env")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    client = ZenRowsClient(api_key)
    params = {
        "mode": "auto",
        "proxy_country": "us",
    }
    print(f"[Lowes BSR] {PRODUCT_GROUP} GET {BSR_URL}")
    started_at = now()
    start = time.time()
    try:
        response = client.get(BSR_URL, params=params, timeout=TIMEOUT)
    except RequestException as exc:
        elapsed = time.time() - start
        write_raw_artifacts(
            status_name="fail",
            body=str(exc),
            headers={},
            meta={
                "status_code": None,
                "success": False,
                "attempt": 1,
                "elapsed_seconds": round(elapsed, 3),
                "x_request_cost": "",
                "error": str(exc),
                "bytes": 0,
                "started_at": started_at,
                "finished_at": now(),
            },
        )
        raise
    elapsed = time.time() - start
    print(f"status={response.status_code} elapsed={elapsed:.1f}s bytes={len(response.text)}")
    for header in ["x-request-cost", "x-request-id", "zr-final-url"]:
        if header in response.headers:
            print(f"{header}: {response.headers[header]}")

    status_name = "success" if response.status_code == 200 else "fail"
    body_path, headers_path, meta_path = write_raw_artifacts(
        status_name=status_name,
        body=response.text,
        headers=dict(response.headers),
        meta={
            "status_code": response.status_code,
            "success": response.status_code == 200,
            "attempt": 1,
            "elapsed_seconds": round(elapsed, 3),
            "x_request_cost": response.headers.get("x-request-cost", ""),
            "error": "" if response.status_code == 200 else response.text[:500],
            "bytes": len(response.text),
            "started_at": started_at,
            "finished_at": now(),
        },
    )
    print(f"html={body_path}")
    print(f"headers={headers_path}")
    print(f"meta={meta_path}")
    return response


def write_raw_artifacts(status_name, body, headers, meta):
    unit_name = f"bsr_{PRODUCT_GROUP.lower()}_{status_name}"
    unit_dir = OUT_DIR / unit_name
    unit_dir.mkdir(parents=True, exist_ok=True)
    body_path = unit_dir / f"bsr_{PRODUCT_GROUP.lower()}_response.html"
    headers_path = unit_dir / f"bsr_{PRODUCT_GROUP.lower()}_headers.json"
    meta_path = unit_dir / f"bsr_{PRODUCT_GROUP.lower()}_meta.json"
    body_path.write_text(body or "", encoding="utf-8", errors="replace")
    headers_path.write_text(json.dumps(headers or {}, indent=2, ensure_ascii=False), encoding="utf-8")
    meta_path.write_text(json.dumps(meta or {}, indent=2, ensure_ascii=False), encoding="utf-8")
    return body_path, headers_path, meta_path


def write_csv(rows):
    if not rows:
        return
    preferred = [
        "product_group",
        "bsr_rank",
        "omni_item_id",
        "item_number",
        "brand",
        "model_id",
        "description",
        "product_url",
        "rating",
        "review_count",
        "selling_price",
    ]
    keys = set()
    for row in rows:
        keys.update(row)
    fieldnames = [key for key in preferred if key in keys]
    fieldnames.extend(sorted(keys - set(fieldnames)))
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def parse_bsr(page_html):
    state = extract_preloaded_state(page_html)
    items = find_item_list(state) or []
    html_prices = product_card_prices(page_html)
    rows = []
    if items:
        for rank, item in enumerate(items, 1):
            bsr_rank = BSR_OFFSET + rank
            row = parse_item(item, 1, rank, bsr_rank, html_prices)
            row["product_group"] = PRODUCT_GROUP
            row["bsr_rank"] = bsr_rank
            rows.append(row)
        return rows, {"source": "preloaded_state", "item_count": len(items)}

    cards = html_product_cards(page_html)
    for rank, card in enumerate(cards, 1):
        bsr_rank = BSR_OFFSET + rank
        rows.append(
            {
                "product_group": PRODUCT_GROUP,
                "bsr_rank": bsr_rank,
                "omni_item_id": card["product_id"],
                "description": card["title"],
                "product_url": card["url"],
                "source": "html_card",
            }
        )
    return rows, {"source": "html_card", "item_count": len(cards)}


def main():
    try:
        response = fetch_bsr()
    except RequestException as exc:
        print(f"request_exception={exc}")
        raise SystemExit(1)
    if response.status_code != 200:
        print(response.text[:500])
        raise SystemExit(1)

    rows, meta = parse_bsr(response.text)
    write_csv(rows)
    meta_path = RUN_ROOT / "manifest.json"
    meta.update(
        {
            "run_type": "step03_bsr_list",
            "run_root": str(RUN_ROOT),
            "product_group": PRODUCT_GROUP,
            "bsr_url": BSR_URL,
            "output_csv": str(CSV_PATH),
            "raw_dir": str(OUT_DIR),
        }
    )
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"parse_source={meta['source']} item_count={meta['item_count']}")
    print(f"csv={CSV_PATH}")
    for row in rows[:10]:
        print(
            f"{row.get('bsr_rank')}: {row.get('omni_item_id')} "
            f"{row.get('brand', '')} {row.get('description', '')[:120]}"
        )


if __name__ == "__main__":
    main()
