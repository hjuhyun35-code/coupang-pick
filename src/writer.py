"""상품 하나에 대한 글을 씁니다. Claude 가 쓰고, 키가 없으면 틀에 맞춰 씁니다.

지켜야 할 것 (쿠팡 '내 스토어 이용 가이드' 2026-08-11 와 표시광고법):
- 사실만. 상품명에 없는 성능·효과를 지어내지 않는다.
- '특가·세일·최저가·인기템·1위·최고·최초·100% 만족·효과 확실' 금지.
- 의료 효과처럼 읽히는 말 금지.
- 쿠팡 공식 추천인 것처럼 쓰지 않는다.
- 경제적 이해관계 고지문은 코드가 반드시 붙인다(모델에게 맡기지 않는다).
"""

import json
import re

from .settings import env

MAX_THREADS = 480  # 쓰레드 한도 500자, 여유
MAX_CAPTION = 2100  # 인스타 한도 2,200자, 여유

BANNED = (
    "특가", "세일", "최저가", "인기템", "1위", "최고", "최초", "100%",
    "효과 확실", "효과 보장", "실패 없는", "공식 추천", "땡처리", "반값", "히트",
)

SYSTEM = (
    "너는 쿠팡 상품 하나를 짧게 소개하는 한국어 SNS 글을 쓴다. 읽는 사람은 20~40대 한국인이다.\n"
    "말투: 이야기하듯 편하게, '~다' 체. 광고 문구가 아니라 써 본 사람이 옆에서 말해 주는 느낌.\n"
    "장면을 보여주고 설명하지 마라. 토막 문장('샀다. 좋다.') 금지, 문장은 자연스럽게 이어라.\n\n"
    "절대 규칙:\n"
    "- 상품명과 가격, 로켓배송 여부 외에는 아는 게 없다. 성능·재질·효과·후기 수치를 지어내지 마라.\n"
    "  쓸 수 있는 건 '이런 상황에 쓰기 좋다' 는 용도 제안까지다.\n"
    "- 다음 말은 쓰지 마라: " + ", ".join(BANNED) + ".\n"
    "- 의료·건강 효과를 단정하지 마라. 쿠팡이 공식 추천한 것처럼 쓰지 마라.\n"
    "- 해시태그는 3~5개, 상품 종류와 쓰임새 위주. 영어 금지.\n"
    "- search_line 은 인스타 캡션 첫 줄이다. 구글·인스타 검색에 걸리게 상품 종류 이름을 그대로 넣어라.\n"
    "- alt_text 는 카드 이미지에 실제로 보이는 것(상품 사진과 글자)만 100자 안에 적어라."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "hook": {"type": "string", "description": "카드 맨 위 한 줄. 28자 안쪽. 멈추게 하는 말."},
        "body_lines": {
            "type": "array",
            "items": {"type": "string"},
            "description": "본문 2~3문장. 한 줄 40자 안쪽. 용도·상황 중심.",
        },
        "search_line": {"type": "string", "description": "캡션 첫 줄. 상품 종류 이름이 그대로 들어간 한 문장."},
        "threads_text": {"type": "string", "description": "쓰레드용 본문. 2~3문장, 300자 안쪽. 링크·고지문은 넣지 마라."},
        "alt_text": {"type": "string"},
        "hashtags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["hook", "body_lines", "search_line", "threads_text", "alt_text", "hashtags"],
    "additionalProperties": False,
}


def _prompt(product: dict, tone: str) -> str:
    rocket = "로켓배송" if product["rocket"] else "일반배송"
    return (
        f"상품명: {product['name']}\n"
        f"가격: {product['price']:,}원\n"
        f"배송: {rocket}\n"
        f"분류: {product.get('category') or '(없음)'}\n\n"
        f"계정 말투 지침: {tone}\n\n"
        "위 정보만으로 글을 써라."
    )


def write_copy(product: dict, config: dict) -> dict:
    """Claude 로 글을 씁니다. 금지어가 섞이면 한 번 더 시도하고, 그래도 남으면 걷어냅니다."""
    from anthropic import Anthropic

    client = Anthropic(api_key=env("ANTHROPIC_API_KEY", required=True))
    model_cfg = config.get("모델", {})
    tone = config["글투"]["지침"]
    warning = ""
    result: dict = {}
    for _ in range(2):
        resp = client.messages.create(
            model=model_cfg.get("이름", "claude-opus-5-5"),
            max_tokens=2000,
            system=SYSTEM,
            output_config={
                "effort": model_cfg.get("effort", "low"),
                "format": {"type": "json_schema", "schema": SCHEMA},
            },
            messages=[{"role": "user", "content": _prompt(product, tone) + warning}],
        )
        if resp.stop_reason == "refusal":
            raise RuntimeError("Claude 가 이 상품 글을 거부했습니다. 다른 상품으로 넘어갑니다.")
        text = next(b.text for b in resp.content if b.type == "text")
        result = json.loads(text)
        hits = banned_words(result)
        if not hits:
            break
        warning = f"\n\n직전 답에 금지어가 있었다: {', '.join(hits)}. 그 말 없이 다시 써라."
    return scrub(result)


