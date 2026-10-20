"""설정 파일(config.json)과 비밀키(환경변수 또는 .env)를 읽어오는 곳."""

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POSTS_DIR = ROOT / "posts"
USED_PATH = POSTS_DIR / "used.json"

KST = timezone(timedelta(hours=9))

# .env 는 내 컴퓨터에서만 씁니다.
# GitHub Actions 에서는 Secrets 가 환경변수로 들어오므로 dotenv 가 없어도 됩니다.
try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ModuleNotFoundError:
    pass


def load_config() -> dict:
    with open(ROOT / "config.json", encoding="utf-8") as f:
        return json.load(f)


def env(name: str, required: bool = False) -> str:
    value = (os.environ.get(name) or "").strip()
    if required and not value:
        raise RuntimeError(
            f"{name} 값이 비어 있습니다. GitHub 저장소의 Secrets 에 넣거나 "
            f"내 컴퓨터라면 .env 파일에 적어 주세요."
        )
    return value


def today_kst() -> datetime:
    return datetime.now(KST)


def ensure_dirs() -> None:
    POSTS_DIR.mkdir(parents=True, exist_ok=True)
