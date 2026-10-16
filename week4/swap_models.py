"""[2교시 / 실습 1-②] ★★ 같은 체인 · 과제 3종 · 모델 2종 — 정답 확인 · 속도 · 비용

    chain = prompt | llm        ← llm 자리만 모델마다 다르다
    (parser 는 응답 정보를 보려고 뒤에서 따로 적용합니다)

실습 1-① 에서 여러분 first_chain.py 의 모델 줄을 직접 바꿔 봤습니다.
이 파일은 그 '한 줄 교체'를 과제 3종 × 모델 2종으로 넓혀 숫자로 비교합니다.

관찰 포인트
    1) '4B로 충분한가'의 답은 과제가 정한다 — 설명 · 형식 · 추론에서 결과가 다르다   ★
    2) usage_metadata(LangChain 이 통일한 토큰 수) 와
       response_metadata(공급자 원본) 는 모양이 다르다
    3) 로컬 첫 호출의 로딩 시간은 load_duration 으로 빼고 본다 — 두 번 돌리지 않는다
    4) 비용은 1회가 아니라 '하루 N명 × M회 × 30일' 로 본다. 출력 비중을 확인한다   ★
    5) '첫 토큰까지'는 invoke 로 잴 수 없다 → 3교시 streaming.py

⚠️ ChatAnthropic 은 쓰지 않습니다.
   Anthropic API 키가 필요하며, Claude Code 구독 계정으로는 호출할 수 없습니다.

화면 표기 — 모델이 만든 문장과 코드가 찍는 설명을 섞어 읽지 않도록 구분합니다
    [모델 응답] · | 로 시작하는 줄   모델이 실제로 만들어 낸 문장
    그 밖의 줄                       코드가 찍는 설명 · 측정값

실행:
    python swap_models.py                      # 측정 (모델 6번 호출)
    python swap_models.py cost 60 150          # 계산만 — 모델을 부르지 않는다
    python swap_models.py cost 60 150 300 5    #   입력토큰 출력토큰 [하루 사용자] [1인당 호출]
"""

import os
import re
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

load_dotenv(override=True)  # .env 에서 OPENAI_API_KEY 를 읽는다  ★

# ── ① 고칠 수 있는 값은 모두 여기에 ─────────────────────────
LOCAL_MODEL = "gemma3:1b"
LOCAL_SMALL = "gemma3:4b"  # 상용 키를 못 쓸 때의 대체 비교용

# 🔶 상용 모델명은 자주 바뀝니다. 수업 전날 공식 문서에서 확인해 확정할 것 ★
OPENAI_MODEL = "gpt-4o-mini"

# 최대 출력 토큰 — 뜻은 같은데 이름이 다릅니다 (Ollama: num_predict / OpenAI: max_tokens · §2-2)
MAX_OUT = 400

# 🔶 단가 — 수업일 공식 가격표의 '100만 토큰당 달러' 를 그대로 옮겨 적는다 (아래는 연습용 가정값)
PRICE_IN_PER_1M = 0.15
PRICE_OUT_PER_1M = 0.60
KRW_PER_USD = 1400  # 🔶 수업일 환율

# 한 달 비용 시나리오 — 내 미니 프로젝트를 상상해서 고쳐 본다
USERS_PER_DAY = 100
CALLS_PER_USER = 10
DAYS_PER_MONTH = 30

# ── ② 프롬프트와 파서는 한 번만 만든다. 끝까지 바뀌지 않는다 ──
prompt = ChatPromptTemplate.from_messages(
    [
        ("system", "당신은 프로그래밍 강사입니다. {level} 눈높이로 설명하세요."),
        ("human", "{question}"),
    ]
)
parser = StrOutputParser()

