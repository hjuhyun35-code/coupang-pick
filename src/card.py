"""인스타에 올릴 카드 이미지(1080x1350 JPEG)를 만듭니다.

HTML 을 크롬으로 열어 사진처럼 찍습니다. 모양을 바꾸려면 templates/card.html 만 고치면 됩니다.
상품 사진은 쿠팡 주소를 그대로 쓰지 않고 내려받아 HTML 안에 심습니다
(쿠팡 이미지 주소는 한 번 더 넘어가는(302) 주소라 인스타가 바로 못 받습니다).
"""

import base64
from pathlib import Path

import requests
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .settings import ROOT

WIDTH, HEIGHT = 1080, 1350
JPEG_QUALITY = 92

_env = Environment(
    loader=FileSystemLoader(ROOT / "templates"),
    autoescape=select_autoescape(["html"]),
)


def fetch_image_data_uri(url: str) -> str:
    """상품 사진을 받아 data: 주소로. 못 받으면 빈 문자열(카드는 글자만으로 나갑니다)."""
    if not url:
        return ""
    try:
        resp = requests.get(
            url,
            timeout=20,
            allow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.coupang.com/"},
        )
        resp.raise_for_status()
    except requests.RequestException:
        return ""
    mime = resp.headers.get("Content-Type", "image/jpeg").split(";")[0]
    if not mime.startswith("image/"):
        return ""
    return f"data:{mime};base64,{base64.b64encode(resp.content).decode('ascii')}"


def render_html(product: dict, copy: dict, config: dict, image_data: str) -> str:
    tpl = _env.get_template("card.html")
    pub = config.get("발행", {})
    return tpl.render(
        theme=pub.get("색테마", "종이"),
        kicker=product.get("category") or "오늘의 픽",
        hook=copy["hook"],
        body_lines=copy["body_lines"][:3],
        name=product["name"],
        price=f"{product['price']:,}원",
        rocket=product["rocket"],
        image=image_data,
        handle=pub.get("계정표시", ""),
        notice_short="쿠팡 파트너스 · 수수료를 받습니다",
    )


def render_card(html: str, out_path: Path) -> Path:
    from playwright.sync_api import sync_playwright

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT})
        page.set_content(html, wait_until="load")
        page.wait_for_timeout(300)
        page.screenshot(path=str(out_path), type="jpeg", quality=JPEG_QUALITY, full_page=False)
        browser.close()
    return out_path


def make_card(product: dict, copy: dict, config: dict, out_path: Path) -> Path:
    image = fetch_image_data_uri(product["image"])
    html = render_html(product, copy, config, image)
    return render_card(html, out_path)
