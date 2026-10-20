# 오늘의 픽 봇 (coupang-pick)

매일 아침 쿠팡 파트너스 API 로 상품 하나를 골라, 글과 카드 이미지를 만들고,
인스타그램·쓰레드에 올리는 봇입니다. GitHub Actions 에서 돌아가므로 내 컴퓨터는 꺼져 있어도 됩니다.

쿠팡 인플루언서 **사이트는 건드리지 않습니다.** 파트너스 약관 제8조 2항(2026-09-07)이
로봇·자동화 수단으로 사이트에 접근하는 것을 금지하므로, 쿠팡이 열어 둔 Open API 만 씁니다.
'내 스토어' 상품 담기는 사람이 손으로 합니다.

## 매일 무슨 일이 일어나나

1. 오전 10시(한국) `오늘의 픽 만들기` 워크플로가 돕니다.
2. config.json 의 카테고리를 날짜 순서로 하나 골라 베스트 상품 30개를 받아 옵니다.
3. 로켓배송·가격대·제외 단어로 거르고, 전에 올린 적 없는 상품 중 순위가 높은 것을 집습니다.
4. Claude 가 글을 쓰고(금지어 검사 포함), 크롬이 1080x1350 카드를 찍습니다.
5. `posts/날짜-번호/` 에 card.jpg 와 post.json 을 저장하고 저장소에 커밋합니다.
6. 텔레그램으로 카드와 글을 보냅니다.
7. `발행.자동발행` 이 true 면 그 자리에서 올립니다. false(기본)면 사람이 `발행하기` 워크플로를 돌려야 올라갑니다.

## 처음 한 번 할 일

GitHub 저장소 → Settings → Secrets and variables → Actions 에 아래를 넣습니다.

| 이름 | 어디서 받나 |
|---|---|
| `COUPANG_ACCESS_KEY`, `COUPANG_SECRET_KEY` | 쿠팡 파트너스 → 추가기능 → API 발급 |
| `ANTHROPIC_API_KEY` | console.anthropic.com (글쓰기용. 없으면 틀에 맞춘 글로 대신) |
| `INSTAGRAM_USER_ID`, `INSTAGRAM_ACCESS_TOKEN` | Meta 앱 `glassnegative-bot` 에 이 계정을 테스터로 추가 → 토큰 발급 (싱간극장 봇과 같은 방법) |
| `THREADS_USER_ID`, `THREADS_ACCESS_TOKEN` | 쓰레드용 Meta 앱 (인스타와 별도 앱) |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | 없어도 됨. 있으면 매일 카드가 폰으로 옴 |

Meta 토큰은 60일마다 만료됩니다. 만료되면 모든 호출이 `API access blocked (code=200)` 로 실패하니 토큰부터 의심하세요.

## 올리는 방법 (자동발행이 꺼져 있을 때)

GitHub → Actions → `발행하기` → Run workflow → slug 에 텔레그램에 적힌 번호(예 `20261021-1`),
confirm 에 `PUBLISH`. 다른 글자를 넣으면 예행연습만 합니다.

## 키 없이 시험하기

```bash
SAMPLE=1 NO_AI=1 python scripts/generate.py
python -m pytest -q
```

Actions 에서도 `오늘의 픽 만들기` → sample 에 `1` 을 넣으면 쿠팡 API 없이 돌아갑니다
(시험용 초안은 발행 스크립트가 거부합니다).

## 꼭 지킬 것

- 모든 글 끝에 고지문이 붙습니다(config.json `고지문`). 지우면 안 됩니다. 표시광고법·쿠팡 운영정책 위반입니다.
- 상품명에 없는 효과·성능을 쓰지 않습니다. `특가·최저가·1위·효과 보장` 같은 말은 코드가 걷어냅니다.
- 새 계정은 하루 1건으로 2주쯤 지켜본 뒤 늘리세요. 처음부터 여러 건을 규칙적으로 올리면 스팸으로 걸립니다.
- 인스타 캡션의 링크는 눌리지 않습니다. 프로필 링크를 '내 스토어' 주소로 두고, 쿠팡 인플루언서의 자동 DM(댓글 키워드) 을 켜 두세요. 쓰레드에는 상품 링크가 그대로 들어갑니다.

## 파일

- `config.json` — 카테고리, 가격대, 말투, 자동발행 여부. 봇의 성격은 전부 여기서 바꿉니다.
- `src/coupang.py` — 쿠팡 파트너스 API (HMAC 서명, 베스트·골드박스·검색·딥링크)
- `src/picker.py` — 상품 고르기와 중복 방지(`posts/used.json`)
- `src/writer.py` — Claude 글쓰기, 금지어 검사, 캡션·쓰레드 조립
- `src/card.py` + `templates/card.html` — 카드 이미지
- `src/publisher.py` — 인스타·쓰레드 올리기
- `scripts/generate.py`, `scripts/publish.py`, `scripts/notify.py` — 워크플로가 부르는 것들
