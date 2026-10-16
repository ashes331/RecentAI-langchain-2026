"""[3교시 / 실습 3] 상용 모델이 실패하면 로컬 모델로 떨어지게 만든다

         상용 API 호출
              │
        실패(장애·한도 초과·키 문제)
              │
              ▼
      로컬 gemma3:4b 로 자동 전환      ← 서비스는 계속된다

관찰 포인트
    1) 주 모델이 실패했는데 에러 없이 결과가 나온다             ★
       "방금 OpenAI가 죽었는데 결과는 나왔습니다"
    2) ⚠️ 그래서 장애가 '조용히' 묻힙니다.
       어떤 모델이 실제로 응답했는지 기록해야 합니다 → 6주차 LangSmith

화면 표기 — 모델이 만든 문장과 코드가 찍는 설명을 섞어 읽지 않도록 구분합니다
    [모델 응답] · | 로 시작하는 줄   모델이 실제로 만들어 낸 문장
    그 밖의 줄                       코드가 찍는 설명 · 측정값

실행:
    python fallback.py
"""

import os
import sys

from dotenv import load_dotenv
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

# 한글 윈도우 콘솔(cp949)은 이모지를 출력하지 못해 오류가 납니다.
# 모델이 이모지를 뱉어도 죽지 않도록, 못 찍는 글자는 ? 로 바꿔 출력합니다.
sys.stdout.reconfigure(errors="replace")

load_dotenv(override=True)

LOCAL_MODEL = "gemma3:1b"

prompt = ChatPromptTemplate.from_messages(
    [
        ("system", "당신은 프로그래밍 강사입니다. {level} 눈높이로 설명하세요."),
        ("human", "{topic}의 장점 3가지를 각각 한 문장으로 알려줘."),
    ]
)
parser = StrOutputParser()
INPUTS = {"level": "초보자", "topic": "파이썬"}

def says(text: str) -> None:
    """모델이 실제로 만들어 낸 문장 — 설명·측정값과 구분해서 찍는다 (2교시 bind_params.py 와 같은 표기)"""
    lines = text.strip().splitlines()
    if len(lines) <= 1:
        print(f"  [모델 응답] {lines[0] if lines else '(빈 응답)'}")
        return
    print("  [모델 응답] ↓")
    for line in lines:
        print(f"  |  {line}")


def build_primary():
    """주 모델 — 일부러 실패하게 만든다 ★

    실패를 만드는 방법 세 가지
      ① 없는 모델명   model="gpt-존재하지-않는-모델"  ← 권장
      ② 잘못된 키     api_key="sk-틀린키"             ← .env 를 망가뜨릴 위험
      ③ 극단적 타임아웃 timeout=0.001                 ← 재현이 들쭉날쭉
    """
    if os.getenv("OPENAI_API_KEY"):
        return "OpenAI(없는 모델명)", ChatOpenAI(
            model="gpt-존재하지-않는-모델",  # 실패 유발 ①
            timeout=10,
            max_retries=0,  # 재시도 없이 바로 실패시켜 수업 시간을 아낀다
        )

    # 키가 없어도 실습은 그대로 됩니다. 주 모델을 '없는 로컬 모델'로 바꾸면
    # 로컬 → 로컬 폴백이 되고, 관찰할 것은 완전히 같습니다.
    print("[주의] OPENAI_API_KEY 가 없습니다 → 주 모델을 '없는 로컬 모델'로 대체합니다.")
    print()
    return "로컬(없는 모델명)", ChatOllama(model="없는-모델-이름")


def main() -> None:
    print("[표시 약속] [모델 응답] 로 시작하는 줄과 그 아래 | 로 시작하는 줄만 모델이 만든 문장입니다.")
    print("            나머지는 코드가 찍는 설명·측정값입니다.")
    print()
    primary_name, primary = build_primary()

    # ── 대체 모델: 로컬 ──
    backup = ChatOllama(model=LOCAL_MODEL, temperature=0.2)

    # ── 폴백 연결 ★ — 이 한 줄이 전부입니다 ──
    llm = primary.with_fallbacks([backup])

    print("=" * 60)
    print(f"주 모델({primary_name})을 부릅니다 …")
    print("=" * 60)

    # 체인의 형태는 지금까지와 똑같습니다
    #     chain = prompt | llm | parser
    #     print(chain.invoke(INPUTS))
    # 다만 여기서는 '누가 대답했는지'까지 보려고 파서를 빼고 호출합니다.
    # (파서를 빼면 AIMessage 가 오고, 거기에 실제 응답 모델이 적혀 있습니다.
    #  parser.invoke(msg) 가 곧 chain 끝의 parser 가 하던 일입니다.)
    msg = (prompt | llm).invoke(INPUTS)
    says(parser.invoke(msg))

    # ── ⚠️ 폴백의 대가 — 누가 대답했는지 확인해 봅시다 ──────
    meta = msg.response_metadata or {}
    actual = meta.get("model_name") or meta.get("model") or "(알 수 없음)"

    print()
    print("=" * 60)
    print(f"실제로 응답한 모델: {actual}")
    print("=" * 60)
    print(
        """
  폴백이 해결하는 것          |  해결하지 못하는 것
  ---------------------------|---------------------------------------------
  서비스가 멈추지 않는다      |  응답 품질이 떨어진다 (사용자는 모른 채 받는다)
  장애 대응 코드가 짧다       |  실패가 조용히 묻힌다 - 로그가 없으면 눈치 못 챔
  (없음)                     |  로컬 모델이 8GB에 안 올라가면 폴백도 실패 ★

  [주의] 폴백이 걸려 있으면 장애가 안 보입니다.
     그래서 '어떤 모델이 실제로 응답했는지' 를 위처럼 기록해야 합니다.
     이 기록을 자동으로 남겨주는 도구가 6주차 LangSmith 입니다.
    """
    )


if __name__ == "__main__":
    main()
