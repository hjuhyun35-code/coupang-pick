"""오늘 올릴 상품을 고르고, 글과 카드를 만들어 posts/ 에 저장합니다.

환경변수
  DRAFT_COUNT  몇 건 만들지 (비우면 config.json 의 하루_개수)
  SAMPLE=1     쿠팡 API 대신 tests/fixtures/products.json 을 씁니다 (키 없이 시험)
  NO_AI=1      Claude 대신 틀에 맞춘 글을 씁니다 (키 없이 시험)
결과
  posts/<YYYYMMDD-N>/card.jpg + post.json, posts/used.json 갱신
  GITHUB_OUTPUT 에 count, slugs 기록
"""

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import card, picker, writer  # noqa: E402
from src.settings import POSTS_DIR, ensure_dirs, load_config, today_kst  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "products.json"


def gather(config: dict, count: int, sample: bool) -> list[dict]:
    cfg = config["고르기"]
    if sample:
        return json.loads(FIXTURES.read_text(encoding="utf-8"))
    from src import coupang

    candidates: list[dict] = []
    for cat in picker.todays_categories(cfg, count):
        print(f"카테고리 베스트 조회: {cat['이름']}({cat['ID']})")
        candidates += coupang.best_in_category(cat["ID"], cfg.get("후보수", 30))
        time.sleep(1)
    if cfg.get("골드박스_포함"):
        print("골드박스 조회")
        candidates += coupang.goldbox(cfg.get("후보수", 30))
        time.sleep(1)
    for kw in cfg.get("검색어", []):
        print(f"검색: {kw}")
        candidates += coupang.search(kw, cfg.get("후보수", 30))
        time.sleep(1)
    return candidates


def next_slug(day: str) -> str:
    n = 1
    while (POSTS_DIR / f"{day}-{n}").exists():
        n += 1
    return f"{day}-{n}"


def main() -> int:
    ensure_dirs()
    config = load_config()
    count = int(os.environ.get("DRAFT_COUNT") or config.get("하루_개수", 1))
    sample = os.environ.get("SAMPLE") == "1"
    no_ai = os.environ.get("NO_AI") == "1" or not os.environ.get("ANTHROPIC_API_KEY")

    if not sample and not (os.environ.get("COUPANG_ACCESS_KEY") and os.environ.get("COUPANG_SECRET_KEY")):
        print("[막힘] 쿠팡 파트너스 API 키가 없습니다. Secrets 에 COUPANG_ACCESS_KEY / COUPANG_SECRET_KEY 를 넣으세요.")
        print("       키 없이 시험하려면 sample=1 로 돌리세요.")
        _output(0, [])
        return 0

    used = picker.load_used()
    candidates = gather(config, count, sample)
    print(f"후보 {len(candidates)}개, 이미 쓴 상품 {len(used)}개")
    picks = picker.choose(candidates, used, config["고르기"], count)
    if not picks:
        print("[주의] 조건에 맞는 새 상품이 없습니다. config.json 의 고르기 조건을 느슨하게 하세요.")
        _output(0, [])
        return 0

    day = today_kst().strftime("%Y%m%d")
    slugs: list[str] = []
    for product in picks:
        slug = next_slug(day)
        folder = POSTS_DIR / slug
        print(f"\n[{slug}] {product['name']} / {product['price']:,}원")
        try:
            copy = writer.fallback_copy(product) if no_ai else writer.write_copy(product, config)
        except RuntimeError as exc:
            print(f"  글쓰기 실패, 건너뜀: {exc}")
            continue
        texts = writer.build_texts(product, copy, config)
        card.make_card(product, copy, config, folder / "card.jpg")
        post = {
            "slug": slug,
            "product": product,
            "copy": copy,
            "caption": texts["caption"],
            "threads_text": texts["threads_text"],
            "alt": copy["alt_text"],
            "card": "card.jpg",
            "ai": not no_ai,
            "sample": sample,
            "created_at": today_kst().isoformat(timespec="seconds"),
            "published": False,
        }
        (folder / "post.json").write_text(json.dumps(post, ensure_ascii=False, indent=2), encoding="utf-8")
        used[product["id"]] = {"slug": slug, "name": product["name"][:40]}
        slugs.append(slug)
        print(f"  카드·글 저장: {folder}")

    if not sample:
        picker.save_used(used)
    _output(len(slugs), slugs)
    return 0


def _output(count: int, slugs: list[str]) -> None:
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"count={count}\nslugs={','.join(slugs)}\n")
    print(f"\n만든 초안: {count}건 {slugs}")


if __name__ == "__main__":
    raise SystemExit(main())
