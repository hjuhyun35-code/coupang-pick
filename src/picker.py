"""오늘 올릴 상품을 고릅니다.

규칙은 전부 config.json 의 '고르기' 에서 옵니다.
- 카테고리를 날짜 순서대로 돌아가며 하나 뽑고(어제 가전이면 오늘은 생활용품)
- 로켓배송·가격대로 거른 뒤
- 전에 올린 적 없는 것 중 순위가 높은 것부터 집습니다.
"""

import json

from .settings import USED_PATH, today_kst


def load_used() -> dict:
    if USED_PATH.exists():
        return json.loads(USED_PATH.read_text(encoding="utf-8"))
    return {}


def save_used(used: dict) -> None:
    USED_PATH.parent.mkdir(parents=True, exist_ok=True)
    USED_PATH.write_text(json.dumps(used, ensure_ascii=False, indent=2), encoding="utf-8")


def todays_categories(cfg: dict, count: int, day_index: int | None = None) -> list[dict]:
    """오늘 돌 카테고리. 하루 한 건이면 하나, 두 건이면 이어지는 둘."""
    cats = cfg["카테고리"]
    if not cats:
        return []
    if day_index is None:
        day_index = today_kst().timetuple().tm_yday
    return [cats[(day_index + i) % len(cats)] for i in range(count)]


def passes(product: dict, cfg: dict) -> bool:
    if cfg.get("로켓배송만") and not product["rocket"]:
        return False
    price = product["price"]
    if price <= 0:
        return False
    if price < cfg.get("최소_가격", 0):
        return False
    if cfg.get("최대_가격") and price > cfg["최대_가격"]:
        return False
    if not product["image"] or not product["url"] or not product["name"]:
        return False
    bad = [w for w in cfg.get("제외_단어", []) if w and w in product["name"]]
    return not bad


def choose(candidates: list[dict], used: dict, cfg: dict, count: int = 1) -> list[dict]:
    """거르고, 쓴 것 빼고, 순위대로 count 개."""
    seen: set[str] = set()
    picked: list[dict] = []
    ordered = sorted(candidates, key=lambda p: (p["rank"] or 9999))
    for p in ordered:
        if p["id"] in used or p["id"] in seen:
            continue
        if not passes(p, cfg):
            continue
        seen.add(p["id"])
        picked.append(p)
        if len(picked) >= count:
            break
    return picked
