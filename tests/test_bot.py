"""키 없이 돌아가는 시험. 서명·고르기·글 조립·카드 렌더까지 확인합니다."""

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import coupang, picker, writer  # noqa: E402
from src.settings import load_config  # noqa: E402

FIX = json.loads((ROOT / "tests" / "fixtures" / "products.json").read_text(encoding="utf-8"))


def test_signature_is_deterministic(monkeypatch):
    monkeypatch.setenv("COUPANG_ACCESS_KEY", "AK")
    monkeypatch.setenv("COUPANG_SECRET_KEY", "SK")
    path = coupang.BASE + "/products/goldbox"
    h1 = coupang.auth_header("GET", path, "limit=10", now="261020T010203Z")
    h2 = coupang.auth_header("GET", path, "limit=10", now="261020T010203Z")
    assert h1 == h2
    assert h1.startswith("CEA algorithm=HmacSHA256, access-key=AK, signed-date=261020T010203Z, signature=")
    # 쿼리가 바뀌면 서명도 바뀌어야 합니다
    assert coupang.auth_header("GET", path, "limit=11", now="261020T010203Z") != h1


def test_signature_matches_reference():
    # 서명 공식: HMAC-SHA256(secret, date + method + path + query)
    import hashlib
    import hmac

    msg = "261020T010203Z" + "GET" + "/p" + "a=1"
    want = hmac.new(b"SK", msg.encode(), hashlib.sha256).hexdigest()
    assert coupang._sign("GET", "/p", "a=1", "SK", "261020T010203Z") == want


def test_normalize_handles_missing_fields():
    p = coupang.normalize({"productId": 1, "productName": " 이름 "}, "x")
    assert p == {
        "id": "1", "name": "이름", "price": 0, "image": "", "url": "", "category": "",
        "rocket": False, "free_shipping": False, "rank": 0, "source": "x",
    }


def test_picker_filters_and_rotates():
    cfg = load_config()["고르기"]
    picks = picker.choose(FIX, used={}, cfg=cfg, count=3)
    names = [p["name"] for p in picks]
    assert "다이어트 보조제 60정" not in " ".join(names)  # 제외_단어
    assert all(p["rocket"] for p in picks)  # 로켓배송만
    assert picks[0]["id"] == "7001"  # 순위 1위부터
    # 쓴 것은 다시 안 뽑힘
    again = picker.choose(FIX, used={"7001": {}}, cfg=cfg, count=1)
    assert again[0]["id"] == "7004"
    cats = picker.todays_categories(cfg, 2, day_index=4)
    assert [c["ID"] for c in cats] == [1017, 1016]


def test_texts_carry_notice_and_limits():
    config = load_config()
    config["발행"]["내_스토어_주소"] = "https://influencers.coupang.com/s/test"
    product = FIX[0]
    copy = writer.fallback_copy(product)
    texts = writer.build_texts(product, copy, config)
    assert config["고지문"] in texts["caption"]
    assert config["고지문"] in texts["threads_text"]
    assert product["url"] in texts["threads_text"]
    assert "influencers.coupang.com/s/test" in texts["caption"]
    assert len(texts["threads_text"]) <= 500
    assert len(texts["caption"]) <= 2200
    assert 1 <= len(texts["hashtags"]) <= 5


def test_scrub_removes_banned_words():
    copy = {
        "hook": "역대 최저가 특가!",
        "body_lines": ["효과 보장 제품이다", "좋다"],
        "search_line": "1위 청소기",
        "threads_text": "인기템",
        "alt_text": "x" * 200,
        "hashtags": ["최저가", "#청소기", "청소기"],
    }
    out = writer.scrub(copy)
    assert not writer.banned_words(out)
    assert out["hashtags"] == ["#최저가", "#청소기"] or "#청소기" in out["hashtags"]
    assert len(out["alt_text"]) == 100


def test_card_renders(tmp_path):
    from src import card

    config = load_config()
    product = FIX[0]
    html = card.render_html(product, writer.fallback_copy(product), config, image_data="")
    assert "로켓배송" in html and "39,900원" in html
    out = card.render_card(html, tmp_path / "card.jpg")
    assert out.exists() and out.stat().st_size > 20_000
