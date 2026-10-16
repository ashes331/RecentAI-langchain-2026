"""[4교시 / 실습 5] ★ Slack API — 체인의 결과를 사람에게 배달한다

지금까지 배운 것은 전부 "무엇을 만들까" 였다.
오늘 배우는 것은 "만든 것을 어디로 보낼까" 다.

    result = chain.invoke(...)
    print(result)      # ← 터미널에만 찍힌다. 터미널을 닫으면 끝.

  상황                         print() 로 충분한가
  ────────────────────────────────────────────────
  내가 지금 보고 있다          충분하다
  밤 2시에 돌아간 배치         아무도 안 본다
  서버에서 돌아가는 체인       로그 파일을 열어야 안다
  팀이 같이 봐야 하는 결과     복사해서 붙여넣어야 한다

오늘의 한 줄 : print() 를 chat_postMessage() 로 바꾼다.

─────────────────────────────────────────────────────────────
사전 준비 (Slack 웹사이트에서 4단계 — 안 하면 ⑥은 반드시 실패한다)

  ① 앱 생성     api.slack.com/apps → Create New App → **Blank app**
                  ⚠️ 2026년에 화면이 바뀌었다. 예전 "From scratch" 가 지금 "Blank app".
  ② 권한 부여   OAuth & Permissions → Scopes → **Bot** Token Scopes
                  → Add an OAuth Scope → chat:write
                  ⚠️ 바로 아래 User Token Scopes 가 아니다. 그건 "내 이름으로" 보내는 권한.
  ③ 설치·토큰   같은 페이지 맨 위 OAuth Tokens → Install to <워크스페이스>
                  → Allow → **Bot User OAuth Token** (xoxb-...) 복사 → .env 에 저장
  ④ 채널 초대   #수업-출력물 채널은 교수자가 만들어 두었다. 채널에 참여한 뒤
                  그 채널에서  /invite @본인앱이름
                  ⚠️ 수강생 전원이 함께 쓰는 채널이다. 보낸 사람은 앱 이름으로 구분된다.

⚠️ 토큰은 비밀번호다. .env 에만 두고 절대 커밋하지 않는다.
   이미 노출했다면 숨기지 말고 OAuth & Permissions 에서 **Regenerate** 한다.
   (이전 토큰은 그 즉시 무효가 된다)

실행:
    python send_slack_message.py                 # 기본 메시지 전송
    python send_slack_message.py "보낼 내용"      # 원하는 내용으로 전송
"""

import os
import sys

from dotenv import load_dotenv
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

load_dotenv()  # .env 를 환경변수로 읽어들인다

TOKEN = os.environ.get("SLACK_BOT_TOKEN")
CHANNEL = os.environ.get("SLACK_CHANNEL", "#수업-출력물")

# ⚠️ 설정 오류(토큰 없음)와 API 오류(권한·채널)를 일부러 분리해 둔다.
#    분리해 두면 "어디서 잘못됐는지" 를 에러 종류만 보고 바로 안다.
if not TOKEN:
    raise SystemExit(
        "SLACK_BOT_TOKEN 이 없습니다.\n"
        "  1) .env.example 을 복사해 .env 로 만든다\n"
        "  2) SLACK_BOT_TOKEN=xoxb-... 를 채운다\n"
        "  3) 따옴표와 앞뒤 공백을 넣지 않는다  ← invalid_auth 의 흔한 범인"
    )

client = WebClient(token=TOKEN)


# ── 이 함수 하나가 오늘의 전부다 ★ ──────────────────────────────
def send(text: str, thread_ts: str | None = None) -> str:
    """슬랙 채널에 text 를 보내고, 보낸 메시지의 타임스탬프(ts)를 돌려준다.

    thread_ts 를 주면 그 메시지의 '스레드 댓글' 로 달린다.
    """
    try:
        res = client.chat_postMessage(  # ★ 핵심 한 줄
            channel=CHANNEL,
            text=text,
            thread_ts=thread_ts,
        )
        print(f"전송 성공 → {CHANNEL} (ts={res['ts']})")
        return res["ts"]

    except SlackApiError as e:
        code = e.response["error"]
        print(f"전송 실패: {code}")
        print(HINTS.get(code, "  → api.slack.com/methods/chat.postMessage 의 Errors 표를 확인하세요."))
        raise


