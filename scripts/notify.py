"""만든 초안(또는 발행 결과)을 텔레그램으로 보냅니다. 설정이 없으면 조용히 건너뜁니다."""

import json
import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
POSTS = ROOT / "posts"
API = "https://api.telegram.org/bot{token}/{method}"


def _call(method: str, data: dict, files: dict | None = None) -> dict:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    resp = requests.post(API.format(token=token, method=method), data=data, files=files, timeout=60)
    payload = resp.json()
    if not payload.get("ok"):
        raise RuntimeError(f"텔레그램 {method} 실패: {payload}")
    return payload


def main() -> int:
    if not os.environ.get("TELEGRAM_BOT_TOKEN") or not os.environ.get("TELEGRAM_CHAT_ID"):
        print("텔레그램 설정이 없어 알림을 건너뜁니다.")
        return 0
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    slugs = [s for s in (os.environ.get("SLUGS") or "").split(",") if s]
    if not slugs:
        _call("sendMessage", {"chat_id": chat_id, "text": "오늘은 조건에 맞는 새 상품이 없어 초안을 만들지 못했습니다."})
        return 0
    for slug in slugs:
        post = json.loads((POSTS / slug / "post.json").read_text(encoding="utf-8"))
        state = "발행 완료 ✅" if post.get("published") else "초안 (아직 안 올림)"
        text = "\n".join(
            [
                f"🛒 {post['product']['name'][:60]}",
                f"{post['product']['price']:,}원" + (" · 로켓" if post["product"]["rocket"] else ""),
                f"{state}",
                "",
                post["threads_text"][:700],
                "",
                "─" * 16,
                slug,
            ]
        )
        if not post.get("published"):
            text += f"\n올리려면 GitHub → Actions → 발행하기 → slug={slug}, confirm=PUBLISH"
            if repo:
                text += f"\nhttps://github.com/{repo}/actions/workflows/publish.yml"
        with open(POSTS / slug / post["card"], "rb") as f:
            _call(
                "sendPhoto",
                {"chat_id": chat_id, "caption": text[:1024]},
                {"photo": ("card.jpg", f.read(), "image/jpeg")},
            )
        print(f"보냄: {slug}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
