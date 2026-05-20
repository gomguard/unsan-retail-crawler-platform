import re
from urllib.parse import urljoin


def default_direct_headers(cookie=None, accept=None, referer=None, user_agent=None):
    headers = {
        "accept": accept or "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "upgrade-insecure-requests": "1",
        "user-agent": user_agent
        or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
    }
    if referer:
        headers["referer"] = referer
    if cookie:
        headers["cookie"] = cookie
    return headers


def is_interstitial(text):
    value = str(text or "")
    return "bm-verify" in value or "/_sec/verify" in value or "Enter the characters you see below" in value


def interstitial_payload(text):
    text = str(text or "")
    i_match = re.search(r"var\s+i\s*=\s*(\d+)", text)
    number_match = re.search(r'Number\("(\d+)"\s*\+\s*"(\d+)"\)', text)
    bm_match = re.search(r'"bm-verify"\s*:\s*"([^"]+)"', text)
    if not (i_match and number_match and bm_match):
        return None
    return {
        "bm-verify": bm_match.group(1),
        "pow": int(i_match.group(1)) + int(number_match.group(1) + number_match.group(2)),
    }


def get_with_interstitial_retry(session, url, headers, timeout):
    response = session.get(url, headers=headers, timeout=timeout)
    if not is_interstitial(response.text):
        return response, False, ""

    payload = interstitial_payload(response.text)
    if not payload:
        return response, False, "interstitial_payload_not_found"

    verify_headers = dict(headers)
    verify_headers.update(
        {
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
            "origin": "https://www.amazon.com",
            "referer": url,
        }
    )
    verify_url = urljoin(url, "/_sec/verify?provider=interstitial")
    verify = session.post(verify_url, headers=verify_headers, json=payload, timeout=timeout)
    if verify.status_code >= 400:
        return response, False, f"interstitial_verify_http_{verify.status_code}"

    retried = session.get(url, headers=headers, timeout=timeout)
    return retried, True, ""
