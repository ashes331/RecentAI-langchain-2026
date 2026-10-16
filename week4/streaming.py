"""[3교시 / 실습 4] ★ 첫 토큰까지의 시간(TTFT)과 총 소요 시간을 함께 잰다

    [invoke]  질문 ──────────── (10초 침묵) ────────────▶ 답 전체가 한 번에
    [stream]  질문 ─ 0.8초 ─▶ 답 ─ 이 ─ 조 ─ 금 ─ 씩 ─ 나 ─ 온 ─ 다 ▶ (총 10초)

    총 소요 시간은 같습니다. 달라지는 것은 '첫 글자가 언제 나오는가' 입니다.

관찰 포인트
    1) 바뀐 것은 invoke → stream 과 반복문뿐. 체인은 그대로다        ★
    2) 총 시간 ≈ 변화 없음  → 스트리밍은 빨라지게 하지 않는다
       (답 길이가 매번 달라 몇 초 차이는 납니다 — 화면의 '답 N자' 를 같이 보세요)
    3) 첫 토큰까지 ≪ 총 시간 → 개선되는 것은 '체감 속도'

🔶 실습 직전 확인: 로컬 모델이 메모리에서 내려가 있으면 첫 토큰까지가 크게 늘어납니다
   (모델 로딩 시간이 포함되므로).  ollama ps 로 올라와 있는지 확인하세요. (1교시)

측정 전 예열 — 모델마다 시간을 재지 않는 호출을 한 번 먼저 합니다
    첫 호출에는 모델 로딩(로컬) · 서버 연결 준비(상용)가 섞입니다.
    예열 없이 재면 먼저 재는 invoke 만 이 시간을 떠안아 stream 이 더 빨라 보입니다.

화면 표기 — 모델이 만든 문장과 코드가 찍는 설명을 섞어 읽지 않도록 구분합니다
    [모델 응답] ~ [모델 응답 끝]     모델이 실제로 만들어 낸 문장
    그 밖의 줄                       코드가 찍는 설명 · 측정값

실행:
    python streaming.py
"""

import os
import sys
import time

from dotenv import load_dotenv
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

# 한글 윈도우 콘솔(cp949)은 이모지를 출력하지 못해 오류가 납니다.
# 모델이 이모지를 뱉어도 죽지 않도록, 못 찍는 글자는 ? 로 바꿔 출력합니다.
sys.stdout.reconfigure(errors="replace")

load_dotenv(override=True)

LOCAL_MODEL = "gemma3:4b"
# 🔶 상용 모델명은 수업 전날 공식 문서에서 확인해 확정할 것
OPENAI_MODEL = "gpt-4o-mini"

prompt = ChatPromptTemplate.from_messages(
    [
        ("system", "당신은 프로그래밍 강사입니다. {level} 눈높이로 설명하세요."),
        ("human", "{topic}의 장점 3가지를 각각 한 문장으로 알려줘."),
    ]
)
INPUTS = {"level": "초보자", "topic": "파이썬"}


def measure_invoke(chain) -> tuple:
    """① invoke — 다 나올 때까지 기다린다."""
    t0 = time.perf_counter()
    text = chain.invoke(INPUTS)
    total = time.perf_counter() - t0
    print(f"[invoke] 총 {total:.2f}초 · 답 {len(text)}자 (답은 다 받았지만 화면에 찍지 않았습니다)")
    return total, len(text)