# ── ③ 과제 3종 — 쉬운 것부터 ───────────────────────────────
TASKS = [
    {
        "id": "①", "name": "설명", "check": "눈으로",
        # 3주차 first_chain.py 와 같은 질문 — 3교시 streaming.py 의 숫자와 이어진다
        "question": "파이썬의 장점 3가지를 각각 한 문장으로 알려줘.",
    },
    {
        "id": "②", "name": "형식", "check": "3줄",
        "question": "파이썬 자료형 3가지를 '1. 이름 - 한 줄 설명' 형식으로 딱 3줄만 쓰세요. "
                    "인사말, 빈 줄, 다른 문장은 쓰지 마세요.",
    },
    {
        "id": "③", "name": "추론", "check": "숫자", "answer": 11,  # 🔶 OpenAI 쪽은 수업 전 공용 키로 1회 확인
        "question": "5명이 서로 한 번씩 악수했다. 그 뒤 그중 2명이 서로 한 번 더 악수했다. "
                    "악수는 모두 몇 번인가? "
                    "풀이를 쓰고 마지막 줄에 숫자만 써라.",
    },
]


def says(text: str) -> None:
    """모델이 실제로 만들어 낸 문장 — 설명·측정값과 구분해서 찍는다 (2교시 bind_params.py 와 같은 표기)"""
    lines = text.strip().splitlines()
    if len(lines) <= 1:
        print(f"  [모델 응답] {lines[0] if lines else '(빈 응답)'}")
        return
    print("  [모델 응답] ↓")
    for line in lines:
        print(f"  |  {line}")


def check_answer(task: dict, text: str) -> str:
    """정답 확인 — 눈으로 해도 되는 일을 대신 세어 줄 뿐, 채점기가 아닙니다."""
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]

    if task["check"] == "3줄":
        ok = len(lines) == 3 and all(line.startswith(f"{i}.") for i, line in enumerate(lines, 1))
        return f"{'통과' if ok else '실패'} (줄 {len(lines)}개)"

    if task["check"] == "숫자":
        nums = re.findall(r"\d+", lines[-1].replace(",", "")) if lines else []  # 마지막 줄의 숫자
        got = int(nums[-1]) if nums else None
        return f"{'통과' if got == task['answer'] else '실패'} (마지막 줄 {got} / 정답 {task['answer']})"

    return "눈으로 (품질 1~5)"


def build_models() -> tuple:
    """바뀌는 것은 이 목록뿐입니다. (모델 목록, 상용 키가 있는가) 를 돌려준다."""
    if os.getenv("OPENAI_API_KEY"):
        return {
            f"로컬 {LOCAL_MODEL}": ChatOllama(model=LOCAL_MODEL, temperature=0.2, num_predict=MAX_OUT),
            f"OpenAI {OPENAI_MODEL}": ChatOpenAI(model=OPENAI_MODEL, temperature=0.2, max_tokens=MAX_OUT),
        }, True

    # ── 대체안: 상용 키가 없으면 로컬 2종으로 비교한다 ──
    #    코드 구조는 완전히 같습니다. 비용은 '(가정) 상용 단가였다면' 으로만 계산하고,
    #    비교표의 비용 칸은 'ollama ps 의 SIZE(메모리 점유)' 로 바꿔 채웁니다.  ★
    print("[주의] OPENAI_API_KEY 가 없습니다 → 로컬 2종 비교로 진행합니다.")
    print("   (.env 에 키를 넣으면 자동으로 로컬 ↔ OpenAI 비교가 됩니다)")
    print()
    return {
        f"소형 {LOCAL_SMALL}": ChatOllama(model=LOCAL_SMALL, temperature=0.2, num_predict=MAX_OUT),
        f"중형 {LOCAL_MODEL}": ChatOllama(model=LOCAL_MODEL, temperature=0.2, num_predict=MAX_OUT),
    }, False


def read_speed(msg, elapsed: float) -> dict:
    """속도 분해 — 공급자마다 원본 정보(response_metadata)의 모양이 다릅니다."""
    meta = msg.response_metadata
    output_tokens = (msg.usage_metadata or {}).get("output_tokens")

    if "eval_duration" in meta:
        # Ollama: 구간별 시간을 나노초로 알려 준다 (3주차 2교시에서 읽어 본 그 값)
        load = meta.get("load_duration", 0) / 1e9
        gen = meta["eval_duration"] / 1e9
        return {
            "load": load,
            "net": elapsed - load,  # 로딩을 뺀 시간 — 두 번 실행하지 않아도 된다
            "tps": meta.get("eval_count", 0) / gen if gen else None,  # 생성 구간만의 토큰/초
            "approx": False,
            "end": meta.get("done_reason"),
        }

    # OpenAI: 구간 정보가 없다 → 전체 시간으로 나눈 근사값 (네트워크 · 대기 포함이라 낮게 나온다)
    return {
        "load": None,
        "net": elapsed,
        "tps": output_tokens / elapsed if output_tokens and elapsed else None,
        "approx": True,
        "end": meta.get("finish_reason"),
    }


