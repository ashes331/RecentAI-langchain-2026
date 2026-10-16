import os
import sys

import requests
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI  # 준비 ① 상용 창구
from dotenv import load_dotenv  # 준비 ② .env 읽는 도구


# override=True: 시스템 환경변수에 같은 이름이 있어도 .env 값을 우선한다
load_dotenv(override=True)

# Windows 콘솔(cp949)은 모델이 뱉는 한자·이모지에서 UnicodeEncodeError 를 낸다.
# 출력 인코딩을 UTF-8 로 바꿔 둔다.
sys.stdout.reconfigure(encoding="utf-8")

MODEL = "gemma3:4b"
OPENAI_MODEL = "gpt-4o-mini"

SLACK_API_URL = "https://slack.com/api/chat.postMessage"

# ── 부품 3개 ──────────────────────────────────────
prompt = ChatPromptTemplate.from_messages(
    [
        ("system", "당신은 프로그래밍 강사입니다. {level} 눈높이로 설명하세요."),
        ("human", "{topic}의 장점 3가지를 각각 한 문장으로 알려줘."),
    ]
)
llm_ollama = ChatOllama(model=MODEL)
llm_openai = ChatOpenAI(model=OPENAI_MODEL)

# step_by_step / with_pipe / batch_demo / stream_demo 가 사용하는 기본 모델.
# OpenAI 로 바꾸려면 llm_openai 로 교체한다.
llm = llm_ollama

parser = StrOutputParser()

# batch_demo 와 slack_demo 가 함께 쓰는 질문 목록
INPUTS = [
    {"level": "초보자", "topic": "파이썬"},
    {"level": "실무자", "topic": "Git"},
]


def step_by_step() -> None:
    """방법 A — 하나씩 손으로 넘기기.

    동작은 한다. 하지만 중간 변수가 3개 필요하고,
    부품이 늘어날수록 코드가 계속 길어진다.
    """
    print("── 방법 A: 손으로 하나씩 ─────────────────")

    messages = prompt.invoke({"level": "초보자", "topic": "파이썬"})
    ai_msg = llm.invoke(messages)
    text = parser.invoke(ai_msg)

    print(text.strip())


def with_pipe() -> None:
    """방법 B — 파이프로 연결하기.  ★

    | 는 파이썬의 __or__ 연산자를 LangChain 이 재정의한 것이다.
    유닉스 파이프(cat file | grep x | wc -l)와 같은 발상.

    이 구조에 이름이 있다 — LCEL (LangChain Expression Language).
    5주차에서 본격적으로 다룬다.
    """
    print("── 방법 B: 파이프로 한 줄 ────────────────")

    chain = prompt | llm | parser  # ← 세 줄이 한 줄로

    text = chain.invoke({"level": "초보자", "topic": "파이썬"})
    print(text.strip())

    # 체인 자체도 .invoke() 를 가진다 → 다른 체인의 부품이 될 수 있다
    print()
    print("체인의 타입:", type(chain))  # RunnableSequence


def batch_demo() -> None:
    """batch() — 여러 입력을 한 번에 실행.

    5주차 Self-Consistency(같은 질문을 여러 번 돌려 다수결)의 기반이 된다.
    """
    print("── batch(): 여러 입력을 한 번에 ──────────")

    chain = prompt | llm | parser
    results = chain.batch(INPUTS)

    for r in results:
        print(r.strip()[:60], "...")
        print("-" * 40)


def stream_demo() -> None:
    """stream() — 토큰 단위로 흘려보내기.

    답이 다 나올 때까지 기다리지 않고 글자가 흘러나온다.
    ChatGPT 의 그 느낌. 4주차에서 자세히 다룬다.
    """
    print("── stream(): 토큰 단위 출력 ──────────────")

    chain = prompt | llm | parser

    for chunk in chain.stream({"level": "초보자", "topic": "파이썬"}):
        print(chunk, end="", flush=True)
    print()