def measure_stream(chain) -> tuple:
    """② stream — 오는 대로 출력한다. 첫 조각이 온 시각을 기록한다."""
    t0 = time.perf_counter()
    first = None
    chars = 0  # 받은 답의 글자 수 — invoke 답과 길이를 견줘 보려고

    # 조각이 오는 대로 그대로 찍히므로, 어디까지가 모델이 쓴 글인지 앞뒤로 표시해 둔다
    print("  [모델 응답] ↓ 오는 대로 찍습니다")
    for chunk in chain.stream(INPUTS):  # ★ invoke → stream, 이것뿐입니다
        if first is None and chunk:
            first = time.perf_counter() - t0  # 첫 글자가 도착한 시각
        chars += len(chunk)
        print(chunk, end="", flush=True)
    print()
    print("  [모델 응답 끝]")

    total = time.perf_counter() - t0
    ttft = f"{first:.2f}초" if first is not None else "측정 불가"
    print(f"[stream] 첫 토큰까지 {ttft} / 총 {total:.2f}초 · 답 {chars}자")
    return first, total, chars


def run(name: str, llm) -> dict:
    chain = prompt | llm | StrOutputParser()

    print()
    print("=" * 60)
    print(f"[{name}]")
    print("=" * 60)

    # 예열 — 시간을 재지 않고 한 번 불러 둔다 (모델 로딩 · 연결 준비를 측정에서 뺀다)
    print("[예열] 측정 전에 한 번 불러 둡니다 (시간은 재지 않습니다)")
    chain.invoke(INPUTS)

    invoke_total, invoke_chars = measure_invoke(chain)
    print()
    ttft, stream_total, stream_chars = measure_stream(chain)

    return {
        "name": name,
        "invoke_total": invoke_total,
        "invoke_chars": invoke_chars,
        "ttft": ttft,
        "stream_total": stream_total,
        "stream_chars": stream_chars,
    }


def main() -> None:
    print("[표시 약속] [모델 응답] 과 [모델 응답 끝] 사이의 줄만 모델이 만든 문장입니다.")
    print("            나머지는 코드가 찍는 설명·측정값입니다.")
    print()
    models = {f"로컬 {LOCAL_MODEL}": ChatOllama(model=LOCAL_MODEL, temperature=0.2)}
    if os.getenv("OPENAI_API_KEY"):
        models[f"OpenAI {OPENAI_MODEL}"] = ChatOpenAI(model=OPENAI_MODEL, temperature=0.2)
    else:
        print("[주의] OPENAI_API_KEY 가 없어 로컬 모델만 측정합니다.")

    rows = [run(name, llm) for name, llm in models.items()]

    # ── 요약 — 두 모델 나란히 ★ ─────────────────────────
    print()
    print("=" * 60)
    print("요약 — invoke 총 · stream 총 · 첫 토큰까지  ★")
    print("=" * 60)
    print(f"  {'모델':<24} {'invoke 총':>10} {'stream 총':>10} {'첫 토큰까지':>12} {'답 길이(invoke/stream)':>24}")
    for r in rows:
        ttft = f"{r['ttft']:.2f}초" if r["ttft"] is not None else "측정불가"
        chars = f"{r['invoke_chars']}자 / {r['stream_chars']}자"
        print(
            f"  {r['name']:<24} {r['invoke_total']:>9.2f}초 "
            f"{r['stream_total']:>9.2f}초 {ttft:>12} {chars:>24}"
        )

    print()
    print("  총 시간 ≒ 변화 없음      → 스트리밍은 빨라지게 하지 않는다")
    print("  첫 토큰까지 ≪ 총 시간    → 개선되는 것은 '체감 속도'")
    print("  (답 길이가 다르면 총 시간도 그만큼 다릅니다 — 답 길이 칸을 같이 보세요)")
    print()
    print("[정리] 스트리밍은 성능 최적화가 아니라 '사용자 경험' 개선입니다.")
    print("       총 시간이 같아도 사용자는 훨씬 빠르다고 느낍니다.")

    # ── 비동기 버전 (소개만) ────────────────────────────
    #   async for chunk in chain.astream(INPUTS):
    #       print(chunk, end="", flush=True)
    #
    #   웹 서버처럼 여러 요청을 동시에 받아야 할 때 씁니다.
    #   본 교과목에서는 직접 쓰지 않습니다. '이런 게 있다' 정도로 넘어갑니다.


if __name__ == "__main__":
    main()
