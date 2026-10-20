"""쿠팡 파트너스 Open API 를 부릅니다.

쿠팡이 공식으로 열어 둔 유일한 자동화 통로입니다.
(인플루언서 사이트를 봇으로 누르는 것은 2026-09-07 약관 제8조 2항으로 금지됐습니다.
 이 파일은 사이트를 건드리지 않고 API 만 씁니다.)

키는 파트너스 대시보드 > 추가기능 > API 발급 에서 받습니다.
서명 방식은 HMAC-SHA256 이고, 아래 _sign() 하나가 전부입니다.
"""

import hashlib
import hmac
import json
import time
from time import gmtime, strftime
from urllib.parse import urlencode

import requests

from .settings import env

HOST = "https://api-gateway.coupang.com"
BASE = "/v2/providers/affiliate_open_api/apis/openapi"
TIMEOUT = 30
RETRY_WAIT = (3, 10, 30)  # 429(너무 자주 부름)나 5xx 가 오면 이만큼 쉬고 다시


class CoupangError(RuntimeError):
    pass


def _sign(method: str, path: str, query: str, secret: str, signed_date: str) -> str:
    """서명 문자열 = 날짜 + 메서드 + 경로 + 쿼리(물음표 없이)."""
    message = signed_date + method + path + query
    return hmac.new(
        secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def auth_header(method: str, path: str, query: str = "", *, now: str | None = None) -> str:
    """Authorization 헤더 값. 시험할 때는 now 를 고정해서 넣습니다."""
    access = env("COUPANG_ACCESS_KEY", required=True)
    secret = env("COUPANG_SECRET_KEY", required=True)
    signed_date = now or strftime("%y%m%dT%H%M%SZ", gmtime())
    signature = _sign(method, path, query, secret, signed_date)
    return (
        f"CEA algorithm=HmacSHA256, access-key={access}, "
        f"signed-date={signed_date}, signature={signature}"
    )


def _request(method: str, path: str, params: dict | None = None, body: dict | None = None) -> dict:
    query = urlencode(params or {})
    url = HOST + path + (f"?{query}" if query else "")
    headers = {
        "Authorization": auth_header(method, path, query),
        "Content-Type": "application/json;charset=UTF-8",
    }
    last = ""
    for i, wait in enumerate((0,) + RETRY_WAIT):
        if wait:
            time.sleep(wait)
        resp = requests.request(
            method, url, headers=headers, data=json.dumps(body) if body else None, timeout=TIMEOUT
        )
        if resp.status_code == 429 or resp.status_code >= 500:
            last = f"HTTP {resp.status_code}: {resp.text[:200]}"
            # 서명에 시각이 들어가므로 다시 부를 때는 헤더도 새로 만듭니다.
            headers["Authorization"] = auth_header(method, path, query)
            continue
        if resp.status_code >= 400:
            raise CoupangError(f"HTTP {resp.status_code}: {resp.text[:300]}")
        payload = resp.json()
        if str(payload.get("rCode", "0")) != "0":
            raise CoupangError(f"{payload.get('rCode')}: {payload.get('rMessage')}")
        return payload.get("data") or {}
    raise CoupangError(f"쿠팡 API 가 계속 거부합니다: {last}")


# ------------------------------------------------------------------ 상품 조회


def normalize(raw: dict, source: str) -> dict:
    """API 응답 한 건을 우리 봇이 쓰는 모양으로 바꿉니다."""
    return {
        "id": str(raw.get("productId", "")),
        "name": (raw.get("productName") or "").strip(),
        "price": int(raw.get("productPrice") or 0),
        "image": raw.get("productImage") or "",
        "url": raw.get("productUrl") or "",  # 이미 파트너스 추적 링크입니다
        "category": raw.get("categoryName") or "",
        "rocket": bool(raw.get("isRocket")),
        "free_shipping": bool(raw.get("isFreeShipping")),
        "rank": int(raw.get("rank") or 0),
        "source": source,
    }


def best_in_category(category_id: int, limit: int = 30) -> list[dict]:
    """카테고리 베스트 상품. ID 목록은 config.json 의 '고르기 → 카테고리' 참고."""
    data = _request("GET", f"{BASE}/products/bestcategories/{category_id}", {"limit": min(limit, 100)})
    return [normalize(p, f"best:{category_id}") for p in _items(data)]


def goldbox(limit: int = 30) -> list[dict]:
    """골드박스(오늘의 특가)."""
    data = _request("GET", f"{BASE}/products/goldbox", {"limit": min(limit, 100)})
    return [normalize(p, "goldbox") for p in _items(data)]


def search(keyword: str, limit: int = 30) -> list[dict]:
    data = _request("GET", f"{BASE}/products/search", {"keyword": keyword, "limit": min(limit, 100)})
    return [normalize(p, f"search:{keyword}") for p in _items(data)]


def deeplink(urls: list[str], sub_id: str = "") -> list[str]:
    """아무 쿠팡 주소나 파트너스 링크로 바꿉니다. 상품 조회 결과는 이미 링크가 붙어 있어 필요 없습니다."""
    body: dict = {"coupangUrls": urls}
    if sub_id:
        body["subId"] = sub_id
    data = _request("POST", f"{BASE}/v1/deeplink", body=body)
    rows = data if isinstance(data, list) else data.get("deeplinkList") or []
    return [r.get("shortenUrl") or r.get("landingUrl") or "" for r in rows]


def _items(data) -> list[dict]:
    """응답이 {'productData': [...]} 일 때도, 바로 [...] 일 때도 있습니다."""
    if isinstance(data, list):
        return data
    return data.get("productData") or []