def cost_usd(input_tokens: int, output_tokens: int) -> tuple:
    """(입력 비용, 출력 비용) — 입력과 출력의 단가가 다릅니다."""
    return (
        input_tokens * PRICE_IN_PER_1M / 1_000_000,
        output_tokens * PRICE_OUT_PER_1M / 1_000_000,
    )


def print_month(input_tokens: int, output_tokens: int,
                users: int = USERS_PER_DAY, calls: int = CALLS_PER_USER) -> None:
    """1회 → 한 달. 곱하기로 봅니다."""
    c_in, c_out = cost_usd(input_tokens, output_tokens)
    once = c_in + c_out
    month_calls = users * calls * DAYS_PER_MONTH
    month = once * month_calls
    share = c_out / once * 100 if once else 0

    print(f"  단가          : 입력 ${PRICE_IN_PER_1M} · 출력 ${PRICE_OUT_PER_1M} (100만 토큰당)")
    print(f"  1회 호출      : 입력 {input_tokens} · 출력 {output_tokens} 토큰 → ${once:.6f} (약 {once * KRW_PER_USD:.2f}원)")
    print(f"  한 달 호출 수 : 하루 {users}명 × {calls}회 × {DAYS_PER_MONTH}일 = {month_calls:,}회")
    print(f"  한 달 비용    : ${month:,.2f} (약 {month * KRW_PER_USD:,.0f}원)")
    print(f"  출력 비중     : {share:.0f}%  ← 비용의 대부분이 출력 토큰에서 나오는가?")


def run_one(name: str, llm, task: dict, show_keys: bool) -> dict:
    """한 모델로 한 과제를 풀고 측정값을 돌려준다."""
    # 💡 파서를 빼면 AIMessage 가 그대로 온다 → 토큰 수와 원본 정보를 볼 수 있다
    #    (호출을 두 번 하지 않으려고 parser 는 뒤에서 따로 적용합니다.
    #     parser.invoke(msg) 가 곧 체인 끝의 parser 가 하던 일입니다.)
    chain = prompt | llm

    t0 = time.perf_counter()
    msg = chain.invoke({"level": "초보자", "question": task["question"]})
    elapsed = time.perf_counter() - t0

    text = parser.invoke(msg)
    usage = msg.usage_metadata or {}  # 🔶 공급자 · 버전에 따라 비어 있을 수 있음
    speed = read_speed(msg, elapsed)
    result = check_answer(task, text)

    print("=" * 64)
    print(f"[과제 {task['id']} {task['name']}] {name}")
    print("=" * 64)
    says(text)
    print()
    print(f"  정답 확인      : {result}")
    print(f"  usage_metadata : {usage or '(측정 불가)'}")
    if show_keys:
        print(f"  response_metadata 키 : {sorted(msg.response_metadata)}")
    if speed["end"] == "length":
        print(f"  [잘림] 최대 출력 {MAX_OUT} 토큰에 걸렸습니다 — 그대로 기록하세요")
    print()

    return {
        "task": task,
        "name": name,
        "result": result,
        "elapsed": elapsed,
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        **speed,
    }


def fmt(value, spec: str = ".1f") -> str:
    return "-" if value is None else format(value, spec)


