"""쓰레드와 인스타그램에 실제로 글을 올립니다. (singan-theater 의 publisher 와 같은 방식)

두 플랫폼 모두:
  1) '컨테이너'를 만든다 (아직 안 올라감)
  2) 서버가 이미지를 다 받을 때까지 기다린다
  3) publish 를 호출하면 그때 올라간다
"""

import time

import requests

from .settings import env

THREADS_HOST = "https://graph.threads.net/v1.0"
INSTAGRAM_HOST = "https://graph.instagram.com/v23.0"
TIMEOUT = 60
POLL_INTERVAL = 5
POLL_MAX = 24  # 최대 2분 대기


class PublishError(RuntimeError):
    pass


def _json(resp: requests.Response) -> dict:
    try:
        return resp.json()
    except ValueError:
        return {"error": {"message": resp.text[:300]}}


def _error_message(payload: dict, resp: requests.Response) -> str:
    err = payload.get("error", {})
    msg = err.get("message") or resp.text[:300]
    code = err.get("code")
    hint = ""
    if code in (190, 102):
        hint = "  → 토큰이 만료됐습니다(60일). 새 토큰을 받아 Secrets 를 바꾸세요."
    elif code == 10 or "permission" in str(msg).lower():
        hint = "  → Meta 앱에 권한(scope)이 빠졌거나 계정이 테스터로 등록되지 않았습니다."
    return f"{msg} (code={code}){hint}"


def _post(url: str, params: dict) -> dict:
    params = {k: v for k, v in params.items() if v not in (None, "")}
    resp = requests.post(url, data=params, timeout=TIMEOUT)
    payload = _json(resp)
    if resp.status_code >= 400 or "error" in payload:
        raise PublishError(_error_message(payload, resp))
    return payload


def _get(url: str, params: dict) -> dict:
    resp = requests.get(url, params=params, timeout=TIMEOUT)
    payload = _json(resp)
    if resp.status_code >= 400 or "error" in payload:
        raise PublishError(_error_message(payload, resp))
    return payload


def _wait_ready(host: str, container_id: str, token: str, status_field: str) -> None:
    for _ in range(POLL_MAX):
        info = _get(
            f"{host}/{container_id}",
            {"fields": f"{status_field},error_message", "access_token": token},
        )
        status = info.get(status_field)
        if status == "FINISHED":
            return
        if status in ("ERROR", "EXPIRED"):
            raise PublishError(f"이미지 처리 실패: {info.get('error_message') or status}")
        time.sleep(POLL_INTERVAL)
    raise PublishError("이미지 처리가 2분 안에 끝나지 않았습니다. 잠시 후 다시 시도하세요.")


def post_to_threads(text: str, image_url: str | None = None) -> str:
    user_id = env("THREADS_USER_ID", required=True)
    token = env("THREADS_ACCESS_TOKEN", required=True)
    base = f"{THREADS_HOST}/{user_id}"
    if image_url:
        container = _post(
            f"{base}/threads",
            {"media_type": "IMAGE", "image_url": image_url, "text": text, "access_token": token},
        )["id"]
        _wait_ready(THREADS_HOST, container, token, "status")
    else:
        container = _post(
            f"{base}/threads", {"media_type": "TEXT", "text": text, "access_token": token}
        )["id"]
        time.sleep(3)
    return _post(f"{base}/threads_publish", {"creation_id": container, "access_token": token})["id"]


def post_to_instagram(caption: str, image_url: str, alt_text: str = "") -> str:
    user_id = env("INSTAGRAM_USER_ID", required=True)
    token = env("INSTAGRAM_ACCESS_TOKEN", required=True)
    base = f"{INSTAGRAM_HOST}/{user_id}"
    params = {
        "image_url": image_url,
        "caption": caption,
        "alt_text": (alt_text or "")[:100],
        "access_token": token,
    }
    try:
        container = _post(f"{base}/media", params)["id"]
    except PublishError as exc:
        # 대체텍스트 때문에 거부되면 그것만 빼고 다시. 게시물 전체를 날릴 이유는 아닙니다.
        if params["alt_text"] and "alt" in str(exc).lower():
            print(f"  대체텍스트가 거부되어 없이 재시도합니다: {exc}")
            container = _post(f"{base}/media", {**params, "alt_text": ""})["id"]
        else:
            raise
    _wait_ready(INSTAGRAM_HOST, container, token, "status_code")
    return _post(f"{base}/media_publish", {"creation_id": container, "access_token": token})["id"]
