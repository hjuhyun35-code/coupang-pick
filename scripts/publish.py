"""초안을 실제로 발행합니다.

카드 이미지는 이 저장소의 공개 주소(raw.githubusercontent.com)를 그대로 씁니다.
안전장치: CONFIRM 이 정확히 PUBLISH 가 아니면 직전까지만 해보고 멈춥니다.
SLUG 에 여러 개를 쉼표로 적으면 차례로 올립니다.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import publisher  # noqa: E402

POSTS = ROOT / "posts"
RAW = "https://raw.githubusercontent.com/{repo}/{branch}/posts/{slug}/{file}"


def check_reachable(url: str) -> None:
    resp = requests.head(url, timeout=30, allow_redirects=True)
    if resp.status_code != 200:
        raise RuntimeError(
            f"이미지를 열 수 없습니다 ({resp.status_code}): {url}\n"
            "  → 저장소가 공개(public)인지, 커밋이 푸시됐는지 확인하세요."
        )
    if "image" not in resp.headers.get("Content-Type", ""):
        raise RuntimeError(f"이미지가 아닙니다: {url}")


def publish_one(slug: str, repo: str, branch: str, confirm: bool) -> dict:
    post_path = POSTS / slug / "post.json"
    if not post_path.exists():
        raise RuntimeError(f"{slug} 초안을 찾을 수 없습니다.")
    post = json.loads(post_path.read_text(encoding="utf-8"))
    if post.get("published"):
        raise RuntimeError(f"{slug} 는 이미 발행됐습니다 ({post.get('published_at')}).")
    if post.get("sample"):
        raise RuntimeError(f"{slug} 는 시험용(SAMPLE) 초안입니다. 진짜 상품이 아니라 올리지 않습니다.")

    url = RAW.format(repo=repo, branch=branch, slug=slug, file=post["card"])
    print(f"발행 대상: {post['product']['name']}")
    print(f"  캡션 {len(post['caption'])}자 / 쓰레드 {len(post['threads_text'])}자")
    check_reachable(url)
    print("  이미지 접근 확인")

    if not confirm:
        print("\n=== 예행연습입니다 (실제로 올리지 않았습니다) ===\n")
        print(post["caption"])
        print("\n--- 쓰레드 ---\n" + post["threads_text"])
        return {}

    results: dict[str, str] = {}
    if os.environ.get("INSTAGRAM_ACCESS_TOKEN"):
        print("인스타그램에 올리는 중...")
        results["instagram"] = publisher.post_to_instagram(post["caption"], url, post.get("alt", ""))
        print(f"  완료: {results['instagram']}")
    if os.environ.get("THREADS_ACCESS_TOKEN"):
        print("쓰레드에 올리는 중...")
        results["threads"] = publisher.post_to_threads(post["threads_text"], url)
        print(f"  완료: {results['threads']}")
    if not results:
        raise RuntimeError("인스타·쓰레드 토큰이 하나도 없습니다.")

    post["published"] = True
    post["published_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    post["post_ids"] = results
    post_path.write_text(json.dumps(post, ensure_ascii=False, indent=2), encoding="utf-8")
    return results


def main() -> int:
    slugs = [s.strip() for s in (os.environ.get("SLUG") or "").split(",") if s.strip()]
    confirm = (os.environ.get("CONFIRM") or "").strip() == "PUBLISH"
    repo = os.environ["GITHUB_REPOSITORY"]
    branch = os.environ.get("BRANCH", "main")
    if not slugs:
        print("[막힘] SLUG 가 비어 있습니다.")
        return 1
    failed = 0
    for slug in slugs:
        try:
            publish_one(slug, repo, branch, confirm)
        except Exception as exc:  # 한 건이 실패해도 나머지는 계속
            failed += 1
            print(f"[실패] {slug}: {exc}")
    return 1 if failed == len(slugs) else 0


if __name__ == "__main__":
    raise SystemExit(main())