def print_summary(rows: list, names: list, has_key: bool) -> None:
    """비교표(실습 2)에 옮겨 적을 수 있게 정리한다."""
    print("=" * 64)
    print("측정 요약 ① — 과제 × 모델")
    print("=" * 64)
    for r in rows:
        tps = ("≈" if r["approx"] else "") + fmt(r["tps"])
        print(f"  과제 {r['task']['id']} | {r['name']} | {r['result']}")
        print(f"      총 {r['elapsed']:.1f}초 · 로딩 {fmt(r['load'])}초 · 로딩 뺀 {r['net']:.1f}초"
              f" · {tps} 토큰/초 · 입력 {r['input_tokens']} · 출력 {r['output_tokens']}")

    print()
    print("=" * 64)
    print("측정 요약 ② — 비교표에 옮길 값")
    print("=" * 64)
    for name in names:
        mine = [r for r in rows if r["name"] == name]
        checked = [r for r in mine if r["task"]["check"] != "눈으로"]
        passed = sum(r["result"].startswith("통과") for r in checked)
        first = mine[0]  # 과제 ①
        speeds = [r["tps"] for r in mine if r["tps"]]
        avg_tps = sum(speeds) / len(speeds) if speeds else None
        is_local = first["load"] is not None

        print(f"[{name}]")
        print(f"  품질 · 정답 확인 통과      : {passed}/{len(checked)}  (과제 ① 품질 1~5 는 눈으로)")
        print(f"  속도 · 총 소요 (과제 ①)    : {first['net']:.1f}초  ← 로딩을 뺀 값")
        print(f"  속도 · 로딩 (과제 ①)       : {fmt(first['load']) + '초' if is_local else '해당 없음'}")
        print(f"  속도 · 생성 속도 (평균)    : {'≈' if first['approx'] else ''}{fmt(avg_tps)} 토큰/초")
        print(f"  비용 · 입력/출력 (과제 ①)  : {first['input_tokens']} / {first['output_tokens']}")
        if is_local and has_key:
            print("  비용 · 1회 / 한 달         : 0원 (호출당 — 전기 · 장비 비용은 별도)")
        elif first["input_tokens"] is not None and first["output_tokens"] is not None:
            label = "(가정) 상용 단가였다면" if not has_key else "과제 ① 기준"
            print(f"  비용 · {label}")
            print_month(first["input_tokens"], first["output_tokens"])
        else:
            print("  비용                       : 측정 불가 (usage_metadata 없음)")
        print()

    print("[참고] '첫 토큰까지'는 invoke 로는 잴 수 없습니다 → 3교시 streaming.py 에서 잽니다.")
    print("[속도] 로컬은 load_duration 을 뺀 값입니다. 두 번 실행하지 않아도 됩니다.")
    print("       OpenAI 의 토큰/초(≈)는 전체 시간으로 나눈 값이라 네트워크 시간이 섞여 낮게 나옵니다.")
    print("[비용] PRICE_* 가 수업일 단가인지 확인하세요. 내 시나리오로 다시 계산하려면:")
    print("       python swap_models.py cost 입력토큰 출력토큰 하루사용자 1인당호출")
    if not has_key:
        print("[대체] 키가 없어 로컬 2종을 비교했습니다. 비교표의 비용 칸은 'ollama ps' SIZE 로 채우세요.")


def main() -> None:
    # 계산만 하는 모드 — 모델을 부르지 않는다 (1교시 vram_calc.py 와 같은 방식)
    if len(sys.argv) >= 4 and sys.argv[1] == "cost":
        numbers = [int(a) for a in sys.argv[2:6]]
        print("=" * 64)
        print("비용 계산 — 모델을 부르지 않습니다")
        print("=" * 64)
        print_month(*numbers)
        return

    print("[표시 약속] [모델 응답] 로 시작하는 줄과 그 아래 | 로 시작하는 줄만 모델이 만든 문장입니다.")
    print("            나머지는 코드가 찍는 설명·측정값입니다.")
    print()
    models, has_key = build_models()
    rows = []
    for task in TASKS:  # 과제 → 모델 순서. 로컬 첫 호출(과제 ①)에 로딩이 들어간다
        for name, llm in models.items():
            rows.append(run_one(name, llm, task, show_keys=(task["id"] == "①")))
    print_summary(rows, list(models), has_key)


if __name__ == "__main__":
    main()