def fallback_copy(product: dict) -> dict:
    """키가 없거나 시험할 때 쓰는 틀. 사실만 적습니다."""
    short = product["name"][:28]
    if len(product["name"]) > 28 and " " in short:
        short = short.rsplit(" ", 1)[0]  # 낱말 중간에서 끊지 않습니다
    return {
        "hook": f"오늘 눈에 들어온 {short}",
        "body_lines": [
            f"{product['name']}",
            f"{product['price']:,}원" + (", 로켓배송" if product["rocket"] else ""),
            "자세한 건 링크에서 확인할 수 있다.",
        ],
        "search_line": f"{short} 오늘의 픽",
        "threads_text": f"오늘 눈에 들어온 {product['name']}. {product['price']:,}원"
        + (", 로켓배송이다." if product["rocket"] else "."),
        "alt_text": f"{short} 상품 사진과 가격 {product['price']:,}원",
        "hashtags": ["#쿠팡추천", "#오늘의픽", "#생활템"],
    }


def banned_words(copy: dict) -> list[str]:
    blob = " ".join(
        [copy.get("hook", ""), copy.get("search_line", ""), copy.get("threads_text", "")]
        + list(copy.get("body_lines", []))
    )
    return [w for w in BANNED if w in blob]


def scrub(copy: dict) -> dict:
    """모델이 두 번 다 금지어를 넣으면 기계적으로 지웁니다. 글이 조금 어색해도 제재보다 낫습니다."""
    def clean(s: str) -> str:
        for w in BANNED:
            s = s.replace(w, "")
        return re.sub(r"\s{2,}", " ", s).strip()

    copy["hook"] = clean(copy.get("hook", ""))[:40]
    copy["search_line"] = clean(copy.get("search_line", ""))
    copy["threads_text"] = clean(copy.get("threads_text", ""))
    copy["body_lines"] = [clean(x) for x in copy.get("body_lines", []) if clean(x)][:4]
    tags = []
    for t in copy.get("hashtags", []):
        t = "#" + re.sub(r"[^0-9A-Za-z가-힣_]", "", t.lstrip("#"))
        if len(t) > 1 and t not in tags:
            tags.append(t)
    copy["hashtags"] = tags[:5]
    copy["alt_text"] = (copy.get("alt_text") or "")[:100]
    return copy


# ------------------------------------------------------------- 최종 글 조립


def build_texts(product: dict, copy: dict, config: dict) -> dict:
    """인스타 캡션과 쓰레드 본문을 완성합니다. 고지문은 여기서 반드시 붙습니다."""
    pub = config.get("발행", {})
    notice = config["고지문"].strip()
    tags = list(dict.fromkeys(config["글투"].get("해시태그", []) + copy["hashtags"]))[:5]
    price_line = f"{product['price']:,}원" + (" · 로켓배송" if product["rocket"] else "")

    # 인스타 캡션에는 링크가 눌리지 않습니다. 내 스토어 주소나 자동 DM 키워드로 안내합니다.
    link_hint = []
    if pub.get("내_스토어_주소"):
        link_hint.append(f"내 스토어(프로필 링크)에서 볼 수 있다 → {pub['내_스토어_주소']}")
    if pub.get("자동DM_키워드"):
        link_hint.append(f"댓글에 '{pub['자동DM_키워드']}' 라고 남기면 DM 으로 링크를 보내 준다.")
    if not link_hint:
        link_hint.append("링크는 프로필에 있다.")

    caption = "\n\n".join(
        [
            copy["search_line"],
            "\n".join(copy["body_lines"]),
            price_line,
            "\n".join(link_hint),
            notice,
            " ".join(tags),
        ]
    )
    caption = caption[:MAX_CAPTION]

    # 쓰레드는 링크가 눌립니다. 본문 + 링크 + 고지문.
    threads = f"{copy['threads_text'].strip()}\n\n{price_line}\n{product['url']}\n\n{notice}"
    if len(threads) > MAX_THREADS:
        room = MAX_THREADS - len(threads) + len(copy["threads_text"])
        threads = f"{copy['threads_text'][: max(room - 1, 0)].rstrip()}…\n\n{price_line}\n{product['url']}\n\n{notice}"

    return {"caption": caption, "threads_text": threads, "hashtags": tags}