def send_slack_message(
    text: str,
    channel: str | None = None,
    token: str | None = None,
    timeout: float = 10.0,
) -> bool:
    """Slack Bot Token 으로 chat.postMessage API 를 호출해 메시지를 보낸다.

    성공하면 True, 실패하면 False 를 반환한다.
    (LLM 호출 결과를 보내는 용도라서, 전송 실패로 프로그램 전체가
    죽지 않도록 예외를 밖으로 던지지 않고 False 로 알린다.)
    """
    # 함수 안에서 읽는 이유: load_dotenv() 호출 순서와 무관하게 항상 최신 값을 쓰기 위해
    token = token or os.getenv("SLACK_BOT_TOKEN")
    channel = channel or os.getenv("SLACK_CHANNEL_ID")

    # 설정 누락은 코드/환경 문제라서 조용히 넘기지 않고 바로 알린다
    if not token:
        raise ValueError("SLACK_BOT_TOKEN 이 없습니다. .env 파일을 확인하세요.")
    if not channel:
        raise ValueError("SLACK_CHANNEL_ID 가 없습니다. .env 파일을 확인하세요.")

    try:
        resp = requests.post(
            SLACK_API_URL,
            headers={"Authorization": f"Bearer {token}"},
            json={"channel": channel, "text": text},
            timeout=timeout,
        )
    except requests.RequestException as e:
        # 네트워크 단절, 타임아웃 등
        print(f"[Slack 전송 실패] 네트워크 오류: {e}")
        return False

    try:
        data = resp.json()
    except ValueError:
        # JSON 이 아닌 응답 (프록시 오류 페이지, 429 등)
        print(f"[Slack 전송 실패] HTTP {resp.status_code}: {resp.text[:200]}")
        return False

    # Slack Web API 는 실패해도 HTTP 200 으로 응답하고,
    # 성공 여부는 JSON 의 "ok" 필드에 들어 있다. 반드시 이 값을 확인해야 한다.
    # 실패 시 "error" 에 이유(not_in_channel, channel_not_found, invalid_auth 등)가 온다.
    if not data.get("ok"):
        print(f"[Slack 전송 실패] {data.get('error', 'unknown_error')}")
        return False

    return True


def slack_demo() -> None:
    """Ollama 와 OpenAI 의 답변을 모두 받아 Slack 으로 한 번에 전송."""
    print("── Slack 전송 (Ollama + OpenAI) ──────────")

    models = {
        f"Ollama ({MODEL})": llm_ollama,
        f"OpenAI ({OPENAI_MODEL})": llm_openai,
    }

    sections = []
    for name, model in models.items():
        chain = prompt | model | parser

        # return_exceptions=True: 질문 하나가 실패해도 나머지 결과는 살린다.
        # 실패한 자리에는 결과 대신 Exception 객체가 들어온다.
        results = chain.batch(INPUTS, return_exceptions=True)

        lines = [f"*[{name}]*"]
        for inp, r in zip(INPUTS, results):
            title = f"{inp['topic']} ({inp['level']})"
            if isinstance(r, Exception):
                body = f"(호출 실패: {type(r).__name__}: {r})"
            else:
                # Slack mrkdwn 은 굵게가 *text* 라서 마크다운의 ** 를 * 로 바꿔 준다
                body = r.strip().replace("**", "*")

            print(f"[{name}] {title}\n{body}\n")
            lines.append(f"*Q. {title}*\n{body}")

        sections.append("\n\n".join(lines))

    message = "\n\n――――――――――\n\n".join(sections)
    ok = send_slack_message(message)
    print("전송 성공" if ok else "전송 실패")


def main() -> None:
    step_by_step()
    print("\n" + "=" * 50 + "\n")

    with_pipe()
    print("\n" + "=" * 50 + "\n")

    batch_demo()
    print("\n" + "=" * 50 + "\n")

    stream_demo()
    print("\n" + "=" * 50 + "\n")

    slack_demo()  # 실행할 때마다 실제 Slack 메시지가 전송된다

    print()
    print("=" * 50)
    print("""
정리

  실행 방식 3종
      invoke()   하나 실행            기본
      batch()    여러 개 병렬 실행     5주차 Self-Consistency
      stream()   토큰 단위 스트리밍    4주차

  10주차 RAG 에서는 앞에 부품이 하나 더 붙는다:
      retriever | prompt | llm | parser
""")
    print("=" * 50)


if __name__ == "__main__":
    main()