# ── 에러 대응표 — 여기서 다 막힌다 ★ ────────────────────────────
#    대부분 코드 문제가 아니라 위의 ①~④ 중 하나를 건너뛴 문제다.
HINTS = {
    "not_in_channel": "  → ④단계 누락. 슬랙 채널에서  /invite @앱이름  을 실행하세요.",
    "missing_scope": "  → ②단계 누락, 또는 스코프를 추가하고 '재설치' 를 안 했습니다.\n"
                     "     chat:write 추가 후 반드시 Install 을 다시 누르세요.\n"
                     "     (이미 발급된 토큰에는 추가한 권한이 들어 있지 않습니다)",
    "channel_not_found": "  → 채널명 오타이거나 비공개 채널입니다.\n"
                         "     '#' 을 포함했는지 확인하거나, 채널 ID(C01ABCD...)를 쓰세요.",
    "invalid_auth": "  → 토큰이 틀렸거나 재발급되었습니다.\n"
                    "     .env 의 앞뒤 따옴표·공백이 흔한 범인입니다.",
    "token_revoked": "  → 토큰이 폐기되었습니다. 앱을 다시 설치해 새 토큰을 받으세요.",
    "ratelimited": "  → 너무 빠르게 반복 호출했습니다. 반복문에 time.sleep(1) 을 넣으세요.",
}


def main() -> None:
    text = sys.argv[1] if len(sys.argv) > 1 else (
        "안녕하세요! 5주차 실습에서 보내는 첫 메시지입니다. 🎉"
    )

    print("=" * 60)
    print(f"채널 : {CHANNEL}")
    print(f"토큰 : {TOKEN[:9]}...{TOKEN[-4:]}   ← 앞뒤만 찍는다. 전체를 찍지 말 것 ⚠️")
    print("=" * 60)

    # send() 는 실패를 그대로 raise 한다 (체인 안에서 쓸 때 조용히 넘어가면 안 되므로).
    # 다만 이 파일을 직접 실행할 때는 긴 트레이스백 대신 위의 안내만 보이게 종료한다.
    try:
        ts = send(text)

        # ts 는 메시지의 고유 ID 다. 이 값을 thread_ts 로 넘기면 스레드 댓글이 된다 ★
        send("↑ 이 메시지의 스레드에 달린 댓글입니다. (thread_ts 활용)", thread_ts=ts)

    except SlackApiError:
        raise SystemExit(1)

    print("=" * 60)
    print("""
관찰 — 무엇을 볼 것인가

  관찰 항목                    짚어줄 말
  ────────────────────────────────────────────────────────────────
  보낸 사람이 '앱 이름'        내 계정이 아니다. Bot 토큰으로 보냈기 때문 ★
  이름 옆의 APP 배지           슬랙이 "사람이 아님" 을 표시해 준다
  🎉 가 그대로 렌더링          text 는 슬랙 서식(mrkdwn)으로 해석된다
  두 번째 메시지가 스레드로     ts 가 메시지의 주소 역할을 한다 ★
  ts 값 (1759xxxxxx.xxxxxx)    유닉스 시각 + 일련번호

💡 한 걸음 더
   · 메시지를 *굵게* · `코드` · <@사용자ID> 로 바꿔 보라
   · 존재하지 않는 채널명을 넣고 어떤 에러가 나는지 확인하라 (channel_not_found)
   · /invite 를 빼먹은 채널로 보내 보라 (not_in_channel) — 오늘 가장 많이 만날 에러
   · blocks= 로 Block Kit 카드를 보내 보라 → api.slack.com/block-kit-builder

⚠️ 캡처를 제출할 때 토큰이 화면에 찍히지 않았는지 반드시 확인할 것.
""")


if __name__ == "__main__":
    main()
