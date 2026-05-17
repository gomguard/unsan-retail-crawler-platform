import html
import json
import re
from urllib.parse import urljoin

from .step00_config import AMAZON_BASE_URL


ASIN_RE = re.compile(r"\b([A-Z0-9]{10})\b")
TAG_RE = re.compile(r"<[^>]+>")


def clean_text(value):
    value = html.unescape(str(value or ""))
    value = TAG_RE.sub(" ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def compact_json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def absolute_amazon_url(path):
    if not path:
        return ""
    value = html.unescape(str(path))
    return urljoin(AMAZON_BASE_URL, value)


def find_result_starts(text, source="main"):
    starts = []
    if source == "bsr":
        patterns = [
            re.compile(r"<div\b(?=[^>]*data-asin=['\"]([A-Z0-9]{10})['\"])[^>]*>", re.I),
        ]
    else:
        patterns = [
            re.compile(r"<div\b(?=[^>]*data-asin=['\"]([A-Z0-9]{10})['\"])(?=[^>]*data-component-type=['\"]s-search-result['\"])[^>]*>", re.I),
            re.compile(r"<div\b(?=[^>]*data-component-type=['\"]s-search-result['\"])(?=[^>]*data-asin=['\"]([A-Z0-9]{10})['\"])[^>]*>", re.I),
        ]
    for pattern in patterns:
        for match in pattern.finditer(text or ""):
            asin = match.group(1)
            if asin:
                starts.append((match.start(), asin))
    starts.sort(key=lambda item: item[0])

    deduped = []
    seen_positions = set()
    for position, asin in starts:
        if position in seen_positions:
            continue
        seen_positions.add(position)
        deduped.append((position, asin))
    return deduped


def card_segments(text, source="main"):
    starts = find_result_starts(text, source=source)
    for index, (position, asin) in enumerate(starts):
        end = starts[index + 1][0] if index + 1 < len(starts) else len(text)
        yield asin, text[position:end]


def first_match(patterns, text, flags=re.I | re.S):
    for pattern in patterns:
        match = re.search(pattern, text or "", flags)
        if match:
            return match.group(1)
    return ""


def product_name(card):
    value = first_match(
        [
            r"<h2[^>]*>.*?<span[^>]*>(.*?)</span>",
            r"<div[^>]+class=['\"][^'\"]*p13n-sc-css-line-clamp[^'\"]*['\"][^>]*>(.*?)</div>",
            r"<img[^>]+alt=['\"]([^'\"]{10,500})['\"]",
            r"<span[^>]+class=['\"][^'\"]*a-text-normal[^'\"]*['\"][^>]*>(.*?)</span>",
            r"aria-label=['\"]([^'\"]{20,300})['\"]",
        ],
        card,
    )
    return clean_text(value)


def valid_product_name(name):
    value = clean_text(name)
    if not value:
        return False
    lowered = value.lower()
    if lowered in {"sponsored", "featured from amazon brands", "more results"}:
        return False
    if lowered.startswith("rated ") or lowered.endswith(" ratings"):
        return False
    return True


def product_url(card, asin):
    return f"{AMAZON_BASE_URL}/dp/{asin}"


def image_url(card):
    return html.unescape(
        first_match(
            [
                r"<img[^>]+(?:src|data-src)=['\"]([^'\"]+)['\"]",
                r'"hiRes"\s*:\s*"([^"]+)"',
            ],
            card,
        )
    )


def price(card):
    whole = first_match([r"<span[^>]+class=['\"][^'\"]*a-price-whole[^'\"]*['\"][^>]*>(.*?)</span>"], card)
    fraction = first_match([r"<span[^>]+class=['\"][^'\"]*a-price-fraction[^'\"]*['\"][^>]*>(.*?)</span>"], card)
    if whole:
        amount = re.sub(r"[^0-9]", "", clean_text(whole))
        cents = re.sub(r"[^0-9]", "", clean_text(fraction))[:2] if fraction else "00"
        if amount:
            return f"{amount}.{cents or '00'}"
    raw = first_match([r"\$([0-9][0-9,]*(?:\.[0-9]{2})?)"], clean_text(card))
    return raw.replace(",", "") if raw else ""


def rating(card):
    raw = first_match([r"([0-5](?:\.[0-9])?)\s+out of\s+5\s+stars"], clean_text(card), flags=re.I)
    return raw


def review_count(card):
    candidates = re.findall(r"aria-label=['\"]([0-9][0-9,\.]*)['\"]", card or "", re.I)
    for candidate in candidates:
        value = candidate.replace(",", "")
        if value.isdigit() and int(value) > 5:
            return value
    text = clean_text(card)
    match = re.search(r"\b([0-9][0-9,]{1,})\b", text)
    return match.group(1).replace(",", "") if match else ""


def brand_from_name(name):
    return str(name or "").split(" ", 1)[0].strip()


def parse_cards(text, page, rank_offset=0, source="main"):
    rows = []
    seen = set()
    for _, (asin, card) in enumerate(card_segments(text, source=source), 1):
        if not asin or asin in seen:
            continue
        seen.add(asin)
        name = product_name(card)
        if source == "main" and not valid_product_name(name):
            continue
        rank_in_page = len(rows) + 1
        rank = rank_offset + len(rows) + 1
        row = {
            "page": page,
            "rank_in_page": rank_in_page,
            "asin": asin,
            "sku_id": asin,
            "brand": brand_from_name(name),
            "product_name": name,
            "product_url": product_url(card, asin),
            "detail_url": f"{AMAZON_BASE_URL}/dp/{asin}",
            "image_url": image_url(card),
            "rating": rating(card),
            "review_count": review_count(card),
            "customer_price": price(card),
            "is_sponsored": "1" if "Sponsored" in clean_text(card[:1000]) else "",
            "source": source,
            "raw_card_json": compact_json({"asin": asin}),
        }
        if source == "bsr":
            row["bsr_rank"] = rank
            row["source_page"] = page
        else:
            row["main_rank"] = rank
            row["global_visual_rank"] = rank
        rows.append(row)
    if source == "bsr":
        for item in bsr_client_recs(text):
            asin = item.get("asin", "")
            if not asin or asin in seen:
                continue
            seen.add(asin)
            rank = rank_offset + len(rows) + 1
            explicit_rank = item.get("bsr_rank") or rank
            rows.append(
                {
                    "page": page,
                    "rank_in_page": len(rows) + 1,
                    "bsr_rank": explicit_rank,
                    "source_page": page,
                    "asin": asin,
                    "sku_id": asin,
                    "brand": "",
                    "product_name": "",
                    "product_url": f"{AMAZON_BASE_URL}/dp/{asin}",
                    "detail_url": f"{AMAZON_BASE_URL}/dp/{asin}",
                    "image_url": "",
                    "rating": "",
                    "review_count": "",
                    "customer_price": "",
                    "source": "bsr",
                    "raw_card_json": compact_json({"asin": asin, "client_recs": True}),
                }
            )
    return rows


def bsr_client_recs(text):
    output = []
    for match in re.finditer(r"data-client-recs-list=['\"]([^'\"]+)['\"]", text or "", re.I | re.S):
        raw = html.unescape(match.group(1))
        try:
            payload = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(payload, list):
            continue
        for item in payload:
            if not isinstance(item, dict):
                continue
            asin = str(item.get("id") or "").strip()
            if not ASIN_RE.fullmatch(asin):
                continue
            metadata = item.get("metadataMap", {}) if isinstance(item.get("metadataMap"), dict) else {}
            output.append(
                {
                    "asin": asin,
                    "bsr_rank": metadata.get("render.zg.rank", ""),
                }
            )
    return output
